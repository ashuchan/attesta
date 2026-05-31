from __future__ import annotations
import pytest
import uuid
from unittest.mock import patch, MagicMock
from sourceloop.domain.bom import BomLine
from sourceloop.domain.part import PartClass


def make_line(mpn: str = "STM32F103C8T6") -> BomLine:
    return BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator="U1", raw_description="MCU",
        mpn=mpn, manufacturer="ST", quantity=1.0, unit="pcs",
        normalized_part_key=f"mpn:{mpn}", part_class=PartClass.A,
        parse_confidence=0.9,
    )


def _make_registry_with_mock(use_mock: bool = True):
    from sourceloop.connectors.registry import ConnectorRegistry
    from sourceloop.connectors.mock import MockConnector
    with patch("sourceloop.connectors.registry.get_connectors_config") as mock_cfg, \
         patch("sourceloop.connectors.registry.get_env") as mock_env, \
         patch.object(MockConnector, "enabled", use_mock):
        mock_env.return_value.sourceloop_use_mock = use_mock

        from sourceloop.config.models import ConnectorEntry
        mock_entry = ConnectorEntry(key="mock", enabled=use_mock, priority=99)
        nexar_entry = ConnectorEntry(key="nexar", enabled=False, priority=10)
        dk_entry = ConnectorEntry(key="digikey", enabled=False, priority=20)
        mouser_entry = ConnectorEntry(key="mouser", enabled=False, priority=30)
        nexar_cfg = MagicMock()
        nexar_cfg.max_rps = 5
        nexar_cfg.max_retries = 3
        nexar_cfg.monthly_quota_soft_cap = 0
        nexar_cfg.limit = 5
        mock_cfg.return_value.connectors = [nexar_entry, dk_entry, mouser_entry, mock_entry]
        mock_cfg.return_value.nexar = nexar_cfg
        registry = ConnectorRegistry()
    return registry


def test_registry_mock_enabled():
    registry = _make_registry_with_mock(use_mock=True)
    line = make_line()
    connectors = registry.connectors_for(line)
    keys = [c.key for c in connectors]
    assert "mock" in keys


def test_registry_no_mock_without_flag():
    registry = _make_registry_with_mock(use_mock=False)
    line = make_line()
    connectors = registry.connectors_for(line)
    keys = [c.key for c in connectors]
    assert "mock" not in keys


def test_registry_connectors_for_returns_empty_for_unsupported():
    registry = _make_registry_with_mock(use_mock=True)
    from sourceloop.domain.bom import BomLine
    from sourceloop.domain.part import PartClass
    # Tier B line (no mpn) — mock connector supports any line with mpn=None
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description="custom",
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="desc:abc", part_class=PartClass.B,
        parse_confidence=0.5,
    )
    # mock connector uses supports() which checks mpn presence
    connectors = registry.connectors_for(line)
    # MockConnector.supports() returns True only when mpn is set
    for c in connectors:
        assert c.supports(line)


def test_digikey_stub_returns_empty():
    from sourceloop.connectors.digikey import DigiKeyConnector
    import asyncio
    connector = DigiKeyConnector()
    line = make_line()
    result = asyncio.run(connector.fetch(line))
    assert result == []


def test_mouser_stub_returns_empty():
    from sourceloop.connectors.mouser import MouserConnector
    import asyncio
    connector = MouserConnector()
    line = make_line()
    result = asyncio.run(connector.fetch(line))
    assert result == []


def test_digikey_supports_branded_mpn():
    from sourceloop.connectors.digikey import DigiKeyConnector
    connector = DigiKeyConnector()
    line = make_line("STM32F103C8T6")
    assert connector.supports(line) is True


def test_digikey_not_supports_no_mpn():
    from sourceloop.connectors.digikey import DigiKeyConnector
    connector = DigiKeyConnector()
    line = BomLine(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), bom_id=uuid.uuid4(),
        line_no=1, raw_designator=None, raw_description="custom",
        mpn=None, manufacturer=None, quantity=1.0, unit="pcs",
        normalized_part_key="desc:abc123", part_class=PartClass.B,
        parse_confidence=0.5,
    )
    assert not connector.supports(line)


def test_mouser_supports_mpn():
    from sourceloop.connectors.mouser import MouserConnector
    connector = MouserConnector()
    line = make_line("STM32F103C8T6")
    assert connector.supports(line) is True


def test_digikey_is_disabled():
    from sourceloop.connectors.digikey import DigiKeyConnector
    connector = DigiKeyConnector()
    assert connector.enabled is False


def test_mouser_is_disabled():
    from sourceloop.connectors.mouser import MouserConnector
    connector = MouserConnector()
    assert connector.enabled is False


def test_registry_unknown_connector_key_skipped():
    from sourceloop.connectors.registry import ConnectorRegistry
    with patch("sourceloop.connectors.registry.get_connectors_config") as mock_cfg, \
         patch("sourceloop.connectors.registry.get_env") as mock_env:
        mock_env.return_value.sourceloop_use_mock = False

        from sourceloop.config.models import ConnectorEntry
        unknown_entry = ConnectorEntry(key="unknown_xyz", enabled=True, priority=5)
        mock_cfg.return_value.connectors = [unknown_entry]
        mock_cfg.return_value.nexar = MagicMock()
        registry = ConnectorRegistry()

    line = make_line()
    connectors = registry.connectors_for(line)
    assert connectors == []
