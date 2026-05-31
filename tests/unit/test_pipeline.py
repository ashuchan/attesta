from __future__ import annotations
import pytest
import uuid
from unittest.mock import AsyncMock, patch
from sourceloop.parsing.base import ParseSource
from sourceloop.parsing.pipeline import BomParser
from sourceloop.tenancy.context import TenantContext


def setup_tenant() -> None:
    TenantContext.set(uuid.uuid4())


@pytest.mark.asyncio
async def test_pipeline_parse_csv():
    setup_tenant()
    content = b"MPN,Qty,Manufacturer,Description\nSTM32F103C8T6,1,STMicro,MCU\nESP8266EX,2,Espressif,WiFi\n"
    source = ParseSource(content=content, filename="bom.csv")
    parser = BomParser()
    result = await parser.parse(source)
    assert len(result.lines) == 2
    assert result.original_format == "csv"
    assert result.lines[0].normalized_part_key.startswith("mpn:")


@pytest.mark.asyncio
async def test_pipeline_parse_xlsx():
    import io
    import openpyxl
    setup_tenant()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["MPN", "Qty", "Manufacturer"])
    ws.append(["STM32F103C8T6", 1, "STMicro"])
    buf = io.BytesIO()
    wb.save(buf)
    content = buf.getvalue()
    source = ParseSource(content=content, filename="bom.xlsx")
    parser = BomParser()
    result = await parser.parse(source)
    assert len(result.lines) >= 1
    assert result.original_format == "xlsx"


@pytest.mark.asyncio
async def test_pipeline_derives_part_key():
    setup_tenant()
    content = b"MPN,Qty\nSTM32F103-C8T6,1\n"
    source = ParseSource(content=content, filename="bom.csv")
    parser = BomParser()
    result = await parser.parse(source)
    assert result.lines[0].normalized_part_key == "mpn:STM32F103C8T6"


@pytest.mark.asyncio
async def test_pipeline_no_mpn_desc_key():
    setup_tenant()
    content = b"Description,Qty\nCustom PCB 100x80mm,1\n"
    source = ParseSource(content=content, filename="bom.csv")
    parser = BomParser()
    result = await parser.parse(source)
    assert result.lines[0].normalized_part_key.startswith("desc:")


@pytest.mark.asyncio
async def test_pipeline_llm_repair_not_called_for_high_confidence():
    """High-confidence lines should not trigger LLM repair."""
    setup_tenant()
    content = b"MPN,Qty,Manufacturer,Description\nSTM32F103C8T6,1,STMicro,MCU\n"
    source = ParseSource(content=content, filename="bom.csv")
    parser = BomParser()
    # repair is imported inside the function, not at module level
    # so we patch the module it lives in
    import sourceloop.parsing.llm_repair as llm_repair_mod
    with patch.object(llm_repair_mod, "repair", new_callable=AsyncMock) as mock_repair:
        result = await parser.parse(source)
    # parse_confidence = 0.5 + 0.3(mpn) + 0.1(qty) + 0.1(desc) = 1.0 >= 0.5 threshold → no repair
    mock_repair.assert_not_called()


@pytest.mark.asyncio
async def test_pipeline_empty_csv_returns_no_lines():
    setup_tenant()
    content = b"MPN,Qty\n"
    source = ParseSource(content=content, filename="bom.csv")
    parser = BomParser()
    result = await parser.parse(source)
    assert result.lines == []


@pytest.mark.asyncio
async def test_pipeline_returns_parse_result_metadata():
    setup_tenant()
    content = b"MPN,Qty\nSTM32F103C8T6,1\n"
    source = ParseSource(content=content, filename="test_bom.csv")
    parser = BomParser()
    result = await parser.parse(source)
    assert result.source_filename == "test_bom.csv"
    assert result.parser_key == "csv"
    assert result.parse_confidence_avg > 0


@pytest.mark.asyncio
async def test_pipeline_unrecognized_columns_no_crash():
    """Row with unrecognized columns should not crash the pipeline."""
    setup_tenant()
    content = b"col_a,col_b\nval_a,val_b\n"
    source = ParseSource(content=content, filename="bom.csv")
    parser = BomParser()
    result = await parser.parse(source)
    # A row with unrecognized cols → no mpn, no qty, no desc → confidence = 0.5
    assert result is not None
    assert len(result.lines) == 1


@pytest.mark.asyncio
async def test_pipeline_llm_repair_called_for_low_confidence_line():
    """Lines with parse_confidence < 0.5 should trigger LLM repair."""
    import dataclasses
    from sourceloop.parsing.base import RawRowSet
    from sourceloop.parsing.orchestrator import ParserOrchestrator
    from unittest.mock import MagicMock

    setup_tenant()

    mock_rawrowset = RawRowSet(
        rows=[{"col_a": "garbled_data", "col_b": "12345"}],
        detected_format="csv", parser_key="csv", parser_confidence=0.4,
    )

    mock_parser = MagicMock()
    mock_parser.key = "csv"
    mock_parser.parse = MagicMock(return_value=mock_rawrowset)

    mock_orchestrator = MagicMock(spec=ParserOrchestrator)
    mock_orchestrator.route = MagicMock(return_value=mock_parser)

    bom_parser = BomParser(orchestrator=mock_orchestrator)
    content = b"col_a,col_b\ngarbled_data,12345\n"
    source = ParseSource(content=content, filename="bom.csv")

    # Inject a low-confidence line via normalizer mock
    import sourceloop.domain.bom as bom_module

    low_conf_line = bom_module.BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description=None,
        mpn=None, manufacturer=None, quantity=None, unit=None,
        normalized_part_key="", part_class=None, parse_confidence=0.3,  # < 0.5 threshold
    )

    async def mock_repair_fn(line, context_str):
        return {"mpn": "REPAIRED123", "manufacturer": "RepairCo"}

    with patch("sourceloop.parsing.pipeline.normalize", return_value=[low_conf_line]), \
         patch("sourceloop.parsing.llm_repair.repair", side_effect=mock_repair_fn) as mock_repair_patch:
        result = await bom_parser.parse(source)

    # repair was called because confidence < 0.5
    mock_repair_patch.assert_called_once()
    assert result is not None
