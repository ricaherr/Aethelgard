"""
TDD — Provider Bugs Fix
Trace_ID: PROVIDER-BUGS-FIX-2026-03-21

Tests for:
  A. _sync_sys_broker_accounts_to_providers removed from DataProviderManager
  B. ctrader selected as primary provider when credentials in additional_config
  C. get_status_report() does not call load_connectors_from_db()
  D. get_active_providers() returns only ctrader+yahoo when DB has only those enabled
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call
import pytest

from core_brain.data_provider_manager import DataProviderManager, ProviderConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(providers: List[Dict], broker_accounts: Optional[List[Dict]] = None) -> Any:
    """Build a minimal StorageManager mock."""
    storage = MagicMock()
    storage.db_path = ":memory:"

    # get_sys_data_providers returns exactly what we pass
    storage.get_sys_data_providers.return_value = [
        {
            "name": p["name"],
            "enabled": p.get("enabled", 0),
            "priority": p.get("priority", 50),
            "requires_auth": p.get("requires_auth", 0),
            "api_key": p.get("api_key"),
            "api_secret": p.get("api_secret"),
            "additional_config": p.get("additional_config", {}),
            "config": {
                "priority": p.get("priority", 50),
                "requires_auth": p.get("requires_auth", 0),
                "api_key": p.get("api_key"),
                "api_secret": p.get("api_secret"),
                "additional_config": p.get("additional_config", {}),
                "is_system": p.get("is_system", 1),
            },
        }
        for p in providers
    ]

    storage.get_sys_broker_accounts.return_value = broker_accounts or []
    storage.save_data_provider = MagicMock()
    storage.get_connector_settings.return_value = {}
    return storage


# ---------------------------------------------------------------------------
# Bug A: _sync_sys_broker_accounts_to_providers must not exist / not be called
# ---------------------------------------------------------------------------

class TestSyncMethodRemoved:
    def test_sync_method_does_not_exist(self) -> None:
        """DataProviderManager must not have _sync_sys_broker_accounts_to_providers."""
        assert not hasattr(DataProviderManager, "_sync_sys_broker_accounts_to_providers"), (
            "_sync_sys_broker_accounts_to_providers still exists. "
            "It violates the architectural separation: sys_broker_accounts != sys_data_providers."
        )

    def test_init_does_not_call_sync(self) -> None:
        """DataProviderManager.__init__ must not invoke any broker-account sync."""
        storage = _make_storage([
            {"name": "ctrader", "enabled": 1, "priority": 100, "requires_auth": 1,
             "additional_config": {"login": "123", "server": "demo"}},
            {"name": "yahoo", "enabled": 1, "priority": 50, "requires_auth": 0},
        ])
        # If sync existed and called get_sys_broker_accounts, this would be > 0
        dm = DataProviderManager(storage=storage)
        storage.get_sys_broker_accounts.assert_not_called()


# ---------------------------------------------------------------------------
# Bug B: ctrader selected as primary when credentials in additional_config
# ---------------------------------------------------------------------------

class TestCtraderPrimarySelection:
    def test_ctrader_selected_when_has_additional_config_credentials(self) -> None:
        """ctrader with access_token in additional_config must be selected as primary."""
        storage = _make_storage([
            {
                "name": "ctrader", "enabled": 1, "priority": 100, "requires_auth": 1,
                "additional_config": {
                    "access_token": "my_oauth_token",
                    "account_number": "9920997",
                    "client_id": "my_client_id",
                    "client_secret": "my_secret",
                    "account_type": "DEMO",
                },
            },
            {"name": "yahoo", "enabled": 1, "priority": 50, "requires_auth": 0},
        ])

        with patch.object(DataProviderManager, "_get_provider_instance") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider

            dm = DataProviderManager(storage=storage)
            selected = dm.get_best_provider()

        assert dm._selected_provider_name == "ctrader", (
            f"Expected ctrader as primary (priority=100, credentials valid), "
            f"got '{dm._selected_provider_name}'."
        )

    def test_ctrader_skipped_when_missing_additional_config_credentials(self) -> None:
        """ctrader without access_token in additional_config must be skipped."""
        storage = _make_storage([
            {
                "name": "ctrader", "enabled": 1, "priority": 100, "requires_auth": 1,
                "additional_config": {},  # No credentials
            },
            {"name": "yahoo", "enabled": 1, "priority": 50, "requires_auth": 0},
        ])

        with patch.object(DataProviderManager, "_get_provider_instance") as mock_get:
            mock_provider = MagicMock()
            mock_get.return_value = mock_provider

            dm = DataProviderManager(storage=storage)
            dm.get_best_provider()

        assert dm._selected_provider_name == "yahoo", (
            f"ctrader without credentials should be skipped. "
            f"Expected yahoo fallback, got '{dm._selected_provider_name}'."
        )


# ---------------------------------------------------------------------------
# Bug D: get_active_providers returns only ctrader + yahoo
# ---------------------------------------------------------------------------

class TestActiveProvidersFilter:
    def test_only_enabled_providers_returned(self) -> None:
        """get_active_providers must return only providers with enabled=True."""
        storage = _make_storage([
            {"name": "ctrader", "enabled": 1, "priority": 100, "requires_auth": 1,
             "additional_config": {"login": "x", "server": "y"}},
            {"name": "yahoo", "enabled": 1, "priority": 50, "requires_auth": 0},
            {"name": "mt5", "enabled": 0, "priority": 70, "requires_auth": 1},
            {"name": "alphavantage", "enabled": 0, "priority": 80, "requires_auth": 1},
        ])

        dm = DataProviderManager(storage=storage)
        active_names = {p["name"] for p in dm.get_active_providers()}

        assert active_names == {"ctrader", "yahoo"}, (
            f"Expected only ctrader+yahoo active, got {active_names}."
        )

    def test_active_providers_sorted_by_priority_desc(self) -> None:
        """get_active_providers must return list sorted by priority descending."""
        storage = _make_storage([
            {"name": "ctrader", "enabled": 1, "priority": 100, "requires_auth": 1,
             "additional_config": {"login": "x", "server": "y"}},
            {"name": "yahoo", "enabled": 1, "priority": 50, "requires_auth": 0},
        ])

        dm = DataProviderManager(storage=storage)
        active = dm.get_active_providers()

        assert active[0]["name"] == "ctrader"
        assert active[1]["name"] == "yahoo"


# ---------------------------------------------------------------------------
# Bug C: get_status_report must not reload connectors on every call
# ---------------------------------------------------------------------------

class TestGetStatusReportNoReload:
    def test_get_status_report_does_not_call_load_connectors_from_db(self) -> None:
        """get_status_report() must not call load_connectors_from_db() on every invocation."""
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator

        # Reset singleton
        ConnectivityOrchestrator._instance = None

        storage = MagicMock()
        storage.get_sys_data_providers.return_value = []
        storage.get_sys_broker_accounts.return_value = []
        storage.get_usr_broker_accounts = MagicMock(return_value=[])
        storage.get_connector_settings.return_value = {}

        orch = ConnectivityOrchestrator()
        orch.set_storage(storage)

        # Reset call count after set_storage (which legitimately loads once)
        storage.get_sys_data_providers.reset_mock()
        storage.get_sys_broker_accounts.reset_mock()

        # Call get_status_report multiple times
        orch.get_status_report()
        orch.get_status_report()
        orch.get_status_report()

        # Must NOT have triggered a reload
        storage.get_sys_data_providers.assert_not_called()
        storage.get_sys_broker_accounts.assert_not_called()

        # Cleanup singleton
        ConnectivityOrchestrator._instance = None


# ---------------------------------------------------------------------------
# LOG-HARDENING-STARTUP-2026-04-08: Severity adjustments
# ---------------------------------------------------------------------------

class TestCTraderCredentialsMissingLogLevel:
    """CTrader credentials-missing message must be INFO (not WARNING) to avoid false-positive noise."""

    def test_missing_credentials_does_not_emit_warning(self) -> None:
        """
        GIVEN: CTraderConnector instantiated with no credentials
        WHEN:  _build_connector_config() is called internally
        THEN:  No WARNING must be emitted — only INFO or lower.
        """
        import logging
        from connectors.ctrader_connector import CTraderConnector

        with patch("connectors.ctrader_connector.logger") as mock_log:
            connector = CTraderConnector()  # no credentials injected
            # _build_connector_config is called in __init__ when no credentials
            mock_log.warning.assert_not_called()

    def test_missing_credentials_emits_info(self) -> None:
        """
        GIVEN: CTraderConnector instantiated with no credentials
        THEN:  logger.info() must be called at least once with 'Credentials not configured'.
        """
        import logging
        from connectors.ctrader_connector import CTraderConnector

        with patch("connectors.ctrader_connector.logger") as mock_log:
            connector = CTraderConnector()
            called_with_credentials_msg = any(
                "Credentials not configured" in str(call_args)
                for call_args in mock_log.info.call_args_list
            )
            assert called_with_credentials_msg, (
                "Expected logger.info() with 'Credentials not configured', but it was not called."
            )


class TestMT5DataProviderNonNumericAccountWarning:
    """Non-numeric account_number must log WARNING (not ERROR) — it is a known graceful-degradation path."""

    def _make_sparse_storage(self) -> Any:
        storage = MagicMock()
        storage.get_sys_broker_accounts.return_value = [
            {
                "account_id": "TEST_ACC",
                "account_name": "AutoDemo",
                "account_number": "AUTO-DEMO-EXEC",  # intentionally non-numeric
                "login": "AUTO-DEMO-EXEC",
                "server": "",
                "platform_id": "mt5",  # required by _load_from_db filter
                "enabled": True,
                "account_role": "SYS_EXEC_DEMO_AUTO",
            }
        ]
        storage.get_credentials.return_value = {"password": ""}
        return storage

    def test_non_numeric_account_number_logs_warning_not_error(self) -> None:
        """
        GIVEN: MT5DataProvider with account_number='AUTO-DEMO-EXEC'
        WHEN:  Provider initialises
        THEN:  logger.warning() is called, logger.error() is NOT called.
        """
        from connectors.mt5_data_provider import MT5DataProvider

        storage = self._make_sparse_storage()
        with patch("connectors.mt5_data_provider.logger") as mock_log:
            provider = MT5DataProvider(storage=storage, account_id="TEST_ACC", init_mt5=False)
            mock_log.error.assert_not_called()
            assert mock_log.warning.call_count >= 1, (
                "Expected at least one logger.warning() call for non-numeric account_number."
            )

    def test_non_numeric_account_number_warning_mentions_graceful_degradation(self) -> None:
        """Warning message must indicate this is a graceful-degradation path, not an unexpected failure."""
        from connectors.mt5_data_provider import MT5DataProvider

        storage = self._make_sparse_storage()
        with patch("connectors.mt5_data_provider.logger") as mock_log:
            provider = MT5DataProvider(storage=storage, account_id="TEST_ACC", init_mt5=False)
            all_warnings = " ".join(str(c) for c in mock_log.warning.call_args_list)
            assert "graceful" in all_warnings.lower() or "non-numeric" in all_warnings.lower(), (
                "Warning message should mention 'graceful' or 'non-numeric' to be self-explanatory."
            )
