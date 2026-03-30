"""
Migration: Fix orphan shadow instances and dead config key
==========================================================

One-shot migration that:
  1. Marks INCUBATING shadow instances as DEAD when their parent strategy
     is still in BACKTEST mode (orphan instances created prematurely).
  2. Resets last_backtest_at = NULL for all BACKTEST strategies so the
     next backtest cycle runs without cooldown interference.
  3. Removes the dead-code 'backtest_config' key from sys_config
     (was a naming duplicate of 'config_backtest' with cooldown_hours=1,
     never read by BacktestOrchestrator).

Safe to re-run — all operations are idempotent.
"""
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data_vault" / "global" / "aethelgard.db"


def run_migration(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        logger.error("DB not found at %s — aborting migration.", db_path)
        return

    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        # 1. Mark orphan INCUBATING instances as DEAD
        cursor.execute(
            """
            UPDATE sys_shadow_instances
            SET    status = 'DEAD', updated_at = CURRENT_TIMESTAMP
            WHERE  status = 'INCUBATING'
            AND    strategy_id IN (
                       SELECT class_id FROM sys_strategies WHERE mode = 'BACKTEST'
                   )
            """
        )
        orphans_fixed = cursor.rowcount
        logger.info("Step 1: %d orphan shadow instance(s) marked DEAD.", orphans_fixed)

        # 2. Reset last_backtest_at for all BACKTEST strategies
        cursor.execute(
            "UPDATE sys_strategies SET last_backtest_at = NULL WHERE mode = 'BACKTEST'"
        )
        cooldowns_reset = cursor.rowcount
        logger.info("Step 2: %d strategy cooldown(s) reset (last_backtest_at = NULL).", cooldowns_reset)

        # 3. Remove dead-code 'backtest_config' key from sys_config
        cursor.execute("DELETE FROM sys_config WHERE key = 'backtest_config'")
        removed_keys = cursor.rowcount
        logger.info("Step 3: %d dead-code sys_config key(s) removed ('backtest_config').", removed_keys)

        conn.commit()
        logger.info(
            "Migration complete — orphans_fixed=%d, cooldowns_reset=%d, keys_removed=%d",
            orphans_fixed, cooldowns_reset, removed_keys,
        )
    except Exception as exc:
        conn.rollback()
        logger.error("Migration failed, rolled back: %s", exc)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
