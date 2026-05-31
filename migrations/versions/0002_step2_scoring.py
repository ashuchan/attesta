"""Step 2: Add score_log table, tier column on current_offer, confidence_summary on sourced_plan.

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-31 00:00:00.000000
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


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

    # Create partitions for current month + 3 ahead — run-time computed so
    # the migration stays correct regardless of when it is applied.
    now = datetime.now(UTC)
    year, month = now.year, now.month
    for _ in range(4):
        ny, nm = _next_month(year, month)
        from_val = f"{year:04d}-{month:02d}-01"
        to_val = f"{ny:04d}-{nm:02d}-01"
        pname = f"score_log_{year:04d}_{month:02d}"
        op.execute(
            f"CREATE TABLE {pname} PARTITION OF score_log "
            f"FOR VALUES FROM ('{from_val}') TO ('{to_val}')"
        )
        year, month = ny, nm

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
