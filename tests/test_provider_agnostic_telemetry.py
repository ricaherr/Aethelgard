from unittest.mock import MagicMock, patch

import connectors.generic_data_provider as generic_module
import connectors.mt5_data_provider as mt5_module
from connectors.base_connector import BaseConnector
from core_brain.data_provider_manager import DataProviderManager
from data_vault.storage import StorageManager
from models.signal import ConnectorType
from start import _bind_signal_factory_reconciliation_connector, _build_active_connectors


class _DummyProvider:
    def __init__(self, *, connected: bool = True) -> None:
        self.is_connected = connected

    def is_available(self) -> bool:
        return self.is_connected


class _DummySignalFactory:
    def __init__(self) -> None:
        self.bound_connector = None

    def set_reconciliation_connector(self, connector):
        self.bound_connector = connector


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


def test_generic_provider_implements_base_connector_contract(monkeypatch) -> None:
    monkeypatch.setattr(generic_module, "yf", object())
    provider = generic_module.GenericDataProvider()

    assert isinstance(provider, BaseConnector)
    assert provider.provider_id == "yahoo"


def test_mt5_provider_implements_base_connector_contract(tmp_path) -> None:
    storage = StorageManager(db_path=str(tmp_path / "mt5_provider_contract.db"))
    provider = mt5_module.MT5DataProvider(storage=storage, init_mt5=False)

    assert isinstance(provider, BaseConnector)
    assert provider.provider_id == "mt5"


def test_data_provider_manager_exposes_singular_active_provider_accessor(tmp_path) -> None:
    storage = StorageManager(db_path=str(tmp_path / "singular_accessor.db"))
    with patch("core_brain.data_provider_manager.StorageManager", return_value=storage):
        manager = DataProviderManager()

    manager.disable_provider("mt5")
    provider = _DummyProvider(connected=True)
    manager.register_provider_instance("ctrader", provider)

    selected = manager.get_active_provider()

    assert selected is not None
    assert selected["name"] == "ctrader"
    assert selected["instance"] is provider


def test_start_wiring_binds_reconciliation_connector_from_active_provider() -> None:
    signal_factory = _DummySignalFactory()
    active_provider = {"name": "ctrader", "instance": _DummyProvider(connected=True)}

    _bind_signal_factory_reconciliation_connector(signal_factory, active_provider)

    assert signal_factory.bound_connector is active_provider["instance"]
