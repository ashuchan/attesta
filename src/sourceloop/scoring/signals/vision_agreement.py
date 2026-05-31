"""VisionAgreement signal — DISABLED (Step 5 vision pipeline)."""
from __future__ import annotations

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext


class VisionAgreementSignal:
    key = "vision_agreement"
    depends_on: list[str] = []
    enabled = False  # requires Step 5 vision VoV; enabled then

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        raise NotImplementedError("VisionAgreementSignal is disabled")
