from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

from sourceloop.domain.bom import BomLine, ParseResult
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.domain.plan import PlanLine, SourcedPlan
from sourceloop.output.json_renderer import render_lint, render_plan


def make_plan(with_lines: bool = True) -> SourcedPlan:
    plan_id = uuid.uuid4()
    tid = uuid.uuid4()
    bid = uuid.uuid4()
    lines = []
    if with_lines:
        lines = [
            PlanLine(
                id=uuid.uuid4(), tenant_id=tid, sourced_plan_id=plan_id,
                bom_line_id=uuid.uuid4(), chosen_listing_id=None,
                offer_snapshot=[{"listing_id": str(uuid.uuid4()), "price_ladder": {"rungs": []}}],
                confidence=None, unsourced_reason=None,
            ),
            PlanLine(
                id=uuid.uuid4(), tenant_id=tid, sourced_plan_id=plan_id,
                bom_line_id=uuid.uuid4(), chosen_listing_id=None,
                offer_snapshot=[],
                confidence=None, unsourced_reason=UnsourcedReason.NO_TIER_A_OFFERS,
            ),
        ]
    return SourcedPlan(
        id=plan_id, tenant_id=tid, bom_id=bid,
        generated_at=datetime.now(UTC),
        tier_a_coverage_pct=50.0, status="sourced", lines=lines,
    )


def make_parse_result() -> ParseResult:
    tid = uuid.uuid4()
    bid = uuid.uuid4()
    lines = [
        BomLine(
            id=uuid.uuid4(), tenant_id=tid, bom_id=bid, line_no=1,
            raw_designator="U1", raw_description="MCU",
            mpn="STM32F103C8T6", manufacturer="ST", quantity=1.0, unit="pcs",
            normalized_part_key="mpn:STM32F103C8T6",
            part_class=PartClass.A, parse_confidence=0.9,
        )
    ]
    return ParseResult(
        lines=lines, source_filename="bom.csv", original_format="csv",
        parse_confidence_avg=0.9, parser_key="csv", parser_confidence=0.85,
    )


def test_render_plan_is_valid_json():
    plan = make_plan()
    output = render_plan(plan)
    data = json.loads(output)
    assert data["tier_a_coverage_pct"] == 50.0
    assert len(data["lines"]) == 2


def test_render_plan_includes_parse_meta():
    plan = make_plan()
    parse_result = make_parse_result()
    output = render_plan(plan, parse_result)
    data = json.loads(output)
    assert "parse_meta" in data
    assert data["parse_meta"]["line_count"] == 1


def test_render_plan_unsourced_reason_serialized():
    plan = make_plan()
    output = render_plan(plan)
    data = json.loads(output)
    unsourced = [ln for ln in data["lines"] if ln["unsourced_reason"]]
    assert unsourced[0]["unsourced_reason"] == "no_tier_a_offers"


def test_render_plan_confidence_is_null():
    plan = make_plan()
    output = render_plan(plan)
    data = json.loads(output)
    for line in data["lines"]:
        assert line["confidence"] is None


def test_render_lint_valid_json():
    parse_result = make_parse_result()
    output = render_lint(parse_result)
    data = json.loads(output)
    assert data["line_count"] == 1
    assert data["format"] == "csv"
    assert len(data["lines"]) == 1
    assert data["lines"][0]["mpn"] == "STM32F103C8T6"


def test_render_plan_no_lines():
    plan = make_plan(with_lines=False)
    output = render_plan(plan)
    data = json.loads(output)
    assert data["lines"] == []


def test_render_plan_contains_plan_id():
    plan = make_plan()
    output = render_plan(plan)
    data = json.loads(output)
    assert "plan_id" in data
    assert "bom_id" in data
    assert "generated_at" in data
    assert "status" in data


def test_render_lint_contains_all_fields():
    parse_result = make_parse_result()
    output = render_lint(parse_result)
    data = json.loads(output)
    assert "source_filename" in data
    assert "parser_key" in data
    assert "parse_confidence_avg" in data
    line = data["lines"][0]
    assert "line_no" in line
    assert "designator" in line
    assert "quantity" in line
    assert "normalized_part_key" in line


def test_render_plan_without_parse_meta():
    plan = make_plan()
    output = render_plan(plan)
    data = json.loads(output)
    assert "parse_meta" not in data


def test_render_plan_chosen_listing_id_null():
    plan = make_plan()
    output = render_plan(plan)
    data = json.loads(output)
    for line in data["lines"]:
        assert line["chosen_listing_id"] is None
