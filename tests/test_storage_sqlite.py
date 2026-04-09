"""
Test Suite for SQLite StorageManager
Verifies data persistence, retrieval, and integrity using SQLite.
"""
import pytest
import os
import json
from datetime import date, datetime
from typing import Any
from data_vault.storage import StorageManager
from models.signal import Signal, ConnectorType, MarketRegime, SignalType

@pytest.fixture
def temp_db_path(tmp_path: Any) -> str:
    """Create a temporary database path"""
    db_file = tmp_path / "test_aethelgard.db"
    return str(db_file)

@pytest.fixture
def storage(temp_db_path: str) -> StorageManager:
    """Initialize StorageManager with temp DB"""
    return StorageManager(db_path=temp_db_path)

def test_sys_config_persistence(storage: StorageManager) -> None:
    """Test saving and retrieving system state"""
    state = {
        "lockdown_mode": True,
        "consecutive_losses": 3,
        "session_stats": {"processed": 100}
    }
    
    storage.update_sys_config(state)
    
    # Create new instance to verify persistence
    new_storage = StorageManager(db_path=storage.db_path)
    loaded_state = new_storage.get_sys_config()
    
    assert loaded_state["lockdown_mode"] is True
    assert loaded_state["consecutive_losses"] == 3
    assert loaded_state["session_stats"]["processed"] == 100

def test_signal_persistence(storage: StorageManager) -> None:
    """Test saving and retrieving sys_signals with trace_id and status"""
    signal = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.95,
        connector_type=ConnectorType.METATRADER5,
        entry_price=1.1000,
        stop_loss=1.0950,
        take_profit=1.1100,
        trace_id="test-trace-123",
        status=None,
        metadata={"regime": "TREND", "score": 95}
    )
    
    assert signal.trace_id == "test-trace-123"
    assert signal.status is None
    
    signal_id = storage.save_signal(signal)
    assert signal_id is not None
    
    # Verify retrieval
    sys_signals = storage.get_sys_signals_today()
    assert len(sys_signals) == 1
    saved_signal = sys_signals[0]
    
    assert saved_signal["symbol"] == "EURUSD"
    assert saved_signal["status"] == "PENDING"  # Newly saved signal starts as PENDING
    assert saved_signal["metadata"]["score"] == 95

def test_trade_result_persistence(storage: StorageManager) -> None:
    """Test saving and retrieving trade results"""
    trade = {
        "id": "test_trade_123",
        "signal_id": "signal_456",
        "symbol": "GBPUSD",
        "entry_price": 1.2500,
        "exit_price": 1.2550,
        "profit": 50.0,
        "exit_reason": "Take Profit",
        "close_time": datetime.now().isoformat()
    }
    
    storage.save_trade_result(trade)
    
    usr_trades = storage.get_recent_usr_trades(limit=10)
    assert len(usr_trades) == 1
    assert usr_trades[0]["symbol"] == "GBPUSD"
    assert usr_trades[0]["profit"] == 50.0
    assert usr_trades[0]["exit_reason"] == "Take Profit"

def test_sys_market_pulse_logging(storage: StorageManager) -> None:
    """Test logging market states for tuner"""
    state = {
        "symbol": "EURUSD",
        "timestamp": datetime.now().isoformat(),
        "regime": "TREND",
        "adx": 30.5,
        "volatility": 0.0015
    }
    
    storage.log_sys_market_pulse(state)
    
    states = storage.get_sys_market_pulse_history(symbol="EURUSD", limit=10)
    assert len(states) == 1
    assert states[0]["data"]["adx"] == 30.5


def test_get_sys_config_tolerates_legacy_null_values(storage: StorageManager) -> None:
    """Legacy NULL values in sys_config must not crash runtime reads."""
    storage.execute_update(
        "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
        ("global_config", None),
    )

    loaded_state = storage.get_sys_config()

    assert "global_config" in loaded_state
    assert loaded_state["global_config"] is None


