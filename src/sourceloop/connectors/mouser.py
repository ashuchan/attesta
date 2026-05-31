from __future__ import annotations

import structlog

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import OfferObservation

log = structlog.get_logger()


class MouserConnector:
    """
    STUB — Step 1. Returns [] and logs connector_stubbed.

    Real auth model (for when this is implemented):
    - Simple API key in query param, per-search and per-day call quotas.
    - Env: MOUSER_API_KEY.
    - To implement: replace fetch() body; flip enabled: true in connectors.yaml.
    """
    key = "mouser"
    enabled = False
    priority = 30

    def supports(self, line: BomLine) -> bool:
        return bool(line.mpn)

    async def fetch(self, line: BomLine) -> list[OfferObservation]:
        log.info("connector_stubbed", key=self.key, part_key=line.normalized_part_key)
        return []
