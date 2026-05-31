from __future__ import annotations

import asyncio
import dataclasses
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from sourceloop.cache.store import OfferStore
from sourceloop.classification.chain import ClassifierChain
from sourceloop.connectors.registry import ConnectorRegistry
from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import CurrentOffer
from sourceloop.domain.part import PartClass
from sourceloop.domain.plan import SourcedPlan
from sourceloop.plan.assembler import PlanAssembler
from sourceloop.repositories.bom_repo import BomRepository
from sourceloop.repositories.demand_repo import DemandRepository
from sourceloop.repositories.plan_repo import PlanRepository
from sourceloop.tenancy.context import TenantContext

log = structlog.get_logger()

# Concurrency bound for Tier-A fetches (keyed to nexar.max_rps from config)
_DEFAULT_CONCURRENCY = 8


class SourcingService:
    """
    Orchestrates: classify → cache-or-fetch → demand event → assemble plan.

    Key design points:
    - In-run MPN dedup: group by normalized_part_key, fetch once, map to all N lines.
    - Bounded asyncio.gather (semaphore) for concurrent Tier-A fetches.
    - Per-line failure isolation: one bad Nexar call never aborts the BOM run.
    - Transaction boundaries: each OfferStore.append commits independently;
      sourced_plan + all plan_lines commit in one transaction at end.
    - Re-sourcing same bom_id replaces the plan (idempotent via PlanRepository.upsert_plan).
    """

    def __init__(
        self,
        session: AsyncSession,
        registry: ConnectorRegistry | None = None,
        classifier: ClassifierChain | None = None,
        max_concurrency: int = _DEFAULT_CONCURRENCY,
        confidence_provider: object | None = None,
    ) -> None:
        self._session = session
        self._registry = registry or ConnectorRegistry()
        self._classifier = classifier or ClassifierChain()
        # confidence_provider is injected; defaults to EngineConfidenceProvider lazily
        # so unit tests that don't need scoring can pass None or a stub without touching disk.
        if confidence_provider is None:
            from sourceloop.scoring.factory import build_confidence_provider as _build
            confidence_provider = _build()
        self._store = OfferStore(session, confidence_provider=confidence_provider)  # type: ignore[arg-type]
        self._bom_repo = BomRepository(session)
        self._plan_repo = PlanRepository(session)
        self._demand_repo = DemandRepository(session)
        self._assembler = PlanAssembler()
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def source_bom(self, bom_id: uuid.UUID) -> SourcedPlan:
        tenant_id = TenantContext.get()
        log.info("sourcing_start", bom_id=str(bom_id), tenant_id=str(tenant_id))

        await self._bom_repo.update_status(bom_id, "sourced")

        # Load lines
        lines = await self._bom_repo.get_lines(bom_id)

        # Step 1: Classify all lines
        classified_lines = self._classify_lines(lines)

        # Step 2: Group Tier-A lines by normalized_part_key (in-run dedup)
        tier_a_lines = [line for line in classified_lines if line.part_class == PartClass.A]
        key_to_lines: dict[str, list[BomLine]] = {}
        for line in tier_a_lines:
            key_to_lines.setdefault(line.normalized_part_key, []).append(line)

        unique_keys = list(key_to_lines.keys())
        log.info("tier_a_dedup", unique_keys=len(unique_keys), total_lines=len(tier_a_lines))

        # Step 3: Fetch offers for each unique key (bounded concurrency)
        key_offers: dict[str, list[CurrentOffer]] = {}
        await asyncio.gather(
            *[self._fetch_key(key, key_to_lines[key][0], key_offers) for key in unique_keys]
        )

        # Step 4: Emit demand events (per line, not per key)
        for line in classified_lines:
            try:
                await self._demand_repo.emit(
                    normalized_part_key=line.normalized_part_key,
                    category=None,  # category comes from offer; line doesn't carry it yet
                )
            except Exception as e:
                log.warning("demand_event_failed", error=str(e), part_key=line.normalized_part_key)

        # Step 5: Assemble plan — map offers back to all lines sharing each key
        line_offers: list[tuple[BomLine, list[CurrentOffer]]] = []
        for line in classified_lines:
            if line.part_class == PartClass.A:
                offers = key_offers.get(line.normalized_part_key, [])
                line_offers.append((line, offers))
            else:
                line_offers.append((line, []))

        plan = self._assembler.assemble(bom_id, tenant_id, line_offers)

        # Step 6: Persist plan in one transaction
        await self._plan_repo.upsert_plan(plan)
        await self._session.commit()

        log.info(
            "sourcing_complete",
            bom_id=str(bom_id),
            tier_a_coverage_pct=plan.tier_a_coverage_pct,
            total_lines=len(classified_lines),
        )
        return plan

    def _classify_lines(self, lines: list[BomLine]) -> list[BomLine]:
        result = []
        for line in lines:
            part_class, signals = self._classifier.classify(line)
            classified = dataclasses.replace(line, part_class=part_class)
            result.append(classified)
        return result

    async def _fetch_key(
        self,
        part_key: str,
        representative_line: BomLine,
        key_offers: dict[str, list[CurrentOffer]],
    ) -> None:
        """Fetch (or cache-hit) for one unique part key. Per-line failure isolated."""
        async with self._semaphore:
            try:
                # Check cache first
                current_offers = await self._store.get_current(part_key)
                if current_offers and not any(
                    self._store.needs_refresh(o, tier="A", field="price_ladder")
                    for o in current_offers
                ):
                    log.info("cache_hit", part_key=part_key)
                    key_offers[part_key] = current_offers
                    return

                # Cache miss or stale → fetch from connectors
                connectors = self._registry.connectors_for(representative_line)
                all_observations = []
                for connector in connectors:
                    try:
                        observations = await connector.fetch(representative_line)
                        all_observations.extend(observations)
                        if observations:
                            break  # First connector with results wins
                    except Exception as e:
                        log.warning(
                            "connector_fetch_failed",
                            connector=connector.key,
                            part_key=part_key,
                            error=str(e),
                        )

                # Append each observation independently (global cache accrues even on partial failure)
                for obs in all_observations:
                    try:
                        await self._store.append(obs)
                    except Exception as e:
                        log.warning("offer_append_failed", part_key=part_key, error=str(e))

                if all_observations:
                    # Re-read fresh current_offers
                    key_offers[part_key] = await self._store.get_current(part_key)
                else:
                    key_offers[part_key] = []

            except Exception as e:
                log.error("fetch_key_failed", part_key=part_key, error=str(e))
                key_offers[part_key] = []
