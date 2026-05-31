"""Completeness signal: fraction of required fields present for the tier."""
from __future__ import annotations

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext

_REQUIRED_BY_TIER: dict[str, list[str]] = {
    "A": ["price_ladder", "moq", "stock"],
    "B": ["price_ladder", "moq", "stock"],
    "C": ["price_ladder"],
}


class CompletenessSignal:
    key = "completeness"
    depends_on: list[str] = []
    enabled = True

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        tier = getattr(subject, "tier", "A")
        required = _REQUIRED_BY_TIER.get(tier, ["price_ladder", "moq", "stock"])
        present = [f for f in required if getattr(subject, f, None) is not None]
        frac = len(present) / len(required) if required else 1.0
        return SignalValue(
            normalized=frac,
            raw=None,
            provenance={"required": required, "present": present, "fraction": frac},
        )
