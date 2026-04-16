"""
data_vault/db_policy_tuner.py — Auto-Tuning de Política de Concurrencia SQLite
================================================================================

Responsabilidad única:
  - Analizar métricas de latencia de transacciones y eventos de lock.
  - Ajustar dinámicamente `busy_timeout` de la conexión activa cuando se
    detectan patrones de contención persistente.
  - Proveer fallback de modo solo-lectura cuando la recuperación es imposible.

Integrado por DatabaseManager; NO debe importarse directamente desde código
de negocio.

TRACE_ID: ETI-EDGE_Resilience_Improvements-2026-04-16
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
from collections import deque
from typing import Dict, Optional, Set

logger = logging.getLogger(__name__)


# ─── Umbrales de auto-tuning ──────────────────────────────────────────────────
P95_WARN_MS: float = 500.0        # p95 > 500ms → escalar busy_timeout
P95_CRITICAL_MS: float = 2000.0   # p95 > 2s  → escalar agresivamente

BUSY_TIMEOUT_MIN_MS: int = 30_000   # 30s mínimo
BUSY_TIMEOUT_MAX_MS: int = 300_000  # 5min máximo
BUSY_TIMEOUT_STEP_MS: int = 15_000  # incremento/decremento por paso

LOCK_RATE_WARN_PER_MIN: float = 5.0    # > 5 events/min → WARN
LOCK_RATE_CRITICAL_PER_MIN: float = 15.0  # > 15 events/min → escalar

LOCK_HISTORY_WINDOW_SECONDS: int = 300  # ventana de 5 min para calcular tasa


class DBPolicyTuner:
    """
    Analiza métricas en tiempo real y ajusta la política de concurrencia
    de las conexiones SQLite activas.

    Lifecycle:
      - Instanciado una vez por DatabaseManager (referencia directa).
      - record_lock_event()      → llamado desde SQLiteDriver._with_retry
      - evaluate_and_tune()      → llamado desde DatabaseManager.transaction()
                                   (throttled: max 1 evaluación cada 30s)
      - apply_read_only_mode()   → llamado desde DatabaseManager cuando
                                   is_degraded() es True.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()

        # Historial de eventos de lock: por db_path, lista de timestamps
        self._lock_events: Dict[str, deque[float]] = {}

        # Busy timeout actual aplicado (en ms), por db_path
        self._current_busy_timeout: Dict[str, int] = {}

        # Bases de datos en modo solo-lectura (escrituras bloqueadas)
        self._read_only_dbs: Set[str] = set()

        # Throttle: timestamp de la última evaluación por db_path
        self._last_tune_ts: Dict[str, float] = {}

        # Intervalo mínimo entre evaluaciones de auto-tuning
        self._tune_interval_seconds: float = 30.0

        # Historial de ajustes para observabilidad
        self._tune_history: deque[Dict[str, object]] = deque(maxlen=50)

    # ─── API pública ──────────────────────────────────────────────────────────

    def record_lock_event(self, db_path: str) -> None:
        """Registra un evento de lock/busy para una db_path."""
        now = time.monotonic()
        with self._lock:
            if db_path not in self._lock_events:
                self._lock_events[db_path] = deque()
            self._lock_events[db_path].append(now)
            self._purge_old_events(db_path, now)

    def get_lock_event_rate(self, db_path: str, window_seconds: int = LOCK_HISTORY_WINDOW_SECONDS) -> float:
        """
        Calcula la tasa de eventos de lock (eventos/minuto) en la ventana.

        Returns:
            Eventos por minuto en la ventana indicada.
        """
        now = time.monotonic()
        with self._lock:
            events = self._lock_events.get(db_path, deque())
            recent = [t for t in events if (now - t) <= window_seconds]
            if window_seconds == 0:
                return 0.0
            return (len(recent) / window_seconds) * 60.0

    def evaluate_and_tune(
        self, db_path: str, p95_ms: float, connection_pool: Dict[str, sqlite3.Connection]
    ) -> Optional[int]:
        """
        Evalúa las métricas actuales y ajusta busy_timeout si es necesario.

        Throttled: solo evalúa cada `_tune_interval_seconds`.

        Args:
            db_path:         Ruta a la base de datos evaluada.
            p95_ms:          Latencia p95 de transacciones recientes (ms).
            connection_pool: Pool activo de DatabaseManager (para aplicar PRAGMA).

        Returns:
            Nuevo busy_timeout_ms si fue ajustado, None si no hubo cambio.
        """
        now = time.monotonic()
        with self._lock:
            last = self._last_tune_ts.get(db_path, 0.0)
            if (now - last) < self._tune_interval_seconds:
                return None
            self._last_tune_ts[db_path] = now

        current_timeout = self._current_busy_timeout.get(db_path, 120_000)
        new_timeout = self._compute_new_timeout(db_path, p95_ms, current_timeout)

        if new_timeout == current_timeout:
            return None

        with self._lock:
            self._current_busy_timeout[db_path] = new_timeout

        self._apply_busy_timeout_to_connection(db_path, new_timeout, connection_pool)
        self._record_tune_event(db_path, current_timeout, new_timeout, p95_ms)
        return new_timeout

    def apply_read_only_mode(
        self, db_path: str, connection_pool: Dict[str, sqlite3.Connection]
    ) -> bool:
        """
        Activa el modo solo-lectura en la conexión activa.

        Aplica PRAGMA query_only=1 y registra el db_path como read-only.

        Args:
            db_path:         Ruta de la BD degradada.
            connection_pool: Pool activo de DatabaseManager.

        Returns:
            True si se aplicó correctamente, False si falló.
        """
        with self._lock:
            if db_path in self._read_only_dbs:
                return True  # ya está en modo read-only

        conn = connection_pool.get(db_path)
        if conn is None:
            logger.warning("[DBPolicyTuner] apply_read_only_mode: no hay conexión activa para %s", db_path)
            with self._lock:
                self._read_only_dbs.add(db_path)
            return False

        try:
            conn.execute("PRAGMA query_only=1").fetchall()
            with self._lock:
                self._read_only_dbs.add(db_path)
            logger.warning(
                "[DBPolicyTuner] Modo solo-lectura ACTIVADO para %s tras recovery fallido", db_path
            )
            return True
        except Exception as exc:
            logger.error("[DBPolicyTuner] No se pudo aplicar PRAGMA query_only para %s: %s", db_path, exc)
            with self._lock:
                self._read_only_dbs.add(db_path)
            return False

    def clear_read_only_mode(
        self, db_path: str, connection_pool: Dict[str, sqlite3.Connection]
    ) -> bool:
        """
        Desactiva el modo solo-lectura (tras reparación operacional).

        Args:
            db_path:         Ruta de la BD a restaurar.
            connection_pool: Pool activo de DatabaseManager.

        Returns:
            True si se restauró correctamente.
        """
        with self._lock:
            self._read_only_dbs.discard(db_path)

        conn = connection_pool.get(db_path)
        if conn is None:
            return True

        try:
            conn.execute("PRAGMA query_only=0").fetchall()
            logger.info("[DBPolicyTuner] Modo solo-lectura DESACTIVADO para %s", db_path)
            return True
        except Exception as exc:
            logger.error("[DBPolicyTuner] No se pudo desactivar PRAGMA query_only para %s: %s", db_path, exc)
            return False

    def is_read_only(self, db_path: str) -> bool:
        """Retorna True si db_path está en modo solo-lectura."""
        return db_path in self._read_only_dbs

    def get_tune_status(self) -> Dict[str, object]:
        """
        Retorna snapshot del estado del auto-tuner para observabilidad.

        Shape:
            {
                "current_busy_timeout": {db_path: ms},
                "lock_rates_per_min":   {db_path: float},
                "read_only_dbs":        [db_path, ...],
                "recent_tune_events":   [{...}, ...],
            }
        """
        with self._lock:
            timeout_snapshot = dict(self._current_busy_timeout)
            read_only_list = list(self._read_only_dbs)
            history = list(self._tune_history)

        rates: Dict[str, float] = {}
        for db_path in list(timeout_snapshot.keys()) + list(self._lock_events.keys()):
            rates[db_path] = self.get_lock_event_rate(db_path)

        return {
            "current_busy_timeout": timeout_snapshot,
            "lock_rates_per_min": rates,
            "read_only_dbs": read_only_list,
            "recent_tune_events": history,
        }

    # ─── Métodos privados ──────────────────────────────────────────────────────

    def _compute_new_timeout(self, db_path: str, p95_ms: float, current_ms: int) -> int:
        """Calcula el nuevo busy_timeout_ms según latencia y tasa de locks."""
        lock_rate = self.get_lock_event_rate(db_path)

        should_escalate = (
            p95_ms >= P95_CRITICAL_MS
            or lock_rate >= LOCK_RATE_CRITICAL_PER_MIN
        )
        should_warn = (
            p95_ms >= P95_WARN_MS
            or lock_rate >= LOCK_RATE_WARN_PER_MIN
        )
        should_reduce = (
            p95_ms < P95_WARN_MS / 2
            and lock_rate < LOCK_RATE_WARN_PER_MIN / 2
            and current_ms > 120_000
        )

        if should_escalate:
            return min(BUSY_TIMEOUT_MAX_MS, current_ms + BUSY_TIMEOUT_STEP_MS * 2)
        if should_warn:
            return min(BUSY_TIMEOUT_MAX_MS, current_ms + BUSY_TIMEOUT_STEP_MS)
        if should_reduce:
            return max(BUSY_TIMEOUT_MIN_MS, current_ms - BUSY_TIMEOUT_STEP_MS)
        return current_ms

    def _apply_busy_timeout_to_connection(
        self, db_path: str, timeout_ms: int, connection_pool: Dict[str, sqlite3.Connection]
    ) -> None:
        """Aplica PRAGMA busy_timeout a la conexión activa."""
        conn = connection_pool.get(db_path)
        if conn is None:
            return
        try:
            conn.execute(f"PRAGMA busy_timeout={timeout_ms}").fetchall()
            logger.info(
                "[DBPolicyTuner] busy_timeout ajustado a %dms para %s", timeout_ms, db_path
            )
        except Exception as exc:
            logger.warning("[DBPolicyTuner] No se pudo aplicar busy_timeout a %s: %s", db_path, exc)

    def _purge_old_events(self, db_path: str, now: float) -> None:
        """Elimina eventos de lock fuera de la ventana de retención."""
        cutoff = now - LOCK_HISTORY_WINDOW_SECONDS
        events = self._lock_events.get(db_path)
        if events is None:
            return
        while events and events[0] < cutoff:
            events.popleft()

    def _record_tune_event(
        self, db_path: str, old_ms: int, new_ms: int, p95_ms: float
    ) -> None:
        """Guarda un registro del ajuste para auditoría y observabilidad."""
        self._tune_history.append({
            "db_path": db_path,
            "old_busy_timeout_ms": old_ms,
            "new_busy_timeout_ms": new_ms,
            "p95_ms": round(p95_ms, 2),
            "lock_rate_per_min": round(self.get_lock_event_rate(db_path), 2),
            "timestamp": time.time(),
        })
        direction = "↑ ESCALADO" if new_ms > old_ms else "↓ REDUCIDO"
        logger.info(
            "[DBPolicyTuner] busy_timeout %s: %dms → %dms (p95=%.1fms) [%s]",
            direction,
            old_ms,
            new_ms,
            p95_ms,
            db_path,
        )
