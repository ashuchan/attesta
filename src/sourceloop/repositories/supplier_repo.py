from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sourceloop.db.tables import SupplierRow
from sourceloop.domain.supplier import Supplier
from .base import AbstractRepository


class SupplierRepository(AbstractRepository[Supplier]):
    """Global repository — NO tenant scoping."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, supplier: Supplier) -> None:
        """Upsert supplier by supplier_id."""
        stmt = pg_insert(SupplierRow).values(
            supplier_id=supplier.supplier_id,
            name=supplier.name,
            region=supplier.region,
            years_active=supplier.years_active,
            trade_assurance=supplier.trade_assurance,
            verified_factory=supplier.verified_factory,
            response_rate=supplier.response_rate,
            repurchase_rate=supplier.repurchase_rate,
            reliability_score=supplier.reliability_score,
            blacklisted=supplier.blacklisted,
            updated_at=supplier.updated_at,
        ).on_conflict_do_update(
            index_elements=["supplier_id"],
            set_={
                "name": supplier.name,
                "region": supplier.region,
                "updated_at": supplier.updated_at,
            }
        )
        await self._session.execute(stmt)
