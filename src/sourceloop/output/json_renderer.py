from __future__ import annotations

import json

from sourceloop.domain.bom import ParseResult
from sourceloop.domain.plan import SourcedPlan


def render_plan(plan: SourcedPlan, parse_result: ParseResult | None = None) -> str:
    """Render a SourcedPlan to JSON string."""
    data: dict[str, object] = {
        "plan_id": str(plan.id),
        "bom_id": str(plan.bom_id),
        "generated_at": plan.generated_at.isoformat(),
        "tier_a_coverage_pct": plan.tier_a_coverage_pct,
        "status": plan.status,
        "lines": [
            {
                "plan_line_id": str(line.id),
                "bom_line_id": str(line.bom_line_id),
                "chosen_listing_id": str(line.chosen_listing_id) if line.chosen_listing_id else None,
                "offers": line.offer_snapshot,
                "confidence": line.confidence,
                "unsourced_reason": line.unsourced_reason.value if line.unsourced_reason else None,
            }
            for line in plan.lines
        ],
    }
    if parse_result:
        data["parse_meta"] = {
            "source_filename": parse_result.source_filename,
            "format": parse_result.original_format,
            "parser_key": parse_result.parser_key,
            "parse_confidence_avg": parse_result.parse_confidence_avg,
            "line_count": len(parse_result.lines),
        }
    return json.dumps(data, indent=2, default=str)


def render_lint(parse_result: ParseResult) -> str:
    """Render parse-only lint output (--lint-only mode)."""
    lines_data = []
    for line in parse_result.lines:
        lines_data.append({
            "line_no": line.line_no,
            "designator": line.raw_designator,
            "mpn": line.mpn,
            "manufacturer": line.manufacturer,
            "quantity": line.quantity,
            "normalized_part_key": line.normalized_part_key,
            "parse_confidence": line.parse_confidence,
            "notes": line.notes,
        })
    data = {
        "source_filename": parse_result.source_filename,
        "format": parse_result.original_format,
        "parser_key": parse_result.parser_key,
        "parse_confidence_avg": parse_result.parse_confidence_avg,
        "line_count": len(parse_result.lines),
        "lines": lines_data,
    }
    return json.dumps(data, indent=2, default=str)
