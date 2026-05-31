"""Initial schema with partitioned tables and seed data.

Revision ID: 0001
Revises:
Create Date: 2026-01-01 00:00:00.000000
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Tenant-scoped tables ─────────────────────────────────────────────────

    op.create_table(
        "tenant",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="customer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "customer_profile",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenant.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "sourcing_strategy", sa.String(20), nullable=False, server_default="balanced"
        ),
        sa.Column("segment", sa.String(100)),
        sa.Column("default_currency", sa.String(10)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "customer_detail",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column("company_name", sa.String(255)),
        sa.Column("contact_name", sa.String(255)),
        sa.Column("email", sa.String(255)),
        sa.Column("phone", sa.String(50)),
        sa.Column("gstin", sa.String(20)),
        sa.Column("address", JSONB),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_customer_detail_tenant_id", "customer_detail", ["tenant_id"])

    op.create_table(
        "bom",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column("source_filename", sa.String(500), nullable=False),
        sa.Column("original_format", sa.String(20), nullable=False),
        sa.Column("line_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("parse_confidence_avg", sa.Float),
        sa.Column("status", sa.String(20), nullable=False, server_default="parsed"),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("parsed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_bom_tenant_id", "bom", ["tenant_id"])

    op.create_table(
        "bom_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "bom_id", UUID(as_uuid=True), sa.ForeignKey("bom.id"), nullable=False
        ),
        sa.Column("line_no", sa.Integer, nullable=False),
        sa.Column("raw_designator", sa.Text),
        sa.Column("raw_description", sa.Text),
        sa.Column("mpn", sa.String(200)),
        sa.Column("manufacturer", sa.String(200)),
        sa.Column("quantity", sa.Numeric(12, 4)),
        sa.Column("unit", sa.String(20)),
        sa.Column("normalized_part_key", sa.String(500), nullable=False),
        sa.Column("part_class", sa.String(1)),
        sa.Column(
            "parse_confidence", sa.Float, nullable=False, server_default="0"
        ),
        sa.Column("notes", sa.Text),
    )
    op.create_index("ix_bom_line_tenant_bom", "bom_line", ["tenant_id", "bom_id"])
    op.create_index(
        "ix_bom_line_normalized_part_key", "bom_line", ["normalized_part_key"]
    )

    op.create_table(
        "sourced_plan",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "bom_id", UUID(as_uuid=True), sa.ForeignKey("bom.id"), nullable=False
        ),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "tier_a_coverage_pct", sa.Float, nullable=False, server_default="0"
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="sourced"),
    )
    op.create_index("ix_sourced_plan_tenant_id", "sourced_plan", ["tenant_id"])
    op.create_index("ix_sourced_plan_bom_id", "sourced_plan", ["bom_id"])

    op.create_table(
        "plan_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column(
            "sourced_plan_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sourced_plan.id"),
            nullable=False,
        ),
        sa.Column(
            "bom_line_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bom_line.id"),
            nullable=False,
        ),
        sa.Column("chosen_listing_id", UUID(as_uuid=True)),
        sa.Column("offer_snapshot", JSONB),
        sa.Column("confidence", sa.Float),
        sa.Column("unsourced_reason", sa.String(30)),
    )
    op.create_index("ix_plan_line_sourced_plan_id", "plan_line", ["sourced_plan_id"])

    # demand_event — PARTITION BY RANGE (ts)
    op.execute("""
        CREATE TABLE demand_event (
            id UUID NOT NULL,
            tenant_id UUID NOT NULL REFERENCES tenant(id),
            normalized_part_key VARCHAR(500) NOT NULL,
            category VARCHAR(200),
            customer_id UUID,
            ts TIMESTAMPTZ NOT NULL,
            PRIMARY KEY (id, ts)
        ) PARTITION BY RANGE (ts)
    """)
    op.execute("""
        CREATE TABLE demand_event_2026_01
        PARTITION OF demand_event
        FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
    """)
    op.execute("""
        CREATE TABLE demand_event_2026_02
        PARTITION OF demand_event
        FOR VALUES FROM ('2026-02-01') TO ('2026-03-01')
    """)
    op.execute("""
        CREATE TABLE demand_event_2026_03
        PARTITION OF demand_event
        FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')
    """)
    op.execute("""
        CREATE TABLE demand_event_2026_04
        PARTITION OF demand_event
        FOR VALUES FROM ('2026-04-01') TO ('2026-05-01')
    """)
    op.execute("""
        CREATE TABLE demand_event_2026_05
        PARTITION OF demand_event
        FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
    """)
    op.execute("""
        CREATE TABLE demand_event_2026_06
        PARTITION OF demand_event
        FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
    """)
    op.execute("""
        CREATE TABLE demand_event_default
        PARTITION OF demand_event DEFAULT
    """)
    op.create_index(
        "ix_demand_event_tenant_part_ts",
        "demand_event",
        ["tenant_id", "normalized_part_key", "ts"],
    )

    # ── Global tables — NO tenant_id ─────────────────────────────────────────

    op.create_table(
        "supplier",
        sa.Column("supplier_id", sa.String(200), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("region", sa.String(100)),
        sa.Column("years_active", sa.Integer),
        sa.Column("trade_assurance", sa.Boolean),
        sa.Column("verified_factory", sa.Boolean),
        sa.Column("response_rate", sa.Float),
        sa.Column("repurchase_rate", sa.Float),
        sa.Column("reliability_score", sa.Float),
        sa.Column(
            "blacklisted", sa.Boolean, nullable=False, server_default="false"
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "listing",
        sa.Column("listing_id", UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column("url", sa.String(2000), unique=True, nullable=False),
        sa.Column(
            "supplier_id",
            sa.String(200),
            sa.ForeignKey("supplier.supplier_id"),
            nullable=False,
        ),
        sa.Column("normalized_part_key", sa.String(500), nullable=False),
        sa.Column("category", sa.String(200)),
        sa.Column("first_seen", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tier", sa.String(1), nullable=False),
    )
    op.create_index(
        "ix_listing_normalized_part_key", "listing", ["normalized_part_key"]
    )
    op.create_index("ix_listing_supplier_id", "listing", ["supplier_id"])

    # offer_observation — PARTITION BY RANGE (captured_at)
    op.execute("""
        CREATE TABLE offer_observation (
            obs_id UUID NOT NULL DEFAULT gen_random_uuid(),
            captured_at TIMESTAMPTZ NOT NULL,
            listing_id UUID NOT NULL REFERENCES listing(listing_id),
            source VARCHAR(20) NOT NULL,
            price_ladder JSONB,
            moq INTEGER,
            lead_time VARCHAR(100),
            stock INTEGER,
            specs JSONB,
            supplier_snapshot JSONB,
            screenshot_ref VARCHAR(500),
            confidence FLOAT,
            category VARCHAR(200),
            field_captured_at JSONB,
            PRIMARY KEY (obs_id, captured_at)
        ) PARTITION BY RANGE (captured_at)
    """)
    op.execute("""
        CREATE TABLE offer_observation_2026_01
        PARTITION OF offer_observation
        FOR VALUES FROM ('2026-01-01') TO ('2026-02-01')
    """)
    op.execute("""
        CREATE TABLE offer_observation_2026_02
        PARTITION OF offer_observation
        FOR VALUES FROM ('2026-02-01') TO ('2026-03-01')
    """)
    op.execute("""
        CREATE TABLE offer_observation_2026_03
        PARTITION OF offer_observation
        FOR VALUES FROM ('2026-03-01') TO ('2026-04-01')
    """)
    op.execute("""
        CREATE TABLE offer_observation_2026_04
        PARTITION OF offer_observation
        FOR VALUES FROM ('2026-04-01') TO ('2026-05-01')
    """)
    op.execute("""
        CREATE TABLE offer_observation_2026_05
        PARTITION OF offer_observation
        FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
    """)
    op.execute("""
        CREATE TABLE offer_observation_2026_06
        PARTITION OF offer_observation
        FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
    """)
    op.execute("""
        CREATE TABLE offer_observation_default
        PARTITION OF offer_observation DEFAULT
    """)
    op.execute(
        "CREATE INDEX ix_offer_obs_listing_captured "
        "ON offer_observation USING brin (captured_at)"
    )
    op.execute(
        "CREATE INDEX ix_offer_obs_listing_id "
        "ON offer_observation (listing_id, captured_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_offer_obs_specs_gin ON offer_observation USING gin (specs)"
    )

    op.create_table(
        "current_offer",
        sa.Column("listing_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("latest_obs_id", UUID(as_uuid=True), nullable=False),
        sa.Column("normalized_part_key", sa.String(500), nullable=False),
        sa.Column(
            "supplier_id",
            sa.String(200),
            sa.ForeignKey("supplier.supplier_id"),
            nullable=False,
        ),
        sa.Column("price_ladder", JSONB),
        sa.Column("moq", sa.Integer),
        sa.Column("lead_time", sa.String(100)),
        sa.Column("stock", sa.Integer),
        sa.Column("specs", JSONB),
        sa.Column("confidence", sa.Float),
        sa.Column("field_captured_at", JSONB),
    )
    op.create_index(
        "ix_current_offer_normalized_part_key", "current_offer", ["normalized_part_key"]
    )

    op.create_table(
        "hotness",
        sa.Column("part_key", sa.String(500), primary_key=True),
        sa.Column("category", sa.String(200)),
        sa.Column("score", sa.Float, nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    # ── Seed: founder-internal tenant ────────────────────────────────────────
    now = datetime.now(timezone.utc).isoformat()
    op.execute(f"""
        INSERT INTO tenant (id, slug, name, kind, created_at)
        VALUES (gen_random_uuid(), 'founder-internal', 'SourceLoop Internal', 'internal', '{now}')
        ON CONFLICT (slug) DO NOTHING
    """)  # noqa: S608


def downgrade() -> None:
    op.drop_table("hotness")
    op.drop_table("current_offer")
    op.execute("DROP TABLE IF EXISTS offer_observation CASCADE")
    op.drop_table("listing")
    op.drop_table("supplier")
    op.execute("DROP TABLE IF EXISTS demand_event CASCADE")
    op.drop_table("plan_line")
    op.drop_table("sourced_plan")
    op.drop_table("bom_line")
    op.drop_table("bom")
    op.drop_table("customer_detail")
    op.drop_table("customer_profile")
    op.drop_table("tenant")