def test_safe_config_getters_return_empty_dict_on_legacy_null(storage: StorageManager) -> None:
    """Typed config getters must normalize legacy NULL rows to empty dicts."""
    storage.execute_update(
        "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
        ("dynamic_params", None),
    )
    storage.execute_update(
        "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
        ("risk_settings", None),
    )
    storage.execute_update(
        "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
        ("modules_config", None),
    )

    assert storage.get_dynamic_params() == {}
    assert storage.get_risk_settings() == {}
    assert storage.get_modules_config() == {}
    assert storage.reload_global_config() == {}


def test_save_edge_learning_persists_without_legacy_manual_commit(storage: StorageManager) -> None:
    """save_edge_learning must persist rows through the repository transaction contract."""
    storage.save_edge_learning(
        detection="Sistema Iniciado",
        action_taken="Auto-test de EDGE",
        learning="Canal de comunicación activo",
        details="startup smoke",
    )

    history = storage.get_edge_learning_history(limit=5)

    assert len(history) == 1
    assert history[0]["detection"] == "Sistema Iniciado"
    assert history[0]["action_taken"] == "Auto-test de EDGE"
    assert history[0]["learning"] == "Canal de comunicación activo"
    assert history[0]["details"] == "startup smoke"


# ── HU 8.6: Regression tests for SystemMixin.write migration ─────────────────


def test_save_tuning_adjustment_persists_via_transaction_contract(storage: StorageManager) -> None:
    """save_tuning_adjustment must persist rows through the repository transaction contract."""
    storage.save_tuning_adjustment({"param": "ema_period", "value": 21, "reason": "test"})

    history = storage.get_tuning_history(limit=5)

    assert len(history) == 1
    assert history[0]["adjustment_data"]["param"] == "ema_period"
    assert history[0]["adjustment_data"]["value"] == 21


def test_save_data_provider_persists_via_transaction_contract(storage: StorageManager) -> None:
    """save_data_provider must persist rows through the repository transaction contract."""
    storage.save_data_provider(
        name="test_provider",
        enabled=True,
        priority=10,
        provider_type="rest",
    )

    providers = storage.get_sys_data_providers()
    names = [p["name"] for p in providers]

    assert "test_provider" in names


def test_update_provider_enabled_persists_via_transaction_contract(storage: StorageManager) -> None:
    """update_provider_enabled must flip the enabled flag through the transaction contract."""
    storage.save_data_provider(name="flip_provider", enabled=True, priority=20)
    storage.update_provider_enabled("flip_provider", False)

    providers = storage.get_sys_data_providers()
    target = next(p for p in providers if p["name"] == "flip_provider")

    assert target["enabled"] == 0


def test_set_connector_enabled_persists_via_transaction_contract(storage: StorageManager) -> None:
    """set_connector_enabled must persist the manual toggle through the transaction contract."""
    storage.set_connector_enabled("mt5", enabled=False)

    settings = storage.get_connector_settings()

    assert "mt5" in settings
    assert settings["mt5"] is False


def test_update_usr_notification_settings_returns_true_and_persists(storage: StorageManager) -> None:
    """update_usr_notification_settings must persist settings and return True via transaction."""
    result = storage.update_usr_notification_settings(
        provider="telegram",
        enabled=True,
        config={"chat_id": "12345", "token": "abc"},
    )

    assert result is True
    row = storage.get_usr_notification_settings("telegram")
    assert row is not None
    assert row["enabled"] == 1
    assert row["config"]["chat_id"] == "12345"


def test_save_notification_returns_true_and_persists(storage: StorageManager) -> None:
    """save_notification must persist the notification and return True via transaction."""
    notification = {
        "id": "notif-001",
        "user_id": "default",
        "category": "RISK",
        "priority": "high",
        "title": "Lockdown Activated",
        "message": "3 consecutive losses triggered lockdown.",
    }

    result = storage.save_notification(notification)

    assert result is True
    notifications = storage.get_user_notifications("default", limit=5)
    assert len(notifications) == 1
    assert notifications[0]["title"] == "Lockdown Activated"


def test_mark_notification_read_marks_and_returns_true(storage: StorageManager) -> None:
    """mark_notification_read must flip read=1 and return True via transaction."""
    storage.save_notification({
        "id": "notif-read-test",
        "user_id": "default",
        "category": "SIGNAL",
        "priority": "low",
        "title": "New Signal",
        "message": "EURUSD BUY",
    })

    result = storage.mark_notification_read("notif-read-test")

    assert result is True
    unread = storage.get_user_notifications("default", unread_only=True, limit=5)
    assert len(unread) == 0


