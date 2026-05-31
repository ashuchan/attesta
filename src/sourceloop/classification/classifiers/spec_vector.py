from __future__ import annotations

from sourceloop.classification.base import ClassificationSignal
from sourceloop.domain.bom import BomLine


class SpecVectorClassifier:
    """
    Registered but INERT in Step 1. Vector-retrieval custom-part matcher.
    Wired as a seam; wakes up when the embedding index exists (Step 2+).
    """
    key = "spec_vector"
    priority = 40
    enabled = False

    def classify(self, line: BomLine) -> ClassificationSignal:
        # Always abstain — Step 1 seam
        return ClassificationSignal(
            classifier_key=self.key,
            proposed_class=None,
            confidence=0.0,
            evidence={"reason": "inert_in_step1"},
        )
