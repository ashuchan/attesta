from __future__ import annotations

import csv
import io

from sourceloop.parsing.base import ParseSource, RawRowSet


class CsvParser:
    key = "csv"
    priority = 20
    enabled = True

    def supports(self, source: ParseSource) -> float:
        if source.filename.lower().endswith(".csv"):
            return 0.85
        # Try to decode and sniff
        try:
            text = source.content[:2048].decode("utf-8", errors="replace")
            dialect = csv.Sniffer().sniff(text, delimiters=",;\t|")
            if dialect:
                return 0.6
        except Exception:
            pass
        return 0.0

    def parse(self, source: ParseSource) -> RawRowSet:
        text = source.content.decode("utf-8", errors="replace")
        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",;\t|")
        except csv.Error:
            dialect = csv.excel  # type: ignore[assignment]
        reader = csv.DictReader(io.StringIO(text), dialect=dialect)
        rows: list[dict[str, str | None]] = []
        for row in reader:
            normalized: dict[str, str | None] = {
                k.strip().lower(): (v.strip() if v else None)
                for k, v in row.items()
                if k is not None
            }
            if any(v for v in normalized.values() if v):
                rows.append(normalized)
        return RawRowSet(
            rows=rows,
            detected_format="csv",
            parser_key=self.key,
            parser_confidence=0.85,
        )
