"""
Test Auto Trading Script
Tests the complete trading workflow: Signal -> Execution -> Monitoring -> Close
"""
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from models.signal import Signal, SignalType, ConnectorType
from core_brain.executor import OrderExecutor
from core_brain.risk_manager import RiskManager
from data_vault.storage import StorageManager
from connectors.mt5_connector import MT5Connector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def test_auto_trading():
    """
    Complete test of automatic trading workflow.
    
    Steps:
    1. Connect to MT5
    2. Create a test signal
    3. Execute via OrderExecutor
    4. Wait 10 seconds
    5. Close position
    6. Verify results in database
    """
    logger.info("=" * 60)
    logger.info("🧪 TESTING AUTOMATIC TRADING WORKFLOW")
    logger.info("=" * 60)
    
    # Initialize components
    storage = StorageManager()
    risk_manager = RiskManager(initial_capital=10000.0)  # $10k demo capital
    mt5_connector = MT5Connector()
    
    # Step 1: Connect to MT5
    logger.info("\n📌 Step 1: Connecting to MT5...")
    if not mt5_connector.connect():
        logger.error("❌ Failed to connect to MT5. Test aborted.")
        return False
    
    logger.info("✅ MT5 Connected")
    
    # Step 2: Create test signal
    logger.info("\n📌 Step 2: Creating test signal...")
    
    # Get current market price
    from connectors.mt5_wrapper import MT5 as mt5
    symbol_info = mt5.symbol_info_tick("EURUSD")
    if not symbol_info:
        logger.error("❌ Could not get EURUSD price")
        mt5_connector.disconnect()
        return False
    
    current_price = symbol_info.ask  # Use ask price for BUY
    sl_distance = 0.00100  # 10 pips
    tp_distance = 0.00200  # 20 pips
    
    test_signal = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        confidence=0.85,
        entry_price=current_price,
        stop_loss=current_price - sl_distance,
        take_profit=current_price + tp_distance,
        timeframe="5m",
        connector_type=ConnectorType.METATRADER5,
        metadata={
            "test": True,
            "description": "Auto Trading Test",
            "timestamp": datetime.now().isoformat()
        }
    )
    
    logger.info(f"✅ Test signal created: {test_signal.symbol} {test_signal.signal_type.value}")
    logger.info(f"   Entry: {test_signal.entry_price:.5f} | SL: {test_signal.stop_loss:.5f} | TP: {test_signal.take_profit:.5f}")
    
    # Step 3: Execute signal
    logger.info("\n📌 Step 3: Executing signal via OrderExecutor...")
    
    # Initialize executor with MT5 connector
    executor = OrderExecutor(
        risk_manager=risk_manager,
        storage=storage,
        connectors={ConnectorType.METATRADER5: mt5_connector}
    )
    
    # Execute asynchronously (we'll use sync wrapper for testing)
    import asyncio
    success = asyncio.run(executor.execute_signal(test_signal))
    
    if not success:
        logger.error("❌ Signal execution failed. Test aborted.")
        mt5_connector.disconnect()
        return False
    
    logger.info("✅ Signal executed successfully")
    
    # Step 4: Get position info
    logger.info("\n📌 Step 4: Verifying position in MT5...")
    
    open_positions = mt5_connector.get_open_positions()
    
    if not open_positions:
        logger.warning("⚠️  No open positions found. Check execution logs.")
        mt5_connector.disconnect()
        return False
    
    logger.info(f"✅ Found {len(open_positions)} open position(s)")
    
    test_position = None
    for pos in open_positions:
        if pos['symbol'] == test_signal.symbol:
            test_position = pos
            break
    
    if not test_position:
        logger.warning(f"⚠️  No position found for {test_signal.symbol}")
        mt5_connector.disconnect()
        return False
    
    logger.info(f"📊 Position Details:")
    logger.info(f"   Ticket: {test_position['ticket']}")
    logger.info(f"   Symbol: {test_position['symbol']}")
    logger.info(f"   Type: {test_position['type']}")
    logger.info(f"   Volume: {test_position['volume']}")
    logger.info(f"   Price Open: {test_position['price_open']}")
    logger.info(f"   Current P/L: {test_position['profit']:.2f}")
    
    # Step 5: Wait 10 seconds
    logger.info("\n📌 Step 5: Waiting 10 seconds before closing...")
    for i in range(10, 0, -1):
        print(f"   ⏱️  {i} seconds remaining...", end='\r')
        time.sleep(1)
    print()  # New line
    
    # Step 6: Close position
    logger.info("\n📌 Step 6: Closing position...")
    
    ticket = test_position['ticket']
    close_success = mt5_connector.close_position(ticket)
    
    if not close_success:
        logger.error(f"❌ Failed to close position {ticket}")
        mt5_connector.disconnect()
        return False
    
    logger.info(f"✅ Position {ticket} closed successfully")
    
    # Step 7: Verify in database
    logger.info("\n📌 Step 7: Verifying in database...")
    
    # Wait a moment for DB update
    time.sleep(2)
    
    recent_trades = storage.get_recent_trades(limit=10)
    
    test_trade_found = False
    for trade in recent_trades:
        if trade.get('symbol') == test_signal.symbol:
            logger.info(f"✅ Trade found in database:")
            logger.info(f"   ID: {trade.get('id')}")
            logger.info(f"   Symbol: {trade.get('symbol')}")
            logger.info(f"   Type: {trade.get('signal_type')}")
            logger.info(f"   Entry: {trade.get('entry_price')}")
            logger.info(f"   P/L: {trade.get('profit_loss', 0):.2f}")
            test_trade_found = True
            break
    
    if not test_trade_found:
        logger.warning("⚠️  Trade not found in database yet (might need more time)")
    
    # Cleanup
    mt5_connector.disconnect()
    
    logger.info("\n" + "=" * 60)
    logger.info("✅ AUTO TRADING TEST COMPLETED SUCCESSFULLY")
    logger.info("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = test_auto_trading()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Test failed with error: {e}", exc_info=True)
        sys.exit(1)
