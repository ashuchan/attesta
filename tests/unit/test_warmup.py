"""Unit tests for WarmupService."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sourceloop.domain.offer import OfferObservation, PriceLadder
from sourceloop.parsing.part_key import build_part_key


def _make_obs(part_key: str = "mpn:TEST") -> OfferObservation:
    now = datetime.now(UTC)
    return OfferObservation(
        listing_id=uuid.uuid4(),
        source="api",
        tier="A",
        captured_at=now,
        normalized_part_key=part_key,
        supplier_id="nexar:1",
        category="MCU",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1,
        lead_time=None,
        stock=100,
        specs={},
        supplier_snapshot={"company_name": "Test"},
        screenshot_ref=None,
        confidence=None,
        field_captured_at={
            "price_ladder": now.isoformat(),
            "stock": now.isoformat(),
            "moq": now.isoformat(),
        },
    )


class TestBuildPartKey:
    def test_mpn_normalized(self):
        assert build_part_key("STM32F103C8T6") == "mpn:STM32F103C8T6"

    def test_mpn_with_separators(self):
        assert build_part_key("STM32F103-C8T6") == "mpn:STM32F103C8T6"

    def test_empty_mpn_fallback(self):
        key = build_part_key("", manufacturer="Murata")
        assert key.startswith("desc:")


@pytest.mark.asyncio
async def test_warmup_service_calls_connector():
    """WarmupService fetches via fetch_mpn (not fetch)."""
    from sourceloop.warmup.service import WarmupService

    obs = _make_obs()

    mock_connector = MagicMock()
    mock_connector.key = "mock"
    mock_connector.fetch_mpn = AsyncMock(return_value=[obs])
    mock_connector.enabled = True

    mock_registry = MagicMock()
    mock_registry.connectors_for_mpn.return_value = [mock_connector]

    mock_session = MagicMock()

    with patch("sourceloop.warmup.service.OfferStore") as MockStore:
        store_instance = MagicMock()
        store_instance.get_current = AsyncMock(return_value=[])  # cache miss
        store_instance.needs_refresh = MagicMock(return_value=True)
        append_result = MagicMock()
        append_result.observations_appended = 1
        store_instance.append_many = AsyncMock(return_value=append_result)
        MockStore.return_value = store_instance

        service = WarmupService(mock_session, registry=mock_registry)
        results = await service.warm_parts([
            {"mpn": "STM32F103C8T6", "manufacturer": "STMicroelectronics", "category": "MCU"}
        ])

    assert results.get("STM32F103C8T6") == 1
    mock_connector.fetch_mpn.assert_called_once()


@pytest.mark.asyncio
async def test_warmup_skips_fresh_cache():
    """WarmupService skips fetch when cache is fresh."""
    from sourceloop.warmup.service import WarmupService

    mock_registry = MagicMock()
    mock_session = MagicMock()
    fresh_offer = MagicMock()

    with patch("sourceloop.warmup.service.OfferStore") as MockStore:
        store_instance = MagicMock()
        store_instance.get_current = AsyncMock(return_value=[fresh_offer])
        store_instance.needs_refresh = MagicMock(return_value=False)  # fresh!
        MockStore.return_value = store_instance

        service = WarmupService(mock_session, registry=mock_registry)
        results = await service.warm_parts([{"mpn": "STM32F103C8T6"}])

    assert results.get("STM32F103C8T6") == 0
    mock_registry.connectors_for_mpn.assert_not_called()
