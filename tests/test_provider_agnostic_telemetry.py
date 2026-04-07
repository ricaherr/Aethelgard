from unittest.mock import MagicMock, patch

from core_brain.data_provider_manager import DataProviderManager
from data_vault.storage import StorageManager
from models.signal import ConnectorType
from start import _build_active_connectors


class _DummyProvider:
    def __init__(self, *, connected: bool = True) -> None:
        self.is_connected = connected

    def is_available(self) -> bool:
        return self.is_connected


def test_telemetry_does_not_require_mt5_if_provider_active(tmp_path) -> None:
    storage = StorageManager(db_path=str(tmp_path / "telemetry_agnostic.db"))
    with patch("core_brain.data_provider_manager.StorageManager", return_value=storage):
        manager = DataProviderManager()

    manager.disable_provider("mt5")
    ctrader_provider = _DummyProvider(connected=True)
    manager.register_provider_instance("ctrader", ctrader_provider)

    selected = manager.get_connected_active_provider()

    assert selected is not None
    assert selected["name"] == "ctrader"
    assert selected["instance"] is ctrader_provider
    assert selected["is_connected"] is True

    providers = {p["name"]: p for p in storage.get_sys_data_providers()}
    assert providers["ctrader"]["connector_module"] == "connectors.ctrader_connector"
    assert providers["ctrader"]["connector_class"] == "CTraderConnector"


def test_startup_wiring_avoids_nominal_mt5_dependency_for_general_flow() -> None:
    ctrader_connector = MagicMock()
    ctrader_connector.is_connected = False
    ctrader_connector.provider_id = "ctrader"

    connectivity_orchestrator = MagicMock()
    connectivity_orchestrator.connectors = {"ctrader": ctrader_connector}

    active_connectors = _build_active_connectors(connectivity_orchestrator)

    assert ConnectorType.METATRADER5 not in active_connectors
    assert ConnectorType.GENERIC in active_connectors
    assert active_connectors[ConnectorType.GENERIC] is ctrader_connector
