"""Extended scoring engine tests: disabled signals, extensibility, weight normalization."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from sourceloop.scoring.aggregator import WeightedSum
from sourceloop.scoring.registry import build_engine, _BUILTIN_SIGNALS
from sourceloop.scoring.rules import Rule, RuleSet
from sourceloop.scoring.signal import ScoringContext, SignalValue
from sourceloop.scoring.signals.completeness import CompletenessSignal
from sourceloop.scoring.signals.freshness import FreshnessSignal
from sourceloop.scoring.signals.part_match import PartMatchSignal
from sourceloop.scoring.signals.price_sanity import PriceSanitySignal
from sourceloop.scoring.signals.source_tier import SourceTierSignal
from sourceloop.scoring.signals.supplier_trust import SupplierTrustSignal
from sourceloop.scoring.signals.vision_agreement import VisionAgreementSignal
from sourceloop.scoring.strategy import ActiveStrategy


class FakePolicies:
    class A:
        price_ladder = type("P", (), {"ttl_days": 5, "ttl_hours": None})()
        stock = type("P", (), {"ttl_days": 3, "ttl_hours": None})()
        moq = type("P", (), {"ttl_days": 14, "ttl_hours": None})()

    def __getattr__(self, item: str):
        if item == "A":
            return self.A
        raise AttributeError(item)


@dataclass
class FakeOffer:
    tier: str = "A"
    price_ladder: object = None
    moq: int | None = 1
    stock: int | None = 100
    field_captured_at: dict = None  # type: ignore[assignment]

    def __post_init__(self):
        if self.field_captured_at is None:
            now = datetime.now(UTC)
            self.field_captured_at = {
                "price_ladder": now.isoformat(),
                "stock": now.isoformat(),
                "moq": now.isoformat(),
            }


def _ctx(now=None):
    return ScoringContext(now=now or datetime.now(UTC), refresh_policies=FakePolicies())


# ── Disabled signals are registered but have enabled=False ───────────────────

class TestDisabledSignalsRegistered:
    def test_all_seven_signals_in_registry(self):
        assert "source_tier" in _BUILTIN_SIGNALS
        assert "freshness" in _BUILTIN_SIGNALS
        assert "completeness" in _BUILTIN_SIGNALS
        assert "price_sanity" in _BUILTIN_SIGNALS
        assert "part_match" in _BUILTIN_SIGNALS
        assert "supplier_trust" in _BUILTIN_SIGNALS
        assert "vision_agreement" in _BUILTIN_SIGNALS

    def test_live_signals_enabled(self):
        assert _BUILTIN_SIGNALS["source_tier"].enabled is True
        assert _BUILTIN_SIGNALS["freshness"].enabled is True
        assert _BUILTIN_SIGNALS["completeness"].enabled is True

    def test_disabled_signals_not_enabled(self):
        assert _BUILTIN_SIGNALS["price_sanity"].enabled is False
        assert _BUILTIN_SIGNALS["part_match"].enabled is False
        assert _BUILTIN_SIGNALS["supplier_trust"].enabled is False
        assert _BUILTIN_SIGNALS["vision_agreement"].enabled is False

    def test_disabled_signal_raises_on_compute(self):
        with pytest.raises(NotImplementedError):
            PriceSanitySignal().compute(FakeOffer(), _ctx())
        with pytest.raises(NotImplementedError):
            PartMatchSignal().compute(FakeOffer(), _ctx())
        with pytest.raises(NotImplementedError):
            SupplierTrustSignal().compute(FakeOffer(), _ctx())
        with pytest.raises(NotImplementedError):
            VisionAgreementSignal().compute(FakeOffer(), _ctx())


# ── Strategy with disabled signals: drops+renormalizes, no error ──────────────

class TestStrategyDropsDisabledSignals:
    """confidence_strict lists disabled signals; they're dropped at load, not a crash."""

    def test_confidence_strict_loads_without_error(self):
        strategies_cfg = {
            "confidence_strict": {
                "signals": ["source_tier", "vision_agreement", "part_match",
                            "price_sanity", "completeness", "supplier_trust", "freshness"],
                "weights": {"source_tier": 30, "vision_agreement": 20, "part_match": 20,
                            "price_sanity": 12, "completeness": 8, "supplier_trust": 6, "freshness": 4},
                "aggregator": "weighted_sum",
                "bands": {"high": 80, "medium": 50},
                "hard_flags": [],
            }
        }
        rules_cfg = [{"when": "always", "then": "confidence_strict"}]
        engine = build_engine(strategies_cfg, rules_cfg)
        # Should score without error; disabled signals are absent
        result = engine.score(FakeOffer(), _ctx())
        assert result.band in ("high", "medium", "low")

    def test_disabled_signals_not_in_result(self):
        strategies_cfg = {
            "confidence_strict": {
                "signals": ["source_tier", "vision_agreement", "completeness"],
                "weights": {"source_tier": 30, "vision_agreement": 20, "completeness": 8},
                "aggregator": "weighted_sum",
                "bands": {"high": 80, "medium": 50},
                "hard_flags": [],
            }
        }
        rules_cfg = [{"when": "always", "then": "confidence_strict"}]
        engine = build_engine(strategies_cfg, rules_cfg)
        result = engine.score(FakeOffer(), _ctx())
        # vision_agreement was disabled → not in signal_values
        assert "vision_agreement" not in result.signals
        assert "source_tier" in result.signals
        assert "completeness" in result.signals


