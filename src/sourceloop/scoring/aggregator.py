"""Aggregator implementations: WeightedSum, Max, EWMA, First."""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .signal import SignalValue


@runtime_checkable
class Aggregator(Protocol):
    def aggregate(self, values: dict[str, SignalValue], weights: dict[str, float]) -> float:
        ...


class WeightedSum:
    """
    score = Σ(weightᵢ × normalizedᵢ) / Σ(weightᵢ) × 100

    Only sums over signals present in *values* (auto-renormalization on dropped signal).
    """
    name = "weighted_sum"

    def aggregate(self, values: dict[str, SignalValue], weights: dict[str, float]) -> float:
        active = [(k, v) for k, v in values.items() if k in weights]
        if not active:
            return 0.0
        total_weight = sum(weights[k] for k, _ in active)
        if total_weight == 0:
            return 0.0
        return sum(weights[k] * v.normalized for k, v in active) / total_weight * 100


class Max:
    name = "max"

    def aggregate(self, values: dict[str, SignalValue], weights: dict[str, float]) -> float:
        if not values:
            return 0.0
        return max(v.normalized for v in values.values()) * 100


class EWMA:
    name = "ewma"

    def __init__(self, alpha: float = 0.7) -> None:
        self.alpha = alpha

    def aggregate(self, values: dict[str, SignalValue], weights: dict[str, float]) -> float:
        vals = list(values.values())
        if not vals:
            return 0.0
        result = vals[0].normalized
        for v in vals[1:]:
            result = self.alpha * result + (1 - self.alpha) * v.normalized
        return result * 100


class First:
    name = "first"

    def aggregate(self, values: dict[str, SignalValue], weights: dict[str, float]) -> float:
        if not values:
            return 0.0
        return next(iter(values.values())).normalized * 100


AGGREGATOR_REGISTRY: dict[str, Aggregator] = {
    "weighted_sum": WeightedSum(),
    "max": Max(),
    "ewma": EWMA(),
    "first": First(),
}
