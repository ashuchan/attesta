"""ScoringEngine: routes subject to appropriate strategy via RuleSet."""
from __future__ import annotations

from .provenance import ScoreResult
from .rules import RuleSet
from .signal import Scorable, ScoringContext
from .strategy import ActiveStrategy


class ScoringEngine:
    def __init__(self, strategies: dict[str, ActiveStrategy], rule_set: RuleSet) -> None:
        self._strategies = strategies
        self._rules = rule_set

    def score(self, subject: Scorable, ctx: ScoringContext) -> ScoreResult:
        strategy_name = self._rules.select_strategy(subject, ctx)
        strategy = self._strategies[strategy_name]
        return strategy.score(subject, ctx)
