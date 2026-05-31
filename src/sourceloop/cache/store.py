from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.cache.confidence import ConfidenceProvider, EngineConfidenceProvider, NullConfidence
from sourceloop.cache.refresh import needs_refresh
from sourceloop.domain.offer import CurrentOffer, OfferObservation
from sourceloop.domain.supplier import Supplier
from sourceloop.repositories.offer_repo import OfferRepository
from sourceloop.repositories.score_log_repo import ScoreLogRepository
from sourceloop.repositories.supplier_repo import SupplierRepository

log = structlog.get_logger()


@dataclass
class AppendResult:
    listings_touched: int = 0
    observations_appended: int = 0
    cache_hits_skipped: int = 0


class OfferStore:
    """
    Global offer cache. Append-on-refresh, never overwrite.
    - get_current: hot-path read from current_offer (with freshness-decayed confidence_effective)
    - needs_refresh: per-(field,tier) TTL check
    - append / append_many: INSERT offer_observation + UPSERT current_offer + write score_log
    """

    def __init__(
        self,
        session: AsyncSession,
        confidence_provider: ConfidenceProvider | None = None,
    ) -> None:
        self._offer_repo = OfferRepository(session)
        self._supplier_repo = SupplierRepository(session)
        self._score_log_repo = ScoreLogRepository(session)
        self._confidence = confidence_provider or NullConfidence()
        self._session = session

    async def get_current(self, normalized_part_key: str) -> list[CurrentOffer]:
        """Return current offers, with confidence_effective computed at read-time."""
        offers = await self._offer_repo.get_current_offers(normalized_part_key)
        if isinstance(self._confidence, EngineConfidenceProvider):
            result = []
            for offer in offers:
                eff = self._confidence.score_effective(offer)
                result.append(dataclasses.replace(offer, confidence_effective=eff))
            return result
        return offers

    def needs_refresh(self, offer: CurrentOffer, tier: str = "A", field: str = "price_ladder") -> bool:
        return needs_refresh(offer, tier=tier, field=field)

    async def append(self, observation: OfferObservation) -> None:
        """Thin wrapper — delegates to append_many for a single observation."""
        await self.append_many([observation])

    async def append_many(self, observations: list[OfferObservation]) -> AppendResult:
        """
        Batch-append observations.
        Groups by URL (supplier × part key × listing_id), processes each group in a savepoint.
        Scores confidence at write-time and writes provenance to score_log.
        """
        result = AppendResult()

        for obs in observations:
            url = self._compute_url(obs)
            sp = None
            try:
                sp = await self._session.begin_nested()

                # Upsert supplier
                supplier = self._make_supplier(obs)
                await self._supplier_repo.upsert(supplier)

                # Upsert listing — get actual listing_id (may differ if URL already existed)
                actual_listing_id = await self._offer_repo.upsert_listing(
                    listing_id=obs.listing_id,
                    url=url,
                    supplier_id=obs.supplier_id,
                    normalized_part_key=obs.normalized_part_key,
                    category=obs.category,
                    tier=obs.tier,
                )

                # Score confidence at write-time; capture full result once for both
                # the stored confidence value and the score_log provenance write.
                score_result_obj = (
                    self._confidence.score_result(obs)
                    if isinstance(self._confidence, EngineConfidenceProvider)
                    else None
                )
                confidence_val = float(score_result_obj.score) if score_result_obj is not None else self._confidence.score(obs)  # type: ignore[attr-defined]
                scored_obs = dataclasses.replace(obs, listing_id=actual_listing_id, confidence=confidence_val)

                # Append observation
                obs_id = await self._offer_repo.append_observation_for_listing(scored_obs, actual_listing_id)
                result.observations_appended += 1
                result.listings_touched += 1

                # Write score provenance if engine provider (duck-typed — not in Protocol)
                if isinstance(self._confidence, EngineConfidenceProvider):
                    score_result = score_result_obj
                    if score_result is not None:
                        try:
                            await self._score_log_repo.write(
                                listing_id=actual_listing_id,
                                captured_at=obs.captured_at,
                                strategy=score_result.strategy,  # type: ignore[attr-defined]
                                score=score_result.score,  # type: ignore[attr-defined]
                                band=score_result.band,  # type: ignore[attr-defined]
                                signals_json=score_result.to_provenance_json(),  # type: ignore[attr-defined]
                            )
                        except Exception as e:
                            log.warning("score_log_write_failed", error=str(e))

                await sp.commit()

                log.info(
                    "offer_appended",
                    part_key=obs.normalized_part_key,
                    supplier_id=obs.supplier_id,
                    tier=obs.tier,
                    confidence=confidence_val,
                )

            except Exception as e:
                if sp is not None:
                    await sp.rollback()
                log.warning("append_observation_failed", url=url, error=str(e))

        return result

    @staticmethod
    def _compute_url(obs: OfferObservation) -> str:
        return f"nexar:{obs.supplier_id}:{obs.normalized_part_key}:{obs.listing_id}"

    @staticmethod
    def _make_supplier(obs: OfferObservation) -> Supplier:
        now = datetime.now(UTC)
        snap = obs.supplier_snapshot or {}
        return Supplier(
            supplier_id=obs.supplier_id,
            name=snap.get("company_name", obs.supplier_id),
            region=snap.get("region"),
            years_active=None,
            trade_assurance=None,
            verified_factory=None,
            response_rate=None,
            repurchase_rate=None,
            reliability_score=None,
            blacklisted=False,
            updated_at=now,
        )
