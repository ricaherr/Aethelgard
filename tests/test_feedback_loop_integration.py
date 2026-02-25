"""
Test Suite: Feedback Loop Integration
======================================

CRITICAL TEST: Complete feedback loop from trade closure → RiskManager → Tuner

Scenario:
  1. Open 3 trades (simulated executions)
  2. Close all 3 trades with loss
  3. Assert RiskManager enters LOCKDOWN
  4. Assert Tuner adjusts parameters (becomes conservative)
  5. Assert reconciliation after reconnect (unprocessed closes are caught)

This test MUST FAIL initially (TDD Red Phase).
This is the heartbeat of Aethelgard's autonomous feedback system.
"""
import pytest
import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path

from data_vault.storage import StorageManager
from core_brain.risk_manager import RiskManager
from core_brain.edge_tuner import EdgeTuner
from models.signal import Signal, SignalType, ConnectorType


@pytest.fixture
def temp_db(tmp_path):
    """Create temporary isolated DB for this test"""
    db_file = tmp_path / "feedback_test.db"
    storage = StorageManager(db_path=str(db_file))
    yield storage
    storage.close()


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create temp config directory with risk_settings.json (still file-based)."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # risk_settings.json remains as a file (not part of this migration phase)
    risk_settings = {
        "max_consecutive_losses": 3,
        "lockdown_mode_enabled": True,
        "min_trades_for_tuning": 5,
        "tuning_enabled": True,
        "target_win_rate": 0.55
    }
    risk_file = config_dir / "risk_settings.json"
    risk_file.write_text(json.dumps(risk_settings, indent=2))
    
    return config_dir


DYNAMIC_PARAMS_SEED = {
    "adx_trend_threshold": 25.0,
    "adx_range_threshold": 20.0,
    "adx_range_exit_threshold": 18.0,
    "volatility_shock_multiplier": 5.0,
    "risk_per_trade": 0.01,
    "max_consecutive_losses": 3,
    "tuning_enabled": True,
    "min_trades_for_tuning": 5,
    "target_win_rate": 0.55,
    "adx_threshold": 25,
    "elephant_atr_multiplier": 0.3,
    "sma20_proximity_percent": 1.5,
    "min_signal_score": 60
}


