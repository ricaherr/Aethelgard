"""
Database Purge Script
Removes ghost records that don't have corresponding real MT5 positions/tickets.
Run this when the bot shows 'position exists' but MT5 account is empty.
"""
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager
from connectors.mt5_connector import get_mt5_connector

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def purge_ghost_records():
    """Purge signals and trades that don't exist in real MT5 account"""
    storage = StorageManager()

    # Get MT5 connector
    mt5_connector = get_mt5_connector()
    if not mt5_connector:
        logger.error("MT5 connector not available. Cannot verify real positions.")
        return

    if not mt5_connector.is_connected:
        logger.error("MT5 not connected. Cannot verify real positions.")
        return

    logger.info("🔍 Starting database purge against MT5 reality...")

    # Get all executed signals
    executed_signals = storage.get_signals(status='executed')
    logger.info(f"Found {len(executed_signals)} executed signals in DB")

    # Get real MT5 positions
    real_positions = mt5_connector.get_open_positions()
    if real_positions is None:
        logger.error("Failed to get MT5 positions")
        return

    real_tickets = {pos.get('ticket') for pos in real_positions}
    logger.info(f"Found {len(real_tickets)} real positions in MT5")

    # Find ghost signals (executed but no real ticket)
    ghost_signals = []
    for signal in executed_signals:
        ticket = signal.get('order_id') or signal.get('ticket')
        if ticket and int(ticket) not in real_tickets:
            ghost_signals.append(signal)

    logger.info(f"Found {len(ghost_signals)} ghost signals to purge")

    # Purge ghost signals
    purged_count = 0
    for signal in ghost_signals:
        signal_id = signal['id']
        symbol = signal['symbol']

        # Mark as ghost cleared
        storage.clear_ghost_position(symbol)
        purged_count += 1
        logger.info(f"🧹 Purged ghost signal: {symbol} (ID: {signal_id})")

    logger.info(f"✅ Purge complete. Cleared {purged_count} ghost records.")


if __name__ == "__main__":
    logger.info("🧽 Starting Aethelgard Database Purge")
    purge_ghost_records()
    logger.info("✨ Purge finished")