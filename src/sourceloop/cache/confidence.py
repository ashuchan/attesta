from __future__ import annotations

from typing import Protocol, runtime_checkable

from sourceloop.domain.offer import OfferObservation


@runtime_checkable
class ConfidenceProvider(Protocol):
    def score(self, observation: OfferObservation) -> float | None:
        ...


class NullConfidence:
    """Step 1 default — always returns None. Step 2 wires in the real scoring engine."""
    def score(self, observation: OfferObservation) -> None:
        return None
