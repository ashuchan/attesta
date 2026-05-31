from __future__ import annotations
from sourceloop.classification.base import ClassificationSignal
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass

BRANDED_MANUFACTURERS = {
    "texas instruments", "ti", "stmicroelectronics", "st", "stm",
    "murata", "tdk", "yageo", "samsung", "avx", "kemet",
    "nxp", "infineon", "microchip", "atmel", "nordic semiconductor",
    "espressif", "qualcomm", "broadcom", "maxim", "analog devices", "adi",
    "linear technology", "vishay", "rohm", "panasonic", "bourns",
    "molex", "amphenol", "te connectivity", "tyco", "jst",
    "winbond", "micron", "issi", "cypress", "lattice", "xilinx", "altera", "intel",
    "invensense", "bosch", "honeywell", "sensirion", "ams",
    "diodes incorporated", "onsemi", "on semiconductor", "fairchild",
    "richtek", "monolithic power", "mps",
}


class KnownManufacturerClassifier:
    key = "known_manufacturer"
    priority = 20
    enabled = True

    def classify(self, line: BomLine) -> ClassificationSignal:
        if not line.manufacturer:
            return ClassificationSignal(
                classifier_key=self.key,
                proposed_class=None,
                confidence=0.0,
                evidence={"reason": "no_manufacturer"},
            )
        mfr_lower = line.manufacturer.strip().lower()
        if mfr_lower in BRANDED_MANUFACTURERS:
            return ClassificationSignal(
                classifier_key=self.key,
                proposed_class=PartClass.A,
                confidence=0.8,
                evidence={"manufacturer": line.manufacturer},
            )
        return ClassificationSignal(
            classifier_key=self.key,
            proposed_class=None,
            confidence=0.0,
            evidence={"manufacturer": line.manufacturer, "reason": "unknown_manufacturer"},
        )
