"""Tests for Step-2 PlanAssembler: confidence stamping, band ordering, chosen_listing_id."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import CurrentOffer, PriceLadder
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.plan.assembler import PlanAssembler, _compute_confidence_summary


def _line(part_class: PartClass = PartClass.A) -> BomLine:
    return BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn="STM32F103C8T6", manufacturer="ST", quantity=1.0, unit="pcs",
        normalized_part_key="mpn:STM32F103C8T6", part_class=part_class, parse_confidence=0.9,
    )


def _offer(confidence: float | None = None, confidence_effective: float | None = None) -> CurrentOffer:
    return CurrentOffer(
        listing_id=uuid.uuid4(), latest_obs_id=uuid.uuid4(),
        normalized_part_key="mpn:STM32F103C8T6", supplier_id="nexar:1",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1, lead_time=None, stock=100, specs={}, confidence=confidence,
        field_captured_at={"price_ladder": datetime.now(UTC).isoformat()},
        confidence_effective=confidence_effective,
    )


class TestAssemblerConfidenceStamping:
    def setup_method(self):
        self.assembler = PlanAssembler()
        self.tenant = uuid.uuid4()
        self.bom = uuid.uuid4()

    def test_line_confidence_is_best_effective_score(self):
        high_offer = _offer(confidence=90.0, confidence_effective=92.0)
        low_offer = _offer(confidence=60.0, confidence_effective=58.0)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [high_offer, low_offer])])
        assert plan.lines[0].confidence == pytest.approx(92.0)

    def test_line_confidence_falls_back_to_stored_when_no_effective(self):
        offer = _offer(confidence=85.0, confidence_effective=None)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [offer])])
        assert plan.lines[0].confidence == pytest.approx(85.0)

    def test_offers_sorted_high_first(self):
        low = _offer(confidence_effective=60.0)
        high = _offer(confidence_effective=95.0)
        medium = _offer(confidence_effective=70.0)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [low, high, medium])])
        scores = [s["confidence"] for s in plan.lines[0].offer_snapshot]
        assert scores == [95.0, 70.0, 60.0]

    def test_chosen_listing_id_set_when_exactly_one_high(self):
        high = _offer(confidence_effective=92.0)
        low = _offer(confidence_effective=55.0)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [high, low])])
        assert plan.lines[0].chosen_listing_id == high.listing_id

    def test_chosen_listing_id_null_when_multiple_highs(self):
        h1 = _offer(confidence_effective=92.0)
        h2 = _offer(confidence_effective=88.0)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [h1, h2])])
        assert plan.lines[0].chosen_listing_id is None

    def test_chosen_listing_id_null_when_no_high(self):
        med = _offer(confidence_effective=70.0)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [med])])
        assert plan.lines[0].chosen_listing_id is None

    def test_confidence_summary_counts_bands(self):
        high = _offer(confidence_effective=95.0)
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [high])])
        assert plan.confidence_summary is not None
        assert plan.confidence_summary["high"] == 1
        assert plan.confidence_summary["medium"] == 0

    def test_confidence_summary_unsourced_when_no_offers(self):
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [])])
        assert plan.confidence_summary["unsourced"] == 1

    def test_no_offers_line_has_null_chosen_and_null_confidence(self):
        plan = self.assembler.assemble(self.bom, self.tenant, [(_line(), [])])
        assert plan.lines[0].chosen_listing_id is None
        assert plan.lines[0].confidence is None
        assert plan.lines[0].unsourced_reason == UnsourcedReason.NO_TIER_A_OFFERS


class TestComputeConfidenceSummary:
    def _make_line(self, confidence: float | None, unsourced: bool = False) -> object:
        from sourceloop.domain.plan import PlanLine
        return PlanLine(
            id=uuid.uuid4(), tenant_id=uuid.uuid4(), sourced_plan_id=uuid.uuid4(),
            bom_line_id=uuid.uuid4(), chosen_listing_id=None,
            offer_snapshot=[{"dummy": 1}] if not unsourced else [],
            confidence=confidence,
            unsourced_reason=UnsourcedReason.NO_TIER_A_OFFERS if unsourced else None,
        )

    def test_counts_all_bands(self):
        lines = [
            self._make_line(confidence=95.0),  # high
            self._make_line(confidence=85.0),  # high
            self._make_line(confidence=70.0),  # medium
            self._make_line(confidence=40.0),  # low
            self._make_line(confidence=None, unsourced=True),  # unsourced
        ]
        summary = _compute_confidence_summary(lines)  # type: ignore[arg-type]
        assert summary == {"high": 2, "medium": 1, "low": 1, "unsourced": 1}
