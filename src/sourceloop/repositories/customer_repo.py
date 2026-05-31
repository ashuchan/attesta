from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.db.tables import TenantRow

from .tenant_scoped import TenantScopedRepository


class CustomerRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_tenant_by_slug(self, slug: str) -> TenantRow | None:
        result = await self._session.execute(
            select(TenantRow).where(TenantRow.slug == slug)
        )
        return result.scalar_one_or_none()

    async def get_tenant_by_id(self, tenant_id: uuid.UUID) -> TenantRow | None:
        result = await self._session.execute(
            select(TenantRow).where(TenantRow.id == tenant_id)
        )
        return result.scalar_one_or_none()
