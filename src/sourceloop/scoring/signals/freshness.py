"""Freshness signal: decays to 0 as the most-volatile field passes its TTL."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sourceloop.scoring.signal import Scorable, SignalValue, ScoringContext

_REQUIRED_FIELDS = ["price_ladder", "moq", "stock"]


class FreshnessSignal:
    key = "freshness"
    depends_on: list[str] = []
    enabled = True

    def compute(self, subject: Scorable, ctx: ScoringContext) -> SignalValue:
        now = ctx.now
        policies = ctx.refresh_policies
        tier = getattr(subject, "tier", "A")
        tier_policies: dict = getattr(policies, tier, {}) or {}

        fractions: list[float] = []
        field_details: dict[str, float] = {}

        for field in _REQUIRED_FIELDS:
            field_ts_str = subject.field_captured_at.get(field)
            if not field_ts_str:
                fractions.append(0.0)
                field_details[field] = 0.0
                continue

            try:
                captured_at = datetime.fromisoformat(field_ts_str)
            except ValueError:
                fractions.append(0.0)
                field_details[field] = 0.0
                continue

            if captured_at.tzinfo is None:
                captured_at = captured_at.replace(tzinfo=UTC)

            # tier_policies may be a Pydantic dict or a class with attr access
            if hasattr(tier_policies, "get"):
                field_policy = tier_policies.get(field)
            else:
                field_policy = getattr(tier_policies, field, None)
            if not field_policy:
                # No policy → assume always fresh
                fractions.append(1.0)
                field_details[field] = 1.0
                continue

            ttl: timedelta | None = None
            if field_policy.ttl_days:
                ttl = timedelta(days=field_policy.ttl_days)
            elif field_policy.ttl_hours:
                ttl = timedelta(hours=field_policy.ttl_hours)

            if ttl is None:
                fractions.append(1.0)
                field_details[field] = 1.0
                continue

            age = now - captured_at
            if age.total_seconds() <= 0:
                frac = 1.0
            elif age >= ttl:
                frac = 0.0
            else:
                frac = 1.0 - (age.total_seconds() / ttl.total_seconds())

            fractions.append(frac)
            field_details[field] = frac

        min_frac = min(fractions) if fractions else 0.0
        return SignalValue(
            normalized=min_frac,
            raw=None,
            provenance={"fields": field_details, "min": min_frac},
        )
