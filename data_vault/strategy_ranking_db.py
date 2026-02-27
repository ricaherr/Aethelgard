import logging
import sqlite3
import uuid
from typing import Dict, List, Optional
from datetime import datetime, timezone
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class StrategyRankingMixin(BaseRepository):
    """Mixin for Strategy Ranking and Shadow Portfolio database operations."""

    def save_strategy_ranking(self, strategy_id: str, ranking_data: Dict) -> str:
        """
        Save or update strategy ranking data.
        Returns trace_id for auditing.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            trace_id = ranking_data.get('trace_id') or f"RANK-{uuid.uuid4().hex[:8].upper()}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO strategy_ranking (
                    strategy_id, profit_factor, win_rate, drawdown_max,
                    sharpe_ratio, consecutive_losses, execution_mode, trace_id,
                    last_update_utc, total_trades, completed_last_50
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                strategy_id,
                ranking_data.get('profit_factor', 0.0),
                ranking_data.get('win_rate', 0.0),
                ranking_data.get('drawdown_max', 0.0),
                ranking_data.get('sharpe_ratio', 0.0),
                ranking_data.get('consecutive_losses', 0),
                ranking_data.get('execution_mode', 'SHADOW'),
                trace_id,
                ranking_data.get('last_update_utc', datetime.now(timezone.utc)),
                ranking_data.get('total_trades', 0),
                ranking_data.get('completed_last_50', 0)
            ))
            conn.commit()
            logger.info(f"Strategy ranking saved: {strategy_id} | Trace_ID: {trace_id}")
            return trace_id
        except Exception as e:
            logger.error(f"Error saving strategy ranking: {e}")
            raise
        finally:
            self._close_conn(conn)

    def get_strategy_ranking(self, strategy_id: str) -> Optional[Dict]:
        """Get current ranking data for a strategy."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy_ranking WHERE strategy_id = ?
            """, (strategy_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            self._close_conn(conn)

    def get_all_strategy_rankings(self) -> List[Dict]:
        """Get all strategy rankings, sorted by execution mode and profit factor."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy_ranking 
                ORDER BY 
                    CASE execution_mode 
                        WHEN 'LIVE' THEN 1
                        WHEN 'SHADOW' THEN 2
                        WHEN 'QUARANTINE' THEN 3
                        ELSE 4
                    END,
                    profit_factor DESC
            """)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def update_strategy_execution_mode(self, strategy_id: str, new_mode: str, trace_id: Optional[str] = None) -> str:
        """
        Update strategy execution mode (SHADOW, LIVE, QUARANTINE).
        Generates trace_id if not provided.
        Returns trace_id for audit trail.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if trace_id is None:
                trace_id = f"RANK-{uuid.uuid4().hex[:8].upper()}"
            
            cursor.execute("""
                UPDATE strategy_ranking 
                SET execution_mode = ?, trace_id = ?, last_update_utc = ?
                WHERE strategy_id = ?
            """, (new_mode, trace_id, datetime.now(timezone.utc), strategy_id))
            
            conn.commit()
            logger.critical(
                f"[TRACE_ID: {trace_id}] Strategy {strategy_id} execution mode changed to {new_mode}"
            )
            return trace_id
        except Exception as e:
            logger.error(f"Error updating execution mode: {e}")
            raise
        finally:
            self._close_conn(conn)

    def get_strategies_by_mode(self, mode: str) -> List[Dict]:
        """Get all strategies with a specific execution mode."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy_ranking 
                WHERE execution_mode = ?
                ORDER BY profit_factor DESC
            """, (mode,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def log_strategy_state_change(self, strategy_id: str, old_mode: str, new_mode: str,
                                 trace_id: str, reason: str, metrics: Dict) -> None:
        """
        Log strategy state changes for audit trail.
        Stores in system_state JSON for historical tracking.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'strategy_id': strategy_id,
                'old_mode': old_mode,
                'new_mode': new_mode,
                'trace_id': trace_id,
                'reason': reason,
                'metrics': metrics
            }
            
            # Save to system_state for persistence
            cursor.execute("""
                INSERT INTO edge_learning (
                    timestamp, detection, action_taken, learning, details
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                datetime.now(timezone.utc).isoformat(),
                f"strategy_mode_change",
                f"{old_mode} -> {new_mode}",
                reason,
                str(log_entry)
            ))
            conn.commit()
            logger.info(f"State change logged: {strategy_id} ({old_mode} -> {new_mode}) | Trace_ID: {trace_id}")
        except Exception as e:
            logger.error(f"Error logging state change: {e}")
        finally:
            self._close_conn(conn)

    def get_strategy_ranking_history(self, strategy_id: str, limit: int = 50) -> List[Dict]:
        """Get historical state changes for a strategy from edge_learning table."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, detection, action_taken, learning, details
                FROM edge_learning
                WHERE detection = 'strategy_mode_change' AND details LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f'%{strategy_id}%', limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)
    def get_regime_weights(self, regime: str, tenant_id: str = "default") -> Dict[str, str]:
        """
        Get metric weights for a specific regime from regime_configs table.
        
        Args:
            regime: Market regime (TREND, RANGE, VOLATILE)
            tenant_id: Tenant identifier for isolation
            
        Returns:
            Dictionary mapping metric_name -> weight (as string for Decimal conversion)
        """
        conn = self._get_conn()
        try:
            # Note: regime_configs currently might be global or tenant-specific.
            # If following the isolation protocol, we filter by tenant_id.
            cursor = conn.cursor()
            cursor.execute("""
                SELECT metric_name, weight FROM regime_configs 
                WHERE regime = ? AND (tenant_id = ? OR tenant_id IS NULL)
                ORDER BY metric_name
            """, (regime, tenant_id))
            rows = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            self._close_conn(conn)

    def get_all_regime_configs(self, tenant_id: str = "default") -> Dict[str, Dict[str, str]]:
        """
        Get all regime configurations as nested dict.
        
        Returns:
            Dict[regime → Dict[metric_name → weight]]
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT regime, metric_name, weight FROM regime_configs
                WHERE (tenant_id = ? OR tenant_id IS NULL)
                ORDER BY regime, metric_name
            """)
            rows = cursor.fetchall()
            
            result = {}
            for regime, metric_name, weight in rows:
                if regime not in result:
                    result[regime] = {}
                result[regime][metric_name] = weight
            
            return result
        finally:
            self._close_conn(conn)

    def update_regime_weight(self, regime: str, metric_name: str, weight: str) -> None:
        """
        Update a specific metric weight for a regime.
        
        Args:
            regime: Market regime
            metric_name: Metric to update
            weight: New weight value (as string for Decimal)
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO regime_configs 
                (regime, metric_name, weight, updated_at)
                VALUES (?, ?, ?, ?)
            """, (regime, metric_name, weight, datetime.now(timezone.utc)))
            conn.commit()
            logger.info(f"Updated regime_config: {regime}/{metric_name} = {weight}")
        except Exception as e:
            logger.error(f"Error updating regime weight: {e}")
            raise
        finally:
            self._close_conn(conn)