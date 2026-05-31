"""
End-to-end integration test using MockConnector against 3 fixture BOMs.
Requires DATABASE_URL env var pointing to a Postgres instance.
Skip if not available.
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures" / "boms"
DB_URL = os.environ.get("DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not DB_URL, reason="DATABASE_URL not set")


@pytest.mark.asyncio
async def test_e2e_csv_bom_with_mock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Full parse→source pipeline on iot_board.csv using MockConnector."""
    monkeypatch.setenv("SOURCELOOP_USE_MOCK", "1")

    # Re-import config with mock enabled
    import importlib  # noqa: F401

    from sourceloop.config import loader as config_loader

    config_loader.get_env.cache_clear()
    config_loader.get_connectors_config.cache_clear()

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from sourceloop.domain.part import UnsourcedReason
    from sourceloop.parsing.base import ParseSource
    from sourceloop.parsing.pipeline import BomParser
    from sourceloop.repositories.bom_repo import BomRepository
    from sourceloop.repositories.customer_repo import CustomerRepository
    from sourceloop.sourcing.tier_a_service import SourcingService
    from sourceloop.tenancy.context import TenantContext

    engine = create_async_engine(DB_URL, echo=False)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    async with factory() as session:
        customer_repo = CustomerRepository(session)
        TenantContext.set(uuid.UUID(int=0))
        tenant_row = await customer_repo.get_tenant_by_slug("founder-internal")
        if tenant_row is None:
            pytest.skip("founder-internal tenant not seeded (run alembic upgrade head)")
        TenantContext.set(tenant_row.id)

        # Parse CSV
        content = (FIXTURES / "iot_board.csv").read_bytes()
        source = ParseSource(content=content, filename="iot_board.csv")
        parser = BomParser()
        parse_result = await parser.parse(source)
        assert len(parse_result.lines) > 0

        # Persist BOM
        bom_repo = BomRepository(session)
        bom = await bom_repo.create_bom(parse_result)
        await bom_repo.create_lines(bom.id, parse_result.lines)
        await session.commit()

    async with factory() as session:
        TenantContext.set(tenant_row.id)
        service = SourcingService(session)
        plan = await service.source_bom(bom.id)

    # Tier-A lines (those with MPN) should have offers from MockConnector
    tier_a_lines = [line for line in plan.lines if line.unsourced_reason != UnsourcedReason.TIER_B_NOT_IN_STEP1]
    assert len(tier_a_lines) > 0

    # Lines without MPN (custom PCB) should be unsourced
    unsourced = [line for line in plan.lines if line.unsourced_reason == UnsourcedReason.TIER_B_NOT_IN_STEP1]
    assert len(unsourced) >= 1  # PCB1 has no MPN → Tier-B

    await engine.dispose()
