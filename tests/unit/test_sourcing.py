from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import CurrentOffer, PriceLadder
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.plan.assembler import PlanAssembler


def make_bom_line(part_class: PartClass = PartClass.A, mpn: str = "STM32F103C8T6") -> BomLine:
    tid = uuid.uuid4()
    bid = uuid.uuid4()
    return BomLine(
        id=uuid.uuid4(), tenant_id=tid, bom_id=bid,
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn=mpn, manufacturer="ST", quantity=1.0, unit="pcs",
        normalized_part_key=f"mpn:{mpn}", part_class=part_class,
        parse_confidence=0.9,
    )


def make_offer(part_key: str = "mpn:STM32F103C8T6") -> CurrentOffer:
    return CurrentOffer(
        listing_id=uuid.uuid4(), latest_obs_id=uuid.uuid4(),
        normalized_part_key=part_key, supplier_id="nexar:1",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1, lead_time=None, stock=100, specs={}, confidence=None,
        field_captured_at={"price_ladder": datetime.now(UTC).isoformat()},
    )


def test_assembler_tier_a_sourced():
    assembler = PlanAssembler()
    tid = uuid.uuid4()
    bid = uuid.uuid4()
    line = make_bom_line(PartClass.A)
    offer = make_offer()
    plan = assembler.assemble(bid, tid, [(line, [offer])])
    assert plan.tier_a_coverage_pct == 100.0
    assert len(plan.lines) == 1
    assert plan.lines[0].unsourced_reason is None
    assert plan.lines[0].confidence is None  # NullConfidence


def test_assembler_tier_a_no_offers():
    assembler = PlanAssembler()
    tid, bid = uuid.uuid4(), uuid.uuid4()
    line = make_bom_line(PartClass.A)
    plan = assembler.assemble(bid, tid, [(line, [])])
    assert plan.tier_a_coverage_pct == 0.0
    assert plan.lines[0].unsourced_reason == UnsourcedReason.NO_TIER_A_OFFERS


def test_assembler_tier_b_marked_unsourced():
    assembler = PlanAssembler()
    tid, bid = uuid.uuid4(), uuid.uuid4()
    line = make_bom_line(PartClass.B)
    plan = assembler.assemble(bid, tid, [(line, [])])
    assert plan.tier_a_coverage_pct == 0.0  # no tier_a lines
    assert plan.lines[0].unsourced_reason == UnsourcedReason.TIER_B_NOT_IN_STEP1


def test_assembler_mixed_coverage():
    assembler = PlanAssembler()
    tid, bid = uuid.uuid4(), uuid.uuid4()
    line_a1 = make_bom_line(PartClass.A, mpn="STM32F103C8T6")
    line_a2 = make_bom_line(PartClass.A, mpn="ESP8266EX")
    line_b = make_bom_line(PartClass.B, mpn="CUSTOM")
    offer = make_offer("mpn:STM32F103C8T6")
    plan = assembler.assemble(bid, tid, [
        (line_a1, [offer]),
        (line_a2, []),
        (line_b, []),
    ])
    # 1 of 2 Tier-A sourced = 50%
    assert plan.tier_a_coverage_pct == 50.0
    assert len(plan.lines) == 3
