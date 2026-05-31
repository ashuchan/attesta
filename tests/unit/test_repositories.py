from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from sourceloop.domain.offer import PriceLadder
from sourceloop.domain.part import PartClass, UnsourcedReason
from sourceloop.tenancy.context import TenantContext


def setup_tenant() -> uuid.UUID:
    tid = uuid.uuid4()
    TenantContext.set(tid)
    return tid


# ─── OfferRepository pure conversions ──────────────────────────────────────

def test_offer_repo_ladder_to_json_none():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)
    assert repo._ladder_to_json(None) is None


def test_offer_repo_ladder_to_json_with_rungs():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)
    ladder = PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}])
    result = repo._ladder_to_json(ladder)
    assert result == {"rungs": [{"qty": 1, "price": 100.0, "currency": "INR"}]}


def test_offer_repo_ladder_to_json_str_none():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)
    assert repo._ladder_to_json_str(None) == "null"


def test_offer_repo_ladder_to_json_str_with_rungs():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)
    ladder = PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}])
    result = repo._ladder_to_json_str(ladder)
    parsed = json.loads(result)
    assert parsed["rungs"][0]["qty"] == 1


def test_offer_repo_dict_to_json_str_none():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)
    assert repo._dict_to_json_str(None) == "null"


def test_offer_repo_dict_to_json_str_with_data():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)
    result = repo._dict_to_json_str({"key": "val"})
    assert json.loads(result) == {"key": "val"}


def test_offer_repo_current_row_to_domain_with_ladder():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)

    mock_row = MagicMock()
    mock_row.listing_id = uuid.uuid4()
    mock_row.latest_obs_id = uuid.uuid4()
    mock_row.normalized_part_key = "mpn:STM32"
    mock_row.supplier_id = "nexar:1"
    mock_row.price_ladder = {"rungs": [{"qty": 1, "price": 100.0, "currency": "INR"}]}
    mock_row.moq = 1
    mock_row.lead_time = None
    mock_row.stock = 100
    mock_row.specs = {"volt": "3.3V"}
    mock_row.confidence = None
    mock_row.field_captured_at = {"price_ladder": "2026-01-01T00:00:00"}

    domain = repo._current_row_to_domain(mock_row)
    assert domain.normalized_part_key == "mpn:STM32"
    assert domain.price_ladder is not None
    assert domain.price_ladder.rungs[0]["qty"] == 1


def test_offer_repo_current_row_to_domain_no_ladder():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)

    mock_row = MagicMock()
    mock_row.listing_id = uuid.uuid4()
    mock_row.latest_obs_id = uuid.uuid4()
    mock_row.normalized_part_key = "mpn:STM32"
    mock_row.supplier_id = "nexar:1"
    mock_row.price_ladder = None
    mock_row.moq = None
    mock_row.lead_time = None
    mock_row.stock = None
    mock_row.specs = None
    mock_row.confidence = None
    mock_row.field_captured_at = None

    domain = repo._current_row_to_domain(mock_row)
    assert domain.price_ladder is None
    assert domain.specs == {}
    assert domain.field_captured_at == {}


@pytest.mark.asyncio
async def test_offer_repo_get_current_offers():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    repo = OfferRepository(session)

    mock_row = MagicMock()
    mock_row.listing_id = uuid.uuid4()
    mock_row.latest_obs_id = uuid.uuid4()
    mock_row.normalized_part_key = "mpn:STM32"
    mock_row.supplier_id = "nexar:1"
    mock_row.price_ladder = {"rungs": []}
    mock_row.moq = 1
    mock_row.lead_time = None
    mock_row.stock = 100
    mock_row.specs = {}
    mock_row.confidence = None
    mock_row.field_captured_at = {}

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    session.execute = AsyncMock(return_value=mock_result)

    offers = await repo.get_current_offers("mpn:STM32")
    assert len(offers) == 1
    assert offers[0].normalized_part_key == "mpn:STM32"


# ─── BomRepository pure conversions ──────────────────────────────────────────

def test_bom_repo_row_to_domain():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    repo = BomRepository(session)

    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.source_filename = "bom.csv"
    mock_row.original_format = "csv"
    mock_row.line_count = 5
    mock_row.parse_confidence_avg = 0.9
    mock_row.status = "parsed"
    mock_row.uploaded_at = datetime.now(UTC)
    mock_row.parsed_at = datetime.now(UTC)

    bom = repo._row_to_domain(mock_row)
    assert bom.source_filename == "bom.csv"
    assert bom.line_count == 5


