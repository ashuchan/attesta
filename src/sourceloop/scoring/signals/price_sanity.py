"""PriceSanity signal — DISABLED (needs cross-offer baseline from ranking step)."""
from __future__ import annotations

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext


class PriceSanitySignal:
    key = "price_sanity"
    depends_on: list[str] = []
    enabled = False  # requires cross-offer price baseline; enabled in §8 ranking step

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        raise NotImplementedError("PriceSanitySignal is disabled")
