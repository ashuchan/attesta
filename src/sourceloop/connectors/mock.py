from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from sourceloop.domain.bom import BomLine
from sourceloop.domain.offer import OfferObservation, PriceLadder

log = structlog.get_logger()

# Deterministic fixture offers for the MPNs in tests/fixtures/boms/
MOCK_OFFERS: dict[str, list[dict[str, object]]] = {
    "mpn:STM32F103C8T6": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "STM32F103C8T6-MOCK",
         "price_ladder": [{"qty": 1, "price": 120.0, "currency": "INR"}, {"qty": 10, "price": 100.0, "currency": "INR"}],
         "moq": 1, "stock": 500, "category": "MCU"},
    ],
    "mpn:ESP8266EX": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "ESP8266EX-MOCK",
         "price_ladder": [{"qty": 1, "price": 50.0, "currency": "INR"}, {"qty": 10, "price": 40.0, "currency": "INR"}],
         "moq": 1, "stock": 1000, "category": "WiFi SoC"},
    ],
    "mpn:GRM188R61A106KE69D": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "GRM188-MOCK",
         "price_ladder": [{"qty": 10, "price": 2.5, "currency": "INR"}, {"qty": 100, "price": 1.8, "currency": "INR"}],
         "moq": 10, "stock": 10000, "category": "Capacitor"},
    ],
    "mpn:RC0402FR0710KL": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "RC0402-MOCK",
         "price_ladder": [{"qty": 100, "price": 0.5, "currency": "INR"}],
         "moq": 100, "stock": 50000, "category": "Resistor"},
    ],
    "mpn:SRR1260100Y": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "SRR1260-MOCK",
         "price_ladder": [{"qty": 1, "price": 35.0, "currency": "INR"}],
         "moq": 1, "stock": 200, "category": "Inductor"},
    ],
    "mpn:STM32H743VIT6": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "H743-MOCK",
         "price_ladder": [{"qty": 1, "price": 800.0, "currency": "INR"}],
         "moq": 1, "stock": 50, "category": "MCU"},
    ],
    "mpn:MPU6000": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "MPU6000-MOCK",
         "price_ladder": [{"qty": 1, "price": 180.0, "currency": "INR"}],
         "moq": 1, "stock": 300, "category": "IMU"},
    ],
    "mpn:W25Q128JVSIQ": [
        {"supplier_id": "mock:s1", "supplier_name": "MockDistributor", "sku": "W25Q128-MOCK",
         "price_ladder": [{"qty": 1, "price": 60.0, "currency": "INR"}],
         "moq": 1, "stock": 2000, "category": "Flash Memory"},
    ],
}


class MockConnector:
    """Deterministic fixture connector. Enabled only via SOURCELOOP_USE_MOCK=1."""
    key = "mock"
    enabled = False  # overridden by env
    priority = 99

    def supports(self, line: BomLine) -> bool:
        return line.normalized_part_key.startswith("mpn:")

    async def fetch(self, line: BomLine) -> list[OfferObservation]:
        offers_data = MOCK_OFFERS.get(line.normalized_part_key, [])
        if not offers_data:
            log.info("mock_connector_no_offer", part_key=line.normalized_part_key)
            return []

        now = datetime.now(UTC)
        observations = []
        for offer in offers_data:
            listing_id = uuid.uuid4()
            price_ladder = PriceLadder(rungs=offer["price_ladder"])  # type: ignore[arg-type]
            obs = OfferObservation(
                listing_id=listing_id,
                source="api",
                tier="A",
                captured_at=now,
                normalized_part_key=line.normalized_part_key,
                supplier_id=str(offer["supplier_id"]),
                category=str(offer["category"]) if offer.get("category") else None,
                price_ladder=price_ladder,
                moq=int(offer["moq"]) if offer.get("moq") is not None else None,  # type: ignore[arg-type]
                lead_time=None,
                stock=int(offer["stock"]) if offer.get("stock") is not None else None,  # type: ignore[arg-type]
                specs={},
                supplier_snapshot={"supplier_id": offer["supplier_id"], "supplier_name": offer["supplier_name"]},
                screenshot_ref=None,
                confidence=None,
                field_captured_at={
                    "price_ladder": now.isoformat(),
                    "stock": now.isoformat(),
                    "moq": now.isoformat(),
                },
            )
            observations.append(obs)
        return observations
