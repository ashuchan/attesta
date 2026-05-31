from __future__ import annotations
import uuid
import dataclasses
import structlog
from sourceloop.parsing.base import ParseSource
from sourceloop.parsing.orchestrator import ParserOrchestrator
from sourceloop.parsing.normalizer import normalize
from sourceloop.parsing.part_key import derive
from sourceloop.domain.bom import ParseResult
from sourceloop.tenancy.context import TenantContext

log = structlog.get_logger()

LLM_REPAIR_THRESHOLD = 0.5


class BomParser:
    """Full parse pipeline: orchestrate → normalize → key derivation."""

    def __init__(self, orchestrator: ParserOrchestrator | None = None) -> None:
        self._orchestrator = orchestrator or ParserOrchestrator()

    async def parse(self, source: ParseSource) -> ParseResult:
        tenant_id = TenantContext.get()
        bom_id = uuid.uuid4()

        # Step 1: Route to the right parser
        parser = self._orchestrator.route(source)
        rawrowset = parser.parse(source)

        # Step 2: Normalize raw rows → BomLines
        lines = normalize(rawrowset, bom_id, tenant_id)

        # Step 3: LLM repair for low-confidence lines
        repaired_lines = []
        for line in lines:
            if line.parse_confidence < LLM_REPAIR_THRESHOLD:
                from sourceloop.parsing.llm_repair import repair
                context_str = str(rawrowset.rows[line.line_no - 1]) if line.line_no <= len(rawrowset.rows) else ""
                updates = await repair(line, context_str)
                if updates:
                    line = dataclasses.replace(
                        line,
                        mpn=updates.get("mpn") or line.mpn,  # type: ignore[arg-type]
                        manufacturer=updates.get("manufacturer") or line.manufacturer,  # type: ignore[arg-type]
                        quantity=updates.get("quantity") or line.quantity,  # type: ignore[arg-type]
                        unit=updates.get("unit") or line.unit,  # type: ignore[arg-type]
                    )
            repaired_lines.append(line)

        # Step 4: Derive normalized_part_key for each line
        keyed_lines = []
        for line in repaired_lines:
            key = derive(line)
            keyed_lines.append(dataclasses.replace(line, normalized_part_key=key))

        avg_confidence = (
            sum(l.parse_confidence for l in keyed_lines) / len(keyed_lines)
            if keyed_lines else 0.0
        )

        log.info(
            "bom_parsed",
            filename=source.filename,
            parser=parser.key,
            line_count=len(keyed_lines),
            avg_confidence=avg_confidence,
        )

        return ParseResult(
            lines=keyed_lines,
            source_filename=source.filename,
            original_format=rawrowset.detected_format,
            parse_confidence_avg=avg_confidence,
            parser_key=parser.key,
            parser_confidence=rawrowset.parser_confidence,
        )
