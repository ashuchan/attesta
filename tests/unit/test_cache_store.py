from __future__ import annotations
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from sourceloop.cache.store import OfferStore
from sourceloop.domain.offer import CurrentOffer, OfferObservation, PriceLadder


def make_current_offer(part_key: str = "mpn:STM32F103C8T6", fresh: bool = True) -> CurrentOffer:
    from datetime import timedelta
    if fresh:
        ts = datetime.now(timezone.utc).isoformat()
    else:
        ts = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
    return CurrentOffer(
        listing_id=uuid.uuid4(), latest_obs_id=uuid.uuid4(),
        normalized_part_key=part_key, supplier_id="nexar:1",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1, lead_time=None, stock=100, specs={}, confidence=None,
        field_captured_at={"price_ladder": ts},
    )


def make_observation(part_key: str = "mpn:STM32F103C8T6") -> OfferObservation:
    return OfferObservation(
        listing_id=uuid.uuid4(), source="api", tier="A",
        captured_at=datetime.now(timezone.utc),
        normalized_part_key=part_key, supplier_id="nexar:1",
        category="MCU",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1, lead_time=None, stock=500, specs={"volt": "3.3V"},
        supplier_snapshot={"company_id": "1", "company_name": "MockDist"},
        screenshot_ref=None, confidence=None,
        field_captured_at={"price_ladder": datetime.now(timezone.utc).isoformat()},
    )


@pytest.mark.asyncio
async def test_get_current_delegates_to_repo():
    session = MagicMock()
    store = OfferStore(session)
    mock_offers = [make_current_offer()]
    store._offer_repo.get_current_offers = AsyncMock(return_value=mock_offers)
    result = await store.get_current("mpn:STM32F103C8T6")
    assert result == mock_offers
    store._offer_repo.get_current_offers.assert_called_once_with("mpn:STM32F103C8T6")


def test_needs_refresh_fresh_offer_returns_false():
    session = MagicMock()
    store = OfferStore(session)
    fresh_offer = make_current_offer(fresh=True)
    assert not store.needs_refresh(fresh_offer, tier="A", field="price_ladder")


def test_needs_refresh_stale_offer_returns_true():
    session = MagicMock()
    store = OfferStore(session)
    stale_offer = make_current_offer(fresh=False)
    assert store.needs_refresh(stale_offer, tier="A", field="price_ladder")


@pytest.mark.asyncio
async def test_append_upserts_supplier_and_calls_repo():
    session = MagicMock()
    store = OfferStore(session)
    store._supplier_repo.upsert = AsyncMock()
    store._offer_repo.upsert_listing = AsyncMock(return_value=uuid.uuid4())
    store._offer_repo.append_observation = AsyncMock()

    obs = make_observation()
    await store.append(obs)

    store._supplier_repo.upsert.assert_called_once()
    store._offer_repo.upsert_listing.assert_called_once()
    store._offer_repo.append_observation.assert_called_once_with(obs)


@pytest.mark.asyncio
async def test_append_is_never_update():
    """append_observation must be called (insert), never update methods."""
    session = MagicMock()
    store = OfferStore(session)
    store._supplier_repo.upsert = AsyncMock()
    store._offer_repo.upsert_listing = AsyncMock(return_value=uuid.uuid4())
    store._offer_repo.append_observation = AsyncMock()

    obs1 = make_observation()
    obs2 = make_observation()

    await store.append(obs1)
    await store.append(obs2)

    # Both observations appended — never "update"
    assert store._offer_repo.append_observation.call_count == 2


@pytest.mark.asyncio
async def test_append_supplier_uses_snapshot_name():
    """Supplier name is taken from supplier_snapshot, not supplier_id."""
    session = MagicMock()
    store = OfferStore(session)
    store._supplier_repo.upsert = AsyncMock()
    store._offer_repo.upsert_listing = AsyncMock(return_value=uuid.uuid4())
    store._offer_repo.append_observation = AsyncMock()

    obs = make_observation()
    await store.append(obs)

    supplier_arg = store._supplier_repo.upsert.call_args[0][0]
    assert supplier_arg.name == "MockDist"
    assert supplier_arg.supplier_id == "nexar:1"
    assert supplier_arg.blacklisted is False
