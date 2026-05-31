from __future__ import annotations

import asyncio
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from sourceloop.config.loader import get_connectors_config, get_env
from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import OfferObservation, PriceLadder

log = structlog.get_logger()

NEXAR_QUERY = """
query SourceLoopMpn($mpn: String!, $limit: Int!, $country: String!, $currency: String!) {
  supSearchMpn(q: $mpn, limit: $limit, country: $country, currency: $currency) {
    hits
    results {
      part {
        mpn
        manufacturer { name }
        category { id name path }
        shortDescription
        specs { attribute { name shortname } displayValue }
        sellers {
          company { id name }
          offers {
            sku
            inventoryLevel
            moq
            orderMultiple
            packaging
            updated
            prices { quantity price currency }
            clickUrl
          }
        }
      }
    }
  }
}
"""


class NexarAuthError(Exception):
    pass


class NexarTokenManager:
    """
    Manages OAuth2 client_credentials token for Nexar.
    - Reads expires_in from response (NEVER hardcoded lifetime).
    - 60s safety skew before expiry.
    - asyncio.Lock prevents concurrent refresh races.
    """

    def __init__(self, client_id: str, client_secret: str, token_url: str) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._token_url = token_url
        self._access_token: str | None = None
        self._expires_at: float = 0.0
        self._lock = asyncio.Lock()
        self._SKEW_SECONDS = 60

    async def get_token(self) -> str:
        async with self._lock:
            if self._access_token and time.monotonic() < self._expires_at:
                return self._access_token
            await self._refresh()
            return self._access_token  # type: ignore[return-value]

    async def _refresh(self) -> None:
        """Fetch a new token with exponential backoff retry."""
        backoff = 1
        last_exc: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=30.0, connect=5, read=20)) as client:
                    resp = await client.post(
                        self._token_url,
                        data={
                            "grant_type": "client_credentials",
                            "client_id": self._client_id,
                            "client_secret": self._client_secret,
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    self._access_token = data["access_token"]
                    expires_in = int(data.get("expires_in", 3600))
                    self._expires_at = time.monotonic() + expires_in - self._SKEW_SECONDS
                    log.info("nexar_token_refreshed", expires_in=expires_in)
                    return
            except Exception as exc:
                last_exc = exc
                log.warning("nexar_token_refresh_failed", attempt=attempt, error=str(exc))
                if attempt < 2:
                    await asyncio.sleep(backoff)
                    backoff *= 2
        raise NexarAuthError(f"Token refresh failed after 3 attempts: {last_exc}")


class NexarClient:
    """
    Transport layer: rate limiting, retry, GraphQL error handling.
    - Shared httpx.AsyncClient with token injection.
    - Token-bucket rate limiter (config max_rps).
    - 429/Retry-After + 5xx backoff retry. Non-429 4xx not retried.
    - Always checks top-level GraphQL `errors` array even on HTTP 200.
    """

    def __init__(self, token_manager: NexarTokenManager) -> None:
        self._token_manager = token_manager
        cfg = get_connectors_config()
        self._max_rps = cfg.nexar.max_rps
        self._max_retries = cfg.nexar.max_retries
        self._monthly_soft_cap = cfg.nexar.monthly_quota_soft_cap
        self._request_count = 0
        # Simple token-bucket: track last request times
        self._request_times: list[float] = []
        self._graphql_url = get_env().nexar_graphql_url

    async def _throttle(self) -> None:
        """Client-side rate limit: max_rps per second."""
        now = time.monotonic()
        # Purge old entries outside the 1-second window
        self._request_times = [t for t in self._request_times if now - t < 1.0]
        if len(self._request_times) >= self._max_rps:
            sleep_for = 1.0 - (now - self._request_times[0])
            if sleep_for > 0:
                await asyncio.sleep(sleep_for)
        self._request_times.append(time.monotonic())

    async def query(self, variables: dict[str, Any]) -> dict[str, Any]:
        """Execute the GraphQL query with throttle + retry."""
        await self._throttle()

        self._request_count += 1
        if self._monthly_soft_cap > 0 and self._request_count >= self._monthly_soft_cap:
            log.warning("nexar_quota_soft_cap_reached", count=self._request_count)

        token = await self._token_manager.get_token()
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"query": NEXAR_QUERY, "variables": variables}

        backoff = 1
        last_exc: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                start = time.monotonic()
                async with httpx.AsyncClient(timeout=httpx.Timeout(timeout=30.0, connect=5, read=20)) as client:
                    resp = await client.post(self._graphql_url, json=payload, headers=headers)

                latency = time.monotonic() - start
                mpn = variables.get("mpn", "")

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", backoff))
                    log.warning("nexar_rate_limited", mpn=mpn, retry_after=retry_after, attempt=attempt)
                    await asyncio.sleep(retry_after)
                    backoff = min(backoff * 2, 60)
                    continue

                if resp.status_code >= 500:
                    log.warning("nexar_retry", mpn=mpn, status=resp.status_code, attempt=attempt)
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)
                    continue

                if resp.status_code >= 400:
                    log.error("nexar_failed", mpn=mpn, status=resp.status_code)
                    return {}  # Non-retryable client error

                body = resp.json()

                # Check GraphQL-level errors (can appear even on HTTP 200)
                if body.get("errors"):
                    messages = [e.get("message", "") for e in body["errors"]]
                    log.error("nexar_graphql_error", mpn=mpn, messages=messages)
                    if not body.get("data"):
                        return {}

                log.info("nexar_ok", mpn=mpn, latency_ms=round(latency * 1000))
                return body.get("data", {})

            except Exception as exc:
                last_exc = exc
                log.warning("nexar_request_error", error=str(exc), attempt=attempt)
                if attempt < self._max_retries:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60)

        log.error("nexar_failed_all_retries", error=str(last_exc))
        return {}


