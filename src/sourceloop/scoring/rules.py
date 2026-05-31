"""Compact rule DSL: when <predicate> → then <strategy_name>."""
from __future__ import annotations

from dataclasses import dataclass

from .signal import Scorable, ScoringContext


@dataclass
class Rule:
    when: str   # "always" | "tier_a" | "tier_b" | ...
    then: str   # strategy name


class RuleSet:
    """
    Evaluates rules in order; first match wins.
    Written as data so Step 3 adds Tier-B rule as a config line, not a code change.
    """

    def __init__(self, rules: list[Rule]) -> None:
        for i, rule in enumerate(rules):
            if rule.when == "always" and i != len(rules) - 1:
                raise ValueError(
                    f"Rule 'when: always' at position {i} is not the last rule — "
                    "it would shadow all subsequent rules. Move it to the end."
                )
        self._rules = rules

    def select_strategy(self, subject: Scorable, ctx: ScoringContext) -> str:
        for rule in self._rules:
            if self._eval(rule.when, subject):
                return rule.then
        raise ValueError(f"No matching rule for subject tier={getattr(subject, 'tier', '?')}")

    @staticmethod
    def _eval(predicate: str, subject: Scorable) -> bool:
        if predicate == "always":
            return True
        if predicate == "tier_a":
            return getattr(subject, "tier", "A") == "A"
        if predicate == "tier_b":
            return getattr(subject, "tier", "A") == "B"
        if predicate == "tier_c":
            return getattr(subject, "tier", "A") == "C"
        return False
