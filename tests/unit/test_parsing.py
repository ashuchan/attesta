from __future__ import annotations

import uuid

import pytest

from sourceloop.domain.bom import BomLine
from sourceloop.parsing.base import ParseSource, RawRowSet
from sourceloop.parsing.normalizer import normalize
from sourceloop.parsing.orchestrator import ParserOrchestrator, UnsupportedBomFormatError
from sourceloop.parsing.parsers.csv_parser import CsvParser
from sourceloop.parsing.parsers.plaintext_parser import PlaintextParser
from sourceloop.parsing.part_key import derive

# ─── part_key tests ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("mpn,expected", [
    ("STM32F103C8T6", "mpn:STM32F103C8T6"),
    ("stm32f103c8t6", "mpn:STM32F103C8T6"),  # lowercase → same
    ("STM32F103-C8T6", "mpn:STM32F103C8T6"),  # hyphen stripped
    ("STM32F103.C8T6", "mpn:STM32F103C8T6"),  # dot stripped
    ("STM32F103_C8T6", "mpn:STM32F103C8T6"),  # underscore stripped
    ("GRM188R61A106KE69D", "mpn:GRM188R61A106KE69D"),
    ("RC0402FR-0710KL", "mpn:RC0402FR0710KL"),
])
def test_mpn_key_collapse(mpn: str, expected: str) -> None:
    """MPNs that differ only in separators/case must collapse to the same key."""
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description=None,
        mpn=mpn, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="", part_class=None, parse_confidence=0.9,
    )
    assert derive(line) == expected


def test_no_mpn_gives_desc_key() -> None:
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="PCB1", raw_description="Custom 4-layer PCB",
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="", part_class=None, parse_confidence=0.5,
    )
    key = derive(line)
    assert key.startswith("desc:")
    assert len(key) == 5 + 16  # "desc:" + 16 hex chars


def test_desc_key_stable() -> None:
    """Same description always gives same key."""
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description="Custom PCB",
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="", part_class=None, parse_confidence=0.5,
    )
    assert derive(line) == derive(line)


def test_different_mpns_stay_distinct() -> None:
    """Near-miss MPNs that differ in a real character must NOT collapse."""
    line_a = BomLine(id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
                     line_no=1, raw_designator=None, raw_description=None,
                     mpn="STM32F103C8T6", manufacturer=None, quantity=1.0, unit="pcs",
                     normalized_part_key="", part_class=None, parse_confidence=0.9)
    line_b = BomLine(id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
                     line_no=2, raw_designator=None, raw_description=None,
                     mpn="STM32F103C6T6", manufacturer=None, quantity=1.0, unit="pcs",
                     normalized_part_key="", part_class=None, parse_confidence=0.9)
    assert derive(line_a) != derive(line_b)


# ─── Parser routing tests ─────────────────────────────────────────────────────

def test_csv_parser_supports_csv_extension() -> None:
    parser = CsvParser()
    source = ParseSource(content=b"mpn,qty\nSTM32,1", filename="bom.csv")
    assert parser.supports(source) > 0.0


def test_plaintext_is_catch_all() -> None:
    parser = PlaintextParser()
    source = ParseSource(content=b"any text content", filename="unknown.bin")
    assert parser.supports(source) > 0.0


def test_orchestrator_routes_csv_by_content() -> None:
    """A .txt file with CSV content should route to CsvParser, not PlaintextParser."""
    content = b"mpn,qty,manufacturer\nSTM32F103C8T6,1,STMicroelectronics\n"
    source = ParseSource(content=content, filename="bom.txt")  # .txt extension but CSV content
    orchestrator = ParserOrchestrator()
    parser = orchestrator.route(source)
    # CsvParser should win due to higher confidence from sniffing
    assert parser.key == "csv"


def test_orchestrator_raises_on_garbage() -> None:
    """Binary garbage with no parseable format raises UnsupportedBomFormatError."""
    content = bytes(range(256))  # binary garbage — fails utf-8, so PlaintextParser returns 0.0
    source = ParseSource(content=content, filename="garbage.bin")
    orchestrator = ParserOrchestrator()
    with pytest.raises(UnsupportedBomFormatError):
        orchestrator.route(source)


def test_normalizer_maps_headers() -> None:
    rawrowset = RawRowSet(
        rows=[{"mpn": "STM32F103C8T6", "qty": "1", "manufacturer": "STMicro", "description": "MCU"}],
        detected_format="csv",
        parser_key="csv",
        parser_confidence=0.9,
    )
    bom_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    lines = normalize(rawrowset, bom_id, tenant_id)
    assert len(lines) == 1
    assert lines[0].mpn == "STM32F103C8T6"
    assert lines[0].quantity == 1.0
    assert lines[0].manufacturer == "STMicro"
