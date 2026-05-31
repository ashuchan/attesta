from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.cache.confidence import ConfidenceProvider, NullConfidence
from sourceloop.cache.refresh import needs_refresh
from sourceloop.domain.offer import CurrentOffer, OfferObservation
from sourceloop.domain.supplier import Supplier
from sourceloop.repositories.offer_repo import OfferRepository
from sourceloop.repositories.supplier_repo import SupplierRepository

log = structlog.get_logger()


class OfferStore:
    """
    Global offer cache. Append-on-refresh, never overwrite.
    - get_current: hot-path read from current_offer
    - needs_refresh: per-(field,tier) TTL check
    - append: INSERT offer_observation + UPSERT current_offer projection
    """

    def __init__(
        self,
        session: AsyncSession,
        confidence_provider: ConfidenceProvider | None = None,
    ) -> None:
        self._offer_repo = OfferRepository(session)
        self._supplier_repo = SupplierRepository(session)
        self._confidence = confidence_provider or NullConfidence()

    async def get_current(self, normalized_part_key: str) -> list[CurrentOffer]:
        return await self._offer_repo.get_current_offers(normalized_part_key)

    def needs_refresh(self, offer: CurrentOffer, tier: str = "A", field: str = "price_ladder") -> bool:
        return needs_refresh(offer, tier=tier, field=field)

    async def append(self, observation: OfferObservation) -> None:
        """
        Append a new offer_observation (NEVER update existing).
        Advance current_offer projection to point at this newest obs.
        Also upsert the Supplier record.
        """
        # Upsert supplier first (global table)
        now = datetime.now(UTC)
        supplier = Supplier(
            supplier_id=observation.supplier_id,
            name=observation.supplier_snapshot.get("company_name", observation.supplier_id),
            region=observation.supplier_snapshot.get("region"),
            years_active=None,
            trade_assurance=None,
            verified_factory=None,
            response_rate=None,
            repurchase_rate=None,
            reliability_score=None,
            blacklisted=False,
            updated_at=now,
        )
        await self._supplier_repo.upsert(supplier)

        # Upsert listing
        await self._offer_repo.upsert_listing(
            listing_id=observation.listing_id,
            url=f"nexar:{observation.supplier_id}:{observation.normalized_part_key}:{observation.listing_id}",
            supplier_id=observation.supplier_id,
            normalized_part_key=observation.normalized_part_key,
            category=observation.category,
            tier=observation.tier,
        )

        # Append observation (never update)
        await self._offer_repo.append_observation(observation)

        log.info(
            "offer_appended",
            part_key=observation.normalized_part_key,
            supplier_id=observation.supplier_id,
            tier=observation.tier,
        )
