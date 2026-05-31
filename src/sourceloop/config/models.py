from __future__ import annotations

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class ConnectorEntry(BaseModel):
    key: str
    enabled: bool
    priority: int


class NexarConfig(BaseModel):
    max_rps: int = 5
    max_retries: int = 3
    monthly_quota_soft_cap: int = 0
    limit: int = 3


class ConnectorsConfig(BaseModel):
    connectors: list[ConnectorEntry]
    nexar: NexarConfig = Field(default_factory=NexarConfig)


class ParserEntry(BaseModel):
    key: str
    enabled: bool
    priority: int


class ParsersConfig(BaseModel):
    parsers: list[ParserEntry]


class ClassifierEntry(BaseModel):
    key: str
    enabled: bool
    priority: int


class ClassifiersConfig(BaseModel):
    aggregator: str
    classifiers: list[ClassifierEntry]


class RefreshFieldPolicy(BaseModel):
    volatility: str
    ttl_days: int | None = None
    ttl_hours: int | None = None
    strategy: str


class RefreshPoliciesConfig(BaseModel):
    A: dict[str, RefreshFieldPolicy]
    B: dict[str, RefreshFieldPolicy]


class ScoringStrategyEntry(BaseModel):
    signals: list[str]
    weights: dict[str, float]
    aggregator: str
    bands: dict[str, float] = Field(default_factory=lambda: {"high": 80.0, "medium": 50.0})
    hard_flags: list[str] = Field(default_factory=list)


class RuleEntry(BaseModel):
    when: str
    then: str


class WarmupPacingConfig(BaseModel):
    max_calls_per_day: int = 200
    spread_over_hours: int = 8
    max_rps_fraction: float = 0.5


class WarmupConfig(BaseModel):
    pacing: WarmupPacingConfig = Field(default_factory=WarmupPacingConfig)


class AppSettings(BaseModel):
    bom_sla_minutes: int = 90
    default_limit: int = 3
    default_tenant_slug: str = "founder-internal"


class EnvSettings(BaseSettings):
    database_url: str = "postgresql+asyncpg://sourceloop:sourceloop@localhost:5432/sourceloop"
    nexar_client_id: str = ""
    nexar_client_secret: str = ""
    nexar_token_url: str = "https://identity.nexar.com/connect/token"
    nexar_graphql_url: str = "https://api.nexar.com/graphql"
    nexar_country: str = "IN"
    nexar_currency: str = "INR"
    anthropic_api_key: str = ""
    sourceloop_default_tenant: str = "founder-internal"
    sourceloop_use_mock: bool = False
    log_level: str = "INFO"

    model_config = {"env_file": ".env", "extra": "ignore"}
