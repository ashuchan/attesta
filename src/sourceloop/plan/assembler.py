from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import CurrentOffer
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.domain.plan import PlanLine, SourcedPlan

_HIGH_THRESHOLD = 80.0
_MEDIUM_THRESHOLD = 50.0


def _band_score(score: float | None) -> int:
    """Map score to sort key: 0=high, 1=medium, 2=low, 3=none."""
    if score is None:
        return 3
    if score >= _HIGH_THRESHOLD:
        return 0
    if score >= _MEDIUM_THRESHOLD:
        return 1
    return 2


def _offer_to_snapshot(offer: CurrentOffer, effective_score: float | None) -> dict[str, object]:
    return {
        "listing_id": str(offer.listing_id),
        "supplier_id": offer.supplier_id,
        "price_ladder": {"rungs": offer.price_ladder.rungs} if offer.price_ladder else None,
        "moq": offer.moq,
        "lead_time": offer.lead_time,
        "stock": offer.stock,
        "confidence": effective_score,
        "confidence_stored": offer.confidence,
    }


class PlanAssembler:
    """
    Builds SourcedPlan + PlanLine domain objects.
    Step 2: stamps plan_line.confidence (effective), sorts offers by band,
    sets chosen_listing_id when exactly one unambiguous High offer exists.
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
                    # Use confidence_effective (live freshness) when available; fall back to stored
                    scored_offers = [
                        (o, o.confidence_effective if o.confidence_effective is not None else o.confidence)
                        for o in offers
                    ]
                    # Sort by confidence band then score desc: High → Medium → Low → unscored
                    scored_offers.sort(key=lambda x: (_band_score(x[1]), -(x[1] or 0.0)))

                    # Best effective score for line-level confidence
                    best_score = scored_offers[0][1] if scored_offers else None

                    # Set chosen_listing_id when exactly ONE High offer exists (unambiguous)
                    high_offers = [(o, s) for o, s in scored_offers if s is not None and s >= _HIGH_THRESHOLD]
                    chosen_listing_id: uuid.UUID | None = high_offers[0][0].listing_id if len(high_offers) == 1 else None

                    plan_lines.append(PlanLine(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        sourced_plan_id=plan_id,
                        bom_line_id=line.id,
                        chosen_listing_id=chosen_listing_id,
                        offer_snapshot=[_offer_to_snapshot(o, s) for o, s in scored_offers],
                        confidence=best_score,
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
            generated_at=datetime.now(UTC),
            tier_a_coverage_pct=coverage,
            status="sourced",
            lines=plan_lines,
            confidence_summary=_compute_confidence_summary(plan_lines),
        )


def _compute_confidence_summary(lines: list[PlanLine]) -> dict[str, int]:
    counts: dict[str, int] = {"high": 0, "medium": 0, "low": 0, "unsourced": 0}
    for line in lines:
        if line.unsourced_reason is not None or not line.offer_snapshot:
            counts["unsourced"] += 1
        elif line.confidence is None:
            counts["unsourced"] += 1
        elif line.confidence >= _HIGH_THRESHOLD:
            counts["high"] += 1
        elif line.confidence >= _MEDIUM_THRESHOLD:
            counts["medium"] += 1
        else:
            counts["low"] += 1
    return counts
