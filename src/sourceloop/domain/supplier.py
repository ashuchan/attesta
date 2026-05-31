from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Supplier:
    supplier_id: str  # namespaced: nexar:{id}
    name: str
    region: str | None
    years_active: int | None
    trade_assurance: bool | None
    verified_factory: bool | None
    response_rate: float | None
    repurchase_rate: float | None
    reliability_score: float | None
    blacklisted: bool
    updated_at: datetime
