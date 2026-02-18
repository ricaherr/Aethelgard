
import unittest
from unittest.mock import MagicMock
import logging
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from core_brain.risk_manager import RiskManager
from models.signal import Signal, SignalType, MarketRegime

class TestRiskJPYFix(unittest.TestCase):
    def setUp(self):
        self.storage = MagicMock()
        self.connector = MagicMock()
        self.regime_classifier = MagicMock()
        
        # Mock storage get_system_state
        self.storage.get_system_state.return_value = {
            'lockdown_mode': False,
            'lockdown_date': None,
            'lockdown_balance': None
        }
        
        # Initialize RiskManager with $8386 balance
        self.risk_manager = RiskManager(
            storage=self.storage,
            initial_capital=8386.09,
            config_path='config/dynamic_params.json'
        )
        self.risk_manager.risk_per_trade = 0.01 # 1%

    def test_gbpjpy_point_value_triangulation(self):
        """Verify that GBPJPY uses USDJPY for triangulation, not GBPJPY price."""
        symbol = "GBPJPY"
        entry_price = 190.45
        usdjpy_price = 150.25
        
        # Mock connector.get_current_price for triangulation
        def side_effect(sym):
            if sym == "USDJPY": return usdjpy_price
            return 0.0
        self.connector.get_current_price.side_effect = side_effect
        
        # Mock symbol info
        symbol_info = MagicMock()
        symbol_info.trade_contract_size = 100000
        
        pip_size = 0.01 # JPY
        
        pv = self.risk_manager._calculate_point_value(
            symbol_info=symbol_info,
            pip_size=pip_size,
            entry_price=entry_price,
            symbol=symbol,
            connector=self.connector
        )
        
        # Expected: (100000 * 0.01) / 150.25 = 6.655
        expected_pv = (100000 * 0.01) / 150.25
        self.assertAlmostEqual(pv, expected_pv, places=4)
        print(f"✅ GBPJPY Point Value: {pv:.4f} (Expected: {expected_pv:.4f})")

    def test_risk_sanity_check_rejection(self):
        """Verify that position size is rejected if risk exceeds sanity limits."""
        # Scenario: Calculation somehow results in 2.0% risk (limit is 2.5% but also 10% deviation from target)
        lots = 1.5
        sl_pips = 12.0
        point_value = 10.0 # $10/pip
        target_usd = 83.86 # 1% of 8386
        balance = 8386.09
        
        actual_risk = lots * sl_pips * point_value # 1.5 * 12 * 10 = 180
        
        is_sane, msg = self.risk_manager._validate_risk_sanity(
            lots=lots,
            sl_pips=sl_pips,
            point_value=point_value,
            target_usd=target_usd,
            balance=balance
        )
        
        self.assertFalse(is_sane)
        self.assertIn("Risk deviation too high", msg)
        print(f"✅ Sanity check rejected high deviation: {msg}")

if __name__ == '__main__':
    unittest.main()
