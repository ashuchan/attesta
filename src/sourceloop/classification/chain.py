from __future__ import annotations

import structlog

from sourceloop.classification.base import ClassificationSignal, PartClassifier
from sourceloop.classification.classifiers.description_heuristic import (
    DescriptionHeuristicClassifier,
)
from sourceloop.classification.classifiers.known_manufacturer import KnownManufacturerClassifier
from sourceloop.classification.classifiers.mpn_presence import MpnPresenceClassifier
from sourceloop.classification.classifiers.spec_vector import SpecVectorClassifier
from sourceloop.config.loader import get_classifiers_config
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass

log = structlog.get_logger()

_CLASSIFIER_CLASSES: dict[str, type] = {
    "mpn_presence": MpnPresenceClassifier,
    "known_manufacturer": KnownManufacturerClassifier,
    "description_heuristic": DescriptionHeuristicClassifier,
    "spec_vector": SpecVectorClassifier,
}


class ClassifierChain:
    """
    Runs enabled classifier strategies, collects signals, aggregates.
    Step 1 aggregator: highest-confidence non-abstaining signal wins; default B if all abstain.
    The aggregator is a swappable strategy — Step 2 replaces it with the §6 scoring engine.
    """

    def __init__(self) -> None:
        cfg = get_classifiers_config()
        self._classifiers: list[PartClassifier] = []
        for entry in sorted(cfg.classifiers, key=lambda e: e.priority):
            if not entry.enabled:
                continue
            cls = _CLASSIFIER_CLASSES.get(entry.key)
            if cls is None:
                continue
            instance = cls()
            self._classifiers.append(instance)  # type: ignore[arg-type]
        self._aggregator = cfg.aggregator

    def classify(self, line: BomLine) -> tuple[PartClass, list[ClassificationSignal]]:
        """
        Classifiers operate on the normalized BomLine ONLY — never on raw file bytes.
        This keeps classifiers format-agnostic.
        Returns (PartClass, signals) for provenance persistence.
        """
        signals: list[ClassificationSignal] = []
        for classifier in self._classifiers:
            signal = classifier.classify(line)
            signals.append(signal)

        return self._aggregate(signals), signals

    def _aggregate(self, signals: list[ClassificationSignal]) -> PartClass:
        """highest_confidence_else_b: pick the highest-confidence non-abstaining signal."""
        non_abstaining = [s for s in signals if s.proposed_class is not None and s.confidence > 0.0]
        if not non_abstaining:
            return PartClass.B  # default: unclassifiable → treat as Tier-B

        best = max(non_abstaining, key=lambda s: s.confidence)
        return best.proposed_class  # type: ignore[return-value]
