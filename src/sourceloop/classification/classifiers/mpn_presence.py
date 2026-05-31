from __future__ import annotations
import re
from sourceloop.classification.base import ClassificationSignal
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass

MPN_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9\-_.]{3,}$", re.IGNORECASE)


class MpnPresenceClassifier:
    key = "mpn_presence"
    priority = 10
    enabled = True

    def classify(self, line: BomLine) -> ClassificationSignal:
        if line.mpn and MPN_PATTERN.match(line.mpn.strip()):
            return ClassificationSignal(
                classifier_key=self.key,
                proposed_class=PartClass.A,
                confidence=0.7,
                evidence={"mpn": line.mpn},
            )
        return ClassificationSignal(
            classifier_key=self.key,
            proposed_class=None,
            confidence=0.0,
            evidence={"reason": "no_valid_mpn"},
        )
