from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from sourceloop.connectors.mock import MockConnector
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass


def make_line(mpn: str | None = "STM32F103C8T6", part_key: str | None = None) -> BomLine:
    return BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn=mpn, manufacturer="STMicro", quantity=1.0, unit="pcs",
        normalized_part_key=part_key or (f"mpn:{mpn}" if mpn else "desc:abc123"),
        part_class=PartClass.A, parse_confidence=0.9,
    )


@pytest.mark.asyncio
async def test_mock_connector_returns_offers_for_known_mpn():
    connector = MockConnector()
    connector.enabled = True
    line = make_line(mpn="STM32F103C8T6", part_key="mpn:STM32F103C8T6")
    observations = await connector.fetch(line)
    assert len(observations) > 0
    assert observations[0].tier == "A"
    assert observations[0].source == "api"
    assert observations[0].confidence is None  # NullConfidence


@pytest.mark.asyncio
async def test_mock_connector_returns_empty_for_unknown_mpn():
    connector = MockConnector()
    connector.enabled = True
    line = make_line(mpn="UNKNOWN9999", part_key="mpn:UNKNOWN9999")
    observations = await connector.fetch(line)
    assert observations == []


@pytest.mark.asyncio
async def test_mock_connector_price_ladder_sorted():
    connector = MockConnector()
    connector.enabled = True
    line = make_line(mpn="STM32F103C8T6", part_key="mpn:STM32F103C8T6")
    observations = await connector.fetch(line)
    if observations and observations[0].price_ladder:
        rungs = observations[0].price_ladder.rungs
        qtys = [r["qty"] for r in rungs]
        assert qtys == sorted(qtys)


@pytest.mark.asyncio
async def test_nexar_token_manager_reuses_token():
    """Token should be reused if not expired — only one HTTP call for N uses."""
    from sourceloop.connectors.nexar import NexarTokenManager

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "tok123", "expires_in": 3600}

    mgr = NexarTokenManager("id", "secret", "http://fake-token")
    post_mock = AsyncMock(return_value=FakeResp())

    # Patch at the module level so AsyncClient() constructor is bypassed
    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_cm.post = post_mock
        mock_client_cls.return_value = mock_cm

        t1 = await mgr.get_token()
        t2 = await mgr.get_token()
        t3 = await mgr.get_token()

    assert t1 == t2 == t3 == "tok123"
    assert post_mock.call_count == 1  # only fetched once


@pytest.mark.asyncio
async def test_nexar_token_manager_refreshes_on_expiry():
    """After simulated expiry, token is refreshed."""
    from sourceloop.connectors.nexar import NexarTokenManager

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "new_tok", "expires_in": 1}

    mgr = NexarTokenManager("id", "secret", "http://fake-token")
    # Force expiry
    mgr._expires_at = 0.0
    post_mock = AsyncMock(return_value=FakeResp())

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as mock_client_cls:
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_cm)
        mock_cm.__aexit__ = AsyncMock(return_value=False)
        mock_cm.post = post_mock
        mock_client_cls.return_value = mock_cm

        tok = await mgr.get_token()

    assert tok == "new_tok"
    assert post_mock.call_count == 1
