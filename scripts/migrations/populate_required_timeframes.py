"""
Migration: Populate required_timeframes in sys_strategies
==========================================================

Sets the required_timeframes JSON list for each strategy based on official
documentation and strategy source code analysis.

Sources:
  BRK_OPEN_0001      → docs/03_ALPHA_ENGINE.md (multi-scale M15/H1/H4 validation)
  institutional_footprint → core_brain/strategies/universal/institutional_footprint.json
  SESS_EXT_0001      → core_brain/strategies/session_extension_0001.py (M5, M15, H1)
  STRUC_SHIFT_0001   → core_brain/strategies/struc_shift_0001.py (H1, H4)
  MOM_BIAS_0001      → H1 primary (no multi-TF docs; lowest safe default)
  LIQ_SWEEP_0001     → H1 primary (no multi-TF docs; lowest safe default)

Safe to re-run — only updates rows where required_timeframes is '[]' or NULL.
"""
import json
import logging
import sqlite3
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_PATH = Path(__file__).parent.parent.parent / "data_vault" / "global" / "aethelgard.db"

STRATEGY_TIMEFRAMES = {
    "BRK_OPEN_0001":         ["M15", "H1", "H4"],
    "institutional_footprint": ["M15", "H1"],
    "MOM_BIAS_0001":         ["H1"],
    "LIQ_SWEEP_0001":        ["H1"],
    "SESS_EXT_0001":         ["M5", "M15", "H1"],
    "STRUC_SHIFT_0001":      ["H1", "H4"],
}


def run_migration(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        logger.error("DB not found at %s — aborting migration.", db_path)
        return

    conn = sqlite3.connect(str(db_path))
    try:
        updated = 0
        cursor = conn.cursor()

        for strategy_id, timeframes in STRATEGY_TIMEFRAMES.items():
            cursor.execute(
                """
                UPDATE sys_strategies
                SET    required_timeframes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE  class_id = ?
                AND   (required_timeframes IS NULL
                       OR required_timeframes = '[]'
                       OR required_timeframes = '')
                """,
                (json.dumps(timeframes), strategy_id),
            )
            rows = cursor.rowcount
            if rows:
                logger.info("  ✓ %s → %s", strategy_id, timeframes)
            else:
                logger.info("  ⏭  %s — already set or not found", strategy_id)
            updated += rows

        conn.commit()
        logger.info("Migration complete — %d strategy(ies) updated.", updated)

    except Exception as exc:
        conn.rollback()
        logger.error("Migration failed, rolled back: %s", exc)
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    run_migration()
