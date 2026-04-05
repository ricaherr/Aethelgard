"""
strategies_db.py — Strategy Metadata and Affinity Score Management
====================================================================

RESPONSIBILITY:
- CRUD operations for sys_strategies (global strategy registry)
- CRUD operations for usr_strategy_logs (per-user strategy learning)
- SINGLE SOURCE OF TRUTH: All affinity scores stored in DB (not JSON files)
- Delegate all connections to DatabaseManager (via BaseRepository)

TRACE_ID: FIX-STRATEGIES-DB-MANAGER-2026-04-01
"""

import json
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class StrategiesMixin(BaseRepository):
    """Mixin for strategy metadata and affinity score database operations."""

    def create_strategy(
        self,
        class_id: str,
        mnemonic: str,
        version: str = "1.0",
        affinity_scores: Optional[Dict[str, float]] = None,
        market_whitelist: Optional[List[str]] = None,
        description: Optional[str] = None,
        strategy_type: str = "PYTHON_CLASS",
        logic: Optional[Dict[str, Any]] = None,
        readiness: str = "UNKNOWN",
        readiness_notes: Optional[str] = None,
        class_file: Optional[str] = None,
        class_name: Optional[str] = None,
        schema_file: Optional[str] = None,
    ) -> bool:
        """Create a new strategy record in the database."""
        affinity_json = json.dumps(affinity_scores or {})
        whitelist_json = json.dumps(market_whitelist or [])
        logic_json = json.dumps(logic) if logic is not None else None

        try:
            self.execute_update(
                """
                INSERT INTO sys_strategies (
                    class_id, mnemonic, version, affinity_scores,
                    market_whitelist, description, type, logic,
                    readiness, readiness_notes, class_file, class_name, schema_file
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    class_id,
                    mnemonic,
                    version,
                    affinity_json,
                    whitelist_json,
                    description,
                    strategy_type,
                    logic_json,
                    readiness,
                    readiness_notes,
                    class_file,
                    class_name,
                    schema_file,
                ),
            )
            logger.info(f"[STRATEGIES] Created: {class_id} ({mnemonic})")
            return True
        except Exception as e:
            logger.error(f"[STRATEGIES] Error creating {class_id}: {e}")
            raise

    def get_strategy(self, class_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve strategy metadata by class_id."""
        try:
            results = self.execute_query(
                "SELECT * FROM sys_strategies WHERE class_id = ?",
                (class_id,)
            )
            if not results:
                return None

            result = results[0]
            # Parse JSON fields
            result["affinity_scores"] = json.loads(result.get("affinity_scores", "{}"))
            result["market_whitelist"] = json.loads(result.get("market_whitelist", "[]"))
            raw_logic = result.get("logic")
            if raw_logic and isinstance(raw_logic, str):
                try:
                    result["logic"] = json.loads(raw_logic)
                except (json.JSONDecodeError, ValueError):
                    result["logic"] = None
            return result
        except Exception as e:
            logger.error(f"[STRATEGIES] Error reading {class_id}: {e}")
            return None

    def get_all_sys_strategies(self) -> List[Dict[str, Any]]:
        """Retrieve all sys_strategies with parsed JSON fields."""
        try:
            results = self.execute_query(
                "SELECT * FROM sys_strategies ORDER BY created_at DESC"
            )
            for result in results:
                result["affinity_scores"] = json.loads(result.get("affinity_scores", "{}"))
                result["market_whitelist"] = json.loads(result.get("market_whitelist", "[]"))
                raw_logic = result.get("logic")
                if raw_logic and isinstance(raw_logic, str):
                    try:
                        result["logic"] = json.loads(raw_logic)
                    except (json.JSONDecodeError, ValueError):
                        result["logic"] = None
            return results
        except Exception as e:
            logger.error(f"[STRATEGIES] Error reading all strategies: {e}")
            return []

    def update_strategy_affinity_scores(
        self,
        class_id: str,
        affinity_scores: Dict[str, float],
    ) -> bool:
        """Update affinity_scores for a strategy."""
        affinity_json = json.dumps(affinity_scores)
        try:
            self.execute_update(
                """
                UPDATE sys_strategies
                SET affinity_scores = ?, updated_at = CURRENT_TIMESTAMP
                WHERE class_id = ?
                """,
                (affinity_json, class_id),
            )
            logger.info(f"[STRATEGIES] Affinity updated for {class_id}")
            return True
        except Exception as e:
            logger.error(f"[STRATEGIES] Error updating affinity for {class_id}: {e}")
            return False

    def get_strategy_by_mnemonic(self, mnemonic: str) -> Optional[Dict[str, Any]]:
        """Get strategy by mnemonic (human-readable name)."""
        results = self.execute_query(
            "SELECT * FROM sys_strategies WHERE mnemonic = ?",
            (mnemonic,)
        )
        if results:
            result = results[0]
            result["affinity_scores"] = json.loads(result.get("affinity_scores", "{}"))
            result["market_whitelist"] = json.loads(result.get("market_whitelist", "[]"))
            return result
        return None

    def delete_strategy(self, class_id: str) -> bool:
        """Delete strategy (hard delete allowed for system cleanup)."""
        try:
            self.execute_update(
                "DELETE FROM sys_strategies WHERE class_id = ?",
                (class_id,)
            )
            logger.info(f"[STRATEGIES] Deleted: {class_id}")
            return True
        except Exception as e:
            logger.error(f"[STRATEGIES] Error deleting {class_id}: {e}")
            return False

    # ──────────────────────────────────────────────────────────────────────────────
    # Strategy Learning Logs (usr_strategy_logs)
    # ──────────────────────────────────────────────────────────────────────────────

    def log_strategy_performance(
        self,
        strategy_id: str,
        asset: str,
        pnl: float,
        usr_trades_count: int,
        win_rate: float,
        profit_factor: float,
        trace_id: Optional[str] = None,
    ) -> bool:
        """Log strategy performance metrics for learning."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            self.execute_update(
                """
                INSERT INTO usr_strategy_logs
                (strategy_id, asset, pnl, usr_trades_count, win_rate, profit_factor, timestamp, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (strategy_id, asset, pnl, usr_trades_count, win_rate, profit_factor, now, trace_id),
            )
            return True
        except Exception as e:
            logger.error(f"[STRATEGIES] Error logging performance for {strategy_id}/{asset}: {e}")
            return False

    def get_strategy_performance_logs(
        self,
        strategy_id: str,
        asset: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Get strategy performance logs (optionally filtered by asset)."""
        if asset:
            return self.execute_query(
                """
                SELECT * FROM usr_strategy_logs
                WHERE strategy_id = ? AND asset = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (strategy_id, asset, limit),
            )
        else:
            return self.execute_query(
                """
                SELECT * FROM usr_strategy_logs
                WHERE strategy_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (strategy_id, limit),
            )

    def aggregate_strategy_performance(
        self,
        strategy_id: str,
        asset: str,
        window_size: int = 50,
    ) -> Optional[Dict[str, Any]]:
        """Aggregate recent performance metrics for a strategy/asset pair."""
        logs = self.execute_query(
            """
            SELECT AVG(pnl) as avg_pnl, AVG(win_rate) as avg_win_rate,
                   AVG(profit_factor) as avg_profit_factor, COUNT(*) as count
            FROM usr_strategy_logs
            WHERE strategy_id = ? AND asset = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (strategy_id, asset, window_size),
        )
        return logs[0] if logs else None