def test_bom_repo_line_row_to_domain():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    repo = BomRepository(session)

    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.bom_id = uuid.uuid4()
    mock_row.line_no = 1
    mock_row.raw_designator = "U1"
    mock_row.raw_description = "MCU"
    mock_row.mpn = "STM32F103C8T6"
    mock_row.manufacturer = "ST"
    mock_row.quantity = 1.0
    mock_row.unit = "pcs"
    mock_row.normalized_part_key = "mpn:STM32F103C8T6"
    mock_row.part_class = "A"
    mock_row.parse_confidence = 0.9
    mock_row.notes = None

    line = repo._line_row_to_domain(mock_row)
    assert line.mpn == "STM32F103C8T6"
    assert line.part_class == PartClass.A
    assert line.quantity == 1.0


def test_bom_repo_line_row_no_part_class():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    repo = BomRepository(session)

    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.bom_id = uuid.uuid4()
    mock_row.line_no = 2
    mock_row.raw_designator = None
    mock_row.raw_description = "Custom"
    mock_row.mpn = None
    mock_row.manufacturer = None
    mock_row.quantity = None
    mock_row.unit = None
    mock_row.normalized_part_key = "desc:abc"
    mock_row.part_class = None
    mock_row.parse_confidence = 0.5
    mock_row.notes = None

    line = repo._line_row_to_domain(mock_row)
    assert line.part_class is None
    assert line.quantity is None


@pytest.mark.asyncio
async def test_bom_repo_get_lines():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    repo = BomRepository(session)

    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.bom_id = uuid.uuid4()
    mock_row.line_no = 1
    mock_row.raw_designator = "U1"
    mock_row.raw_description = "MCU"
    mock_row.mpn = "STM32"
    mock_row.manufacturer = "ST"
    mock_row.quantity = 1.0
    mock_row.unit = "pcs"
    mock_row.normalized_part_key = "mpn:STM32"
    mock_row.part_class = "A"
    mock_row.parse_confidence = 0.9
    mock_row.notes = None

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_row]
    session.execute = AsyncMock(return_value=mock_result)

    lines = await repo.get_lines(uuid.uuid4())
    assert len(lines) == 1
    assert lines[0].mpn == "STM32"


@pytest.mark.asyncio
async def test_bom_repo_update_status():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    repo = BomRepository(session)

    await repo.update_status(uuid.uuid4(), "sourced")
    session.execute.assert_called_once()


# ─── PlanRepository pure conversions ────────────────────────────────────────

def test_plan_repo_line_row_to_domain():
    from sourceloop.repositories.plan_repo import PlanRepository
    tid = setup_tenant()
    session = MagicMock()
    repo = PlanRepository(session)

    plan_id = uuid.uuid4()
    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.sourced_plan_id = plan_id
    mock_row.bom_line_id = uuid.uuid4()
    mock_row.chosen_listing_id = None
    mock_row.offer_snapshot = [{"listing_id": str(uuid.uuid4())}]
    mock_row.confidence = None
    mock_row.unsourced_reason = None

    line = repo._line_row_to_domain(mock_row)
    assert line.confidence is None
    assert line.unsourced_reason is None


def test_plan_repo_line_row_to_domain_with_unsourced_reason():
    from sourceloop.repositories.plan_repo import PlanRepository
    tid = setup_tenant()
    session = MagicMock()
    repo = PlanRepository(session)

    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.sourced_plan_id = uuid.uuid4()
    mock_row.bom_line_id = uuid.uuid4()
    mock_row.chosen_listing_id = None
    mock_row.offer_snapshot = None
    mock_row.confidence = None
    mock_row.unsourced_reason = "no_tier_a_offers"

    line = repo._line_row_to_domain(mock_row)
    assert line.unsourced_reason == UnsourcedReason.NO_TIER_A_OFFERS
    assert line.offer_snapshot == []


# ─── DemandRepository ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_demand_repo_emit():
    from sourceloop.repositories.demand_repo import DemandRepository
    tid = setup_tenant()
    session = MagicMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    repo = DemandRepository(session)

    await repo.emit(normalized_part_key="mpn:STM32", category="MCU")
    session.execute.assert_called_once()


@pytest.mark.asyncio
async def test_demand_repo_emit_with_customer():
    from sourceloop.repositories.demand_repo import DemandRepository
    tid = setup_tenant()
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    repo = DemandRepository(session)

    customer_id = uuid.uuid4()
    await repo.emit(normalized_part_key="mpn:STM32", category=None, customer_id=customer_id)
    session.execute.assert_called_once()


