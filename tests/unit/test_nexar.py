from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ─── NexarTokenManager tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_token_manager_fetches_on_first_call():
    from sourceloop.connectors.nexar import NexarTokenManager
    mgr = NexarTokenManager("client_id", "client_secret", "http://fake-token/")

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "tok_abc", "expires_in": 3600}

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(return_value=FakeResp())
        MockClient.return_value = instance

        token = await mgr.get_token()

    assert token == "tok_abc"
    assert instance.post.call_count == 1


@pytest.mark.asyncio
async def test_token_manager_reuses_valid_token():
    import time

    from sourceloop.connectors.nexar import NexarTokenManager
    mgr = NexarTokenManager("id", "secret", "http://fake/")
    mgr._access_token = "cached_tok"
    mgr._expires_at = time.monotonic() + 3600  # not expired

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        token = await mgr.get_token()

    assert token == "cached_tok"
    MockClient.assert_not_called()


@pytest.mark.asyncio
async def test_token_manager_refreshes_on_expiry():
    from sourceloop.connectors.nexar import NexarTokenManager
    mgr = NexarTokenManager("id", "secret", "http://fake/")
    mgr._access_token = "old_tok"
    mgr._expires_at = 0.0  # already expired

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self): return {"access_token": "new_tok", "expires_in": 3600}

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(return_value=FakeResp())
        MockClient.return_value = instance

        token = await mgr.get_token()

    assert token == "new_tok"


@pytest.mark.asyncio
async def test_token_manager_raises_after_max_retries():
    from sourceloop.connectors.nexar import NexarAuthError, NexarTokenManager
    mgr = NexarTokenManager("id", "secret", "http://fake/")

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(side_effect=Exception("connection error"))
        MockClient.return_value = instance

        with patch("asyncio.sleep", AsyncMock()), pytest.raises(NexarAuthError):
            await mgr.get_token()


@pytest.mark.asyncio
async def test_token_manager_concurrent_calls_only_one_refresh():
    """asyncio.Lock prevents concurrent double-fetch."""
    from sourceloop.connectors.nexar import NexarTokenManager
    call_count = 0

    class FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            nonlocal call_count
            call_count += 1
            return {"access_token": f"tok_{call_count}", "expires_in": 3600}

    mgr = NexarTokenManager("id", "secret", "http://fake/")

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(return_value=FakeResp())
        MockClient.return_value = instance

        tokens = await asyncio.gather(*[mgr.get_token() for _ in range(5)])

    assert len(set(tokens)) == 1
    assert instance.post.call_count == 1


# ─── NexarClient tests ───────────────────────────────────────────────────────

def _make_client():
    from sourceloop.connectors.nexar import NexarClient, NexarTokenManager
    mgr = MagicMock(spec=NexarTokenManager)
    mgr.get_token = AsyncMock(return_value="tok")
    with patch("sourceloop.connectors.nexar.get_connectors_config") as mock_cfg, \
         patch("sourceloop.connectors.nexar.get_env") as mock_env:
        mock_cfg.return_value.nexar.max_rps = 5
        mock_cfg.return_value.nexar.max_retries = 3
        mock_cfg.return_value.nexar.monthly_quota_soft_cap = 0
        mock_env.return_value.nexar_graphql_url = "http://fake/graphql"
        client = NexarClient(mgr)
    return client, mgr


@pytest.mark.asyncio
async def test_nexar_client_429_respects_retry_after():
    client, mgr = _make_client()
    call_num = 0

    class Resp429:
        status_code = 429
        headers = {"Retry-After": "1"}
        def json(self): return {}

    class RespOk:
        status_code = 200
        headers = {}
        def json(self): return {"data": {"supSearchMpn": {"hits": 0, "results": []}}}

    async def fake_post(*a, **kw):
        nonlocal call_num
        call_num += 1
        if call_num == 1:
            return Resp429()
        return RespOk()

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(side_effect=fake_post)
        MockClient.return_value = instance
        with patch("asyncio.sleep", AsyncMock()):
            result = await client.query({"mpn": "TEST", "limit": 3, "country": "IN", "currency": "INR"})

    assert call_num == 2


@pytest.mark.asyncio
async def test_nexar_client_5xx_retries():
    client, mgr = _make_client()
    call_num = 0

    class Resp5xx:
        status_code = 503
        headers = {}
        def json(self): return {}

    class RespOk:
        status_code = 200
        headers = {}
        def json(self): return {"data": {"supSearchMpn": {"hits": 0, "results": []}}}

    async def fake_post(*a, **kw):
        nonlocal call_num
        call_num += 1
        if call_num <= 2:
            return Resp5xx()
        return RespOk()

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(side_effect=fake_post)
        MockClient.return_value = instance
        with patch("asyncio.sleep", AsyncMock()):
            result = await client.query({"mpn": "X", "limit": 3, "country": "IN", "currency": "INR"})

    assert call_num == 3


