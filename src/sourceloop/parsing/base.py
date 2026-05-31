from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ParseSource:
    """Wraps input — format-agnostic. Parsers inspect content, not bare path."""
    content: bytes
    filename: str
    declared_content_type: str | None = None
    _sniffed_mime: str | None = field(default=None, compare=False, hash=False)

    @property
    def sniffed_mime(self) -> str | None:
        return self._sniffed_mime


@dataclass(frozen=True)
class RawRowSet:
    rows: list[dict[str, str | None]]
    detected_format: str
    parser_key: str
    parser_confidence: float


@runtime_checkable
class BomFileParser(Protocol):
    key: str
    priority: int
    enabled: bool

    def supports(self, source: ParseSource) -> float:
        """Return 0.0 if not supported, else confidence 0..1."""
        ...

    def parse(self, source: ParseSource) -> RawRowSet:
        ...
