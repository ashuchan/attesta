"""Unit tests for the scoring engine, signals, and aggregators."""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from sourceloop.scoring.aggregator import Max, WeightedSum
from sourceloop.scoring.provenance import ScoreResult
from sourceloop.scoring.rules import Rule, RuleSet
from sourceloop.scoring.signal import ScoringContext, SignalValue
from sourceloop.scoring.signals.completeness import CompletenessSignal
from sourceloop.scoring.signals.freshness import FreshnessSignal
from sourceloop.scoring.signals.source_tier import SourceTierSignal
from sourceloop.scoring.strategy import ActiveStrategy


# ── Fixtures ────────────────────────────────────────────────────────────────


class FakePolicies:
    """Minimal refresh policy stub (A: price_ladder=5 days, stock=3 days, moq=14 days)."""
    class A:
        price_ladder = type("P", (), {"ttl_days": 5, "ttl_hours": None})()
        stock = type("P", (), {"ttl_days": 3, "ttl_hours": None})()
        moq = type("P", (), {"ttl_days": 14, "ttl_hours": None})()

    def __getattr__(self, item):
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

    def __post_init__(self) -> None:
        if self.field_captured_at is None:
            now = datetime.now(UTC)
            self.field_captured_at = {
                "price_ladder": now.isoformat(),
                "stock": now.isoformat(),
                "moq": now.isoformat(),
            }


def _ctx(now: datetime | None = None) -> ScoringContext:
    return ScoringContext(now=now or datetime.now(UTC), refresh_policies=FakePolicies())


# ── Signal tests ────────────────────────────────────────────────────────────

class TestSourceTierSignal:
    def test_tier_a_returns_1(self):
        sig = SourceTierSignal()
        sv = sig.compute(FakeOffer(tier="A"), _ctx())
        assert sv.normalized == 1.0

    def test_tier_b_returns_06(self):
        sig = SourceTierSignal()
        sv = sig.compute(FakeOffer(tier="B"), _ctx())
        assert sv.normalized == 0.6

    def test_unknown_tier_returns_0(self):
        sig = SourceTierSignal()
        sv = sig.compute(FakeOffer(tier="Z"), _ctx())
        assert sv.normalized == 0.0


class TestFreshnessSignal:
    def test_fresh_returns_1(self):
        sig = FreshnessSignal()
        now = datetime.now(UTC)
        offer = FakeOffer(field_captured_at={
            "price_ladder": now.isoformat(),
            "stock": now.isoformat(),
            "moq": now.isoformat(),
        })
        sv = sig.compute(offer, _ctx(now=now))
        assert sv.normalized == pytest.approx(1.0)

    def test_stale_price_ladder_decays(self):
        sig = FreshnessSignal()
        now = datetime.now(UTC)
        old = now - timedelta(days=6)  # past 5-day TTL
        offer = FakeOffer(field_captured_at={
            "price_ladder": old.isoformat(),
            "stock": now.isoformat(),
            "moq": now.isoformat(),
        })
        sv = sig.compute(offer, _ctx(now=now))
        assert sv.normalized == 0.0  # price_ladder TTL exceeded → min=0

    def test_half_stale_returns_half(self):
        sig = FreshnessSignal()
        now = datetime.now(UTC)
        half_life = now - timedelta(days=2, hours=12)  # exactly 2.5 days into 5-day TTL
        offer = FakeOffer(field_captured_at={
            "price_ladder": half_life.isoformat(),
            "stock": now.isoformat(),
            "moq": now.isoformat(),
        })
        sv = sig.compute(offer, _ctx(now=now))
        assert 0.4 < sv.normalized < 0.6  # approximately 0.5

    def test_missing_field_returns_0(self):
        sig = FreshnessSignal()
        now = datetime.now(UTC)
        offer = FakeOffer(field_captured_at={})  # no fields
        sv = sig.compute(offer, _ctx(now=now))
        assert sv.normalized == 0.0


class TestCompletenessSignal:
    def test_all_fields_present(self):
        sig = CompletenessSignal()
        offer = FakeOffer(price_ladder=object(), moq=1, stock=100)
        sv = sig.compute(offer, _ctx())
        assert sv.normalized == pytest.approx(1.0)

    def test_missing_stock(self):
        sig = CompletenessSignal()
        offer = FakeOffer(price_ladder=object(), moq=1, stock=None)
        sv = sig.compute(offer, _ctx())
        assert sv.normalized == pytest.approx(2 / 3)

    def test_all_missing(self):
        sig = CompletenessSignal()
        offer = FakeOffer(price_ladder=None, moq=None, stock=None)
        sv = sig.compute(offer, _ctx())
        assert sv.normalized == 0.0


# ── Aggregator tests ─────────────────────────────────────────────────────────

