from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import CurrentOffer
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.domain.plan import PlanLine, SourcedPlan


def _offer_to_snapshot(offer: CurrentOffer) -> dict[str, object]:
    return {
        "listing_id": str(offer.listing_id),
        "supplier_id": offer.supplier_id,
        "price_ladder": {"rungs": offer.price_ladder.rungs} if offer.price_ladder else None,
        "moq": offer.moq,
        "lead_time": offer.lead_time,
        "stock": offer.stock,
        "confidence": offer.confidence,
    }


class PlanAssembler:
    """
    Builds SourcedPlan + PlanLine domain objects.
    Step 1: chosen_listing_id is NULL; all found offers attached in offer_snapshot.
    Ranking/selection is Step 2.
    """

    def assemble(
        self,
        bom_id: uuid.UUID,
        tenant_id: uuid.UUID,
        line_offers: list[tuple[BomLine, list[CurrentOffer]]],
    ) -> SourcedPlan:
        plan_id = uuid.uuid4()
        plan_lines: list[PlanLine] = []
        tier_a_sourced = 0
        tier_a_total = 0

        for line, offers in line_offers:
            if line.part_class == PartClass.A:
                tier_a_total += 1
                if offers:
                    tier_a_sourced += 1
                    plan_lines.append(PlanLine(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        sourced_plan_id=plan_id,
                        bom_line_id=line.id,
                        chosen_listing_id=None,  # Step 2
                        offer_snapshot=[_offer_to_snapshot(o) for o in offers],
                        confidence=None,  # NullConfidence — Step 2
                        unsourced_reason=None,
                    ))
                else:
                    plan_lines.append(PlanLine(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        sourced_plan_id=plan_id,
                        bom_line_id=line.id,
                        chosen_listing_id=None,
                        offer_snapshot=[],
                        confidence=None,
                        unsourced_reason=UnsourcedReason.NO_TIER_A_OFFERS,
                    ))
            else:
                # Tier-B/C: classified but not sourced in Step 1
                plan_lines.append(PlanLine(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    sourced_plan_id=plan_id,
                    bom_line_id=line.id,
                    chosen_listing_id=None,
                    offer_snapshot=[],
                    confidence=None,
                    unsourced_reason=UnsourcedReason.TIER_B_NOT_IN_STEP1,
                ))

        coverage = (tier_a_sourced / tier_a_total * 100.0) if tier_a_total > 0 else 0.0

        return SourcedPlan(
            id=plan_id,
            tenant_id=tenant_id,
            bom_id=bom_id,
            generated_at=datetime.now(timezone.utc),
            tier_a_coverage_pct=coverage,
            status="sourced",
            lines=plan_lines,
        )
