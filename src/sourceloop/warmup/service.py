"""WarmupService — pre-warms the global offer cache for seed parts."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.cache.store import AppendResult, OfferStore
from sourceloop.connectors.registry import ConnectorRegistry
from sourceloop.parsing.part_key import build_part_key

log = structlog.get_logger()


class WarmupService:
    """
    Pre-warms the cache for a list of (mpn, manufacturer, category) tuples.

    Design:
    - Tier-agnostic: uses ConnectorRegistry.connectors_for_mpn → fetch_mpn.
    - Adding a Tier-B connector in Step 4 adds results here with zero code change.
    - Bounded concurrency (semaphore).
    - Per-part failure isolation.
    """

    def __init__(
        self,
        session: AsyncSession,
        registry: ConnectorRegistry | None = None,
        max_concurrency: int = 4,
    ) -> None:
        self._store = OfferStore(session)
        self._registry = registry or ConnectorRegistry()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def warm_parts(
        self, parts: list[dict]  # [{mpn, manufacturer?, category?}]
    ) -> dict[str, int]:
        """
        Warm cache for each part.
        Returns {mpn: observations_appended}.
        """
        results: dict[str, int] = {}
        tasks = [self._warm_one(p, results) for p in parts]
        await asyncio.gather(*tasks)
        return results

    async def _warm_one(self, part: dict, results: dict[str, int]) -> None:
        mpn: str = part.get("mpn", "")
        manufacturer: str | None = part.get("manufacturer")
        category: str | None = part.get("category")

        if not mpn:
            return

        normalized_part_key = build_part_key(mpn=mpn, manufacturer=manufacturer)

        async with self._semaphore:
            try:
                # Check cache first — skip if fresh
                current_offers = await self._store.get_current(normalized_part_key)
                if current_offers and not any(
                    self._store.needs_refresh(o, tier="A", field="price_ladder")
                    for o in current_offers
                ):
                    log.info("warmup_cache_hit", mpn=mpn, part_key=normalized_part_key)
                    results[mpn] = 0
                    return

                connectors = self._registry.connectors_for_mpn(mpn)
                all_obs = []
                for connector in connectors:
                    try:
                        obs = await connector.fetch_mpn(
                            mpn=mpn,
                            manufacturer=manufacturer,
                            normalized_part_key=normalized_part_key,
                            category=category,
                        )
                        all_obs.extend(obs)
                        if obs:
                            break  # First connector with results wins
                    except Exception as e:
                        log.warning(
                            "warmup_connector_failed",
                            connector=connector.key,
                            mpn=mpn,
                            error=str(e),
                        )

                if all_obs:
                    append_result: AppendResult = await self._store.append_many(all_obs)
                    results[mpn] = append_result.observations_appended
                    log.info(
                        "warmup_part_done",
                        mpn=mpn,
                        observations=append_result.observations_appended,
                    )
                else:
                    results[mpn] = 0
                    log.info("warmup_no_offers", mpn=mpn)

            except Exception as e:
                log.error("warmup_part_failed", mpn=mpn, error=str(e))
                results[mpn] = 0

    async def dry_run_parts(self, parts: list[dict]) -> tuple[int, int]:
        """
        Dry-run: check cache + TTL for each part without fetching.
        Returns (would_fetch_count, already_warm_count). Zero quota spent.
        """
        would_fetch = 0
        already_warm = 0
        for part in parts:
            mpn: str = part.get("mpn", "")
            manufacturer: str | None = part.get("manufacturer")
            if not mpn:
                continue
            normalized_part_key = build_part_key(mpn=mpn, manufacturer=manufacturer)
            current_offers = await self._store.get_current(normalized_part_key)
            if current_offers and not any(
                self._store.needs_refresh(o, tier="A", field="price_ladder")
                for o in current_offers
            ):
                already_warm += 1
            else:
                would_fetch += 1
        return would_fetch, already_warm
