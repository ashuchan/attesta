from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class PriceLadder:
    """Sorted by quantity ascending."""
    rungs: list[dict[str, Any]]  # [{qty, price, currency}, ...]


@dataclass(frozen=True)
class OfferObservation:
    listing_id: uuid.UUID
    source: str  # 'api' | 'dom' | 'mtop' | 'vision' | 'rfq'
    tier: str    # 'A' | 'B' | 'C'
    captured_at: datetime
    normalized_part_key: str
    supplier_id: str  # namespaced e.g. nexar:{id}
    category: str | None
    price_ladder: PriceLadder | None
    moq: int | None
    lead_time: str | None
    stock: int | None
    specs: dict[str, Any]
    supplier_snapshot: dict[str, Any]
    screenshot_ref: str | None
    confidence: float | None  # always None in Step 1
    field_captured_at: dict[str, str]  # field -> ISO timestamp


@dataclass(frozen=True)
class CurrentOffer:
    listing_id: uuid.UUID
    latest_obs_id: uuid.UUID
    normalized_part_key: str
    supplier_id: str
    price_ladder: PriceLadder | None
    moq: int | None
    lead_time: str | None
    stock: int | None
    specs: dict[str, Any]
    confidence: float | None
    field_captured_at: dict[str, str]
    tier: str = "A"                            # needed by Scorable protocol
    confidence_effective: float | None = None  # read-time freshness-decayed score (never persisted)
