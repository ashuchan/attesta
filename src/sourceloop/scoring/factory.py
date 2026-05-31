"""Factory: build the default ScoringEngine from YAML config."""
from __future__ import annotations

from functools import lru_cache

from .engine import ScoringEngine
from .registry import build_engine


@lru_cache(maxsize=1)
def get_scoring_engine() -> ScoringEngine:
    """Load scoring config and build engine. Cached — called once per process."""
    from sourceloop.config.loader import get_scoring_rules, get_scoring_strategies

    strategies_cfg = {
        name: entry.model_dump()
        for name, entry in get_scoring_strategies().items()
    }
    rules_cfg = [r.model_dump() for r in get_scoring_rules()]
    return build_engine(strategies_cfg=strategies_cfg, rules_cfg=rules_cfg)


def build_confidence_provider() -> object:
    """Return an EngineConfidenceProvider backed by the default engine."""
    from sourceloop.cache.confidence import EngineConfidenceProvider
    return EngineConfidenceProvider(get_scoring_engine())
