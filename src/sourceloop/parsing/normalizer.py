from __future__ import annotations

import re
import uuid

from sourceloop.domain.bom import BomLine
from sourceloop.parsing.base import RawRowSet

# Header lexicon: canonical field -> aliases
HEADER_MAP: dict[str, list[str]] = {
    "mpn": ["mpn", "part number", "partnumber", "part_number", "mfr part", "mfrpart", "part no", "part#"],
    "quantity": ["qty", "quantity", "count", "amount", "num"],
    "manufacturer": ["manufacturer", "mfr", "brand", "maker", "mfg"],
    "raw_designator": ["ref", "designator", "reference", "refdes", "ref des", "ref_des"],
    "raw_description": ["description", "value", "desc", "component", "name", "part name"],
    "unit": ["unit", "units", "uom"],
}


def _match_header(header: str) -> str | None:
    """Map a raw header string to a canonical field name."""
    h = header.strip().lower()
    for canonical, aliases in HEADER_MAP.items():
        if h in aliases:
            return canonical
    return None


def normalize(
    rawrowset: RawRowSet,
    bom_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> list[BomLine]:
    """Map RawRowSet → list[BomLine] using header lexicon."""
    lines = []
    for line_no, raw_row in enumerate(rawrowset.rows, start=1):
        # Build a canonical row dict
        canonical: dict[str, str | None] = {}
        for raw_key, val in raw_row.items():
            mapped = _match_header(raw_key)
            if mapped and mapped not in canonical:
                canonical[mapped] = val if val else None

        # Parse quantity
        qty: float | None = None
        qty_str = canonical.get("quantity")
        if qty_str:
            try:
                qty = float(re.sub(r"[^\d.]", "", qty_str))
            except ValueError:
                qty = None

        mpn = canonical.get("mpn")
        manufacturer = canonical.get("manufacturer")
        raw_desc = canonical.get("raw_description")
        raw_des = canonical.get("raw_designator")

        # parse_confidence: higher if MPN is present and quantity is valid
        parse_confidence = 0.5
        if mpn:
            parse_confidence += 0.3
        if qty is not None:
            parse_confidence += 0.1
        if raw_desc:
            parse_confidence += 0.1
        parse_confidence = min(parse_confidence, 1.0)

        line = BomLine(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            bom_id=bom_id,
            line_no=line_no,
            raw_designator=raw_des,
            raw_description=raw_desc,
            mpn=mpn,
            manufacturer=manufacturer,
            quantity=qty,
            unit=canonical.get("unit"),
            normalized_part_key="",  # filled by part_key.derive() after
            part_class=None,  # filled by classifier chain
            parse_confidence=parse_confidence,
        )
        lines.append(line)
    return lines
