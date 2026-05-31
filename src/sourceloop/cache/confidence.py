from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol, runtime_checkable

from sourceloop.domain.offer import OfferObservation


@runtime_checkable
class ConfidenceProvider(Protocol):
    def score(self, observation: OfferObservation) -> float | None:
        ...


class NullConfidence:
    """Step 1 default — always returns None. Step 2 wires in the real scoring engine."""
    def score(self, observation: OfferObservation) -> None:
        return None


class EngineConfidenceProvider:
    """
    Step 2 confidence provider backed by the ScoringEngine.

    - score(obs) → float | None  (ConfidenceProvider Protocol)
    - score_result(obs) → ScoreResult | None  (extra method, for score_log provenance)
    - score_effective(offer) → float | None  (read-time freshness-decayed, never persisted)
    """

    def __init__(self, engine: object) -> None:  # ScoringEngine — avoid circular import
        self._engine = engine

    def _make_ctx(self) -> object:
        from sourceloop.config.loader import get_refresh_policies
        from sourceloop.scoring.signal import ScoringContext
        return ScoringContext(now=datetime.now(UTC), refresh_policies=get_refresh_policies())

    def score(self, observation: OfferObservation) -> float | None:
        result = self.score_result(observation)
        if result is None:
            return None
        return float(result.score)  # type: ignore[attr-defined]

    def score_result(self, observation: OfferObservation) -> object | None:
        """Full ScoreResult with provenance — used for score_log writes."""
        try:
            ctx = self._make_ctx()
            return self._engine.score(observation, ctx)  # type: ignore[attr-defined]
        except Exception:
            return None

    def score_effective(self, offer: object) -> float | None:
        """
        Re-score at read-time with now's timestamp so freshness is current.
        Returns confidence_effective (never persisted).
        """
        try:
            ctx = self._make_ctx()
            result = self._engine.score(offer, ctx)  # type: ignore[attr-defined]
            return float(result.score)  # type: ignore[attr-defined]
        except Exception:
            return None
