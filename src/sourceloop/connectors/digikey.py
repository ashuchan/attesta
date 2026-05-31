from __future__ import annotations

import structlog

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import OfferObservation

log = structlog.get_logger()


class DigiKeyConnector:
    """
    STUB — Step 1. Returns [] and logs connector_stubbed.

    Real auth model (for when this is implemented):
    - OAuth2 client_credentials with separate sandbox vs prod base URL.
    - Requires Digi-Key app approval. Env: DIGIKEY_CLIENT_ID, DIGIKEY_CLIENT_SECRET.
    - To implement: replace fetch() body; flip enabled: true in connectors.yaml.
    """
    key = "digikey"
    enabled = False
    priority = 20

    def supports(self, line: BomLine) -> bool:
        return bool(line.mpn)

    async def fetch(self, line: BomLine) -> list[OfferObservation]:
        log.info("connector_stubbed", key=self.key, part_key=line.normalized_part_key)
        return []
