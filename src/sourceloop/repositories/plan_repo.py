from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.db.tables import PlanLineRow, SourcedPlanRow
from sourceloop.domain.part import UnsourcedReason
from sourceloop.domain.plan import PlanLine, SourcedPlan

from .tenant_scoped import TenantScopedRepository


class PlanRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_plan(self, plan: SourcedPlan) -> SourcedPlan:
        """Replace existing plan for this bom_id (idempotent re-sourcing)."""
        tenant_id = self._current_tenant()

        existing = await self._session.execute(
            select(SourcedPlanRow).where(
                SourcedPlanRow.bom_id == plan.bom_id,
                SourcedPlanRow.tenant_id == tenant_id,
            )
        )
        existing_rows = existing.scalars().all()
        for ex_row in existing_rows:
            self._assert_tenant(ex_row.tenant_id)
            await self._session.execute(
                delete(PlanLineRow).where(PlanLineRow.sourced_plan_id == ex_row.id)
            )
            await self._session.delete(ex_row)

        plan_row = SourcedPlanRow(
            id=plan.id,
            tenant_id=tenant_id,
            bom_id=plan.bom_id,
            generated_at=plan.generated_at,
            tier_a_coverage_pct=plan.tier_a_coverage_pct,
            status=plan.status,
            confidence_summary=plan.confidence_summary,
        )
        self._session.add(plan_row)
        await self._session.flush()

        for line in plan.lines:
            offer_snap: list[dict[str, Any]] = line.offer_snapshot
            line_row = PlanLineRow(
                id=line.id,
                tenant_id=tenant_id,
                sourced_plan_id=plan.id,
                bom_line_id=line.bom_line_id,
                chosen_listing_id=line.chosen_listing_id,
                offer_snapshot=offer_snap,
                confidence=line.confidence,
                unsourced_reason=line.unsourced_reason.value if line.unsourced_reason else None,
            )
            self._session.add(line_row)

        await self._session.flush()
        return plan

    async def get_plan(self, bom_id: uuid.UUID) -> SourcedPlan | None:
        result = await self._session.execute(
            select(SourcedPlanRow).where(
                SourcedPlanRow.bom_id == bom_id,
                SourcedPlanRow.tenant_id == self._current_tenant(),
            )
        )
        plan_row = result.scalar_one_or_none()
        if plan_row is None:
            return None
        self._assert_tenant(plan_row.tenant_id)

        lines_result = await self._session.execute(
            select(PlanLineRow).where(PlanLineRow.sourced_plan_id == plan_row.id)
        )
        line_rows = lines_result.scalars().all()
        lines = [self._line_row_to_domain(r) for r in line_rows]
        return SourcedPlan(
            id=plan_row.id,
            tenant_id=plan_row.tenant_id,
            bom_id=plan_row.bom_id,
            generated_at=plan_row.generated_at,
            tier_a_coverage_pct=plan_row.tier_a_coverage_pct,
            status=plan_row.status,
            lines=lines,
        )

    def _line_row_to_domain(self, row: PlanLineRow) -> PlanLine:
        self._assert_tenant(row.tenant_id)
        return PlanLine(
            id=row.id,
            tenant_id=row.tenant_id,
            sourced_plan_id=row.sourced_plan_id,
            bom_line_id=row.bom_line_id,
            chosen_listing_id=row.chosen_listing_id,
            offer_snapshot=row.offer_snapshot or [],
            confidence=row.confidence,
            unsourced_reason=UnsourcedReason(row.unsourced_reason) if row.unsourced_reason else None,
        )
