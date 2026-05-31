"""SupplierTrust signal — DISABLED (requires supplier.reliability_score populated)."""
from __future__ import annotations

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext


class SupplierTrustSignal:
    key = "supplier_trust"
    depends_on: list[str] = []
    enabled = False  # requires supplier.reliability_score; enabled when populated

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        raise NotImplementedError("SupplierTrustSignal is disabled")
