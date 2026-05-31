from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass


def make_line() -> BomLine:
    return BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="Microcontroller ARM Cortex-M3",
        mpn=None, manufacturer=None, quantity=None, unit=None,
        normalized_part_key="desc:abc", part_class=PartClass.B,
        parse_confidence=0.4,
    )


@pytest.mark.asyncio
async def test_repair_skipped_when_no_api_key():
    from sourceloop.parsing.llm_repair import repair
    line = make_line()
    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": ""}):
        result = await repair(line, "some context")
    assert result == {}


@pytest.mark.asyncio
async def test_repair_calls_anthropic_when_api_key_set():
    from sourceloop.parsing.llm_repair import repair
    line = make_line()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"mpn": "STM32F103C8T6", "manufacturer": "ST", "quantity": 1, "unit": "pcs"}')]

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test_key"}), \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await repair(line, "raw context here")

    assert result.get("mpn") == "STM32F103C8T6"
    assert result.get("manufacturer") == "ST"


@pytest.mark.asyncio
async def test_repair_returns_empty_on_anthropic_exception():
    from sourceloop.parsing.llm_repair import repair
    line = make_line()

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(side_effect=Exception("API error"))

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test_key"}), \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await repair(line, "context")

    assert result == {}


@pytest.mark.asyncio
async def test_repair_handles_malformed_json_response():
    from sourceloop.parsing.llm_repair import repair
    line = make_line()

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="not valid json at all")]

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test_key"}), \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await repair(line, "context")

    # No JSON braces → returns {}
    assert result == {}


@pytest.mark.asyncio
async def test_repair_handles_empty_content():
    from sourceloop.parsing.llm_repair import repair
    line = make_line()

    mock_response = MagicMock()
    mock_response.content = []

    mock_client = MagicMock()
    mock_client.messages = MagicMock()
    mock_client.messages.create = AsyncMock(return_value=mock_response)

    with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test_key"}), \
         patch("anthropic.AsyncAnthropic", return_value=mock_client):
        result = await repair(line, "context")

    assert result == {}
