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


@cli.command()
@click.option("--seed-file", default=None, help="Path to seed_parts.yaml (default: config/seed_parts.yaml)")
@click.option("--ahead-months", default=3, help="Months of partitions to ensure ahead")
@click.option("--dry-run", is_flag=True, help="Report which parts would be fetched without spending quota")
@click.option("--category", default=None, help="Filter seed parts by category")
@click.option("--limit", default=None, type=int, help="Limit number of parts to warm")
def warmup(seed_file: str | None, ahead_months: int, dry_run: bool, category: str | None, limit: int | None) -> None:
    """Pre-warm the offer cache from seed_parts.yaml and ensure DB partitions."""
    asyncio.run(_warmup_async(seed_file, ahead_months, dry_run, category, limit))


async def _warmup_async(
    seed_file: str | None,
    ahead_months: int,
    dry_run: bool,
    category: str | None,
    limit: int | None,
) -> None:
    from sourceloop.config.loader import get_seed_parts
    from sourceloop.db.engine import get_engine, get_session_factory
    from sourceloop.db.partitioning import ensure_partitions
    from sourceloop.warmup.service import WarmupService

    if dry_run:
        click.echo("DRY RUN — no Nexar calls will be made.", err=True)

    # Step 1: ensure partitions (idempotent DDL — safe even in dry-run)
    engine = get_engine()
    async with engine.connect() as conn:
        created = await ensure_partitions(conn, ahead_months=ahead_months)
        await conn.commit()
    click.echo(f"Partition statements executed: {created}", err=True)

    # Step 2: load seed parts
    if seed_file:
        import yaml
        with open(seed_file) as f:
            raw = yaml.safe_load(f)
        parts = raw.get("parts", [])
    else:
        parts = get_seed_parts()

    if category:
        parts = [p for p in parts if p.get("category", "").lower() == category.lower()]
    if limit:
        parts = parts[:limit]

    if not parts:
        click.echo("No seed parts found.", err=True)
        return

    click.echo(f"Seed parts to warm: {len(parts)}", err=True)

    if dry_run:
        # Check cache without fetching
        factory = get_session_factory()
        async with factory() as session:
            service = WarmupService(session)
            would_fetch, already_warm = await service.dry_run_parts(parts)
        click.echo(
            f"Dry-run complete: {already_warm} already warm (would skip), "
            f"{would_fetch} would be fetched.",
            err=True,
        )
        return

    # Step 3: warm (real fetch)
    factory = get_session_factory()
    async with factory() as session:
        service = WarmupService(session)
        results = await service.warm_parts(parts)
        await session.commit()

    total_obs = sum(results.values())
    click.echo(
        f"Warmup complete: {len(parts)} parts, {total_obs} observations appended.",
        err=True,
    )
    for mpn, count in results.items():
        click.echo(f"  {mpn}: {count}", err=True)


@cli.group("db")
def db_group() -> None:
    """Database management commands."""


@db_group.command("ensure-partitions")
@click.option("--ahead-months", default=3, show_default=True, help="Months of partitions to ensure ahead of today")
def db_ensure_partitions(ahead_months: int) -> None:
    """Ensure monthly partitions exist for offer_observation, demand_event, score_log."""
    asyncio.run(_db_ensure_partitions_async(ahead_months))


async def _db_ensure_partitions_async(ahead_months: int) -> None:
    from sourceloop.db.engine import get_engine
    from sourceloop.db.partitioning import ensure_partitions

    engine = get_engine()
    async with engine.connect() as conn:
        created = await ensure_partitions(conn, ahead_months=ahead_months)
        await conn.commit()
    click.echo(f"Partition statements executed: {created} (idempotent — safe to re-run)", err=True)