@pytest.mark.asyncio
async def test_nexar_client_4xx_not_retried():
    client, mgr = _make_client()
    call_num = 0

    class Resp4xx:
        status_code = 400
        headers = {}
        def json(self): return {}

    async def fake_post(*a, **kw):
        nonlocal call_num
        call_num += 1
        return Resp4xx()

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(side_effect=fake_post)
        MockClient.return_value = instance
        result = await client.query({"mpn": "X", "limit": 3, "country": "IN", "currency": "INR"})

    assert call_num == 1
    assert result == {}


@pytest.mark.asyncio
async def test_nexar_client_graphql_errors_on_200():
    client, mgr = _make_client()

    class RespWithErrors:
        status_code = 200
        headers = {}
        def json(self): return {"errors": [{"message": "some graphql error"}], "data": None}

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(return_value=RespWithErrors())
        MockClient.return_value = instance
        result = await client.query({"mpn": "X", "limit": 3, "country": "IN", "currency": "INR"})

    assert result == {}


@pytest.mark.asyncio
async def test_nexar_client_network_exception_all_retries():
    client, mgr = _make_client()

    with patch("sourceloop.connectors.nexar.httpx.AsyncClient") as MockClient:
        instance = AsyncMock()
        instance.__aenter__ = AsyncMock(return_value=instance)
        instance.__aexit__ = AsyncMock(return_value=False)
        instance.post = AsyncMock(side_effect=Exception("network error"))
        MockClient.return_value = instance
        with patch("asyncio.sleep", AsyncMock()):
            result = await client.query({"mpn": "X", "limit": 3, "country": "IN", "currency": "INR"})

    assert result == {}


# ─── NexarConnector mapping tests ────────────────────────────────────────────

NEXAR_FIXTURE_RESPONSE = {
    "supSearchMpn": {
        "hits": 1,
        "results": [
            {
                "part": {
                    "mpn": "STM32F103C8T6",
                    "manufacturer": {"name": "STMicroelectronics"},
                    "category": {"id": "123", "name": "MCU", "path": "IC/MCU"},
                    "shortDescription": "ARM Cortex-M3 MCU",
                    "specs": [
                        {"attribute": {"name": "Supply Voltage", "shortname": "volt"}, "displayValue": "3.3V"}
                    ],
                    "sellers": [
                        {
                            "company": {"id": "42", "name": "Mouser"},
                            "offers": [
                                {
                                    "sku": "STM32-SKU1",
                                    "inventoryLevel": 500,
                                    "moq": 1,
                                    "orderMultiple": 1,
                                    "packaging": "Cut Tape",
                                    "updated": "2026-01-01",
                                    "prices": [
                                        {"quantity": 1, "price": 120.0, "currency": "INR"},
                                        {"quantity": 10, "price": 100.0, "currency": "INR"},
                                    ],
                                    "clickUrl": "https://mouser.com/stm32"
                                },
                                {
                                    "sku": "STM32-SKU2",
                                    "inventoryLevel": 200,
                                    "moq": 10,
                                    "orderMultiple": 10,
                                    "packaging": "Reel",
                                    "updated": "2026-01-01",
                                    "prices": [
                                        {"quantity": 10, "price": 95.0, "currency": "INR"},
                                    ],
                                    "clickUrl": None,
                                },
                            ]
                        }
                    ]
                }
            }
        ]
    }
}


def _make_nexar_connector():
    """Create NexarConnector with mocked config to avoid env deps."""
    with patch("sourceloop.connectors.nexar.get_env") as mock_env, \
         patch("sourceloop.connectors.nexar.get_connectors_config") as mock_cfg:
        mock_env.return_value.nexar_client_id = "test_id"
        mock_env.return_value.nexar_client_secret = "test_secret"
        mock_env.return_value.nexar_token_url = "http://fake/token"
        mock_env.return_value.nexar_graphql_url = "http://fake/graphql"
        mock_env.return_value.nexar_country = "IN"
        mock_env.return_value.nexar_currency = "INR"
        mock_cfg.return_value.nexar.limit = 5
        mock_cfg.return_value.nexar.max_rps = 5
        mock_cfg.return_value.nexar.max_retries = 3
        mock_cfg.return_value.nexar.monthly_quota_soft_cap = 0
        from sourceloop.connectors.nexar import NexarConnector
        return NexarConnector()


def _make_line(mpn: str = "STM32F103C8T6"):
    from sourceloop.domain.bom import BomLine
    from sourceloop.domain.part import PartClass
    return BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn=mpn, manufacturer="ST", quantity=1.0, unit="pcs",
        normalized_part_key=f"mpn:{mpn}", part_class=PartClass.A,
        parse_confidence=0.9,
    )


