from __future__ import annotations
import pytest
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from sourceloop.sourcing.tier_a_service import SourcingService
from sourceloop.tenancy.context import TenantContext
from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import CurrentOffer, OfferObservation, PriceLadder
from sourceloop.domain.part import PartClass, UnsourcedReason


def setup_tenant() -> uuid.UUID:
    tid = uuid.uuid4()
    TenantContext.set(tid)
    return tid


def make_bom_line(
    mpn: str = "STM32F103C8T6",
    part_class: PartClass = PartClass.A,
    part_key: str | None = None,
    tenant_id: uuid.UUID | None = None,
    bom_id: uuid.UUID | None = None,
) -> BomLine:
    return BomLine(
        id=uuid.uuid4(),
        tenant_id=tenant_id or uuid.uuid4(),
        bom_id=bom_id or uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn=mpn, manufacturer="ST", quantity=1.0, unit="pcs",
        normalized_part_key=part_key or f"mpn:{mpn}",
        part_class=part_class, parse_confidence=0.9,
    )


def make_current_offer(part_key: str = "mpn:STM32F103C8T6") -> CurrentOffer:
    return CurrentOffer(
        listing_id=uuid.uuid4(), latest_obs_id=uuid.uuid4(),
        normalized_part_key=part_key, supplier_id="nexar:1",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1, lead_time=None, stock=100, specs={}, confidence=None,
        field_captured_at={"price_ladder": datetime.now(timezone.utc).isoformat()},
    )


def make_mock_session() -> MagicMock:
    session = MagicMock()
    session.commit = AsyncMock()
    return session


def _make_service_with_mocked_registry(session, use_mock_connector=True):
    """Create SourcingService with all repos mocked out."""
    from sourceloop.connectors.mock import MockConnector

    mock_registry = MagicMock()
    if use_mock_connector:
        connector = MockConnector()
        connector.enabled = True
        mock_registry.connectors_for = MagicMock(return_value=[connector])
    else:
        mock_registry.connectors_for = MagicMock(return_value=[])

    from sourceloop.classification.chain import ClassifierChain
    service = SourcingService(session, registry=mock_registry)
    return service


@pytest.mark.asyncio
async def test_sourcing_service_cache_hit_no_connector_call():
    """Cache hit within TTL → connector fetch is never called."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)
    fresh_offer = make_current_offer("mpn:STM32F103C8T6")

    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[
        make_bom_line("STM32F103C8T6", PartClass.A, tenant_id=tid, bom_id=bom_id)
    ])
    service._store.get_current = AsyncMock(return_value=[fresh_offer])
    service._store.needs_refresh = MagicMock(return_value=False)
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()

    mock_connector = MagicMock()
    mock_connector.supports = MagicMock(return_value=True)
    mock_connector.fetch = AsyncMock(return_value=[])
    service._registry.connectors_for = MagicMock(return_value=[mock_connector])

    plan = await service.source_bom(bom_id)

    mock_connector.fetch.assert_not_called()
    assert plan.tier_a_coverage_pct == 100.0


@pytest.mark.asyncio
async def test_sourcing_service_cache_miss_calls_connector():
    """Cache miss → connector is called, observation appended."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)
    fresh_offer = make_current_offer("mpn:STM32F103C8T6")

    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[
        make_bom_line("STM32F103C8T6", PartClass.A, tenant_id=tid, bom_id=bom_id)
    ])
    service._store.get_current = AsyncMock(side_effect=[[], [fresh_offer]])
    service._store.needs_refresh = MagicMock(return_value=True)
    service._store.append = AsyncMock()
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()

    obs = OfferObservation(
        listing_id=uuid.uuid4(), source="api", tier="A",
        captured_at=datetime.now(timezone.utc),
        normalized_part_key="mpn:STM32F103C8T6", supplier_id="nexar:1",
        category="MCU", price_ladder=None, moq=1, lead_time=None,
        stock=100, specs={}, supplier_snapshot={},
        screenshot_ref=None, confidence=None, field_captured_at={},
    )
    mock_connector = MagicMock()
    mock_connector.key = "mock"
    mock_connector.supports = MagicMock(return_value=True)
    mock_connector.fetch = AsyncMock(return_value=[obs])
    service._registry.connectors_for = MagicMock(return_value=[mock_connector])

    plan = await service.source_bom(bom_id)

    mock_connector.fetch.assert_called_once()
    service._store.append.assert_called_once_with(obs)