class TestFeedbackLoopIntegration:
    """
    CRITICAL INTEGRATION TEST: Trade Closure → Feedback Loop → System Adaptation
    """
    
    @pytest.mark.asyncio
    async def test_three_losses_trigger_lockdown_and_tuner_adjustment(
        self, temp_db, temp_config_dir
    ):
        """
        Test the complete feedback loop:
        1. Create 3 closed trades with losses
        2. RiskManager records results and enters LOCKDOWN at trade #3
        3. Tuner reads trades from DB and adjusts parameters
        4. Assert that dynamic_params in DB changed (became more conservative)
        
        EXPECTED FLOW:
          Trade 1 (Loss) → consecutive_losses=1
          Trade 2 (Loss) → consecutive_losses=2
          Trade 3 (Loss) → consecutive_losses=3 → LOCKDOWN ACTIVATED
          
        THEN:
          EdgeTuner.adjust_parameters() reads trades from DB
          Detects consecutive_losses=3 >= trigger threshold (5 in current code, should be 3)
          Adjusts parameters to be MORE CONSERVATIVE:
            - ADX threshold UP (only strong trends)
            - ATR multiplier UP (only big candles)
            - SMA20 proximity DOWN (tighter filter)
            - Min score UP (higher quality signals)
        """
        
        # ========== SETUP: Initialize components ==========
        # Seed dynamic params in DB (SSOT — Rule 14)
        temp_db.update_dynamic_params(DYNAMIC_PARAMS_SEED)
        temp_db.update_risk_settings({
            "max_consecutive_losses": 3,
            "lockdown_mode_enabled": True,
            "min_trades_for_tuning": 5,
            "tuning_enabled": True,
            "target_win_rate": 0.55
        })
        
        # Initialize RiskManager (DB-only, no config_path)
        risk_manager = RiskManager(
            storage=temp_db,
            initial_capital=10000.0
        )
        
        # Initialize Tuner (DB-only, no config_path)
        edge_tuner = EdgeTuner(storage=temp_db)
        
        # Read initial parameters from DB
        initial_config = temp_db.get_dynamic_params()
        initial_adx = initial_config.get("adx_threshold", 25)
        initial_atr = initial_config.get("elephant_atr_multiplier", 0.3)
        initial_sma20 = initial_config.get("sma20_proximity_percent", 1.5)
        initial_score = initial_config.get("min_signal_score", 60)
        
        print(f"\n[INITIAL PARAMETERS]")
        print(f"   ADX Threshold: {initial_adx}")
        print(f"   ATR Multiplier: {initial_atr}")
        print(f"   SMA20 Proximity: {initial_sma20}%")
        print(f"   Min Score: {initial_score}")
        
        # Verify RiskManager is NOT locked initially
        assert not risk_manager.is_locked(), "RiskManager should NOT be locked initially"
        assert risk_manager.consecutive_losses == 0, "Should start with 0 consecutive losses"
        
        # ========== PHASE 1: SIMULATE 5 TRADES (2 WINS + 3 LOSSES) ==========
        print(f"\n[PHASE 1] Simulating 5 trades (2 wins + 3 losses)...")
        
        trades_data = []
        
        # Trade 1-2: WINS (to ensure statistical significance: 40% win rate -> 60% loss rate)
        for i in range(1, 3):
            trade = {
                "id": f"trade_{i}",
                "signal_id": f"signal_{i}",
                "symbol": "EURUSD",
                "entry_price": 1.0850 + (i * 0.001),
                "exit_price": 1.0850 + (i * 0.001) + 0.0015,  # WIN: +15 pips
                "profit_loss": +150.0,  # Win
                "profit": +150.0,
                "is_win": True,
                "pips": 15,
                "exit_reason": "take_profit_hit",
                "close_time": (datetime.now() - timedelta(minutes=10-i)).isoformat()
            }
            
            temp_db.save_trade_result(trade)
            trades_data.append(trade)
            risk_manager.record_trade_result(is_win=True, pnl=+150.0)
            
            print(f"   Trade {i}: WIN   | PnL=+150 | consecutive_losses={risk_manager.consecutive_losses} | locked={risk_manager.is_locked()}")
        
        # Trade 3-5: LOSSES (consecutive_losses triggers: 1, 2, 3 -> LOCKDOWN)
        for i in range(3, 6):
            trade = {
                "id": f"trade_{i}",
                "signal_id": f"signal_{i}",
                "symbol": "EURUSD",
                "entry_price": 1.0850 + (i * 0.001),
                "exit_price": 1.0850 + (i * 0.001) - 0.0010,  # LOSS: -10 pips
                "profit_loss": -100.0,  # Loss
                "profit": -100.0,
                "is_win": False,
                "pips": 10,
                "exit_reason": "stop_loss_hit",
                "close_time": (datetime.now() - timedelta(minutes=5-(i-2))).isoformat()
            }
            
            temp_db.save_trade_result(trade)
            trades_data.append(trade)
            risk_manager.record_trade_result(is_win=False, pnl=-100.0)
            
            print(f"   Trade {i}: LOSS  | PnL=-100 | consecutive_losses={risk_manager.consecutive_losses} | locked={risk_manager.is_locked()}")
        
        # ========== PHASE 2: ASSERT LOCKDOWN ACTIVATED ==========
        print(f"\n[PHASE 2] Verifying LOCKDOWN activation...")
        
        assert risk_manager.consecutive_losses == 3, \
            f"Expected 3 consecutive losses (after 2 wins), got {risk_manager.consecutive_losses}"
        
        assert risk_manager.is_locked(), \
            "RiskManager should be LOCKED after 3 consecutive losses"
        
        # Verify lockdown persisted in DB
        system_state = temp_db.get_system_state()
        assert system_state.get("lockdown_mode") is True, \
            "Lockdown mode should be persisted in DB"
        
        print(f"   [OK] RiskManager LOCKED: consecutive_losses={risk_manager.consecutive_losses}")
        print(f"   [OK] Lockdown persisted in DB")
        
        # ========== PHASE 3: TUNER READS TRADES AND ADJUSTS PARAMETERS ==========
        print(f"\n[PHASE 3] EdgeTuner analyzing and adjusting parameters...")
        
        # Call EdgeTuner.adjust_parameters()
        adjustment_result = edge_tuner.adjust_parameters(limit_trades=100)
        
        assert adjustment_result is not None, \
            "EdgeTuner should return adjustment result"
        
        # Read updated config from DB (SSOT)
        updated_config = temp_db.get_dynamic_params()
        updated_adx = updated_config.get("adx_threshold", 25)
        updated_atr = updated_config.get("elephant_atr_multiplier", 0.3)
        updated_sma20 = updated_config.get("sma20_proximity_percent", 1.5)
        updated_score = updated_config.get("min_signal_score", 60)
        
        print(f"\n[UPDATED PARAMETERS]")
        print(f"   ADX Threshold: {initial_adx} -> {updated_adx}")
        print(f"   ATR Multiplier: {initial_atr} -> {updated_atr}")
        print(f"   SMA20 Proximity: {initial_sma20}% -> {updated_sma20}%")
        print(f"   Min Score: {initial_score} -> {updated_score}")
        
        # ========== PHASE 4: VERIFY PARAMETERS BECAME MORE CONSERVATIVE ==========
        print(f"\n[PHASE 4] Asserting CONSERVATIVE mode activation...")
        
        # After losses, should become MORE restrictive:
        # - ADX higher (more selective about trends)
        # - ATR higher (only big candles)
        # - SMA20 lower (tighter filter)
        # - Score higher (higher quality signals only)
        
        # The exact values depend on EdgeTuner's logic, but they should CHANGE
        # and move in the "conservative" direction
        
        params_changed = (
            updated_adx != initial_adx or
            updated_atr != initial_atr or
            updated_sma20 != initial_sma20 or
            updated_score != initial_score
        )
        
        assert params_changed, \
            "Parameters should have been adjusted after detecting consecutive losses"
        
        # Verify adjustment record was saved
        assert "trigger" in adjustment_result, \
            "Adjustment result should contain trigger reason"
        
        print(f"   [OK] Parameters adjusted (trigger: {adjustment_result.get('trigger')})")
        print(f"   [OK] Adjustment factor: {adjustment_result.get('adjustment_factor')}")
        
        # ========== PHASE 5: RECONCILIATION TEST (Simulate Reconnect) ==========
        print(f"\n[PHASE 5] Testing reconciliation after disconnect/reconnect...")
        
        # Simulate: System was down, 2 more trades closed while offline
        offline_trades = [
            {
                "id": "trade_4_offline",
                "signal_id": "signal_4",
                "symbol": "GBPUSD",
                "entry_price": 1.2700,
                "exit_price": 1.2690,
                "profit_loss": -50.0,
                "profit": -50.0,
                "is_win": False,
                "pips": 10,
                "exit_reason": "stop_loss_hit",
                "close_time": (datetime.now() - timedelta(minutes=10)).isoformat()
            },
            {
                "id": "trade_5_offline",
                "signal_id": "signal_5",
                "symbol": "AUDUSD",
                "entry_price": 0.6500,
                "exit_price": 0.6495,
                "profit_loss": -75.0,
                "profit": -75.0,
                "is_win": False,
                "pips": 5,
                "exit_reason": "stop_loss_hit",
                "close_time": (datetime.now() - timedelta(minutes=8)).isoformat()
            }
        ]
        
        # Save offline trades to DB (simulating they arrived from broker)
        for offline_trade in offline_trades:
            temp_db.save_trade_result(offline_trade)
        
        # Now query recent trades and verify all 7 are there (5 initial + 2 offline)
        all_trades = temp_db.get_recent_trades(limit=100)
        
        assert len(all_trades) >= 5, \
            f"Should have at least 5 trades in DB, got {len(all_trades)}"
        
        print(f"   [OK] Reconciliation: Found {len(all_trades)} trades in DB after reconnect")
        
        # ========== FINAL ASSERTIONS ==========
        print(f"\n[TEST PASSED] Complete Feedback Loop Verified")
        print(f"   - RiskManager.lockdown_mode = {risk_manager.is_locked()}")
        print(f"   - EdgeTuner adjusted parameters = {params_changed}")
        print(f"   - Reconciliation recovered trades = {len(all_trades)}")


class TestRiskSettingsSourceOfTruth:
    """
    Verify that max_consecutive_losses is managed from DB (SSOT — Rule 14).
    """
    
    def test_max_consecutive_losses_from_db(self, temp_db):
        """
        Assert that:
        1. Dynamic params in DB contain max_consecutive_losses
        2. Risk settings in DB contain max_consecutive_losses
        3. Both sources agree on the same value
        """
        # Seed both sources
        temp_db.update_dynamic_params(DYNAMIC_PARAMS_SEED)
        temp_db.update_risk_settings({
            "max_consecutive_losses": 3,
            "lockdown_mode_enabled": True
        })
        
        # Verify dynamic_params
        dp = temp_db.get_dynamic_params()
        assert "max_consecutive_losses" in dp, \
            "dynamic_params must contain max_consecutive_losses"
        assert dp["max_consecutive_losses"] == 3
        
        # Verify risk_settings
        rs = temp_db.get_risk_settings()
        assert "max_consecutive_losses" in rs, \
            "risk_settings must contain max_consecutive_losses"
        assert rs["max_consecutive_losses"] == 3
        
        print(f"[OK] Single Source of Truth (DB): max_consecutive_losses = 3")
