from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from .part import PartClass


@dataclass(frozen=True)
class BomLine:
    id: uuid.UUID
    tenant_id: uuid.UUID
    bom_id: uuid.UUID
    line_no: int
    raw_designator: str | None
    raw_description: str | None
    mpn: str | None
    manufacturer: str | None
    quantity: float | None
    unit: str | None
    normalized_part_key: str
    part_class: PartClass | None
    parse_confidence: float
    notes: str | None = None


@dataclass(frozen=True)
class ParseResult:
    lines: list[BomLine]
    source_filename: str
    original_format: str
    parse_confidence_avg: float
    parser_key: str
    parser_confidence: float


@dataclass(frozen=True)
class Bom:
    id: uuid.UUID
    tenant_id: uuid.UUID
    source_filename: str
    original_format: str
    line_count: int
    parse_confidence_avg: float
    status: str
    uploaded_at: datetime
    parsed_at: datetime | None
