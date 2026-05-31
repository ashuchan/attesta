from __future__ import annotations

import io

from sourceloop.parsing.base import ParseSource, RawRowSet

PDF_MAGIC = b"%PDF"


class PdfParser:
    key = "pdf"
    priority = 30
    enabled = True

    def supports(self, source: ParseSource) -> float:
        if source.content[:4] == PDF_MAGIC:
            return 0.9
        if source.filename.lower().endswith(".pdf"):
            return 0.7
        return 0.0

    def parse(self, source: ParseSource) -> RawRowSet:
        import pdfplumber
        rows: list[dict[str, str | None]] = []
        confidence = 0.5

        with pdfplumber.open(io.BytesIO(source.content)) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                if tables:
                    for table in tables:
                        extracted = self._table_to_rows(table)
                        rows.extend(extracted)
                    confidence = 0.75
                else:
                    # Fallback: text layout heuristics
                    text = page.extract_text() or ""
                    extracted = self._text_to_rows(text)
                    rows.extend(extracted)
                    confidence = 0.4

        return RawRowSet(
            rows=rows,
            detected_format="pdf",
            parser_key=self.key,
            parser_confidence=confidence,
        )

    def _table_to_rows(self, table: list[list[str | None]]) -> list[dict[str, str | None]]:
        if not table or len(table) < 2:
            return []
        headers = [str(h).strip().lower() if h else f"col_{i}" for i, h in enumerate(table[0])]
        result = []
        for row in table[1:]:
            if not any(c for c in row if c):
                continue
            row_dict: dict[str, str | None] = {}
            for i, h in enumerate(headers):
                val = row[i] if i < len(row) else None
                row_dict[h] = str(val).strip() if val else None
            result.append(row_dict)
        return result

    def _text_to_rows(self, text: str) -> list[dict[str, str | None]]:
        """Best-effort text layout parsing."""
        rows = []
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        for line in lines:
            parts = line.split()
            if len(parts) >= 2:
                rows.append({"raw_text": line, "tokens": " ".join(parts)})
        return rows
