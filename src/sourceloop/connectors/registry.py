from __future__ import annotations

import structlog

from sourceloop.config.loader import get_connectors_config, get_env
from sourceloop.connectors.base import DistributorConnector
from sourceloop.connectors.digikey import DigiKeyConnector
from sourceloop.connectors.mock import MockConnector
from sourceloop.connectors.mouser import MouserConnector
from sourceloop.connectors.nexar import NexarConnector
from sourceloop.domain.bom import BomLine

log = structlog.get_logger()

_CONNECTOR_CLASSES: dict[str, type] = {
    "nexar": NexarConnector,
    "digikey": DigiKeyConnector,
    "mouser": MouserConnector,
    "mock": MockConnector,
}


class ConnectorRegistry:
    def __init__(self) -> None:
        cfg = get_connectors_config()
        env = get_env()
        self._connectors: list[DistributorConnector] = []

        for entry in sorted(cfg.connectors, key=lambda e: e.priority):
            enabled = entry.enabled
            # Env override: SOURCELOOP_USE_MOCK=1 enables mock
            if entry.key == "mock" and env.sourceloop_use_mock:
                enabled = True

            if not enabled:
                continue

            cls = _CONNECTOR_CLASSES.get(entry.key)
            if cls is None:
                log.warning("unknown_connector_key", key=entry.key)
                continue
            instance = cls()
            instance.priority = entry.priority  # type: ignore[attr-defined]
            if not instance.enabled:
                continue
            self._connectors.append(instance)  # type: ignore[arg-type]

    def connectors_for(self, line: BomLine) -> list[DistributorConnector]:
        """Return enabled connectors that support this BomLine, sorted by priority."""
        return [c for c in self._connectors if c.supports(line)]

    def connectors_for_mpn(self, mpn: str) -> list[DistributorConnector]:
        """Return enabled connectors that support a direct MPN fetch (warmup path)."""
        if not mpn:
            return []
        return [c for c in self._connectors if c.enabled and hasattr(c, "fetch_mpn")]