class TestWeightedSum:
    def test_all_ones_with_weights(self):
        agg = WeightedSum()
        values = {
            "source_tier": SignalValue(normalized=1.0, raw=None, provenance={}),
            "freshness": SignalValue(normalized=1.0, raw=None, provenance={}),
            "completeness": SignalValue(normalized=1.0, raw=None, provenance={}),
        }
        weights = {"source_tier": 60, "freshness": 25, "completeness": 15}
        score = agg.aggregate(values, weights)
        assert score == pytest.approx(100.0)

    def test_auto_renormalization_on_missing_signal(self):
        agg = WeightedSum()
        # Only source_tier present; freshness and completeness dropped (unavailable)
        values = {
            "source_tier": SignalValue(normalized=1.0, raw=None, provenance={}),
        }
        weights = {"source_tier": 60, "freshness": 25, "completeness": 15}
        score = agg.aggregate(values, weights)
        assert score == pytest.approx(100.0)  # 60/60 * 100

    def test_partial_scores(self):
        agg = WeightedSum()
        values = {
            "source_tier": SignalValue(normalized=1.0, raw=None, provenance={}),
            "freshness": SignalValue(normalized=0.5, raw=None, provenance={}),
            "completeness": SignalValue(normalized=1.0, raw=None, provenance={}),
        }
        weights = {"source_tier": 60, "freshness": 25, "completeness": 15}
        score = agg.aggregate(values, weights)
        expected = (60 * 1.0 + 25 * 0.5 + 15 * 1.0) / 100 * 100  # 87.5
        assert score == pytest.approx(expected)


class TestMax:
    def test_returns_max(self):
        agg = Max()
        values = {
            "a": SignalValue(normalized=0.3, raw=None, provenance={}),
            "b": SignalValue(normalized=0.9, raw=None, provenance={}),
        }
        assert agg.aggregate(values, {}) == pytest.approx(90.0)


# ── Strategy tests ───────────────────────────────────────────────────────────

class TestActiveStrategy:
    def _build_strategy(self):
        return ActiveStrategy(
            name="confidence_tier_a",
            signals=[SourceTierSignal(), FreshnessSignal(), CompletenessSignal()],  # type: ignore[list-item]
            weights={"source_tier": 60, "freshness": 25, "completeness": 15},
            aggregator=WeightedSum(),
            bands={"high": 80, "medium": 50},
            hard_flags=[],
        )

    def test_perfect_offer_is_high(self):
        strategy = self._build_strategy()
        now = datetime.now(UTC)
        offer = FakeOffer(
            tier="A",
            price_ladder=object(),
            moq=1,
            stock=100,
            field_captured_at={
                "price_ladder": now.isoformat(),
                "stock": now.isoformat(),
                "moq": now.isoformat(),
            },
        )
        result = strategy.score(offer, _ctx(now=now))
        assert result.band == "high"
        assert result.score >= 80

    def test_stale_offer_may_drop_band(self):
        strategy = self._build_strategy()
        now = datetime.now(UTC)
        old = now - timedelta(days=10)  # well past all TTLs
        offer = FakeOffer(
            tier="A",
            price_ladder=object(),
            moq=1,
            stock=100,
            field_captured_at={
                "price_ladder": old.isoformat(),
                "stock": old.isoformat(),
                "moq": old.isoformat(),
            },
        )
        result = strategy.score(offer, _ctx(now=now))
        # freshness=0.0 → score = (60*1.0 + 25*0.0 + 15*1.0)/100*100 = 75 → medium
        assert result.score == pytest.approx(75.0)
        assert result.band == "medium"


# ── Rule DSL tests ───────────────────────────────────────────────────────────

class TestRuleSet:
    def test_always_matches(self):
        rules = RuleSet([Rule(when="always", then="confidence_tier_a")])
        assert rules.select_strategy(FakeOffer(), _ctx()) == "confidence_tier_a"

    def test_tier_a_matches(self):
        rules = RuleSet([Rule(when="tier_a", then="confidence_tier_a")])
        assert rules.select_strategy(FakeOffer(tier="A"), _ctx()) == "confidence_tier_a"

    def test_tier_a_does_not_match_tier_b(self):
        rules = RuleSet([Rule(when="tier_a", then="confidence_tier_a")])
        with pytest.raises(ValueError):
            rules.select_strategy(FakeOffer(tier="B"), _ctx())

    def test_first_match_wins(self):
        rules = RuleSet([
            Rule(when="tier_a", then="strict"),
            Rule(when="always", then="default"),
        ])
        assert rules.select_strategy(FakeOffer(tier="A"), _ctx()) == "strict"
        assert rules.select_strategy(FakeOffer(tier="B"), _ctx()) == "default"
