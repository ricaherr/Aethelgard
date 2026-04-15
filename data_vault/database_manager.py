"""
DatabaseManager — Centralized Connection Pool & Configuration (SSOT)
=====================================================================

SINGLE RESPONSIBILITY:
- Manage ALL SQLite connections across Aethelgard
- Enforce PRAGMA configuration globally (SINGLE SOURCE OF TRUTH)
- Health checks, reconnection, graceful shutdown
- Thread-safe pooling (one connection per db_path)

CRITICAL RULES:
- NO direct sqlite3.connect() calls outside this module
- NO PRAGMA statements elsewhere (all here)
- NO connection.close() in business code (managed here)
- SINGLE instance (Singleton pattern)

TRACE_ID: FIX-DATABASE-MANAGER-SINGLETON-2026-04-01
"""

import threading
import sqlite3
import logging
import time
from collections import deque
from typing import Optional, Dict, Any, Generator
from contextlib import contextmanager
from datetime import datetime, timezone

# Sentinel value for "no operation tag" — avoids None ambiguity in metrics dicts.
_NO_TAG = "__untagged__"

logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Singleton database connection manager.
    Handles pooling, health checks, and PRAGMA configuration.
    """

    _instance: Optional["DatabaseManager"] = None
    _init_lock: threading.Lock = threading.Lock()
    _initialized: bool = False

    def __new__(cls) -> "DatabaseManager":
        """Enforce singleton pattern."""
        if cls._instance is None:
            with cls._init_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        """Initialize singleton (only once)."""
        if self._initialized:
            return

        self._connection_pool: Dict[str, sqlite3.Connection] = {}
        self._pool_lock: threading.Lock = threading.Lock()
        self._config_lock: threading.Lock = threading.Lock()
        self._tx_lock_pool: Dict[str, threading.RLock] = {}
        self._health_timestamps: Dict[str, float] = {}
        self._tx_metrics_lock: threading.Lock = threading.Lock()
        self._tx_latency_samples: Dict[str, deque[float]] = {}
        self._tx_last_latency_ms: Dict[str, float] = {}
        self._tx_metrics_window_size: int = 120
        # Per-operation-tag latency samples — key: operation_tag
        self._op_latency_samples: Dict[str, deque[float]] = {}
        self._op_last_latency_ms: Dict[str, float] = {}

        # PRAGMA Configuration (SSOT)
        self._pragma_config: Dict[str, Any] = {
            "journal_mode": "WAL",
            "busy_timeout": 120000,  # 120 seconds (optimal with single connection)
            "synchronous": "NORMAL",  # Reduce unnecessary fsync
            "wal_autocheckpoint": 50000,  # 200MB before checkpoint (reduce frequent blocking)
            "temp_store": "MEMORY",  # Temp files in RAM
            # NORMAL avoids persistent exclusive DB locks across multiple processes
            # (launcher + API subprocess), while WAL still guarantees write serialization.
            "locking_mode": "NORMAL",
            "cache_size": -64000,  # 64MB cache
            "query_only": False,  # Allow writes by default
        }

        self._initialized = True
        logger.info("[DatabaseManager] Singleton initialized with SSOT PRAGMA configuration")

    def get_connection(self, db_path: str) -> sqlite3.Connection:
        """
        Get or create a connection to db_path.
        Thread-safe; uses double-check pattern.

        Returns:
            sqlite3.Connection with row_factory enabled
        """
        # Fast path: connection exists and is healthy
        if db_path in self._connection_pool:
            conn = self._connection_pool[db_path]
            if self._is_connection_healthy(conn):
                return conn
            else:
                logger.warning(f"[DatabaseManager] Stale connection detected for {db_path}, recreating...")
                with self._pool_lock:
                    del self._connection_pool[db_path]

        # Slow path: create new connection
        with self._pool_lock:
            # Double-check: another thread might have created it
            if db_path in self._connection_pool and self._is_connection_healthy(
                self._connection_pool[db_path]
            ):
                return self._connection_pool[db_path]

            # Create and configure connection with bounded retries to absorb
            # transient startup races from sibling processes touching the same DB.
            conn: sqlite3.Connection | None = None
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    conn = sqlite3.connect(db_path, check_same_thread=False, timeout=120)
                    conn.row_factory = sqlite3.Row

                    # Apply SSOT PRAGMA configuration
                    # NOTE: .fetchall() is required on Python 3.14+ — Connection.execute()
                    # uses a shared implicit cursor; unconsumed rows from PRAGMA calls
                    # (e.g. journal_mode, locking_mode) leave it dirty and cause
                    # "another row available" on the next conn.execute() call.
                    for pragma_key, pragma_value in self._pragma_config.items():
                        if pragma_key == "query_only":
                            # query_only is special (boolean)
                            conn.execute(f"PRAGMA query_only={1 if pragma_value else 0}").fetchall()
                        else:
                            conn.execute(f"PRAGMA {pragma_key}={pragma_value}").fetchall()
                    break
                except sqlite3.OperationalError as e:
                    last_error = e
                    if conn is not None:
                        try:
                            conn.close()
                        except Exception:
                            logger.debug("[DatabaseManager] Failed to close transient connection", exc_info=True)
                    if attempt >= 3:
                        raise
                    logger.warning(
                        "[DatabaseManager] Connection init retry %s/3 for %s due to OperationalError: %s",
                        attempt,
                        db_path,
                        e,
                    )
                    time.sleep(0.2 * attempt)

            if conn is None:
                if last_error is not None:
                    raise last_error
                raise sqlite3.OperationalError("Failed to initialize SQLite connection")

            self._connection_pool[db_path] = conn
            self._health_timestamps[db_path] = time.time()
            logger.info(
                f"[DatabaseManager] Created persistent connection for {db_path} with SSOT config"
            )
            return conn

    def _is_connection_healthy(self, conn: sqlite3.Connection) -> bool:
        """
        Check if connection is still operational.
        Performs lightweight health check (SELECT 1).
        """
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            return True
        except (sqlite3.ProgrammingError, sqlite3.OperationalError) as e:
            logger.debug(f"[DatabaseManager] Connection health check failed: {e}")
            return False
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def create_dedicated_read_connection(self, db_path: str) -> sqlite3.Connection:
        """
        Create an isolated read-only connection for maintenance operations.

        This connection is NOT part of the shared pool and must be closed
        explicitly by the caller. It avoids contention with the operational
        shared handle used by application reads/writes.
        """
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            check_same_thread=False,
            timeout=120,
        )
        conn.row_factory = sqlite3.Row
        return conn

    @contextmanager
    def transaction(
        self, db_path: str, operation_tag: str = _NO_TAG
    ) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for transactions with optional origin tagging.

        Args:
            db_path:       Target database path.
            operation_tag: Logical operation name for latency tracing
                           (e.g. "update_sys_config", "log_audit_event").
                           Defaults to "__untagged__" when not supplied.

        Usage:
            with db_manager.transaction(db_path, operation_tag="persist_scan_kpi") as conn:
                conn.cursor().execute("INSERT ...")
                # Auto-commits on exit, latency recorded under the tag.
        """
        conn = self.get_connection(db_path)
        with self._pool_lock:
            tx_lock = self._tx_lock_pool.setdefault(db_path, threading.RLock())

        with tx_lock:
            started = time.perf_counter()
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"[DatabaseManager] Transaction rollback due to: {e}")
                raise
            finally:
                elapsed_ms = (time.perf_counter() - started) * 1000.0
                self._record_transaction_latency(db_path, elapsed_ms, operation_tag)

    def execute_query(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """
        Execute a SELECT query (read-only).
        Returns list of dicts.

        Args:
            db_path: Database path
            sql: SQL query
            params: Query parameters

        Returns:
            List of dictionaries (via row_factory)
        """
        conn = self.get_connection(db_path)
        with self._pool_lock:
            tx_lock = self._tx_lock_pool.setdefault(db_path, threading.RLock())

        cursor: sqlite3.Cursor | None = None
        with tx_lock:
            try:
                cursor = conn.cursor()
                cursor.execute(sql, params)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
            except Exception as e:
                logger.error(f"[DatabaseManager] Query execution failed: {e}")
                raise
            finally:
                if cursor is not None:
                    try:
                        cursor.close()
                    except Exception:
                        logger.debug("[DatabaseManager] Failed to close query cursor", exc_info=True)

    def execute_update(
        self, db_path: str, sql: str, params: tuple[Any, ...] = (), operation_tag: str = _NO_TAG
    ) -> int:
        """
        Execute INSERT/UPDATE/DELETE (write operation).
        Auto-commits.

        Args:
            db_path:       Database path
            sql:           SQL statement
            params:        Parameters
            operation_tag: Logical operation name for latency tracing.

        Returns:
            rows_affected (for UPDATE/DELETE) or last_insert_rowid() (for INSERT)
        """
        with self.transaction(db_path, operation_tag=operation_tag) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, params)
            # Return affected rows for UPDATE/DELETE, or last insert id
            if "INSERT" in sql.upper():
                return cursor.lastrowid if cursor.lastrowid is not None else 0
            else:
                return cursor.rowcount if cursor.rowcount is not None else 0

    def execute_many(
        self,
        db_path: str,
        sql: str,
        param_list: list[tuple[Any, ...]],
        operation_tag: str = _NO_TAG,
    ) -> int:
        """
        Execute batch INSERT/UPDATE/DELETE statements in a single transaction.

        Args:
            db_path:       Database path
            sql:           SQL statement
            param_list:    List of parameter tuples
            operation_tag: Logical operation name for latency tracing.

        Returns:
            Number of rows affected (best effort from sqlite cursor.rowcount)
        """
        if not param_list:
            return 0

        with self.transaction(db_path, operation_tag=operation_tag) as conn:
            cursor = conn.cursor()
            cursor.executemany(sql, param_list)
            return cursor.rowcount if cursor.rowcount is not None else 0

    def close_connection(self, db_path: str) -> None:
        """
        Explicitly close a connection (rarely needed).
        Called during graceful shutdown or error recovery.

        Args:
            db_path: Database path
        """
        with self._pool_lock:
            if db_path in self._connection_pool:
                try:
                    # Checkpoint WAL before closing (graceful)
                    conn = self._connection_pool[db_path]
                    conn.execute("PRAGMA wal_checkpoint(RESTART)").fetchall()
                    conn.close()
                except Exception as e:
                    logger.error(f"[DatabaseManager] Error closing {db_path}: {e}")
                finally:
                    del self._connection_pool[db_path]
                    if db_path in self._health_timestamps:
                        del self._health_timestamps[db_path]
                    if db_path in self._tx_lock_pool:
                        del self._tx_lock_pool[db_path]
                    logger.info(f"[DatabaseManager] Closed connection for {db_path}")

    def shutdown(self) -> None:
        """
        Graceful shutdown: close all connections.
        Called on application exit.
        """
        logger.info("[DatabaseManager] Initiating graceful shutdown...")
        with self._pool_lock:
            for db_path in list(self._connection_pool.keys()):
                try:
                    conn = self._connection_pool[db_path]
                    # Final checkpoint before closing
                    conn.execute("PRAGMA wal_checkpoint(RESTART)").fetchall()
                    conn.close()
                    logger.info(f"[DatabaseManager] Closed: {db_path}")
                except Exception as e:
                    logger.error(f"[DatabaseManager] Error shutting down {db_path}: {e}")
            self._connection_pool.clear()
            self._health_timestamps.clear()
            self._tx_lock_pool.clear()
        logger.info("[DatabaseManager] Graceful shutdown complete")

    def health_check(self) -> Dict[str, Any]:
        """
        Check health of all connections.
        Returns status dict for monitoring.

        Returns:
            {
                "status": "HEALTHY" | "DEGRADED" | "CRITICAL",
                "connections": {db_path: {"healthy": bool, "age_seconds": int}},
                "pool_size": int,
                "timestamp": ISO8601
            }
        """
        status_details: Dict[str, Any] = {}
        for db_path, conn in self._connection_pool.items():
            is_healthy = self._is_connection_healthy(conn)
            age = time.time() - self._health_timestamps.get(db_path, time.time())
            status_details[db_path] = {"healthy": is_healthy, "age_seconds": int(age)}

        # Determine overall status
        if not status_details:
            overall_status = "UNKNOWN"
        elif all(s["healthy"] for s in status_details.values()):
            overall_status = "HEALTHY"
        elif any(s["healthy"] for s in status_details.values()):
            overall_status = "DEGRADED"
        else:
            overall_status = "CRITICAL"

        return {
            "status": overall_status,
            "connections": status_details,
            "pool_size": len(self._connection_pool),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_pragma_config(self) -> Dict[str, Any]:
        """
        Get current PRAGMA configuration (SSOT).
        Useful for documentation and debugging.

        Returns:
            Current PRAGMA settings
        """
        return self._pragma_config.copy()

    def is_sqlite_lock_error(self, error: Exception) -> bool:
        """Classify transient SQLite lock/busy errors in a single reusable place."""
        message = str(error).lower()
        return (
            "database is locked" in message
            or "database table is locked" in message
            or "database is busy" in message
            or "busy" in message
            or "locked" in message
        )

    def observe_sqlite_concurrency_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        """Hook for SQLite concurrency observability; currently logs at debug level."""
        logger.debug("[DatabaseManager] sqlite_concurrency_event=%s payload=%s", event_name, payload)

    def _record_transaction_latency(
        self, db_path: str, latency_ms: float, operation_tag: str = _NO_TAG
    ) -> None:
        """Store rolling transaction latency metrics per db_path and per operation_tag."""
        bounded_latency = max(0.0, float(latency_ms))
        with self._tx_metrics_lock:
            # Per-db-path bucket
            bucket = self._tx_latency_samples.get(db_path)
            if bucket is None:
                bucket = deque(maxlen=self._tx_metrics_window_size)
                self._tx_latency_samples[db_path] = bucket
            bucket.append(bounded_latency)
            self._tx_last_latency_ms[db_path] = bounded_latency

            # Per-operation-tag bucket (origin tracing)
            tag = operation_tag or _NO_TAG
            op_bucket = self._op_latency_samples.get(tag)
            if op_bucket is None:
                op_bucket = deque(maxlen=self._tx_metrics_window_size)
                self._op_latency_samples[tag] = op_bucket
            op_bucket.append(bounded_latency)
            self._op_last_latency_ms[tag] = bounded_latency

    def get_transaction_metrics(self, db_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Return rolling transaction latency metrics for observability/backpressure.

        Shape:
            {
                "global":      {"count": N, "avg_ms": X, "p95_ms": Y, "last_ms": Z},
                "by_db_path":  {path: {...}},
                "by_operation": {tag: {"count": N, "avg_ms": X, "p95_ms": Y, "last_ms": Z}},
            }
        """

        def _build_metrics(samples: list[float], last_ms: float) -> Dict[str, Any]:
            if not samples:
                return {"count": 0, "avg_ms": 0.0, "p95_ms": 0.0, "last_ms": last_ms}
            ordered = sorted(samples)
            idx = max(0, int(len(ordered) * 0.95) - 1)
            return {
                "count": len(samples),
                "avg_ms": round(sum(samples) / len(samples), 3),
                "p95_ms": round(ordered[idx], 3),
                "last_ms": round(last_ms, 3),
            }

        with self._tx_metrics_lock:
            if db_path is not None:
                bucket = list(self._tx_latency_samples.get(db_path, deque()))
                last = float(self._tx_last_latency_ms.get(db_path, 0.0))
                return {db_path: _build_metrics(bucket, last)}

            global_samples: list[float] = []
            for bucket in self._tx_latency_samples.values():
                global_samples.extend(list(bucket))
            last_global = max(self._tx_last_latency_ms.values()) if self._tx_last_latency_ms else 0.0

            result: Dict[str, Any] = {
                "global": _build_metrics(global_samples, float(last_global)),
                "by_db_path": {},
                "by_operation": {},
            }
            for path, bucket in self._tx_latency_samples.items():
                last = float(self._tx_last_latency_ms.get(path, 0.0))
                result["by_db_path"][path] = _build_metrics(list(bucket), last)
            for tag, op_bucket in self._op_latency_samples.items():
                last = float(self._op_last_latency_ms.get(tag, 0.0))
                result["by_operation"][tag] = _build_metrics(list(op_bucket), last)
            return result

    def set_pragma_value(self, key: str, value: Any) -> None:
        """
        Update a PRAGMA value (rarely used; config should be static).
        Applies to new connections; existing connections unchanged.

        Args:
            key: PRAGMA key (e.g., 'busy_timeout')
            value: New value
        """
        with self._config_lock:
            if key in self._pragma_config:
                self._pragma_config[key] = value
                logger.warning(f"[DatabaseManager] PRAGMA {key} updated to {value} (affects new connections only)")
            else:
                logger.error(f"[DatabaseManager] Unknown PRAGMA key: {key}")


# Singleton instance (accessed via get_database_manager())
_db_manager_instance: Optional[DatabaseManager] = None


def get_database_manager() -> DatabaseManager:
    """
    Get the singleton DatabaseManager instance.
    Thread-safe; use this instead of DatabaseManager() constructor.

    Returns:
        DatabaseManager singleton
    """
    global _db_manager_instance
    if _db_manager_instance is None:
        _db_manager_instance = DatabaseManager()
    return _db_manager_instance
