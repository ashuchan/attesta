"""ScoreResult — immutable scoring output with full provenance."""
from __future__ import annotations

from dataclasses import dataclass, field

from .signal import SignalValue


@dataclass(frozen=True)
class ScoreResult:
    score: float                          # 0 – 100
    band: str                             # "high" | "medium" | "low"
    strategy: str
    signals: dict[str, SignalValue]
    weights: dict[str, float]             # configured weights (not renormalized)
    hard_flags_fired: list[str] = field(default_factory=list)
    unavailable_signals: list[str] = field(default_factory=list)

    def to_provenance_json(self) -> dict:
        return {
            "score": self.score,
            "band": self.band,
            "strategy": self.strategy,
            "signals": {
                k: {"normalized": v.normalized, "raw": v.raw, "provenance": v.provenance}
                for k, v in self.signals.items()
            },
            "weights": self.weights,
            "hard_flags_fired": self.hard_flags_fired,
            "unavailable_signals": self.unavailable_signals,
        }
