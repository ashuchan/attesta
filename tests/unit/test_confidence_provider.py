"""Unit tests for EngineConfidenceProvider."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from sourceloop.cache.confidence import EngineConfidenceProvider, NullConfidence
from sourceloop.domain.offer import OfferObservation, PriceLadder
from sourceloop.scoring.aggregator import WeightedSum
from sourceloop.scoring.engine import ScoringEngine
from sourceloop.scoring.rules import Rule, RuleSet
from sourceloop.scoring.signals.completeness import CompletenessSignal
from sourceloop.scoring.signals.freshness import FreshnessSignal
from sourceloop.scoring.signals.source_tier import SourceTierSignal
from sourceloop.scoring.strategy import ActiveStrategy


def _make_obs() -> OfferObservation:
    now = datetime.now(UTC)
    return OfferObservation(
        listing_id=uuid.uuid4(),
        source="api",
        tier="A",
        captured_at=now,
        normalized_part_key="mpn:TEST",
        supplier_id="nexar:42",
        category="MCU",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1,
        lead_time=None,
        stock=500,
        specs={},
        supplier_snapshot={},
        screenshot_ref=None,
        confidence=None,
        field_captured_at={
            "price_ladder": now.isoformat(),
            "stock": now.isoformat(),
            "moq": now.isoformat(),
        },
    )


def _make_engine() -> ScoringEngine:
    strategy = ActiveStrategy(
        name="confidence_tier_a",
        signals=[SourceTierSignal(), FreshnessSignal(), CompletenessSignal()],  # type: ignore[list-item]
        weights={"source_tier": 60, "freshness": 25, "completeness": 15},
        aggregator=WeightedSum(),
        bands={"high": 80, "medium": 50},
        hard_flags=[],
    )
    return ScoringEngine(
        strategies={"confidence_tier_a": strategy},
        rule_set=RuleSet([Rule(when="always", then="confidence_tier_a")]),
    )


class TestNullConfidence:
    def test_always_none(self):
        obs = _make_obs()
        assert NullConfidence().score(obs) is None


class TestEngineConfidenceProvider:
    def test_score_returns_float(self):
        provider = EngineConfidenceProvider(_make_engine())
        obs = _make_obs()
        score = provider.score(obs)
        assert score is not None
        assert 0.0 <= score <= 100.0

    def test_fresh_offer_scores_high(self):
        provider = EngineConfidenceProvider(_make_engine())
        obs = _make_obs()
        score = provider.score(obs)
        assert score is not None
        assert score >= 80.0  # fresh + complete + tier-A

    def test_score_result_has_provenance(self):
        provider = EngineConfidenceProvider(_make_engine())
        obs = _make_obs()
        result = provider.score_result(obs)
        assert result is not None
        assert hasattr(result, "score")
        assert hasattr(result, "band")
        assert hasattr(result, "strategy")
        assert result.band in ("high", "medium", "low")  # type: ignore[attr-defined]

    def test_score_effective_returns_float(self):
        provider = EngineConfidenceProvider(_make_engine())
        obs = _make_obs()
        eff = provider.score_effective(obs)
        assert eff is not None
        assert 0.0 <= eff <= 100.0
