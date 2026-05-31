"""Idempotent partition automation for offer_observation, demand_event, score_log."""
from __future__ import annotations

import sqlalchemy as sa
import structlog
from datetime import UTC, datetime
from sqlalchemy.ext.asyncio import AsyncConnection

log = structlog.get_logger()

PARTITIONED_TABLES = [
    ("offer_observation", "offer_observation"),
    ("demand_event", "demand_event"),
    ("score_log", "score_log"),
]


def _next_month_start(year: int, month: int) -> tuple[int, int]:
    if month == 12:
        return year + 1, 1
    return year, month + 1


async def ensure_partitions(conn: AsyncConnection, ahead_months: int = 3) -> int:
    """
    Idempotent: create monthly partitions for current + N ahead months.
    Safe to call repeatedly — uses CREATE TABLE IF NOT EXISTS.
    Returns count of partition statements executed.
    """
    now = datetime.now(UTC)
    year, month = now.year, now.month
    created = 0

    for _ in range(ahead_months + 1):
        ny, nm = _next_month_start(year, month)
        from_val = f"{year:04d}-{month:02d}-01"
        to_val = f"{ny:04d}-{nm:02d}-01"

        for table_name, prefix in PARTITIONED_TABLES:
            partition_name = f"{prefix}_{year:04d}_{month:02d}"
            await conn.execute(sa.text(
                f"CREATE TABLE IF NOT EXISTS {partition_name} "
                f"PARTITION OF {table_name} "
                f"FOR VALUES FROM ('{from_val}') TO ('{to_val}')"
            ))
            log.debug(
                "partition_ensured",
                table=table_name,
                partition=partition_name,
            )
            created += 1

        year, month = ny, nm

    return created
