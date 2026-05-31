from __future__ import annotations

import uuid

from sourceloop.classification.chain import ClassifierChain
from sourceloop.classification.classifiers.description_heuristic import (
    DescriptionHeuristicClassifier,
)
from sourceloop.classification.classifiers.known_manufacturer import KnownManufacturerClassifier
from sourceloop.classification.classifiers.mpn_presence import MpnPresenceClassifier
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass


def make_line(**kwargs: object) -> BomLine:
    defaults: dict[str, object] = dict(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description=None,
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="mpn:TEST", part_class=None, parse_confidence=0.9,
    )
    defaults.update(kwargs)
    return BomLine(**defaults)  # type: ignore[arg-type]


def test_mpn_presence_classifies_a():
    classifier = MpnPresenceClassifier()
    line = make_line(mpn="STM32F103C8T6")
    signal = classifier.classify(line)
    assert signal.proposed_class == PartClass.A
    assert signal.confidence > 0.0


def test_mpn_presence_abstains_on_no_mpn():
    classifier = MpnPresenceClassifier()
    line = make_line(mpn=None)
    signal = classifier.classify(line)
    assert signal.proposed_class is None


def test_known_manufacturer_classifies_a():
    classifier = KnownManufacturerClassifier()
    line = make_line(manufacturer="Texas Instruments")
    signal = classifier.classify(line)
    assert signal.proposed_class == PartClass.A


def test_description_heuristic_classifies_b():
    classifier = DescriptionHeuristicClassifier()
    line = make_line(raw_description="Custom PCB machined housing")
    signal = classifier.classify(line)
    assert signal.proposed_class == PartClass.B


def test_chain_all_abstain_defaults_to_b():
    chain = ClassifierChain()
    # Line with no MPN, unknown manufacturer, no commodity description
    line = make_line(mpn=None, manufacturer="XYZ Corp Unknown", raw_description="some widget")
    part_class, signals = chain.classify(line)
    assert part_class == PartClass.B


def test_chain_classifies_off_normalized_bom_line():
    """Classifiers MUST operate only on BomLine — not raw bytes."""
    chain = ClassifierChain()
    line = make_line(mpn="STM32F103C8T6", manufacturer="STMicroelectronics")
    part_class, signals = chain.classify(line)
    assert part_class == PartClass.A
    assert any(s.proposed_class == PartClass.A for s in signals)


def test_chain_highest_confidence_wins():
    chain = ClassifierChain()
    # MPN present AND known manufacturer → A (both signal A, higher confidence wins)
    line = make_line(mpn="GRM188R61A106KE69D", manufacturer="Murata")
    part_class, signals = chain.classify(line)
    assert part_class == PartClass.A


def test_signals_preserved_for_provenance():
    chain = ClassifierChain()
    line = make_line(mpn="STM32F103C8T6", manufacturer="STMicroelectronics")
    _, signals = chain.classify(line)
    keys = {s.classifier_key for s in signals}
    # All enabled classifiers should emit a signal
    assert "mpn_presence" in keys
    assert "known_manufacturer" in keys
    assert "description_heuristic" in keys
