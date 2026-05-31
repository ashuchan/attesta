from __future__ import annotations

from typing import Protocol, runtime_checkable

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import OfferObservation


@runtime_checkable
class DistributorConnector(Protocol):
    key: str
    enabled: bool
    priority: int

    def supports(self, line: BomLine) -> bool:
        ...

    async def fetch(self, line: BomLine) -> list[OfferObservation]:
        ...

    async def fetch_mpn(
        self,
        mpn: str,
        manufacturer: str | None,
        normalized_part_key: str,
        category: str | None,
    ) -> list[OfferObservation]:
        ...
