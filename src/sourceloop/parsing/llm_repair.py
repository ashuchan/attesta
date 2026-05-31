from __future__ import annotations

import json

import structlog

from sourceloop.domain.bom import BomLine

log = structlog.get_logger()

REPAIR_SCHEMA = {
    "mpn": "string or null",
    "manufacturer": "string or null",
    "quantity": "number or null",
    "unit": "string or null",
}


async def repair(line: BomLine, source_context: str = "") -> dict[str, object]:
    """
    Claude fallback for low-confidence BomLines.
    Returns a dict with extracted fields; caller merges back into the line.
    Only called when parse_confidence < threshold.
    """
    import os
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        log.warning("llm_repair_skipped", reason="no_api_key", line_no=line.line_no)
        return {}

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key)
        prompt = (
            f"Extract electronics BOM fields from this line. "
            f"Return ONLY valid JSON matching this schema: {json.dumps(REPAIR_SCHEMA)}.\n\n"
            f"Raw data: {source_context}\n"
            f"Description: {line.raw_description!r}\n"
            f"Designator: {line.raw_designator!r}"
        )
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        text = response.content[0].text if response.content else "{}"
        # Extract JSON from response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        log.warning("llm_repair_failed", error=str(e), line_no=line.line_no)
    return {}
