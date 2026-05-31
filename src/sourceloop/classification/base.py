from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass


@dataclass(frozen=True)
class ClassificationSignal:
    classifier_key: str
    proposed_class: PartClass | None  # None = abstain
    confidence: float  # 0..1
    evidence: dict[str, Any]


@runtime_checkable
class PartClassifier(Protocol):
    key: str
    priority: int
    enabled: bool

    def classify(self, line: BomLine) -> ClassificationSignal:
        ...
