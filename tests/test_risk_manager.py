"""
Test Suite for RiskManager
Validates position sizing, risk reduction, and lockdown mode
Following TDD methodology for Aethelgard
"""
import pytest
from datetime import datetime
from core_brain.risk_manager import RiskManager
from models.signal import MarketRegime


class TestRiskManagerBasics:
    """Test basic initialization and configuration"""
    
    def test_risk_manager_initialization(self):
        """Should initialize with default parameters"""
        rm = RiskManager(initial_capital=10000)
        assert rm.capital == 10000
        assert rm.base_risk_pct == 1.0
        assert rm.volatile_risk_pct == 0.5
        assert rm.max_consecutive_losses == 3
        assert rm.is_locked is False
    
    def test_custom_initialization(self):
        """Should accept custom risk parameters"""
        rm = RiskManager(
            initial_capital=50000,
            base_risk_pct=2.0,
            volatile_risk_pct=1.0,
            max_consecutive_losses=5
        )
        assert rm.capital == 50000
        assert rm.base_risk_pct == 2.0
        assert rm.volatile_risk_pct == 1.0
        assert rm.max_consecutive_losses == 5


class TestPositionSizing:
    """Test position size calculations"""
    
    def test_position_size_normal_regime_trend(self):
        """Should calculate 1% risk in TREND regime"""
        rm = RiskManager(initial_capital=10000)
        
        # Capital: 10000, Risk: 1% = 100
        # Entry: 100, SL: 95, Risk per unit: 5
        # Position size: 100 / 5 = 20 units
        size = rm.calculate_position_size(
            regime=MarketRegime.TREND,
            entry_price=100.0,
            stop_loss=95.0
        )
        assert size == 20.0
    
    def test_position_size_normal_regime_neutral(self):
        """Should calculate 1% risk in NEUTRAL regime"""
        rm = RiskManager(initial_capital=10000)
        
        # Capital: 10000, Risk: 1% = 100
        # Entry: 50, SL: 48, Risk per unit: 2
        # Position size: 100 / 2 = 50 units
        size = rm.calculate_position_size(
            regime=MarketRegime.NEUTRAL,
            entry_price=50.0,
            stop_loss=48.0
        )
        assert size == 50.0
    
    def test_position_size_volatile_regime(self):
        """Should calculate 0.5% risk in VOLATILE/RANGE regime"""
        rm = RiskManager(initial_capital=10000)
        
        # Capital: 10000, Risk: 0.5% = 50
        # Entry: 100, SL: 95, Risk per unit: 5
        # Position size: 50 / 5 = 10 units (half of normal)
        size = rm.calculate_position_size(
            regime=MarketRegime.RANGE,
            entry_price=100.0,
            stop_loss=95.0
        )
        assert size == 10.0
    
    def test_position_size_crash_regime(self):
        """Should calculate 0.5% risk in CRASH regime"""
        rm = RiskManager(initial_capital=10000)
        
        # Capital: 10000, Risk: 0.5% = 50
        # Entry: 200, SL: 190, Risk per unit: 10
        # Position size: 50 / 10 = 5 units
        size = rm.calculate_position_size(
            regime=MarketRegime.CRASH,
            entry_price=200.0,
            stop_loss=190.0
        )
        assert size == 5.0
    
    def test_position_size_zero_risk(self):
        """Should return 0 if stop_loss equals entry_price"""
        rm = RiskManager(initial_capital=10000)
        
        size = rm.calculate_position_size(
            regime=MarketRegime.TREND,
            entry_price=100.0,
            stop_loss=100.0
        )
        assert size == 0.0
    
    def test_position_size_invalid_stop_loss(self):
        """Should handle invalid stop loss (beyond entry for long)"""
        rm = RiskManager(initial_capital=10000)
        
        # SL above entry for long position - invalid
        size = rm.calculate_position_size(
            regime=MarketRegime.TREND,
            entry_price=100.0,
            stop_loss=105.0
        )
        assert size == 0.0


