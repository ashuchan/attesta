from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.db.tables import BomLineRow, BomRow
from sourceloop.domain.bom import Bom, BomLine, ParseResult
from sourceloop.domain.part import PartClass

from .tenant_scoped import TenantScopedRepository


class BomRepository(TenantScopedRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_bom(self, parse_result: ParseResult) -> Bom:
        tenant_id = self._current_tenant()
        now = datetime.now(UTC)
        row = BomRow(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            source_filename=parse_result.source_filename,
            original_format=parse_result.original_format,
            line_count=len(parse_result.lines),
            parse_confidence_avg=parse_result.parse_confidence_avg,
            status="parsed",
            uploaded_at=now,
            parsed_at=now,
        )
        self._session.add(row)
        await self._session.flush()
        return self._row_to_domain(row)

    async def get_bom(self, bom_id: uuid.UUID) -> Bom | None:
        result = await self._session.execute(
            select(BomRow).where(
                BomRow.id == bom_id, BomRow.tenant_id == self._current_tenant()
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        self._assert_tenant(row.tenant_id)
        return self._row_to_domain(row)

    async def update_status(self, bom_id: uuid.UUID, status: str) -> None:
        await self._session.execute(
            update(BomRow)
            .where(BomRow.id == bom_id, BomRow.tenant_id == self._current_tenant())
            .values(status=status)
        )

    async def create_lines(self, bom_id: uuid.UUID, lines: list[BomLine]) -> list[BomLine]:
        tenant_id = self._current_tenant()
        rows = []
        for line in lines:
            row = BomLineRow(
                id=line.id,
                tenant_id=tenant_id,
                bom_id=bom_id,
                line_no=line.line_no,
                raw_designator=line.raw_designator,
                raw_description=line.raw_description,
                mpn=line.mpn,
                manufacturer=line.manufacturer,
                quantity=line.quantity,
                unit=line.unit,
                normalized_part_key=line.normalized_part_key,
                part_class=line.part_class.value if line.part_class else None,
                parse_confidence=line.parse_confidence,
                notes=line.notes,
            )
            rows.append(row)
        self._session.add_all(rows)
        await self._session.flush()
        return lines

    async def get_lines(self, bom_id: uuid.UUID) -> list[BomLine]:
        result = await self._session.execute(
            select(BomLineRow).where(
                BomLineRow.bom_id == bom_id,
                BomLineRow.tenant_id == self._current_tenant(),
            )
        )
        rows = result.scalars().all()
        return [self._line_row_to_domain(r) for r in rows]

    def _row_to_domain(self, row: BomRow) -> Bom:
        return Bom(
            id=row.id,
            tenant_id=row.tenant_id,
            source_filename=row.source_filename,
            original_format=row.original_format,
            line_count=row.line_count,
            parse_confidence_avg=row.parse_confidence_avg or 0.0,
            status=row.status,
            uploaded_at=row.uploaded_at,
            parsed_at=row.parsed_at,
        )

    def _line_row_to_domain(self, row: BomLineRow) -> BomLine:
        self._assert_tenant(row.tenant_id)
        return BomLine(
            id=row.id,
            tenant_id=row.tenant_id,
            bom_id=row.bom_id,
            line_no=row.line_no,
            raw_designator=row.raw_designator,
            raw_description=row.raw_description,
            mpn=row.mpn,
            manufacturer=row.manufacturer,
            quantity=float(row.quantity) if row.quantity is not None else None,
            unit=row.unit,
            normalized_part_key=row.normalized_part_key,
            part_class=PartClass(row.part_class) if row.part_class else None,
            parse_confidence=row.parse_confidence,
            notes=row.notes,
        )
