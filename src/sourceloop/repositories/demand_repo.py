from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .tenant_scoped import TenantScopedRepository





class DemandRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def emit(
        self,
        normalized_part_key: str,
        category: str | None,
        customer_id: uuid.UUID | None = None,
    ) -> None:
        tenant_id = self._current_tenant()
        now = datetime.now(UTC)
        await self._session.execute(
            text("""
                INSERT INTO demand_event (id, tenant_id, normalized_part_key, category, customer_id, ts)
                VALUES (:id, :tenant_id, :part_key, :category, :customer_id, :ts)
            """),
            {
                "id": str(uuid.uuid4()),
                "tenant_id": str(tenant_id),
                "part_key": normalized_part_key,
                "category": category,
                "customer_id": str(customer_id) if customer_id else None,
                "ts": now,
            },
        )

    async def hotness_feed(
        self, since: datetime
    ) -> list[tuple[str, str | None, datetime]]:
        """
        De-identified feed: (normalized_part_key, category, ts).
        NO tenant/customer identifiers — reads cross-tenant by design (hotness is global).
        """
        result = await self._session.execute(
            text("""
                SELECT normalized_part_key, category, ts
                FROM demand_event
                WHERE ts >= :since
                ORDER BY ts DESC
            """),
            {"since": since},
        )
        return [(row[0], row[1], row[2]) for row in result.fetchall()]