# ─── BomRepository create_bom ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_bom_repo_create_bom():
    from sourceloop.domain.bom import BomLine, ParseResult
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    repo = BomRepository(session)

    line = BomLine(
        id=uuid.uuid4(), tenant_id=tid, bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn="STM32", manufacturer="ST", quantity=1.0, unit="pcs",
        normalized_part_key="mpn:STM32", part_class=PartClass.A,
        parse_confidence=0.9,
    )
    parse_result = ParseResult(
        lines=[line], source_filename="bom.csv", original_format="csv",
        parse_confidence_avg=0.9, parser_key="csv", parser_confidence=0.9,
    )
    bom = await repo.create_bom(parse_result)
    assert bom.source_filename == "bom.csv"
    session.add.assert_called_once()
    session.flush.assert_called_once()


@pytest.mark.asyncio
async def test_bom_repo_get_bom_found():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()

    mock_row = MagicMock()
    mock_row.id = uuid.uuid4()
    mock_row.tenant_id = tid
    mock_row.source_filename = "bom.csv"
    mock_row.original_format = "csv"
    mock_row.line_count = 5
    mock_row.parse_confidence_avg = 0.9
    mock_row.status = "parsed"
    mock_row.uploaded_at = datetime.now(UTC)
    mock_row.parsed_at = datetime.now(UTC)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_row
    session.execute = AsyncMock(return_value=mock_result)
    repo = BomRepository(session)

    bom = await repo.get_bom(uuid.uuid4())
    assert bom is not None
    assert bom.status == "parsed"


@pytest.mark.asyncio
async def test_bom_repo_get_bom_not_found():
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    repo = BomRepository(session)

    bom = await repo.get_bom(uuid.uuid4())
    assert bom is None


@pytest.mark.asyncio
async def test_bom_repo_create_lines():
    from sourceloop.domain.bom import BomLine
    from sourceloop.repositories.bom_repo import BomRepository
    tid = setup_tenant()
    session = MagicMock()
    session.add_all = MagicMock()
    session.flush = AsyncMock()
    repo = BomRepository(session)

    lines = [
        BomLine(
            id=uuid.uuid4(), tenant_id=tid, bom_id=uuid.uuid4(),
            line_no=1, raw_designator="U1", raw_description="MCU",
            mpn="STM32", manufacturer="ST", quantity=1.0, unit="pcs",
            normalized_part_key="mpn:STM32", part_class=PartClass.A,
            parse_confidence=0.9,
        )
    ]
    result = await repo.create_lines(uuid.uuid4(), lines)
    assert result == lines
    session.add_all.assert_called_once()


# ─── OfferRepository append/upsert (mocked execute) ──────────────────────────

@pytest.mark.asyncio
async def test_offer_repo_upsert_listing():
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    lid = uuid.uuid4()
    mock_result = MagicMock()
    mock_result.fetchone.return_value = (lid,)
    session.execute = AsyncMock(return_value=mock_result)
    repo = OfferRepository(session)

    result = await repo.upsert_listing(
        listing_id=lid,
        url="http://test/stm32",
        supplier_id="nexar:1",
        normalized_part_key="mpn:STM32",
        category="MCU",
        tier="A",
    )
    assert result == lid


@pytest.mark.asyncio
async def test_offer_repo_append_observation():
    from sourceloop.domain.offer import OfferObservation, PriceLadder
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    repo = OfferRepository(session)

    obs = OfferObservation(
        listing_id=uuid.uuid4(), source="api", tier="A",
        captured_at=datetime.now(UTC),
        normalized_part_key="mpn:STM32", supplier_id="nexar:1",
        category="MCU",
        price_ladder=PriceLadder(rungs=[{"qty": 1, "price": 100.0, "currency": "INR"}]),
        moq=1, lead_time=None, stock=500, specs={"volt": "3.3V"},
        supplier_snapshot={"company_id": "1", "company_name": "Mouser"},
        screenshot_ref=None, confidence=None,
        field_captured_at={"price_ladder": datetime.now(UTC).isoformat()},
    )
    await repo.append_observation(obs)
    # execute called twice (INSERT + upsert current_offer)
    assert session.execute.call_count == 2


@pytest.mark.asyncio
async def test_offer_repo_append_observation_no_price_ladder():
    from sourceloop.domain.offer import OfferObservation
    from sourceloop.repositories.offer_repo import OfferRepository
    session = MagicMock()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    repo = OfferRepository(session)

    obs = OfferObservation(
        listing_id=uuid.uuid4(), source="api", tier="A",
        captured_at=datetime.now(UTC),
        normalized_part_key="mpn:STM32", supplier_id="nexar:1",
        category=None, price_ladder=None, moq=None, lead_time=None,
        stock=None, specs={}, supplier_snapshot={},
        screenshot_ref=None, confidence=None, field_captured_at={},
    )
    await repo.append_observation(obs)
    assert session.execute.call_count == 2


