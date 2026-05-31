from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sourceloop.config.loader import get_refresh_policies
from sourceloop.domain.offer import CurrentOffer


def needs_refresh(offer: CurrentOffer, tier: str = "A", field: str = "price_ladder") -> bool:
    """
    Check if a CurrentOffer needs refreshing based on per-(tier, field) TTL policy.

    For Tier-A the binding field is price_ladder (5 days LAZY).
    Policy lookup is keyed on (tier, field) — not field alone — so Tier-B's 48h
    VOLATILE policy never applies to Tier-A offers.
    """
    policies = get_refresh_policies()
    tier_policies = getattr(policies, tier, None)
    if tier_policies is None:
        return True  # unknown tier → refresh

    field_policy = tier_policies.get(field)
    if field_policy is None:
        return True  # unknown field → refresh

    # Determine TTL in seconds
    if field_policy.ttl_days is not None:
        ttl = timedelta(days=field_policy.ttl_days)
    elif field_policy.ttl_hours is not None:
        ttl = timedelta(hours=field_policy.ttl_hours)
    else:
        return True

    # Look up field_captured_at for this specific field
    captured_at_str = offer.field_captured_at.get(field)
    if not captured_at_str:
        return True  # no timestamp → refresh

    try:
        captured_at = datetime.fromisoformat(captured_at_str)
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
    except ValueError:
        return True

    age = datetime.now(UTC) - captured_at
    return age > ttl