class TestLockdownMode:
    """Test lockdown mode activation and recovery"""
    
    def test_single_loss_no_lockdown(self):
        """Should not activate lockdown after single loss"""
        rm = RiskManager(initial_capital=10000)
        
        rm.record_trade_result(is_win=False, pnl=-100)
        assert rm.is_locked is False
        assert rm.consecutive_losses == 1
    
    def test_two_losses_no_lockdown(self):
        """Should not activate lockdown after two losses"""
        rm = RiskManager(initial_capital=10000)
        
        rm.record_trade_result(is_win=False, pnl=-100)
        rm.record_trade_result(is_win=False, pnl=-150)
        assert rm.is_locked is False
        assert rm.consecutive_losses == 2
    
    def test_three_losses_activates_lockdown(self):
        """Should activate lockdown after 3 consecutive losses"""
        rm = RiskManager(initial_capital=10000)
        
        rm.record_trade_result(is_win=False, pnl=-100)
        rm.record_trade_result(is_win=False, pnl=-150)
        rm.record_trade_result(is_win=False, pnl=-200)
        
        assert rm.is_locked is True
        assert rm.consecutive_losses == 3
    
    def test_win_resets_consecutive_losses(self):
        """Should reset consecutive losses counter after win"""
        rm = RiskManager(initial_capital=10000)
        
        rm.record_trade_result(is_win=False, pnl=-100)
        rm.record_trade_result(is_win=False, pnl=-150)
        rm.record_trade_result(is_win=True, pnl=200)
        
        assert rm.is_locked is False
        assert rm.consecutive_losses == 0
    
    def test_lockdown_prevents_trading(self):
        """Should return 0 position size when locked"""
        rm = RiskManager(initial_capital=10000)
        
        # Activate lockdown
        rm.record_trade_result(is_win=False, pnl=-100)
        rm.record_trade_result(is_win=False, pnl=-150)
        rm.record_trade_result(is_win=False, pnl=-200)
        
        # Try to calculate position size
        size = rm.calculate_position_size(
            regime=MarketRegime.TREND,
            entry_price=100.0,
            stop_loss=95.0
        )
        
        assert size == 0.0
        assert rm.is_locked is True
    
    def test_manual_unlock(self):
        """Should allow manual unlock of lockdown mode"""
        rm = RiskManager(initial_capital=10000)
        
        # Activate lockdown
        rm.record_trade_result(is_win=False, pnl=-100)
        rm.record_trade_result(is_win=False, pnl=-150)
        rm.record_trade_result(is_win=False, pnl=-200)
        assert rm.is_locked is True
        
        # Manual unlock
        rm.unlock()
        assert rm.is_locked is False
        assert rm.consecutive_losses == 0
    
    def test_capital_updates_after_trades(self):
        """Should update capital after recording trades"""
        rm = RiskManager(initial_capital=10000)
        
        rm.record_trade_result(is_win=True, pnl=500)
        assert rm.capital == 10500
        
        rm.record_trade_result(is_win=False, pnl=-300)
        assert rm.capital == 10200
        
        rm.record_trade_result(is_win=True, pnl=800)
        assert rm.capital == 11000


class TestRiskValidation:
    """Test risk validation and edge cases"""
    
    def test_can_trade_when_unlocked(self):
        """Should allow trading when not locked"""
        rm = RiskManager(initial_capital=10000)
        assert rm.can_trade() is True
    
    def test_cannot_trade_when_locked(self):
        """Should prevent trading when locked"""
        rm = RiskManager(initial_capital=10000)
        
        # Activate lockdown
        for _ in range(3):
            rm.record_trade_result(is_win=False, pnl=-100)
        
        assert rm.can_trade() is False
    
    def test_get_current_risk_pct_trend(self):
        """Should return base risk for TREND regime"""
        rm = RiskManager(initial_capital=10000)
        risk_pct = rm.get_current_risk_pct(MarketRegime.TREND)
        assert risk_pct == 1.0
    
    def test_get_current_risk_pct_range(self):
        """Should return reduced risk for RANGE regime"""
        rm = RiskManager(initial_capital=10000)
        risk_pct = rm.get_current_risk_pct(MarketRegime.RANGE)
        assert risk_pct == 0.5
    
    def test_get_current_risk_pct_crash(self):
        """Should return reduced risk for CRASH regime"""
        rm = RiskManager(initial_capital=10000)
        risk_pct = rm.get_current_risk_pct(MarketRegime.CRASH)
        assert risk_pct == 0.5
    
    def test_get_status_report(self):
        """Should provide comprehensive status report"""
        rm = RiskManager(initial_capital=10000)
        
        rm.record_trade_result(is_win=False, pnl=-100)
        rm.record_trade_result(is_win=False, pnl=-150)
        
        status = rm.get_status()
        
        assert status['capital'] == 9750
        assert status['consecutive_losses'] == 2
        assert status['is_locked'] is False
        assert status['base_risk_pct'] == 1.0
        assert 'trades_until_lockdown' in status
        assert status['trades_until_lockdown'] == 1
