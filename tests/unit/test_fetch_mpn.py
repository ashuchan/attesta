"""Unit tests for fetch_mpn on mock connector and nexar connector delegation."""
from __future__ import annotations

import pytest

from sourceloop.connectors.mock import MockConnector


@pytest.mark.asyncio
async def test_mock_fetch_mpn_known_key():
    """fetch_mpn returns observations for known normalized_part_key."""
    conn = MockConnector()
    conn.enabled = True
    obs = await conn.fetch_mpn(
        mpn="STM32F103C8T6",
        manufacturer=None,
        normalized_part_key="mpn:STM32F103C8T6",
        category=None,
    )
    assert len(obs) > 0
    assert obs[0].normalized_part_key == "mpn:STM32F103C8T6"
    assert obs[0].tier == "A"


@pytest.mark.asyncio
async def test_mock_fetch_mpn_unknown_key():
    """fetch_mpn returns empty list for unknown keys."""
    conn = MockConnector()
    conn.enabled = True
    obs = await conn.fetch_mpn(
        mpn="UNKNOWN123",
        manufacturer=None,
        normalized_part_key="mpn:UNKNOWN123",
        category=None,
    )
    assert obs == []


@pytest.mark.asyncio
async def test_mock_fetch_delegates_to_fetch_mpn():
    """MockConnector.fetch() delegates to fetch_mpn()."""
    from unittest.mock import AsyncMock, patch
    from sourceloop.domain.bom import BomLine
    from sourceloop.domain.part import PartClass
    import uuid

    conn = MockConnector()
    conn.enabled = True

    line = BomLine(
        id=uuid.uuid4(),
        bom_id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        line_no=1,
        raw_designator="U1",
        raw_description="MCU",
        mpn="STM32F103C8T6",
        manufacturer=None,
        quantity=1.0,
        unit="pcs",
        normalized_part_key="mpn:STM32F103C8T6",
        part_class=PartClass.A,
        parse_confidence=1.0,
        notes=None,
    )

    with patch.object(conn, "fetch_mpn", new_callable=AsyncMock) as mock_fetch_mpn:
        mock_fetch_mpn.return_value = []
        await conn.fetch(line)
        mock_fetch_mpn.assert_called_once_with(
            mpn="STM32F103C8T6",
            manufacturer=None,
            normalized_part_key="mpn:STM32F103C8T6",
            category=None,
        )
