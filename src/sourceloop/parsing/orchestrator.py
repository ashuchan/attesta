from __future__ import annotations

import structlog

from sourceloop.parsing.base import BomFileParser, ParseSource
from sourceloop.parsing.registry import ParserRegistry

log = structlog.get_logger()


class UnsupportedBomFormatError(Exception):
    pass


class ParserOrchestrator:
    """Sniffs content, routes to highest-confidence parser, tie-breaks by priority."""

    def __init__(self, registry: ParserRegistry | None = None) -> None:
        self._registry = registry or ParserRegistry()

    def route(self, source: ParseSource) -> BomFileParser:
        """Return the parser that should handle this source."""
        candidates: list[tuple[float, int, BomFileParser]] = []
        for parser in self._registry.all_parsers():
            confidence = parser.supports(source)
            if confidence > 0.0:
                candidates.append((confidence, parser.priority, parser))

        if not candidates:
            raise UnsupportedBomFormatError(
                f"No parser supports file: {source.filename!r}. "
                "Supported formats: xlsx, csv, pdf, plaintext."
            )

        # Sort by confidence DESC, then priority ASC (lower priority number = preferred)
        candidates.sort(key=lambda t: (-t[0], t[1]))
        chosen = candidates[0][2]
        log.info("parser_selected", parser=chosen.key, filename=source.filename, confidence=candidates[0][0])
        return chosen
