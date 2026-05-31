from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .base import metadata


class Base(DeclarativeBase):
    metadata = metadata


# ─── Tenant-scoped (private) tables ──────────────────────────────────────────


class TenantRow(Base):
    __tablename__ = "tenant"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False, default="customer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CustomerProfileRow(Base):
    __tablename__ = "customer_profile"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), unique=True, nullable=False
    )
    sourcing_strategy: Mapped[str] = mapped_column(
        String(20), nullable=False, default="balanced"
    )
    segment: Mapped[str | None] = mapped_column(String(100))
    default_currency: Mapped[str | None] = mapped_column(String(10))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class CustomerDetailRow(Base):
    __tablename__ = "customer_detail"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    company_name: Mapped[str | None] = mapped_column(String(255))
    contact_name: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    gstin: Mapped[str | None] = mapped_column(String(20))
    address: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BomRow(Base):
    __tablename__ = "bom"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    original_format: Mapped[str] = mapped_column(String(20), nullable=False)
    line_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    parse_confidence_avg: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="parsed")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    parsed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class BomLineRow(Base):
    __tablename__ = "bom_line"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    bom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom.id"), nullable=False
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    raw_designator: Mapped[str | None] = mapped_column(Text)
    raw_description: Mapped[str | None] = mapped_column(Text)
    mpn: Mapped[str | None] = mapped_column(String(200))
    manufacturer: Mapped[str | None] = mapped_column(String(200))
    quantity: Mapped[float | None] = mapped_column(Numeric(12, 4))
    unit: Mapped[str | None] = mapped_column(String(20))
    normalized_part_key: Mapped[str] = mapped_column(String(500), nullable=False)
    part_class: Mapped[str | None] = mapped_column(String(1))
    parse_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    notes: Mapped[str | None] = mapped_column(Text)


class SourcedPlanRow(Base):
    __tablename__ = "sourced_plan"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    bom_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom.id"), nullable=False
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tier_a_coverage_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="sourced")


class PlanLineRow(Base):
    __tablename__ = "plan_line"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    sourced_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sourced_plan.id"), nullable=False
    )
    bom_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bom_line.id"), nullable=False
    )
    chosen_listing_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    offer_snapshot: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    unsourced_reason: Mapped[str | None] = mapped_column(String(30))


class DemandEventRow(Base):
    __tablename__ = "demand_event"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenant.id"), nullable=False
    )
    normalized_part_key: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(200))
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, primary_key=True)
    __table_args__ = (
        # PK is (id, ts) — defined in migration DDL for partitioned table
    )


# ─── Global (shared) tables — NO tenant_id ───────────────────────────────────


class SupplierRow(Base):
    __tablename__ = "supplier"
    supplier_id: Mapped[str] = mapped_column(String(200), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    region: Mapped[str | None] = mapped_column(String(100))
    years_active: Mapped[int | None] = mapped_column(Integer)
    trade_assurance: Mapped[bool | None] = mapped_column(Boolean)
    verified_factory: Mapped[bool | None] = mapped_column(Boolean)
    response_rate: Mapped[float | None] = mapped_column(Float)
    repurchase_rate: Mapped[float | None] = mapped_column(Float)
    reliability_score: Mapped[float | None] = mapped_column(Float)
    blacklisted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ListingRow(Base):
    __tablename__ = "listing"
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    url: Mapped[str] = mapped_column(String(2000), unique=True, nullable=False)
    supplier_id: Mapped[str] = mapped_column(
        String(200), ForeignKey("supplier.supplier_id"), nullable=False
    )
    normalized_part_key: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str | None] = mapped_column(String(200))
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    tier: Mapped[str] = mapped_column(String(1), nullable=False)


class OfferObservationRow(Base):
    """
    Partitioned table — actual DDL in migration (PARTITION BY RANGE captured_at).
    SQLAlchemy ORM mapped to the parent table; partitions created in migration.
    """

    __tablename__ = "offer_observation"
    obs_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, default=uuid.uuid4
    )
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, primary_key=True
    )
    listing_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("listing.listing_id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    price_ladder: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    moq: Mapped[int | None] = mapped_column(Integer)
    lead_time: Mapped[str | None] = mapped_column(String(100))
    stock: Mapped[int | None] = mapped_column(Integer)
    specs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    supplier_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    screenshot_ref: Mapped[str | None] = mapped_column(String(500))
    confidence: Mapped[float | None] = mapped_column(Float)
    category: Mapped[str | None] = mapped_column(String(200))
    field_captured_at: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("obs_id", "captured_at", name="uq_offer_observation_obs_captured"),
    )


class CurrentOfferRow(Base):
    __tablename__ = "current_offer"
    listing_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    latest_obs_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    normalized_part_key: Mapped[str] = mapped_column(String(500), nullable=False)
    supplier_id: Mapped[str] = mapped_column(
        String(200), ForeignKey("supplier.supplier_id"), nullable=False
    )
    price_ladder: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    moq: Mapped[int | None] = mapped_column(Integer)
    lead_time: Mapped[str | None] = mapped_column(String(100))
    stock: Mapped[int | None] = mapped_column(Integer)
    specs: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    confidence: Mapped[float | None] = mapped_column(Float)
    field_captured_at: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class HotnessRow(Base):
    __tablename__ = "hotness"
    part_key: Mapped[str] = mapped_column(String(500), primary_key=True)
    category: Mapped[str | None] = mapped_column(String(200))
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
