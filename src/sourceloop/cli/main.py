from __future__ import annotations

import asyncio
import sys
import uuid
from pathlib import Path

import click
import structlog

log = structlog.get_logger()


@click.group()
def cli() -> None:
    """SourceLoop — BOM-to-sourcing-plan pipeline."""
    import logging

    import structlog as sl

    sl.configure(
        processors=[
            sl.contextvars.merge_contextvars,
            sl.processors.add_log_level,
            sl.processors.TimeStamper(fmt="iso"),
            sl.dev.ConsoleRenderer(),
        ],
        wrapper_class=sl.make_filtering_bound_logger(logging.INFO),
        logger_factory=sl.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


@cli.command()
@click.argument("path", type=click.Path(exists=True))
@click.option("--tenant", default=None, help="Tenant slug (default: founder-internal)")
@click.option("--out", default=None, help="Output file path (default: stdout)")
@click.option("--bom-id", default=None, help="Re-source existing BOM by ID (skip re-parse)")
@click.option("--lint-only", is_flag=True, help="Parse only, no sourcing (BOM linter)")
def parse(
    path: str,
    tenant: str | None,
    out: str | None,
    bom_id: str | None,
    lint_only: bool,
) -> None:
    """Parse a BOM file and generate a sourcing plan."""
    asyncio.run(_parse_async(path, tenant, out, bom_id, lint_only))


async def _parse_async(
    path: str,
    tenant_slug: str | None,
    out: str | None,
    bom_id_str: str | None,
    lint_only: bool,
) -> None:
    from sourceloop.config.loader import get_app_settings
    from sourceloop.db.engine import get_session_factory
    from sourceloop.output.json_renderer import render_lint, render_plan
    from sourceloop.parsing.base import ParseSource
    from sourceloop.parsing.pipeline import BomParser
    from sourceloop.repositories.bom_repo import BomRepository
    from sourceloop.repositories.customer_repo import CustomerRepository
    from sourceloop.sourcing.tier_a_service import SourcingService
    from sourceloop.tenancy.context import TenantContext

    settings = get_app_settings()
    slug = tenant_slug or settings.default_tenant_slug

    factory = get_session_factory()

    async with factory() as session:
        # Resolve tenant
        TenantContext.set(uuid.UUID(int=0))  # placeholder
        customer_repo = CustomerRepository(session)
        tenant_row = await customer_repo.get_tenant_by_slug(slug)
        if tenant_row is None:
            click.echo(f"Error: tenant '{slug}' not found. Run alembic upgrade head first.", err=True)
            sys.exit(1)
        TenantContext.set(tenant_row.id)

        structlog.contextvars.bind_contextvars(tenant_id=str(tenant_row.id))

        parse_result = None
        existing_bom_id: uuid.UUID | None = None

        if bom_id_str:
            # --bom-id: re-source existing BOM without re-parsing
            existing_bom_id = uuid.UUID(bom_id_str)
            bom_repo = BomRepository(session)
            bom = await bom_repo.get_bom(existing_bom_id)
            if bom is None:
                click.echo(f"Error: BOM {bom_id_str} not found for tenant {slug}", err=True)
                sys.exit(1)
            click.echo(
                f"Re-sourcing existing BOM: {bom.source_filename} "
                f"({bom.line_count} lines)",
                err=True,
            )
        else:
            # Default: parse the file as a new BOM
            file_path = Path(path)
            content = file_path.read_bytes()
            source = ParseSource(content=content, filename=file_path.name)

            parser = BomParser()
            parse_result = await parser.parse(source)

            if lint_only:
                output = render_lint(parse_result)
                summary = (
                    f"Parsed {len(parse_result.lines)} lines | "
                    f"format={parse_result.original_format} | "
                    f"avg_confidence={parse_result.parse_confidence_avg:.2f}"
                )
                click.echo(summary, err=True)
                if out:
                    Path(out).write_text(output)
                else:
                    click.echo(output)
                return

            # Persist BOM + lines
            bom_repo = BomRepository(session)
            bom = await bom_repo.create_bom(parse_result)
            await bom_repo.create_lines(bom.id, parse_result.lines)
            await session.commit()
            existing_bom_id = bom.id
            click.echo(
                f"Parsed {len(parse_result.lines)} lines from {file_path.name} "
                f"[{parse_result.original_format}] → bom_id={bom.id}",
                err=True,
            )

    # Source the BOM
    async with factory() as sourcing_session:
        TenantContext.set(tenant_row.id)
        service = SourcingService(sourcing_session)
        plan = await service.source_bom(existing_bom_id)  # type: ignore[arg-type]

    cache_hits = sum(1 for line in plan.lines if line.unsourced_reason is None and line.offer_snapshot)
    total = len(plan.lines)
    summary = (
        f"Sourced: {cache_hits}/{total} lines | "
        f"Tier-A coverage: {plan.tier_a_coverage_pct:.1f}% | "
        f"plan_id={plan.id}"
    )
    click.echo(summary, err=True)

    output = render_plan(plan, parse_result)
    if out:
        Path(out).write_text(output)
        click.echo(f"Plan written to {out}", err=True)
    else:
        click.echo(output)
