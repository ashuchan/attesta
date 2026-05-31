import uuid
from datetime import UTC, datetime

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import PriceLadder
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.domain.plan import SourcedPlan


def test_bom_line_frozen() -> None:
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn="STM32F103C8T6", manufacturer="STMicro", quantity=1.0, unit="pcs",
        normalized_part_key="mpn:STM32F103C8T6", part_class=PartClass.A,
        parse_confidence=0.9,
    )
    try:
        object.__setattr__(line, "mpn", "other")  # type: ignore
        raise AssertionError("Should be frozen")
    except Exception:
        pass


def test_part_class_values() -> None:
    assert PartClass.A.value == "A"
    assert PartClass.B.value == "B"
    assert PartClass.C.value == "C"


def test_unsourced_reason_values() -> None:
    assert UnsourcedReason.NO_TIER_A_OFFERS.value == "no_tier_a_offers"
    assert UnsourcedReason.TIER_B_NOT_IN_STEP1.value == "tier_b_not_in_step1"


def test_price_ladder() -> None:
    ladder = PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}, {"qty": 10, "price": 90.0, "currency": "INR"}])
    assert ladder.rungs[0]["qty"] == 1
    assert ladder.rungs[1]["price"] == 90.0


def test_sourced_plan_coverage() -> None:
    plan = SourcedPlan(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        generated_at=datetime.now(UTC),
        tier_a_coverage_pct=75.0, status="sourced", lines=[],
    )
    assert plan.tier_a_coverage_pct == 75.0
