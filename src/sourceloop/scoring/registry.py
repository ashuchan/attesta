"""Signal registry — load signals from config, build active strategies and engine."""
from __future__ import annotations

from typing import Any

import structlog

from .aggregator import AGGREGATOR_REGISTRY, Aggregator
from .engine import ScoringEngine
from .rules import Rule, RuleSet
from .signal import Signal
from .strategy import ActiveStrategy

log = structlog.get_logger()

# ── Built-in signal implementations ──────────────────────────────────────────
from .signals.completeness import CompletenessSignal
from .signals.freshness import FreshnessSignal
from .signals.part_match import PartMatchSignal
from .signals.price_sanity import PriceSanitySignal
from .signals.source_tier import SourceTierSignal
from .signals.supplier_trust import SupplierTrustSignal
from .signals.vision_agreement import VisionAgreementSignal

_BUILTIN_SIGNALS: dict[str, Signal] = {
    # Live signals
    "source_tier": SourceTierSignal(),  # type: ignore[dict-item]
    "freshness": FreshnessSignal(),  # type: ignore[dict-item]
    "completeness": CompletenessSignal(),  # type: ignore[dict-item]
    # Registered-but-disabled signals: present in registry so strategies can reference them;
    # dropped+renormalized at load time (not an error). Log emitted once: signal_disabled.
    "price_sanity": PriceSanitySignal(),  # type: ignore[dict-item]
    "part_match": PartMatchSignal(),  # type: ignore[dict-item]
    "supplier_trust": SupplierTrustSignal(),  # type: ignore[dict-item]
    "vision_agreement": VisionAgreementSignal(),  # type: ignore[dict-item]
}


def build_engine(
    strategies_cfg: dict[str, Any],
    rules_cfg: list[dict[str, str]],
    extra_signals: dict[str, Signal] | None = None,
) -> ScoringEngine:
    """
    Build a ScoringEngine from raw config dicts (loaded from YAML).

    strategies_cfg: dict[strategy_name, {signals, weights, aggregator, bands, hard_flags}]
    rules_cfg: list[{when, then}]
    """
    all_signals = dict(_BUILTIN_SIGNALS)
    if extra_signals:
        all_signals.update(extra_signals)

    active_strategies: dict[str, ActiveStrategy] = {}
    for name, cfg in strategies_cfg.items():
        signal_keys: list[str] = cfg.get("signals", [])
        weights: dict[str, float] = cfg.get("weights", {})
        aggregator_name: str = cfg.get("aggregator", "weighted_sum")
        bands: dict[str, float] = cfg.get("bands", {"high": 80.0, "medium": 50.0})
        hard_flags: list[str] = cfg.get("hard_flags", [])

        agg: Aggregator = AGGREGATOR_REGISTRY.get(aggregator_name, AGGREGATOR_REGISTRY["weighted_sum"])

        signals: list[Signal] = []
        for key in signal_keys:
            sig = all_signals.get(key)
            if sig is None:
                log.warning("unknown_signal", key=key, strategy=name)
                continue
            if not sig.enabled:
                log.info("strategy_signal_disabled_dropped", signal=key, strategy=name)
                continue
            signals.append(sig)

        active_strategies[name] = ActiveStrategy(
            name=name,
            signals=signals,
            weights=weights,
            aggregator=agg,
            bands=bands,
            hard_flags=hard_flags,
        )

    rules = [Rule(when=r["when"], then=r["then"]) for r in rules_cfg]
    rule_set = RuleSet(rules)

    return ScoringEngine(active_strategies, rule_set)
