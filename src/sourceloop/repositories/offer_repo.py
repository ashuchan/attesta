from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.db.tables import CurrentOfferRow, ListingRow
from sourceloop.domain.offer import CurrentOffer, OfferObservation, PriceLadder

from .base import AbstractRepository


class OfferRepository(AbstractRepository[CurrentOffer]):
    """Global repository — NO tenant scoping. The shared cache IS the moat."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_current_offers(self, normalized_part_key: str) -> list[CurrentOffer]:
        result = await self._session.execute(
            select(CurrentOfferRow).where(
                CurrentOfferRow.normalized_part_key == normalized_part_key
            )
        )
        rows = result.scalars().all()
        return [self._current_row_to_domain(r) for r in rows]

    async def upsert_listing(
        self,
        listing_id: uuid.UUID,
        url: str,
        supplier_id: str,
        normalized_part_key: str,
        category: str | None,
        tier: str,
    ) -> uuid.UUID:
        """Upsert listing by url (UNIQUE). Returns listing_id."""
        now = datetime.now(UTC)
        stmt = pg_insert(ListingRow).values(
            listing_id=listing_id,
            url=url,
            supplier_id=supplier_id,
            normalized_part_key=normalized_part_key,
            category=category,
            first_seen=now,
            tier=tier,
        ).on_conflict_do_update(
            index_elements=["url"],
            set_={
                "category": category,
                "supplier_id": supplier_id,
            }
        ).returning(ListingRow.listing_id)
        result = await self._session.execute(stmt)
        row = result.fetchone()
        return row[0] if row else listing_id

    async def append_observation(self, obs: OfferObservation) -> None:
        """Append-only insert. Never updates an existing observation."""
        # Use raw SQL for partitioned table insert — SQLAlchemy ORM insert may not
        # route correctly to the right partition in all versions
        from sqlalchemy import text
        obs_id = uuid.uuid4()
        await self._session.execute(
            text("""
                INSERT INTO offer_observation
                  (obs_id, captured_at, listing_id, source, price_ladder, moq, lead_time,
                   stock, specs, supplier_snapshot, screenshot_ref, confidence, category, field_captured_at)
                VALUES
                  (:obs_id, :captured_at, :listing_id, :source, :price_ladder::jsonb, :moq, :lead_time,
                   :stock, :specs::jsonb, :supplier_snapshot::jsonb, :screenshot_ref, :confidence,
                   :category, :field_captured_at::jsonb)
            """),
            {
                "obs_id": str(obs_id),
                "captured_at": obs.captured_at,
                "listing_id": str(obs.listing_id),
                "source": obs.source,
                "price_ladder": self._ladder_to_json_str(obs.price_ladder),
                "moq": obs.moq,
                "lead_time": obs.lead_time,
                "stock": obs.stock,
                "specs": self._dict_to_json_str(obs.specs),
                "supplier_snapshot": self._dict_to_json_str(obs.supplier_snapshot),
                "screenshot_ref": obs.screenshot_ref,
                "confidence": obs.confidence,
                "category": obs.category,
                "field_captured_at": self._dict_to_json_str(obs.field_captured_at),
            }
        )
        # Upsert current_offer projection to point at this latest obs
        stmt = pg_insert(CurrentOfferRow).values(
            listing_id=obs.listing_id,
            latest_obs_id=obs_id,
            normalized_part_key=obs.normalized_part_key,
            supplier_id=obs.supplier_id,
            price_ladder=self._ladder_to_json(obs.price_ladder),
            moq=obs.moq,
            lead_time=obs.lead_time,
            stock=obs.stock,
            specs=obs.specs,
            confidence=obs.confidence,
            field_captured_at=obs.field_captured_at,
        ).on_conflict_do_update(
            index_elements=["listing_id"],
            set_={
                "latest_obs_id": obs_id,
                "price_ladder": self._ladder_to_json(obs.price_ladder),
                "moq": obs.moq,
                "lead_time": obs.lead_time,
                "stock": obs.stock,
                "specs": obs.specs,
                "confidence": obs.confidence,
                "field_captured_at": obs.field_captured_at,
            }
        )
        await self._session.execute(stmt)

    def _ladder_to_json(self, ladder: PriceLadder | None) -> dict[str, Any] | None:
        if ladder is None:
            return None
        return {"rungs": ladder.rungs}

    def _ladder_to_json_str(self, ladder: PriceLadder | None) -> str:
        import json
        if ladder is None:
            return "null"
        return json.dumps({"rungs": ladder.rungs})

    def _dict_to_json_str(self, d: dict[str, Any] | None) -> str:
        import json
        if d is None:
            return "null"
        return json.dumps(d)

    def _current_row_to_domain(self, row: CurrentOfferRow) -> CurrentOffer:
        ladder = None
        if row.price_ladder:
            ladder = PriceLadder(rungs=row.price_ladder.get("rungs", []))
        return CurrentOffer(
            listing_id=row.listing_id,
            latest_obs_id=row.latest_obs_id,
            normalized_part_key=row.normalized_part_key,
            supplier_id=row.supplier_id,
            price_ladder=ladder,
            moq=row.moq,
            lead_time=row.lead_time,
            stock=row.stock,
            specs=row.specs or {},
            confidence=row.confidence,
            field_captured_at=row.field_captured_at or {},
        )