def test_delete_old_notifications_returns_count_via_transaction(storage: StorageManager) -> None:
    """delete_old_notifications must delete stale rows and return count via transaction."""
    storage.execute_update(
        """INSERT INTO usr_notifications
           (id, user_id, category, priority, title, message, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, datetime('now', '-3 days'))""",
        ("old-notif-001", "default", "SYSTEM", "low", "Old alert", "Old message"),
    )

    deleted = storage.delete_old_notifications(hours=48)

    assert deleted == 1
    remaining = storage.get_user_notifications("default", limit=10)
    assert not any(n["id"] == "old-notif-001" for n in remaining)


def test_save_symbol_mapping_persists_via_transaction_contract(storage: StorageManager) -> None:
    """save_symbol_mapping must persist the mapping row through the transaction contract."""
    storage.save_symbol_mapping(
        internal_symbol="EURUSD",
        provider_id="mt5",
        provider_symbol="EURUSD",
        is_default=True,
    )

    symbol_map = storage.get_symbol_map()

    assert "EURUSD" in symbol_map
    assert "mt5" in symbol_map["EURUSD"]
    assert symbol_map["EURUSD"]["mt5"] == "EURUSD"


def test_update_usr_preferences_persists_via_transaction_contract(storage: StorageManager) -> None:
    """update_usr_preferences must persist user prefs (upsert) through the transaction contract."""
    result = storage.update_usr_preferences(
        user_id="default",
        preferences={"auto_trading_enabled": True, "notify_usr_signals": False},
    )

    assert result is True
    prefs = storage.get_usr_preferences("default")
    assert prefs is not None
    assert prefs["auto_trading_enabled"] == 1


async def test_update_dedup_rule_persists_via_transaction_contract(storage: StorageManager) -> None:
    """update_dedup_rule must persist the learned window through the transaction contract."""
    success = await storage.update_dedup_rule(
        symbol="EURUSD",
        timeframe="M15",
        strategy="EMA_CROSS",
        current_window_minutes=30,
        data_points_observed=100,
        learning_enabled=True,
        trace_id="HU8.6-TEST",
    )

    assert success is True
    rule = await storage.get_dedup_rule("EURUSD", "M15", "EMA_CROSS")
    assert rule is not None
    assert rule["current_window_minutes"] == 30
    assert rule["data_points_observed"] == 100


def test_mark_orphan_shadow_instances_dead_updates_incubating_status(storage: StorageManager) -> None:
    """mark_orphan_shadow_instances_dead must mark INCUBATING instances DEAD via transaction."""
    storage.execute_update(
        "INSERT INTO sys_strategies (class_id, mnemonic, mode) VALUES (?, ?, ?)",
        ("strat-bt-001", "EMA_CROSS_v1", "BACKTEST"),
    )
    storage.execute_update(
        """INSERT INTO sys_shadow_instances
           (instance_id, strategy_id, account_id, account_type, status)
           VALUES (?, ?, ?, ?, ?)""",
        ("inst-001", "strat-bt-001", "demo_acct", "DEMO", "INCUBATING"),
    )

    count = storage.mark_orphan_shadow_instances_dead()

    assert count == 1
    rows = storage.execute_query(
        "SELECT status FROM sys_shadow_instances WHERE instance_id = ?", ("inst-001",)
    )
    assert rows[0]["status"] == "DEAD"


def test_update_strategy_execution_params_persists_via_transaction_contract(storage: StorageManager) -> None:
    """update_strategy_execution_params must persist JSON params through the transaction contract."""
    storage.execute_update(
        "INSERT INTO sys_strategies (class_id, mnemonic, mode) VALUES (?, ?, ?)",
        ("strat-exec-001", "RSI_TREND_v1", "BACKTEST"),
    )
    params_json = '{"adaptive_threshold": 0.75, "failure_count": 0}'

    storage.update_strategy_execution_params("strat-exec-001", params_json)

    rows = storage.execute_query(
        "SELECT execution_params FROM sys_strategies WHERE class_id = ?", ("strat-exec-001",)
    )
    assert rows[0]["execution_params"] == params_json