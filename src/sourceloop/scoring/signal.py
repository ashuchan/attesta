"""Signal Protocol and SignalValue — the unit of scoring work."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class Scorable(Protocol):
    """Anything the scoring engine can score (OfferObservation or CurrentOffer)."""
    tier: str
    field_captured_at: dict[str, str]
    price_ladder: Any  # PriceLadder | None
    moq: int | None
    stock: int | None


@dataclass(frozen=True)
class SignalValue:
    normalized: float        # 0.0 .. 1.0
    raw: float | None
    provenance: dict[str, Any]


@dataclass(frozen=True)
class ScoringContext:
    now: datetime
    refresh_policies: Any  # RefreshPoliciesConfig — avoid circular import


@runtime_checkable
class Signal(Protocol):
    key: str
    depends_on: list[str]
    enabled: bool

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        ...
