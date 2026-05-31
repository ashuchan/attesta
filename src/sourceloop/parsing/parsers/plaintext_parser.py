from __future__ import annotations

import re

from sourceloop.parsing.base import ParseSource, RawRowSet


class PlaintextParser:
    key = "plaintext"
    priority = 99
    enabled = True

    def supports(self, source: ParseSource) -> float:
        # Catch-all — always supports but with lowest confidence
        try:
            source.content.decode("utf-8")
            return 0.3
        except UnicodeDecodeError:
            return 0.0

    def parse(self, source: ParseSource) -> RawRowSet:
        text = source.content.decode("utf-8", errors="replace")
        rows: list[dict[str, str | None]] = []
        delimiters = re.compile(r"[\t,;|]+")

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        headers: list[str] | None = None

        for line in lines:
            parts = [p.strip() for p in delimiters.split(line)]
            if not any(parts):
                continue
            if headers is None:
                headers = [p.lower() for p in parts]
                continue
            row_dict: dict[str, str | None] = {}
            for i, h in enumerate(headers):
                row_dict[h] = parts[i] if i < len(parts) else None
            if any(v for v in row_dict.values() if v):
                rows.append(row_dict)

        return RawRowSet(
            rows=rows,
            detected_format="plaintext",
            parser_key=self.key,
            parser_confidence=0.4,
        )
