from __future__ import annotations

import re

from sourceloop.classification.base import ClassificationSignal
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass

COMMODITY_PATTERNS = re.compile(
    r"\b(custom|machined|fabricated|pcb|printed circuit|3d print|cable assembly|"
    r"harness|bracket|enclosure|housing|sheet metal|rubber|foam|label|sticker)\b",
    re.IGNORECASE,
)


class DescriptionHeuristicClassifier:
    key = "description_heuristic"
    priority = 30
    enabled = True

    def classify(self, line: BomLine) -> ClassificationSignal:
        desc = line.raw_description or ""
        if COMMODITY_PATTERNS.search(desc):
            return ClassificationSignal(
                classifier_key=self.key,
                proposed_class=PartClass.B,
                confidence=0.6,
                evidence={"description": desc[:100]},
            )
        return ClassificationSignal(
            classifier_key=self.key,
            proposed_class=None,
            confidence=0.0,
            evidence={"reason": "no_commodity_signal"},
        )