@pytest.mark.asyncio
async def test_sourcing_service_dedup_same_mpn():
    """Same MPN on N lines → connector called only ONCE."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)
    fresh_offer = make_current_offer("mpn:STM32F103C8T6")
    lines = [make_bom_line("STM32F103C8T6", PartClass.A, tenant_id=tid, bom_id=bom_id) for _ in range(5)]

    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=lines)
    service._store.get_current = AsyncMock(side_effect=[[], [fresh_offer]] + [[fresh_offer]] * 10)
    service._store.needs_refresh = MagicMock(return_value=True)
    service._store.append = AsyncMock()
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()

    obs = OfferObservation(
        listing_id=uuid.uuid4(), source="api", tier="A",
        captured_at=datetime.now(timezone.utc),
        normalized_part_key="mpn:STM32F103C8T6", supplier_id="nexar:1",
        category=None, price_ladder=None, moq=1, lead_time=None,
        stock=100, specs={}, supplier_snapshot={},
        screenshot_ref=None, confidence=None, field_captured_at={},
    )
    mock_connector = MagicMock()
    mock_connector.key = "mock"
    mock_connector.supports = MagicMock(return_value=True)
    mock_connector.fetch = AsyncMock(return_value=[obs])
    service._registry.connectors_for = MagicMock(return_value=[mock_connector])

    plan = await service.source_bom(bom_id)

    assert mock_connector.fetch.call_count == 1


@pytest.mark.asyncio
async def test_sourcing_service_per_line_failure_isolated():
    """A connector failure on one line doesn't abort the whole run."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)

    line_a = make_bom_line("STM32F103C8T6", PartClass.A, "mpn:STM32F103C8T6", tenant_id=tid, bom_id=bom_id)
    line_b = make_bom_line("ESP8266EX", PartClass.A, "mpn:ESP8266EX", tenant_id=tid, bom_id=bom_id)
    good_offer = make_current_offer("mpn:ESP8266EX")

    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[line_a, line_b])

    async def get_current(key: str) -> list:
        if "STM32" in key:
            return []
        return [good_offer]

    service._store.get_current = AsyncMock(side_effect=get_current)
    service._store.needs_refresh = MagicMock(return_value=True)
    service._store.append = AsyncMock()
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()

    async def failing_fetch(line: BomLine) -> list:
        if line.mpn == "STM32F103C8T6":
            raise Exception("Nexar error")
        return []

    mock_connector = MagicMock()
    mock_connector.key = "mock"
    mock_connector.supports = MagicMock(return_value=True)
    mock_connector.fetch = AsyncMock(side_effect=failing_fetch)
    service._registry.connectors_for = MagicMock(return_value=[mock_connector])

    plan = await service.source_bom(bom_id)
    assert plan is not None


@pytest.mark.asyncio
async def test_sourcing_service_tier_b_not_sourced():
    """Tier-B lines are classified but not sourced."""
    from sourceloop.classification.chain import ClassifierChain
    from sourceloop.domain.part import PartClass as PC
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    # Use a mock classifier that always returns Tier B
    mock_classifier = MagicMock(spec=ClassifierChain)
    mock_classifier.classify = MagicMock(return_value=(PC.B, []))

    service = SourcingService(session, classifier=mock_classifier)
    tier_b_line = make_bom_line("CUSTOM", PartClass.B, "desc:abc123", tenant_id=tid, bom_id=bom_id)

    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[tier_b_line])
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()
    service._registry.connectors_for = MagicMock(return_value=[])

    plan = await service.source_bom(bom_id)
    assert plan.lines[0].unsourced_reason == UnsourcedReason.TIER_B_NOT_IN_STEP1


@pytest.mark.asyncio
async def test_sourcing_service_no_lines():
    """Empty BOM returns plan with 0 lines."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)
    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[])
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()
    service._registry.connectors_for = MagicMock(return_value=[])

    plan = await service.source_bom(bom_id)
    assert len(plan.lines) == 0


@pytest.mark.asyncio
async def test_sourcing_service_connector_no_results():
    """Connector returns empty list → plan line is unsourced NO_TIER_A_OFFERS."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)
    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[
        make_bom_line("RAREPART", PartClass.A, tenant_id=tid, bom_id=bom_id)
    ])
    service._store.get_current = AsyncMock(return_value=[])
    service._store.needs_refresh = MagicMock(return_value=True)
    service._store.append = AsyncMock()
    service._demand_repo.emit = AsyncMock()
    service._plan_repo.upsert_plan = AsyncMock()

    mock_connector = MagicMock()
    mock_connector.key = "mock"
    mock_connector.supports = MagicMock(return_value=True)
    mock_connector.fetch = AsyncMock(return_value=[])
    service._registry.connectors_for = MagicMock(return_value=[mock_connector])

    plan = await service.source_bom(bom_id)
    assert plan.lines[0].unsourced_reason == UnsourcedReason.NO_TIER_A_OFFERS


@pytest.mark.asyncio
async def test_sourcing_service_demand_event_failure_not_fatal():
    """Demand event failure should not abort sourcing."""
    tid = setup_tenant()
    bom_id = uuid.uuid4()
    session = make_mock_session()

    service = SourcingService(session)
    fresh_offer = make_current_offer("mpn:STM32F103C8T6")

    service._bom_repo.update_status = AsyncMock()
    service._bom_repo.get_lines = AsyncMock(return_value=[
        make_bom_line("STM32F103C8T6", PartClass.A, tenant_id=tid, bom_id=bom_id)
    ])
    service._store.get_current = AsyncMock(return_value=[fresh_offer])
    service._store.needs_refresh = MagicMock(return_value=False)
    service._demand_repo.emit = AsyncMock(side_effect=Exception("DB error"))
    service._plan_repo.upsert_plan = AsyncMock()
    service._registry.connectors_for = MagicMock(return_value=[])

    plan = await service.source_bom(bom_id)
    assert plan is not None
