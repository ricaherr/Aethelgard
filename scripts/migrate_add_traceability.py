"""
Database Migration: Add Traceability Fields
Adds connector_type, account_id, account_type (DEMO/REAL), market_type to signals and trades.
"""
import sqlite3
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = "data_vault/aethelgard.db"

def migrate_database():
    """Add traceability columns to signals and trades tables."""
    
    if not Path(DB_PATH).exists():
        logger.error(f"Database not found at {DB_PATH}")
        return False
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    try:
        # Check current schema for signals
        cursor.execute("PRAGMA table_info(signals)")
        signals_columns = [col[1] for col in cursor.fetchall()]
        
        # Add missing columns to signals
        new_columns_signals = {
            'connector_type': 'TEXT',  # METATRADER5, NINJATRADER8, PAPER, etc.
            'account_id': 'TEXT',      # UUID de la cuenta en tabla accounts
            'account_type': 'TEXT',    # DEMO, REAL
            'market_type': 'TEXT',     # FOREX, CRYPTO, STOCKS, FUTURES
            'platform': 'TEXT',        # MT5, NT8, BINANCE, etc.
            'order_id': 'TEXT',        # ID de orden del broker
            'volume': 'REAL'           # Volumen/lotes ejecutados
        }
        
        for col_name, col_type in new_columns_signals.items():
            if col_name not in signals_columns:
                logger.info(f"Adding column '{col_name}' to signals table...")
                cursor.execute(f"ALTER TABLE signals ADD COLUMN {col_name} {col_type}")
                logger.info(f"  ✅ Added {col_name}")
        
        # Check current schema for trades
        cursor.execute("PRAGMA table_info(trades)")
        trades_columns = [col[1] for col in cursor.fetchall()]
        
        # Add missing columns to trades
        new_columns_trades = {
            'connector_type': 'TEXT',
            'account_id': 'TEXT',
            'account_type': 'TEXT',
            'market_type': 'TEXT',
            'platform': 'TEXT',
            'volume': 'REAL',
            'commission': 'REAL',     # Comisiones pagadas
            'swap': 'REAL'            # Swap overnight
        }
        
        for col_name, col_type in new_columns_trades.items():
            if col_name not in trades_columns:
                logger.info(f"Adding column '{col_name}' to trades table...")
                cursor.execute(f"ALTER TABLE trades ADD COLUMN {col_name} {col_type}")
                logger.info(f"  ✅ Added {col_name}")
        
        conn.commit()
        logger.info("\n✅ Migration completed successfully!")
        
        # Show updated schema
        cursor.execute("PRAGMA table_info(signals)")
        signals_schema = cursor.fetchall()
        logger.info(f"\n📋 Signals table schema ({len(signals_schema)} columns):")
        for col in signals_schema:
            logger.info(f"  - {col[1]} ({col[2]})")
        
        cursor.execute("PRAGMA table_info(trades)")
        trades_schema = cursor.fetchall()
        logger.info(f"\n📋 Trades table schema ({len(trades_schema)} columns):")
        for col in trades_schema:
            logger.info(f"  - {col[1]} ({col[2]})")
        
        return True
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    logger.info("🔄 Starting database migration...")
    success = migrate_database()
    
    if success:
        logger.info("\n✅ Database migration completed!")
        logger.info("Next steps:")
        logger.info("  1. Update Signal model to include new fields")
        logger.info("  2. Update OrderExecutor to save connector/account info")
        logger.info("  3. Update ClosingMonitor to track platform/account")
    else:
        logger.error("\n❌ Migration failed!")
