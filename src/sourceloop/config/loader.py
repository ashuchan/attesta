from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from .models import (
    AppSettings,
    ClassifiersConfig,
    ConnectorEntry,
    ConnectorsConfig,
    EnvSettings,
    ParsersConfig,
    RefreshPoliciesConfig,
    RuleEntry,
    ScoringStrategyEntry,
    WarmupConfig,
)

CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config"


def _load_yaml(filename: str) -> dict:  # type: ignore[type-arg]
    path = CONFIG_DIR / filename
    with open(path) as f:
        return yaml.safe_load(f)


@lru_cache
def get_env() -> EnvSettings:
    return EnvSettings()  # type: ignore[call-arg]


@lru_cache
def get_connectors_config() -> ConnectorsConfig:
    raw = _load_yaml("connectors.yaml")
    cfg = ConnectorsConfig(**raw)
    # Apply env override: SOURCELOOP_USE_MOCK=1 enables mock connector
    env = get_env()
    if env.sourceloop_use_mock:
        # Pydantic models are immutable; rebuild with mock enabled
        new_connectors = []
        for c in cfg.connectors:
            if c.key == "mock":
                new_connectors.append(ConnectorEntry(key=c.key, enabled=True, priority=c.priority))
            else:
                new_connectors.append(c)
        cfg = ConnectorsConfig(connectors=new_connectors, nexar=cfg.nexar)
    return cfg


@lru_cache
def get_parsers_config() -> ParsersConfig:
    return ParsersConfig(**_load_yaml("parsers.yaml"))


@lru_cache
def get_classifiers_config() -> ClassifiersConfig:
    return ClassifiersConfig(**_load_yaml("classifiers.yaml"))


@lru_cache
def get_refresh_policies() -> RefreshPoliciesConfig:
    return RefreshPoliciesConfig(**_load_yaml("refresh_policies.yaml"))


@lru_cache
def get_app_settings() -> AppSettings:
    return AppSettings(**_load_yaml("settings.yaml"))


@lru_cache
def get_scoring_strategies() -> dict[str, ScoringStrategyEntry]:
    raw = _load_yaml("scoring_strategies.yaml")
    return {name: ScoringStrategyEntry(**cfg) for name, cfg in raw.items()}


@lru_cache
def get_scoring_rules() -> list[RuleEntry]:
    raw = _load_yaml("rules.yaml")
    return [RuleEntry(**r) for r in raw]


@lru_cache
def get_warmup_config() -> WarmupConfig:
    try:
        return WarmupConfig(**_load_yaml("warmup.yaml"))
    except FileNotFoundError:
        return WarmupConfig()


@lru_cache
def get_seed_parts() -> list[dict]:  # type: ignore[type-arg]
    raw = _load_yaml("seed_parts.yaml")
    return raw.get("parts", [])
