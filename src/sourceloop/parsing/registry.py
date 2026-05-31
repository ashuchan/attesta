from __future__ import annotations

from sourceloop.config.loader import get_parsers_config
from sourceloop.parsing.base import BomFileParser
from sourceloop.parsing.parsers.csv_parser import CsvParser
from sourceloop.parsing.parsers.pdf_parser import PdfParser
from sourceloop.parsing.parsers.plaintext_parser import PlaintextParser
from sourceloop.parsing.parsers.xlsx_parser import XlsxParser

_PARSER_CLASSES: dict[str, type] = {
    "xlsx": XlsxParser,
    "csv": CsvParser,
    "pdf": PdfParser,
    "plaintext": PlaintextParser,
}


class ParserRegistry:
    def __init__(self) -> None:
        cfg = get_parsers_config()
        self._parsers: list[BomFileParser] = []
        for entry in sorted(cfg.parsers, key=lambda e: e.priority):
            if not entry.enabled:
                continue
            cls = _PARSER_CLASSES.get(entry.key)
            if cls is None:
                continue
            instance = cls()
            instance.priority = entry.priority  # type: ignore[attr-defined]
            self._parsers.append(instance)  # type: ignore[arg-type]

    def all_parsers(self) -> list[BomFileParser]:
        return list(self._parsers)
