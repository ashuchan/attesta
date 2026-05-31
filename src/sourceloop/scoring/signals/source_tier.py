"""SourceTier signal: normalized score based on data-source tier."""
from __future__ import annotations

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext

_TIER_SCORES: dict[str, float] = {"A": 1.0, "B": 0.6, "C": 0.3}


class SourceTierSignal:
    key = "source_tier"
    depends_on: list[str] = []
    enabled = True

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        tier = getattr(subject, "tier", "A")
        score = _TIER_SCORES.get(tier, 0.0)
        return SignalValue(normalized=score, raw=None, provenance={"tier": tier})