def test_nexar_connector_maps_seller_x_offer():
    """One seller with 2 offers → 2 OfferObservation objects."""
    connector = _make_nexar_connector()
    line = _make_line()
    observations = connector._map_response(NEXAR_FIXTURE_RESPONSE, line)

    assert len(observations) == 2
    obs1, obs2 = observations

    assert obs1.normalized_part_key == "mpn:STM32F103C8T6"
    assert obs1.supplier_id == "nexar:42"
    assert obs1.tier == "A"
    assert obs1.source == "api"
    assert obs1.confidence is None
    assert obs1.lead_time is None
    assert obs1.price_ladder is not None
    assert obs1.price_ladder.rungs[0]["qty"] == 1
    assert obs1.price_ladder.rungs[1]["qty"] == 10


def test_nexar_connector_null_click_url_synthesized():
    """When clickUrl is None, a stable surrogate URL is synthesized."""
    connector = _make_nexar_connector()
    line = _make_line()
    observations = connector._map_response(NEXAR_FIXTURE_RESPONSE, line)
    assert len(observations) == 2
    # Both should succeed without error


def test_nexar_connector_zero_hits_returns_empty():
    connector = _make_nexar_connector()
    line = _make_line("UNKNOWN")
    result = connector._map_response({"supSearchMpn": {"hits": 0, "results": []}}, line)
    assert result == []


def test_nexar_connector_disabled_without_credentials():
    """Connector registers as disabled when credentials are missing."""
    with patch("sourceloop.connectors.nexar.get_env") as mock_env, \
         patch("sourceloop.connectors.nexar.get_connectors_config") as mock_cfg:
        mock_env.return_value.nexar_client_id = ""
        mock_env.return_value.nexar_client_secret = ""
        mock_env.return_value.nexar_country = "IN"
        mock_env.return_value.nexar_currency = "INR"
        mock_cfg.return_value.nexar.limit = 5
        mock_cfg.return_value.nexar.max_rps = 5
        mock_cfg.return_value.nexar.max_retries = 3
        mock_cfg.return_value.nexar.monthly_quota_soft_cap = 0
        from sourceloop.connectors.nexar import NexarConnector
        connector = NexarConnector()
        assert not connector.enabled


@pytest.mark.asyncio
async def test_nexar_connector_fetch_disabled_returns_empty():
    with patch("sourceloop.connectors.nexar.get_env") as mock_env, \
         patch("sourceloop.connectors.nexar.get_connectors_config") as mock_cfg:
        mock_env.return_value.nexar_client_id = ""
        mock_env.return_value.nexar_client_secret = ""
        mock_env.return_value.nexar_country = "IN"
        mock_env.return_value.nexar_currency = "INR"
        mock_cfg.return_value.nexar.limit = 5
        mock_cfg.return_value.nexar.max_rps = 5
        mock_cfg.return_value.nexar.max_retries = 3
        mock_cfg.return_value.nexar.monthly_quota_soft_cap = 0
        from sourceloop.connectors.nexar import NexarConnector
        connector = NexarConnector()

    line = _make_line()
    result = await connector.fetch(line)
    assert result == []


@pytest.mark.asyncio
async def test_nexar_connector_fetch_no_mpn_returns_empty():
    connector = _make_nexar_connector()
    from sourceloop.domain.bom import BomLine
    from sourceloop.domain.part import PartClass
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description="custom",
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="desc:abc", part_class=PartClass.B,
        parse_confidence=0.5,
    )
    result = await connector.fetch(line)
    assert result == []


def test_nexar_connector_supports_line_with_mpn():
    connector = _make_nexar_connector()
    line = _make_line("STM32F103C8T6")
    assert connector.supports(line) is True


def test_nexar_connector_not_supports_no_mpn():
    connector = _make_nexar_connector()
    from sourceloop.domain.bom import BomLine
    from sourceloop.domain.part import PartClass
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description="custom",
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="desc:abc", part_class=PartClass.B,
        parse_confidence=0.5,
    )
    assert not connector.supports(line)


def test_nexar_connector_specs_mapped():
    connector = _make_nexar_connector()
    line = _make_line()
    observations = connector._map_response(NEXAR_FIXTURE_RESPONSE, line)
    assert observations[0].specs.get("volt") == "3.3V"


def test_nexar_connector_category_from_response():
    connector = _make_nexar_connector()
    line = _make_line()
    observations = connector._map_response(NEXAR_FIXTURE_RESPONSE, line)
    assert observations[0].category == "MCU"


def test_nexar_connector_stock_mapped():
    connector = _make_nexar_connector()
    line = _make_line()
    observations = connector._map_response(NEXAR_FIXTURE_RESPONSE, line)
    assert observations[0].stock == 500
    assert observations[1].stock == 200


def test_nexar_connector_empty_data_returns_empty():
    connector = _make_nexar_connector()
    line = _make_line()
    assert connector._map_response({}, line) == []
