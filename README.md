# SourceLoop

> **This repo does not replace selling.** The Step-1 build and the Days 22–30
> outreach run in parallel. The first real BOM should come from a prospect
> conversation (Kaynes / CynLr / Niqo / Inito), not a fixture. If you have gone a
> week writing code without sending a pilot ask, stop and send three.

BOM parser + Tier-A connector + cache → real sourcing plan for branded electronics lines.

## Quick start

```bash
# 1. Start Postgres
docker-compose up -d

# 2. Install
pip install -e ".[dev]"

# 3. Configure
cp .env.example .env
# Fill NEXAR_CLIENT_ID / NEXAR_CLIENT_SECRET in .env

# 4. Migrate
alembic upgrade head

# 5. Parse a BOM (live Nexar data)
sourceloop parse path/to/bom.xlsx --tenant founder-internal --out plan.json

# 5a. Lint only (no sourcing — free BOM-linter lead magnet)
sourceloop parse path/to/bom.csv --lint-only

# 5b. Re-source existing BOM (prices may have moved)
sourceloop parse path/to/bom.xlsx --bom-id <uuid>

# Mock mode (no credentials needed — uses fixture offers)
SOURCELOOP_USE_MOCK=1 sourceloop parse tests/fixtures/boms/iot_board.csv
```

## Architecture

- **Multi-tenancy**: pooled DB, `tenant_id` on private tables, row-scoped at repository layer
- **Parser family**: xlsx / csv / pdf / plaintext — sniffs content, not extension
- **Classifier chain**: MPN presence + known manufacturer + description heuristics → Tier A/B/C
- **Connector registry**: Nexar (real), DigiKey/Mouser (stubs), Mock (CI)
- **Cache**: `offer_observation` append-only, `current_offer` projection, 5-day Tier-A TTL
- **Confidence**: NULL in Step 1 (scoring engine is Step 2)

## Cache economics

A common branded part (STM32, LDO) fetched once stays fresh for 5 days.
The second customer BOM containing that part is served from `current_offer` — zero Nexar calls.
This shared cache is the moat; it is deliberately NOT tenant-scoped.

## Running tests

```bash
pytest tests/unit/ -q                   # unit tests (no DB needed)
DATABASE_URL=... pytest tests/integration/  # integration (requires Postgres)
```
