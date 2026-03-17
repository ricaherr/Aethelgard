import json
import logging
import sqlite3
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Optional, Dict, List, Any, Tuple

from .base_repo import BaseRepository
from utils.time_utils import to_utc, to_utc_datetime

logger = logging.getLogger(__name__)

class ExecutionMixin(BaseRepository):
    """
    Mixin para operaciones de base de datos relacionadas con la ejecución de alta fidelidad.
    Implementa el Shadow Reporting y monitoreo de slippage.
    """

    def log_execution_shadow(
        self,
        signal_id: str,
        symbol: str,
        theoretical_price: Decimal,
        real_price: Decimal,
        slippage_pips: Decimal,
        latency_ms: float,
        status: str,
        user_id: str,
        trace_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Registra un 'Shadow Log' para comparar el precio teórico vs real.
        Cumple con la norma de fidelidad F-001 del Manifiesto.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Convertimos Decimal a float o str para SQLite
            # Usamos float para precios para permitir comparaciones, 
            # pero Decimal en la lógica para evitar errores IEEE 754.
            
            cursor.execute("""
                INSERT INTO usr_execution_logs (
                    signal_id, symbol, theoretical_price, real_price, 
                    slippage_pips, latency_ms, status, user_id, 
                    trace_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, 
                symbol, 
                float(theoretical_price), 
                float(real_price), 
                float(slippage_pips), 
                latency_ms, 
                status, 
                user_id, 
                trace_id, 
                json.dumps(metadata) if metadata else None
            ))
            
            conn.commit()
            logger.info(
                f"[SHADOW-LOG] Registrada ejecución para {symbol}. "
                f"Slippage: {slippage_pips} pips. Trace: {trace_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Error al registrar Shadow Log: {e}")
            return False
        finally:
            self._close_conn(conn)

    def get_execution_shadow_logs(self, limit: int = 100, user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera los logs de ejecución recientes."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM usr_execution_logs"
            params = []
            
            if user_id:
                query += " WHERE user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log = dict(row)
                if log.get('metadata'):
                    try:
                        log['metadata'] = json.loads(log['metadata'])
                    except:
                        log['metadata'] = {}
                logs.append(log)
            return logs
        finally:
            self._close_conn(conn)

    def get_execution_shadow_logs_by_symbol_and_window(
        self,
        symbol: str,
        window_minutes: int = 60,
        user_id: Optional[str] = None,
        status_filter: str = "SUCCESS"
    ) -> List[Dict[str, Any]]:
        """
        Recupera logs de ejecución shadow para un símbolo dentro de una ventana de tiempo.
        Usado por CoherenceService para análisis de drift.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            window_minutes: Look-back window in minutes (default 60)
            user_id: Optional user ID for isolation
            status_filter: Filter by execution status (default "SUCCESS")
        
        Returns:
            List of execution logs with fields: signal_id, symbol, theoretical_price, 
            real_price, slippage_pips, latency_ms, status, timestamp
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Calculate time threshold using to_utc() for system-standard UTC normalization
            # SQLite stores timestamps as ISO 8601 strings in UTC via DEFAULT CURRENT_TIMESTAMP
            time_threshold = to_utc(datetime.now(timezone.utc) - timedelta(minutes=window_minutes))
            
            query = """
                SELECT
                    signal_id,
                    symbol,
                    theoretical_price,
                    real_price,
                    slippage_pips,
                    latency_ms,
                    status,
                    timestamp
                FROM usr_execution_logs
                WHERE symbol = ? 
                    AND status = ?
                    AND timestamp >= ?
            """
            params = [symbol, status_filter, time_threshold]
            
            if user_id:
                query += " AND user_id = ?"
                params.append(user_id)
            
            query += " ORDER BY timestamp ASC"
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = [dict(row) for row in rows]
            return logs
        finally:
            self._close_conn(conn)

    def get_slippage_p90(self, symbol: str, min_records: int = 50) -> Optional[Decimal]:
        """
        Return the 90th-percentile absolute slippage (pips) for a symbol.

        Reads from usr_execution_logs for auto-calibration of SlippageController.
        Returns None when fewer than min_records exist (insufficient history).
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT ABS(slippage_pips) FROM usr_execution_logs "
                "WHERE symbol = ? ORDER BY ABS(slippage_pips) ASC",
                (symbol,),
            )
            values = [row[0] for row in cursor.fetchall()]
            if len(values) < min_records:
                return None
            idx = min(int(len(values) * 0.9), len(values) - 1)
            return Decimal(str(values[idx]))
        except Exception as exc:
            logger.debug("[ExecutionMixin] get_slippage_p90 failed for %s: %s", symbol, exc)
            return None
        finally:
            self._close_conn(conn)

    # ── Cooldown Tracker (sys_cooldown_tracker) ───────────────────────────────

    def get_active_cooldown(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """
        Returns the active cooldown record for a signal_id if it has not expired.
        Returns None if no record exists or the cooldown has already expired.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT * FROM sys_cooldown_tracker
                WHERE signal_id = ?
                  AND cooldown_expires > datetime('now')
                """,
                (signal_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as exc:
            logger.error("[ExecutionMixin] get_active_cooldown error for %s: %s", signal_id, exc)
            return None
        finally:
            self._close_conn(conn)

    def register_cooldown(
        self,
        signal_id: str,
        failure_reason: str,
        retry_count: int,
        cooldown_expires: datetime,
    ) -> None:
        """
        Inserts or replaces a cooldown record for a signal.
        Called by CooldownManager after a signal execution failure.
        """
        def _write(conn: sqlite3.Connection) -> None:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO sys_cooldown_tracker
                    (signal_id, failure_reason, retry_count, cooldown_expires, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    signal_id,
                    failure_reason,
                    retry_count,
                    cooldown_expires.isoformat() if isinstance(cooldown_expires, datetime) else str(cooldown_expires),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            conn.commit()

        try:
            self._execute_serialized(_write)
            logger.debug(
                "[ExecutionMixin] Cooldown registered: signal=%s reason=%s expires=%s",
                signal_id, failure_reason, cooldown_expires,
            )
        except Exception as exc:
            logger.error("[ExecutionMixin] register_cooldown error for %s: %s", signal_id, exc)

    def clear_cooldown(self, signal_id: str) -> None:
        """
        Removes the cooldown record for a signal_id.
        Called when a signal is retried successfully or manually cleared.
        """
        def _delete(conn: sqlite3.Connection) -> None:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM sys_cooldown_tracker WHERE signal_id = ?",
                (signal_id,),
            )
            conn.commit()

        try:
            self._execute_serialized(_delete)
            logger.debug("[ExecutionMixin] Cooldown cleared for signal=%s", signal_id)
        except Exception as exc:
            logger.error("[ExecutionMixin] clear_cooldown error for %s: %s", signal_id, exc)

    def count_active_cooldowns(self) -> int:
        """
        Returns the number of signals currently under active cooldown (not yet expired).
        Used by SignalSelector to gate the pipeline when too many cooldowns accumulate.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM sys_cooldown_tracker WHERE cooldown_expires > datetime('now')"
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0
        except Exception as exc:
            logger.error("[ExecutionMixin] count_active_cooldowns error: %s", exc)
            return 0
        finally:
            self._close_conn(conn)

