from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sourceloop.cache.confidence import NullConfidence
from sourceloop.cache.refresh import needs_refresh
from sourceloop.domain.offer import CurrentOffer, PriceLadder


def make_offer(field_captured_at: dict[str, str]) -> CurrentOffer:
    return CurrentOffer(
        listing_id=uuid.uuid4(),
        latest_obs_id=uuid.uuid4(),
        normalized_part_key="mpn:STM32F103C8T6",
        supplier_id="nexar:123",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1,
        lead_time=None,
        stock=100,
        specs={},
        confidence=None,
        field_captured_at=field_captured_at,
    )


def test_tier_a_price_not_stale_within_5_days():
    """A Tier-A price captured 1 day ago should NOT need refresh (TTL=5d)."""
    recent = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    offer = make_offer({"price_ladder": recent})
    assert not needs_refresh(offer, tier="A", field="price_ladder")


def test_tier_a_price_stale_after_5_days():
    """A Tier-A price captured 6 days ago SHOULD need refresh (TTL=5d)."""
    old = (datetime.now(UTC) - timedelta(days=6)).isoformat()
    offer = make_offer({"price_ladder": old})
    assert needs_refresh(offer, tier="A", field="price_ladder")


def test_tier_a_specs_not_stale_within_75_days():
    """Tier-A specs TTL=75d. 10-day-old specs should not trigger refresh."""
    recent = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    offer = make_offer({"specs": recent, "price_ladder": recent})
    assert not needs_refresh(offer, tier="A", field="specs")


def test_tier_a_no_timestamp_forces_refresh():
    """Missing field_captured_at for the requested field → always refresh."""
    offer = make_offer({})
    assert needs_refresh(offer, tier="A", field="price_ladder")


def test_tier_b_price_uses_48h_ttl():
    """Tier-B has 48h TTL for price_ladder — must not affect Tier-A."""
    # 60h old — would be stale under Tier-B, but we pass tier="B" explicitly
    old = (datetime.now(UTC) - timedelta(hours=60)).isoformat()
    offer = make_offer({"price_ladder": old})
    # Tier-B: stale
    assert needs_refresh(offer, tier="B", field="price_ladder")
    # Tier-A: NOT stale (60h < 5d=120h)
    assert not needs_refresh(offer, tier="A", field="price_ladder")


def test_null_confidence_returns_none():
    from sourceloop.domain.offer import OfferObservation
    provider = NullConfidence()
    obs = OfferObservation(
        listing_id=uuid.uuid4(), source="api", tier="A",
        captured_at=datetime.now(UTC),
        normalized_part_key="mpn:X", supplier_id="nexar:1",
        category=None, price_ladder=None, moq=None, lead_time=None,
        stock=None, specs={}, supplier_snapshot={}, screenshot_ref=None,
        confidence=None, field_captured_at={},
    )
    assert provider.score(obs) is None
