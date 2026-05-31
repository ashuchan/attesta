"""ActiveStrategy: loaded, validated, ready-to-score strategy."""
from __future__ import annotations

import structlog

from .aggregator import Aggregator
from .provenance import ScoreResult
from .signal import Scorable, Signal, ScoringContext, SignalValue

log = structlog.get_logger()


class ActiveStrategy:
    """
    A fully-loaded strategy. Receives enabled signals only at construction.
    Handles per-signal failures, renormalizes weights automatically, maps score to band.
    """

    def __init__(
        self,
        name: str,
        signals: list[Signal],
        weights: dict[str, float],
        aggregator: Aggregator,
        bands: dict[str, float],
        hard_flags: list[str],
    ) -> None:
        self.name = name
        self._signals: dict[str, Signal] = {s.key: s for s in signals}
        self._weights = weights
        self._aggregator = aggregator
        self._bands = bands          # {"high": 80.0, "medium": 50.0}
        self._hard_flags = hard_flags

    def score(self, subject: Scorable, ctx: ScoringContext) -> ScoreResult:
        signal_values: dict[str, SignalValue] = {}
        unavailable: list[str] = []

        for key, signal in self._signals.items():
            try:
                sv = signal.compute(subject, ctx)
                signal_values[key] = sv
            except Exception as exc:
                log.warning("signal_compute_failed", signal=key, error=str(exc))
                unavailable.append(key)

        # Check hard flags (mechanism for Step 3+; none fire in Step 2)
        hard_flags_fired: list[str] = []

        # Aggregate (WeightedSum auto-renormalizes over available signals)
        raw_score = self._aggregator.aggregate(signal_values, self._weights)

        # Map to band; hard flags force "low"
        if hard_flags_fired:
            band = "low"
        elif raw_score >= self._bands.get("high", 80.0):
            band = "high"
        elif raw_score >= self._bands.get("medium", 50.0):
            band = "medium"
        else:
            band = "low"

        return ScoreResult(
            score=raw_score,
            band=band,
            strategy=self.name,
            signals=signal_values,
            weights=self._weights,
            hard_flags_fired=hard_flags_fired,
            unavailable_signals=unavailable,
        )