class NexarConnector:
    """
    Maps Nexar API response to domain OfferObservation objects.
    One observation per (seller x offer).
    """

    def __init__(self) -> None:
        env = get_env()
        self._country = env.nexar_country
        self._currency = env.nexar_currency
        self._limit = get_connectors_config().nexar.limit

        if not env.nexar_client_id or not env.nexar_client_secret:
            log.warning("nexar_credentials_missing")
            self.enabled = False
            self._client: NexarClient | None = None
            return

        self.enabled = True
        token_manager = NexarTokenManager(
            client_id=env.nexar_client_id,
            client_secret=env.nexar_client_secret,
            token_url=env.nexar_token_url,
        )
        self._client = NexarClient(token_manager)

    key = "nexar"
    priority = 10

    def supports(self, line: BomLine) -> bool:
        return bool(line.mpn and self.enabled)

    async def fetch(self, line: BomLine) -> list[OfferObservation]:
        if not self.enabled or self._client is None:
            log.warning("nexar_disabled", reason="no_credentials_or_disabled")
            return []

        if not line.mpn:
            return []

        variables = {
            "mpn": line.mpn,
            "limit": self._limit,
            "country": self._country,
            "currency": self._currency,
        }
        log.info("nexar_request", mpn=line.mpn)
        data = await self._client.query(variables)
        return self._map_response(data, line)

    def _map_response(self, data: dict[str, Any], line: BomLine) -> list[OfferObservation]:
        """Map seller x offer → one OfferObservation each."""
        search_result = data.get("supSearchMpn", {})
        hits = search_result.get("hits", 0)
        if hits == 0:
            return []

        results = search_result.get("results", [])
        observations = []
        now = datetime.now(UTC)

        for result in results:
            part = result.get("part", {})
            category_obj = part.get("category") or {}
            category = category_obj.get("name") or line.raw_description

            specs = {}
            for spec in part.get("specs", []):
                attr = spec.get("attribute", {})
                shortname = attr.get("shortname") or attr.get("name", "")
                if shortname:
                    specs[shortname] = spec.get("displayValue", "")

            for seller in part.get("sellers", []):
                company = seller.get("company", {})
                company_id = company.get("id", "unknown")
                company_name = company.get("name", "")
                supplier_id = f"nexar:{company_id}"

                for offer in seller.get("offers", []):
                    sku = offer.get("sku", "")
                    click_url = offer.get("clickUrl")

                    # Synthesize stable URL when clickUrl is absent
                    if not click_url:
                        click_url = f"nexar:{company_id}:{line.mpn}:{sku}"

                    # Build price ladder sorted by quantity
                    prices = offer.get("prices", [])
                    rungs = sorted(
                        [{"qty": p["quantity"], "price": p["price"], "currency": p["currency"]}
                         for p in prices if "quantity" in p and "price" in p],
                        key=lambda r: r["qty"],
                    )
                    price_ladder = PriceLadder(rungs=rungs) if rungs else None

                    moq = offer.get("moq")
                    # Never fabricate lead_time when absent
                    lead_time: str | None = None

                    listing_id = uuid.uuid4()
                    obs = OfferObservation(
                        listing_id=listing_id,
                        source="api",
                        tier="A",
                        captured_at=now,
                        normalized_part_key=line.normalized_part_key,
                        supplier_id=supplier_id,
                        category=category,
                        price_ladder=price_ladder,
                        moq=int(moq) if moq is not None else None,
                        lead_time=lead_time,
                        stock=offer.get("inventoryLevel"),
                        specs=specs,
                        supplier_snapshot={
                            "company_id": company_id,
                            "company_name": company_name,
                        },
                        screenshot_ref=None,
                        confidence=None,  # NullConfidence — Step 2
                        field_captured_at={
                            "price_ladder": now.isoformat(),
                            "stock": now.isoformat(),
                            "moq": now.isoformat(),
                            "specs": now.isoformat(),
                        },
                    )
                    observations.append(obs)

        return observations
