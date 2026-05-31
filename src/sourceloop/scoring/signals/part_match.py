"""PartMatch signal — DISABLED (requires §10 part-matcher match-certainty score)."""
from __future__ import annotations

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext


class PartMatchSignal:
    key = "part_match"
    depends_on: list[str] = []
    enabled = False  # requires part-matcher certainty; enabled in §10

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        raise NotImplementedError("PartMatchSignal is disabled")