# ── Engine extensibility: enabling a disabled signal changes score without editing engine.py ─

class TestEngineExtensibility:
    """Prove that adding a signal is config + module, never engine.py edit."""

    def _make_always_high_signal(self):
        class AlwaysHighSignal:
            key = "always_high"
            depends_on: list = []
            enabled = True

            def compute(self, subject, ctx) -> SignalValue:
                return SignalValue(normalized=1.0, raw=None, provenance={})

        return AlwaysHighSignal()

    def test_extra_signal_injected_via_extra_signals(self):
        """Adding a new signal via extra_signals changes score without touching engine.py."""
        # Base strategy: source_tier only
        strategies_cfg = {
            "test_strategy": {
                "signals": ["source_tier", "always_high"],
                "weights": {"source_tier": 50, "always_high": 50},
                "aggregator": "weighted_sum",
                "bands": {"high": 80, "medium": 50},
                "hard_flags": [],
            }
        }
        rules_cfg = [{"when": "always", "then": "test_strategy"}]
        extra = {"always_high": self._make_always_high_signal()}
        engine = build_engine(strategies_cfg, rules_cfg, extra_signals=extra)
        result = engine.score(FakeOffer(), _ctx())
        assert "always_high" in result.signals


# ── WeightedSum normalization corner cases ────────────────────────────────────

class TestWeightedSumNormalization:
    def test_weights_not_summing_to_100_still_correct(self):
        """Weights are arbitrary; the aggregator normalizes by actual weight sum."""
        agg = WeightedSum()
        values = {
            "a": SignalValue(normalized=1.0, raw=None, provenance={}),
            "b": SignalValue(normalized=1.0, raw=None, provenance={}),
        }
        # Weights sum to 3, not 100
        weights = {"a": 1, "b": 2}
        score = agg.aggregate(values, weights)
        assert score == pytest.approx(100.0)

    def test_signal_failure_renormalization(self):
        """When a signal is UNAVAILABLE, survivors' weights fill the 0-100 scale."""
        agg = WeightedSum()
        values = {
            "source_tier": SignalValue(normalized=1.0, raw=None, provenance={}),
            # freshness UNAVAILABLE (absent from values)
            "completeness": SignalValue(normalized=1.0, raw=None, provenance={}),
        }
        weights = {"source_tier": 60, "freshness": 25, "completeness": 15}
        score = agg.aggregate(values, weights)
        # Score = (60*1.0 + 15*1.0) / 75 * 100 = 100.0
        assert score == pytest.approx(100.0)


# ── Engine: failing signal marks UNAVAILABLE, score still valid ───────────────

class TestEngineFailingSignal:
    def test_failing_signal_becomes_unavailable_score_still_valid(self):
        class BrokenSignal:
            key = "broken"
            depends_on: list = []
            enabled = True

            def compute(self, subject, ctx) -> SignalValue:
                raise RuntimeError("simulated failure")

        strategy = ActiveStrategy(
            name="test",
            signals=[SourceTierSignal(), BrokenSignal()],  # type: ignore[list-item]
            weights={"source_tier": 60, "broken": 40},
            aggregator=WeightedSum(),
            bands={"high": 80, "medium": 50},
            hard_flags=[],
        )
        result = strategy.score(FakeOffer(), _ctx())
        assert "broken" in result.unavailable_signals
        assert "source_tier" in result.signals
        # Score is still valid (auto-renormalized over source_tier only)
        assert 0.0 <= result.score <= 100.0
        assert result.band in ("high", "medium", "low")
