from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .part import UnsourcedReason


@dataclass(frozen=True)
class PlanLine:
    id: uuid.UUID
    tenant_id: uuid.UUID
    sourced_plan_id: uuid.UUID
    bom_line_id: uuid.UUID
    chosen_listing_id: uuid.UUID | None
    offer_snapshot: list[dict[str, Any]]
    confidence: float | None  # always None in Step 1
    unsourced_reason: UnsourcedReason | None


@dataclass(frozen=True)
class SourcedPlan:
    id: uuid.UUID
    tenant_id: uuid.UUID
    bom_id: uuid.UUID
    generated_at: datetime
    tier_a_coverage_pct: float
    status: str
    lines: list[PlanLine]
