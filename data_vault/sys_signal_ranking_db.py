import logging
import sqlite3
import uuid
from typing import Any, Dict, List, Optional, cast
from datetime import datetime, timezone
from .base_repo import BaseRepository

logger: logging.Logger = logging.getLogger(__name__)


class StrategyRankingMixin(BaseRepository):
    """Mixin for Strategy Ranking and Shadow Portfolio database operations."""

    def save_signal_ranking(self, strategy_id: str, ranking_data: Dict[str, Any]) -> str:
        """
        Save or update strategy ranking data.
        Returns trace_id for auditing.
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            trace_id = ranking_data.get('trace_id') or f"RANK-{uuid.uuid4().hex[:8].upper()}"
            
            cursor.execute("""
                INSERT OR REPLACE INTO sys_signal_ranking (
                    strategy_id, profit_factor, win_rate, drawdown_max,
                    sharpe_ratio, consecutive_losses, execution_mode, trace_id,
                    last_update_utc, total_usr_trades, completed_last_50
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
                ranking_data.get('total_usr_trades', 0),
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

    def get_signal_ranking(self, strategy_id: str) -> Optional[Dict[str, Any]]:
        """Get current ranking data for a strategy."""
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sys_signal_ranking WHERE strategy_id = ?
            """, (strategy_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)
            return None
        finally:
            self._close_conn(conn)

    def _get_mode_from_sys_strategies(self, strategy_id: str) -> str:
        """
        Consulta sys_strategies para obtener el mode configurado (SSOT).
        Retorna 'BACKTEST' si la estrategia no existe — safe default conservador
        que evita que estrategias no registradas lleguen a producción.
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            row = conn.execute(
                "SELECT mode FROM sys_strategies WHERE class_id = ?",
                (strategy_id,),
            ).fetchone()
            if row and row[0]:
                return cast(str, row[0])
            return 'BACKTEST'
        except Exception as e:
            logger.error(f"[LAZY-INIT] Error reading sys_strategies for {strategy_id}: {e}")
            return 'BACKTEST'
        finally:
            self._close_conn(conn)

    def ensure_signal_ranking_for_strategy(self, strategy_id: str) -> Dict[str, Any]:
        """
        Lazy initialization: Obtener o crear entrada en sys_signal_ranking para una estrategia.
        
        Si la estrategia YA existe en sys_signal_ranking, retornar registro existente.
        Si NO existe, crear automáticamente con valores por defecto (SHADOW mode, métricas en 0).
        
        IDEMPOTENTE: Safe to call multiple times. No duplica registros.
        
        Trace_ID: LAZY-INIT-SIGNAL-RANKING-S007
        
        Args:
            strategy_id: Identificador único de la estrategia (ej: 'BRK_OPEN_0001')
            
        Returns:
            Dict[str, Any] con los datos de sys_signal_ranking (existente o recién creado)
            
        Usado por: StrategyEngineFactory._get_execution_mode() cuando carga estrategias
        """
        # Intentar obtener registro existente
        existing = self.get_signal_ranking(strategy_id)
        if existing:
            logger.debug(f"[LAZY-INIT] {strategy_id}: Already exists in sys_signal_ranking")
            return existing
        
        # No existe → Determinar modo desde sys_strategies (SSOT)
        initial_mode: str = self._get_mode_from_sys_strategies(strategy_id)
        logger.warning(
            f"[LAZY-INIT] {strategy_id}: Creating automatic entry in sys_signal_ranking "
            f"(mode={initial_mode} from sys_strategies)"
        )

        self.save_signal_ranking(
            strategy_id=strategy_id,
            ranking_data={
                'execution_mode': initial_mode,
                'profit_factor': 0.0,
                'win_rate': 0.0,
                'drawdown_max': 0.0,
                'sharpe_ratio': 0.0,
                'consecutive_losses': 0,
                'total_usr_trades': 0,
                'completed_last_50': 0,
                'trace_id': f"LAZY-INIT-{strategy_id}"
            }
        )
        
        # Retornar registro recién creado
        return self.get_signal_ranking(strategy_id) or {}

    def get_all_signal_rankings(self) -> List[Dict[str, Any]]:
        """Get all strategy rankings, sorted by execution mode and profit factor."""
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sys_signal_ranking 
                ORDER BY 
                    CASE execution_mode 
                        WHEN 'LIVE' THEN 1
                        WHEN 'SHADOW' THEN 2
                        WHEN 'QUARANTINE' THEN 3
                        ELSE 4
                    END,
                    profit_factor DESC
            """)
            rows: List[Any] = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def update_strategy_execution_mode(self, strategy_id: str, new_mode: str, trace_id: Optional[str] = None) -> str:
        """
        Update strategy execution mode (SHADOW, LIVE, QUARANTINE).
        Generates trace_id if not provided.
        Returns trace_id for audit trail.
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            if trace_id is None:
                trace_id = f"RANK-{uuid.uuid4().hex[:8].upper()}"
            
            cursor.execute("""
                UPDATE sys_signal_ranking 
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

    def get_strategies_by_mode(self, mode: str) -> List[Dict[str, Any]]:
        """Get all strategies with a specific execution mode."""
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sys_signal_ranking 
                WHERE execution_mode = ?
                ORDER BY profit_factor DESC
            """, (mode,))
            rows: List[Any] = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def log_strategy_state_change(self, strategy_id: str, old_mode: str, new_mode: str,
                                 trace_id: str, reason: str, metrics: Dict[str, Any]) -> None:
        """
        Log strategy state changes for audit trail.
        Stores in sys_config JSON for historical tracking.
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            log_entry = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'strategy_id': strategy_id,
                'old_mode': old_mode,
                'new_mode': new_mode,
                'trace_id': trace_id,
                'reason': reason,
                'metrics': metrics
            }
            
            # Save to sys_config for persistence
            cursor.execute("""
                INSERT INTO usr_edge_learning (
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

    def get_signal_ranking_history(self, strategy_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Get historical state changes for a strategy from usr_edge_learning table."""
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                SELECT timestamp, detection, action_taken, learning, details
                FROM usr_edge_learning
                WHERE detection = 'strategy_mode_change' AND details LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f'%{strategy_id}%', limit))
            rows: List[Any] = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)
    def get_regime_weights(self, regime: str, user_id: str = "default") -> Dict[str, str]:
        """
        Get metric weights for a specific regime from sys_regime_configs table.
        
        Args:
            regime: Market regime (TREND, RANGE, VOLATILE)
            user_id: User identifier for isolation
            
        Returns:
            Dictionary mapping metric_name -> weight (as string for Decimal conversion)
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            # Note: sys_regime_configs currently might be global or user-specific.
            # If following the isolation protocol, we filter by user_id.
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                SELECT metric_name, weight FROM sys_regime_configs 
                WHERE regime = ? AND (user_id = ? OR user_id IS NULL)
                ORDER BY metric_name
            """, (regime, user_id))
            rows: List[Any] = cursor.fetchall()
            return {row[0]: row[1] for row in rows}
        finally:
            self._close_conn(conn)

    def get_all_sys_regime_configs(self, user_id: str = "default") -> Dict[str, Dict[str, str]]:
        """
        Get all regime configurations as nested dict.
        
        Returns:
            Dict[regime → Dict[metric_name → weight]]
        """
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                SELECT regime, metric_name, weight FROM sys_regime_configs
                WHERE (user_id = ? OR user_id IS NULL)
                ORDER BY regime, metric_name
            """, (user_id,))
            rows: List[Any] = cursor.fetchall()
            
            result: Dict[str, Dict[str, Any]] = {}
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
        conn: sqlite3.Connection = self._get_conn()
        try:
            cursor: sqlite3.Cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sys_regime_configs 
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
