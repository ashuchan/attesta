"""Step 2: Add score_log table, tier column on current_offer, confidence_summary on sourced_plan.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-31 00:00:00.000000
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── score_log — PARTITION BY RANGE (captured_at) ────────────────────────
    op.execute("""
        CREATE TABLE score_log (
            id UUID NOT NULL DEFAULT gen_random_uuid(),
            captured_at TIMESTAMPTZ NOT NULL,
            listing_id UUID NOT NULL REFERENCES listing(listing_id),
            strategy VARCHAR(100) NOT NULL,
            score FLOAT NOT NULL,
            band VARCHAR(20) NOT NULL,
            signals JSONB,
            PRIMARY KEY (id, captured_at)
        ) PARTITION BY RANGE (captured_at)
    """)
    op.execute("""
        CREATE TABLE score_log_2026_05
        PARTITION OF score_log
        FOR VALUES FROM ('2026-05-01') TO ('2026-06-01')
    """)
    op.execute("""
        CREATE TABLE score_log_2026_06
        PARTITION OF score_log
        FOR VALUES FROM ('2026-06-01') TO ('2026-07-01')
    """)
    op.execute("""
        CREATE TABLE score_log_2026_07
        PARTITION OF score_log
        FOR VALUES FROM ('2026-07-01') TO ('2026-08-01')
    """)
    op.execute("""
        CREATE TABLE score_log_2026_08
        PARTITION OF score_log
        FOR VALUES FROM ('2026-08-01') TO ('2026-09-01')
    """)
    op.execute("""
        CREATE TABLE score_log_default
        PARTITION OF score_log DEFAULT
    """)
    op.execute(
        "CREATE INDEX ix_score_log_listing_captured "
        "ON score_log (listing_id, captured_at DESC)"
    )

    # ── current_offer: add tier column (always 'A' until Tier-B added) ───────
    op.add_column(
        "current_offer",
        sa.Column("tier", sa.String(1), nullable=False, server_default="A"),
    )

    # ── sourced_plan: add confidence_summary column ───────────────────────────
    op.add_column(
        "sourced_plan",
        sa.Column("confidence_summary", JSONB),
    )


def downgrade() -> None:
    op.drop_column("sourced_plan", "confidence_summary")
    op.drop_column("current_offer", "tier")
    op.execute("DROP TABLE IF EXISTS score_log CASCADE")
