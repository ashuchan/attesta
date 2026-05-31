"""ScoreLogRepository — append-only write of score provenance."""
from __future__ import annotations

import json
import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class ScoreLogRepository:
    """Global repository (no tenant_id). Write-only; reads are analytics-side."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def write(
        self,
        listing_id: uuid.UUID,
        captured_at: datetime,
        strategy: str,
        score: float,
        band: str,
        signals_json: dict | None,
    ) -> None:
        """Append a score provenance record. Never updates existing rows."""
        log_id = uuid.uuid4()
        await self._session.execute(
            text("""
                INSERT INTO score_log
                  (id, captured_at, listing_id, strategy, score, band, signals)
                VALUES
                  (:id, :captured_at, :listing_id, :strategy, :score, :band, :signals::jsonb)
            """),
            {
                "id": str(log_id),
                "captured_at": captured_at,
                "listing_id": str(listing_id),
                "strategy": strategy,
                "score": score,
                "band": band,
                "signals": json.dumps(signals_json) if signals_json is not None else "null",
            },
        )
