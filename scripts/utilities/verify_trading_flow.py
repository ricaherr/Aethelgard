"""
Verify Full Trading Flow: Signal -> Risk -> Execution -> Feedback
This script validates each step of the Aethelgard trading lifecycle.
"""
import sys
import asyncio
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.signal import Signal, SignalType, ConnectorType, MarketRegime
from core_brain.risk_manager import RiskManager
from core_brain.executor import OrderExecutor
from data_vault.storage import StorageManager
from connectors.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("VerificationFlow")

class MockConnector:
    """Mock connector for testing the flow without a real terminal"""
    def connect(self) -> bool: return True
    def execute_signal(self, signal) -> dict:
        return {
            "success": True,
            "ticket": 12345678,
            "price": 1.0855,
            "status": "success"
        }

async def verify_flow():
    success_count = 0
    total_steps = 6
    
    logger.info("=" * 60)
    logger.info("🚀 STARTING FULL TRADING FLOW VERIFICATION")
    logger.info("=" * 60)

    # 1. Initialize Components
    logger.info("\nStep 1: Initializing Components...")
    storage = StorageManager()
    risk_manager = RiskManager(storage=storage, initial_capital=10000.0)
    
    # Try to connect MT5, fallback to Mock
    executor = OrderExecutor(risk_manager=risk_manager, storage=storage)
    
    try:
        mt5_connector = MT5Connector()
        if mt5_connector.connect():
            logger.info("✅ MT5 Connected successfully")
            executor.connectors[ConnectorType.METATRADER5] = mt5_connector
        else:
            logger.warning("⚠️ MT5 Connection failed. Using MockConnector for flow verification.")
            executor.connectors[ConnectorType.METATRADER5] = MockConnector()
    except Exception as e:
        logger.warning(f"⚠️ MT5 initialization error ({e}). Using MockConnector.")
        executor.connectors[ConnectorType.METATRADER5] = MockConnector()
    
    success_count += 1
    logger.info(f"Progress: {success_count}/{total_steps}")

    # 2. Create Dummy Signal with realistic prices
    logger.info("\nStep 2: Creating Dummy Signal...")
    
    # Get current price from connector (agnostic approach)
    if ConnectorType.METATRADER5 in executor.connectors:
        connector = executor.connectors[ConnectorType.METATRADER5]
        if hasattr(connector, 'get_symbol_info'):
            symbol_info = connector.get_symbol_info("EURUSD")
            if symbol_info and hasattr(symbol_info, 'ask'):
                current_price = symbol_info.ask
            else:
                logger.warning("Could not get tick, using fallback price")
                current_price = 1.0850  # Fallback
        else:
            current_price = 1.0850  # Mock connector fallback
    else:
        current_price = 1.0850  # No MT5 connector, use fallback
    sl_distance_pips = 50  # 50 pips stop loss
    tp_distance_pips = 150  # 150 pips take profit (3:1 R:R)
    pip_size = 0.0001  # EURUSD pip size
    
    signal = Signal(
        symbol="EURUSD",
        signal_type="BUY",
        confidence=0.85,
        entry_price=current_price,
        stop_loss=current_price - (sl_distance_pips * pip_size),
        take_profit=current_price + (tp_distance_pips * pip_size),
        volume=0.10,  # IC Markets minimum lot size
        connector_type=ConnectorType.METATRADER5,
        metadata={"strategy_id": "VerificationTest", "regime": "TREND"}
    )
    
    logger.info(f"✅ Created Signal: {signal.signal_type.value} {signal.symbol} @ {current_price:.5f}")
    logger.info(f"   SL: {signal.stop_loss:.5f} (-{sl_distance_pips} pips)")
    logger.info(f"   TP: {signal.take_profit:.5f} (+{tp_distance_pips} pips)")
    success_count += 1
    logger.info(f"Progress: {success_count}/{total_steps}")

    # 3. Risk Validation
    logger.info("\nStep 3: Risk Validation...")
    is_risk_ok = not risk_manager.is_locked()
    if is_risk_ok:
        logger.info("✅ Risk validation passed (Not in lockdown)")
    else:
        logger.error("❌ Risk validation failed (Lockdown active)!")
        return
    success_count += 1
    logger.info(f"Progress: {success_count}/{total_steps}")

    # 4. Execution
    logger.info("\nStep 4: Executing Signal...")
    execution_success = await executor.execute_signal(signal)
    
    if execution_success:
        logger.info("✅ Execution step completed")
    else:
        logger.error("❌ Execution step failed!")
        return
    success_count += 1
    logger.info(f"Progress: {success_count}/{total_steps}")

    # 5. Database Verification
    logger.info("\nStep 5: Verifying Database Persistence...")
    signals_today = storage.get_signals_today()
    found = False
    for s in signals_today:
        if s['symbol'] == "EURUSD" and s['metadata'].get('strategy_id') == "VerificationTest":
            logger.info(f"✅ Signal found in DB with ID: {s['id']}")
            found = True
            signal_db_id = s['id']
            break
    
    if not found:
        logger.error("❌ Signal NOT found in database!")
        return
    success_count += 1
    logger.info(f"Progress: {success_count}/{total_steps}")

    # 6. Feedback Loop (Closing Position)
    logger.info("\nStep 6: Simulating Feedback Loop (Closing Position)...")
    # Simulate a result
    trade_result = {
        "signal_id": signal_db_id,
        "symbol": "EURUSD",
        "entry_price": 1.0850,
        "exit_price": 1.0950,
        "pips": 100.0,
        "profit_loss": 150.0,
        "duration_minutes": 120,
        "is_win": True,
        "exit_reason": "take_profit",
        "market_regime": "TREND",
        "volatility_atr": 0.0015,
        "parameters_used": {"adx": 35}
    }
    
    try:
        trade_id = storage.save_trade_result(trade_result)
        logger.info(f"✅ Trade result persisted in Feedback Loop. ID: {trade_id}")
        
        # Verify stats update
        stats = storage.get_statistics()
        logger.info(f"✅ Current stats: Total Signals={stats['total_signals']}")
    except Exception as e:
        logger.error(f"❌ Feedback loop error: {e}")
        return
        
    success_count += 1
    logger.info(f"Progress: {success_count}/{total_steps}")

    logger.info("\n" + "=" * 60)
    logger.info("🏁 VERIFICATION COMPLETED SUCCESSFULLY!")
    logger.info(f"All {success_count}/{total_steps} steps passed.")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(verify_flow())