# ─── SupplierRepository ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_supplier_repo_upsert():
    from sourceloop.domain.supplier import Supplier
    from sourceloop.repositories.supplier_repo import SupplierRepository
    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock())
    repo = SupplierRepository(session)

    supplier = Supplier(
        supplier_id="nexar:1", name="Mouser", region="IN",
        years_active=None, trade_assurance=None, verified_factory=None,
        response_rate=None, repurchase_rate=None, reliability_score=None,
        blacklisted=False, updated_at=datetime.now(UTC),
    )
    await repo.upsert(supplier)
    session.execute.assert_called_once()


# ─── PlanRepository ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_plan_repo_get_plan_not_found():
    from sourceloop.repositories.plan_repo import PlanRepository
    tid = setup_tenant()
    session = MagicMock()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute = AsyncMock(return_value=mock_result)
    repo = PlanRepository(session)

    plan = await repo.get_plan(uuid.uuid4())
    assert plan is None


@pytest.mark.asyncio
async def test_plan_repo_upsert_plan_no_existing():
    from sourceloop.domain.plan import PlanLine, SourcedPlan
    from sourceloop.repositories.plan_repo import PlanRepository
    tid = setup_tenant()
    session = MagicMock()

    # First execute: no existing plans
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    session.execute = AsyncMock(return_value=mock_result)
    session.add = MagicMock()
    session.flush = AsyncMock()
    repo = PlanRepository(session)

    plan_id = uuid.uuid4()
    bom_id = uuid.uuid4()
    plan = SourcedPlan(
        id=plan_id, tenant_id=tid, bom_id=bom_id,
        generated_at=datetime.now(UTC),
        tier_a_coverage_pct=100.0, status="sourced",
        lines=[
            PlanLine(
                id=uuid.uuid4(), tenant_id=tid, sourced_plan_id=plan_id,
                bom_line_id=uuid.uuid4(), chosen_listing_id=None,
                offer_snapshot=[], confidence=None, unsourced_reason=None,
            )
        ],
    )
    result = await repo.upsert_plan(plan)
    assert result == plan
    assert session.add.call_count >= 2  # plan_row + line_row


@pytest.mark.asyncio
async def test_plan_repo_upsert_plan_replaces_existing():
    """When existing plan is found, it's deleted before inserting new one."""
    from sourceloop.domain.plan import SourcedPlan
    from sourceloop.repositories.plan_repo import PlanRepository
    tid = setup_tenant()
    session = MagicMock()

    # Existing plan row
    existing_plan_row = MagicMock()
    existing_plan_row.id = uuid.uuid4()
    existing_plan_row.tenant_id = tid

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [existing_plan_row]
    session.execute = AsyncMock(return_value=mock_result)
    session.delete = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    repo = PlanRepository(session)

    plan_id = uuid.uuid4()
    plan = SourcedPlan(
        id=plan_id, tenant_id=tid, bom_id=uuid.uuid4(),
        generated_at=datetime.now(UTC),
        tier_a_coverage_pct=50.0, status="sourced", lines=[],
    )
    result = await repo.upsert_plan(plan)
    assert result == plan
    session.delete.assert_called_once_with(existing_plan_row)


@pytest.mark.asyncio
async def test_plan_repo_get_plan_found():
    """get_plan returns a SourcedPlan when row exists."""
    from sourceloop.repositories.plan_repo import PlanRepository
    tid = setup_tenant()
    session = MagicMock()

    plan_row = MagicMock()
    plan_row.id = uuid.uuid4()
    plan_row.tenant_id = tid
    plan_row.bom_id = uuid.uuid4()
    plan_row.generated_at = datetime.now(UTC)
    plan_row.tier_a_coverage_pct = 100.0
    plan_row.status = "sourced"

    line_row = MagicMock()
    line_row.id = uuid.uuid4()
    line_row.tenant_id = tid
    line_row.sourced_plan_id = plan_row.id
    line_row.bom_line_id = uuid.uuid4()
    line_row.chosen_listing_id = None
    line_row.offer_snapshot = []
    line_row.confidence = None
    line_row.unsourced_reason = None

    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        mock_r = MagicMock()
        if call_count == 1:
            mock_r.scalar_one_or_none.return_value = plan_row
        else:
            mock_r.scalars.return_value.all.return_value = [line_row]
        return mock_r

    session.execute = AsyncMock(side_effect=side_effect)
    repo = PlanRepository(session)

    plan = await repo.get_plan(uuid.uuid4())
    assert plan is not None
    assert plan.tier_a_coverage_pct == 100.0
    assert len(plan.lines) == 1
