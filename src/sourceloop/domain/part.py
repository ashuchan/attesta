from __future__ import annotations

from enum import StrEnum


class PartClass(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class UnsourcedReason(StrEnum):
    NO_TIER_A_OFFERS = "no_tier_a_offers"
    TIER_B_NOT_IN_STEP1 = "tier_b_not_in_step1"
    TIER_A_FETCH_FAILED = "tier_a_fetch_failed"
    UNPARSEABLE_LINE = "unparseable_line"
