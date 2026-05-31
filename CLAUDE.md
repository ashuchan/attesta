# SourceLoop — Build Rules for Claude Code

You are building Step 1 of the SourceLoop build sequence: BOM parsing + Tier-A
connectors + Tier-A cache. Nothing else.

## Hard boundaries — do NOT cross
- NO scoring/confidence logic. `ConfidenceProvider` returns None. The `confidence`
  column exists but stays NULL. Scoring is Step 2.
- NO ranking, post-processors, hotness scheduler, vision, stealth scraping, RFQ.
- NO web framework, no payments, no auth UI.
- Tier-B/C lines are CLASSIFIED and marked unsourced. Do not acquire them.

## Multi-tenancy — the rule that must never break
- Private tables (tenant, customer_profile, customer_detail, bom, bom_line,
  sourced_plan, plan_line, demand_event) carry tenant_id; access ONLY via
  TenantScopedRepository which auto-scopes every query.
- Global tables (supplier, listing, offer_observation, current_offer, hotness)
  have NO tenant_id and are accessed via plain repositories. The supplier cache is
  shared across all tenants ON PURPOSE — that is the moat. Never add tenant_id to it.
- A read returning a foreign tenant_id must raise CrossTenantAccessError.

## Nexar connector (§7A) — specifics that must not be improvised
- GraphQL only: single POST to https://api.nexar.com/graphql with {query, variables}.
- OAuth2 client_credentials at https://identity.nexar.com/connect/token; form-encoded
  body; read expires_in from the response, NEVER hardcode token lifetime; refresh with
  a 60s skew under an asyncio.Lock. Authorization: Bearer <token>.
- Three classes: NexarTokenManager (auth), NexarClient (transport/throttle/retry),
  NexarConnector (mapping). One responsibility each.
- Always set country:"IN", currency:"INR" in the query (config-driven). US default is wrong.
- Rate limits are per-plan, not a fixed constant: client-side throttle (config max_rps,
  default 5) + reactive 429/Retry-After backoff. Check the GraphQL top-level `errors`
  array even on HTTP 200.
- Map seller×offer → one OfferObservation each. Append-only to offer_observation;
  advance current_offer projection. confidence stays NULL. Namespace supplier ids as
  `nexar:{companyId}`. Leave lead_time null when absent — never fabricate.
- Tier-A price TTL = 5 days: if current_offer price is fresher, DO NOT call the API.

## Design discipline
- Small classes, one responsibility each. Interfaces are typing.Protocol.
- Parsing is a FAMILY: one BomFileParser strategy per format behind a ParserOrchestrator
  that sniffs CONTENT (not extension) and routes to highest-confidence parser.
- Classification is a CHAIN of small PartClassifier strategies emitting ClassificationSignal.
- parsers, classifiers, connectors are three PARALLEL registries. Do NOT merge them.
- Config precedence: env > YAML > coded default. Only loader reads os.environ.
- Cache writes are append-only. Never UPDATE or DELETE an offer_observation.
