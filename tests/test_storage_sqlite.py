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

def test_system_state_persistence(storage: StorageManager) -> None:
    """Test saving and retrieving system state"""
    state = {
        "lockdown_mode": True,
        "consecutive_losses": 3,
        "session_stats": {"processed": 100}
    }
    
    storage.update_system_state(state)
    
    # Create new instance to verify persistence
    new_storage = StorageManager(db_path=storage.db_path)
    loaded_state = new_storage.get_system_state()
    
    assert loaded_state["lockdown_mode"] is True
    assert loaded_state["consecutive_losses"] == 3
    assert loaded_state["session_stats"]["processed"] == 100

def test_signal_persistence(storage: StorageManager) -> None:
    """Test saving and retrieving signals with trace_id and status"""
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
    signals = storage.get_signals_today()
    assert len(signals) == 1
    saved_signal = signals[0]
    
    assert saved_signal["symbol"] == "EURUSD"
    assert saved_signal["status"] == "executed"
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
    
    trades = storage.get_recent_trades(limit=10)
    assert len(trades) == 1
    assert trades[0]["symbol"] == "GBPUSD"
    assert trades[0]["profit"] == 50.0
    assert trades[0]["exit_reason"] == "Take Profit"

def test_market_state_logging(storage: StorageManager) -> None:
    """Test logging market states for tuner"""
    state = {
        "symbol": "EURUSD",
        "timestamp": datetime.now().isoformat(),
        "regime": "TREND",
        "adx": 30.5,
        "volatility": 0.0015
    }
    
    storage.log_market_state(state)
    
    states = storage.get_market_state_history(symbol="EURUSD", limit=10)
    assert len(states) == 1
    assert states[0]["data"]["adx"] == 30.5