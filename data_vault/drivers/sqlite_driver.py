"""SQLite driver implementation for the agnostic persistence contract."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Callable, Deque, Generator, Literal

from data_vault.database_manager import DatabaseManager

from .errors import PersistenceTransactionError, normalize_persistence_error
from .interface import IDatabaseDriver

logger = logging.getLogger(__name__)

WriteMode = Literal["critical", "telemetry"]


@dataclass
class SQLiteConcurrencyPolicy:
    """Runtime policy for retry/backoff and selective telemetry queueing."""

    retry_max_attempts: int = 3
    retry_base_backoff_ms: int = 25
    retry_backoff_multiplier: float = 2.0
    retry_max_backoff_ms: int = 500
    telemetry_queue_max_size: int = 200
    telemetry_flush_interval_ms: int = 250

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "SQLiteConcurrencyPolicy":
        return cls(
            retry_max_attempts=max(1, int(raw.get("retry_max_attempts", cls.retry_max_attempts))),
            retry_base_backoff_ms=max(1, int(raw.get("retry_base_backoff_ms", cls.retry_base_backoff_ms))),
            retry_backoff_multiplier=max(1.0, float(raw.get("retry_backoff_multiplier", cls.retry_backoff_multiplier))),
            retry_max_backoff_ms=max(1, int(raw.get("retry_max_backoff_ms", cls.retry_max_backoff_ms))),
            telemetry_queue_max_size=max(1, int(raw.get("telemetry_queue_max_size", cls.telemetry_queue_max_size))),
            telemetry_flush_interval_ms=max(0, int(raw.get("telemetry_flush_interval_ms", cls.telemetry_flush_interval_ms))),
        )


class SQLiteDriver(IDatabaseDriver):
    """Adapter that delegates SQLite operations to DatabaseManager."""

    def __init__(self, database_manager: DatabaseManager) -> None:
        self.database_manager = database_manager
        self._policy_override: SQLiteConcurrencyPolicy | None = None
        self._policy_cache_by_db_path: dict[str, tuple[float, SQLiteConcurrencyPolicy]] = {}
        self._policy_ttl_seconds: float = 5.0
        self._queue_lock = threading.Lock()
        self._write_lock_pool_guard = threading.Lock()
        self._write_lock_pool: dict[str, threading.RLock] = {}
        self._telemetry_queue: Deque[tuple[str, str, tuple[Any, ...], bool]] = deque()
        self._last_flush_ts: float = time.time()
        self._force_critical_writes = threading.local()
        self._metrics: dict[str, float | int] = {
            "retry_attempts": 0,
            "retry_exhausted": 0,
            "telemetry_enqueued": 0,
            "telemetry_dropped": 0,
            "telemetry_flushed": 0,
            "last_flush_latency_ms": 0,
        }

    def get_connection(self, db_path: str) -> sqlite3.Connection:
        try:
            return self.database_manager.get_connection(db_path)
        except Exception as error:  # pragma: no cover - normalized for callers
            raise normalize_persistence_error(error) from error

    def execute(
        self,
        db_path: str,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        write_mode: WriteMode = "critical",
    ) -> int:
        try:
            effective_mode: WriteMode = self._resolve_write_mode(write_mode)
            if effective_mode == "telemetry":
                with self._get_write_lock(db_path):
                    self._enqueue_telemetry_write(db_path, sql, params)
                    self._flush_telemetry_queue_if_due(db_path)
                return 1
            with self._get_write_lock(db_path):
                return self._execute_update_with_retry(db_path, sql, params)
        except Exception as error:
            raise normalize_persistence_error(error) from error

    def execute_many(
        self,
        db_path: str,
        sql: str,
        param_list: list[tuple[Any, ...]],
        *,
        write_mode: WriteMode = "critical",
    ) -> int:
        try:
            if not param_list:
                return 0

            effective_mode: WriteMode = self._resolve_write_mode(write_mode)
            if effective_mode == "telemetry":
                with self._get_write_lock(db_path):
                    for params in param_list:
                        self._enqueue_telemetry_write(db_path, sql, params, is_many=True)
                    self._flush_telemetry_queue_if_due(db_path)
                return len(param_list)
            with self._get_write_lock(db_path):
                return self._execute_many_with_retry(db_path, sql, param_list)
        except Exception as error:
            raise normalize_persistence_error(error) from error

    def fetch_one(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        try:
            conn = self.database_manager.get_connection(db_path)
            cursor = conn.cursor()
            try:
                cursor.execute(sql, params)
                row = cursor.fetchone()
                if row is None:
                    return None
                return dict(row)
            finally:
                try:
                    cursor.close()
                except Exception:
                    logger.debug("[SQLiteDriver] Failed to close fetch_one cursor", exc_info=True)
        except Exception as error:
            raise normalize_persistence_error(error) from error

    def fetch_all(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        try:
            return self.database_manager.execute_query(db_path, sql, params)
        except Exception as error:
            raise normalize_persistence_error(error) from error

    @contextmanager
    def transaction(self, db_path: str) -> Generator[sqlite3.Connection, None, None]:
        try:
            with self.database_manager.transaction(db_path) as conn:
                yield conn
        except Exception as error:
            normalized = normalize_persistence_error(error)
            logger.error("[SQLiteDriver] Transaction failed on %s: %s", db_path, normalized)
            raise PersistenceTransactionError(str(normalized)) from error

    def health_check(self) -> dict[str, Any]:
        return self.database_manager.health_check()

    @contextmanager
    def force_critical_writes(self) -> Generator[None, None, None]:
        """Force critical path while bootstrapping/migrating to bypass telemetry queue."""
        setattr(self._force_critical_writes, "enabled", True)
        try:
            yield
        finally:
            setattr(self._force_critical_writes, "enabled", False)

    def set_runtime_concurrency_policy(self, policy: dict[str, Any]) -> None:
        """Set explicit runtime policy override (used by tests and controlled scenarios)."""
        self._policy_override = SQLiteConcurrencyPolicy.from_raw(policy)

    def get_concurrency_metrics(self) -> dict[str, float | int]:
        """Return a point-in-time snapshot for observability and tests."""
        return dict(self._metrics)

    def flush_telemetry_queue(self, db_path: str) -> int:
        """Flush queued telemetry writes with retry protection.

        Returns:
            Number of writes flushed successfully.
        """
        with self._queue_lock:
            items = list(self._telemetry_queue)
            self._telemetry_queue.clear()

        if not items:
            return 0

        started_at = time.perf_counter()
        flushed = 0
        for queued_db_path, sql, params, is_many in items:
            target_db_path = queued_db_path or db_path
            with self._get_write_lock(target_db_path):
                if is_many:
                    self._execute_many_with_retry(target_db_path, sql, [params])
                    flushed += 1
                else:
                    self._execute_update_with_retry(target_db_path, sql, params)
                    flushed += 1

        self._metrics["telemetry_flushed"] = int(self._metrics["telemetry_flushed"]) + flushed
        latency_ms = int((time.perf_counter() - started_at) * 1000)
        self._metrics["last_flush_latency_ms"] = latency_ms
        self._last_flush_ts = time.time()
        return flushed

    def _resolve_write_mode(self, write_mode: WriteMode) -> WriteMode:
        force_critical = bool(getattr(self._force_critical_writes, "enabled", False))
        if force_critical:
            return "critical"
        return write_mode

    def _policy_for_db(self, db_path: str) -> SQLiteConcurrencyPolicy:
        if self._policy_override is not None:
            return self._policy_override

        now = time.time()
        cached = self._policy_cache_by_db_path.get(db_path)
        if cached is not None:
            cached_ts, cached_policy = cached
            if (now - cached_ts) <= self._policy_ttl_seconds:
                return cached_policy

        loaded = self._load_policy_from_sys_config(db_path)
        self._policy_cache_by_db_path[db_path] = (now, loaded)
        return loaded

    def _load_policy_from_sys_config(self, db_path: str) -> SQLiteConcurrencyPolicy:
        default_policy = SQLiteConcurrencyPolicy()
        try:
            rows = self.database_manager.execute_query(
                db_path,
                """
                SELECT key, value
                FROM sys_config
                WHERE key IN (
                    'sqlite_retry_max_attempts',
                    'sqlite_retry_base_backoff_ms',
                    'sqlite_retry_backoff_multiplier',
                    'sqlite_retry_max_backoff_ms',
                    'sqlite_telemetry_queue_max_size',
                    'sqlite_telemetry_flush_interval_ms',
                    'sqlite_concurrency_policy'
                )
                """,
            )
        except Exception:
            return default_policy

        if not rows:
            return default_policy

        parsed: dict[str, Any] = {}
        for row in rows:
            key = str(row.get("key", ""))
            raw_value = row.get("value")
            if key == "sqlite_concurrency_policy" and isinstance(raw_value, str):
                try:
                    policy_json = json.loads(raw_value)
                    if isinstance(policy_json, dict):
                        parsed.update(policy_json)
                except Exception:
                    continue
                continue

            mapping = {
                "sqlite_retry_max_attempts": "retry_max_attempts",
                "sqlite_retry_base_backoff_ms": "retry_base_backoff_ms",
                "sqlite_retry_backoff_multiplier": "retry_backoff_multiplier",
                "sqlite_retry_max_backoff_ms": "retry_max_backoff_ms",
                "sqlite_telemetry_queue_max_size": "telemetry_queue_max_size",
                "sqlite_telemetry_flush_interval_ms": "telemetry_flush_interval_ms",
            }
            target_key = mapping.get(key)
            if target_key is None:
                continue
            parsed[target_key] = raw_value

        if not parsed:
            return default_policy
        return SQLiteConcurrencyPolicy.from_raw(parsed)

    def _execute_update_with_retry(self, db_path: str, sql: str, params: tuple[Any, ...]) -> int:
        policy = self._policy_for_db(db_path)
        return self._with_retry(
            db_path=db_path,
            operation=lambda: self.database_manager.execute_update(db_path, sql, params),
            policy=policy,
        )

    def _execute_many_with_retry(self, db_path: str, sql: str, param_list: list[tuple[Any, ...]]) -> int:
        policy = self._policy_for_db(db_path)
        return self._with_retry(
            db_path=db_path,
            operation=lambda: self.database_manager.execute_many(db_path, sql, param_list),
            policy=policy,
        )

    def _with_retry(
        self,
        *,
        db_path: str,
        operation: Callable[[], int],
        policy: SQLiteConcurrencyPolicy,
    ) -> int:
        attempt = 1
        while True:
            try:
                return operation()
            except Exception as error:
                if not self._is_lock_or_busy_error(error):
                    raise
                if attempt >= policy.retry_max_attempts:
                    self._metrics["retry_exhausted"] = int(self._metrics["retry_exhausted"]) + 1
                    self._observe("retry_exhausted", db_path=db_path, attempts=attempt, error=str(error))
                    raise

                self._metrics["retry_attempts"] = int(self._metrics["retry_attempts"]) + 1
                backoff_seconds = self._compute_backoff_seconds(attempt, policy)
                self._observe(
                    "retry_attempt",
                    db_path=db_path,
                    attempt=attempt,
                    backoff_seconds=backoff_seconds,
                    error=str(error),
                )
                time.sleep(backoff_seconds)
                attempt += 1

    def _is_lock_or_busy_error(self, error: Exception) -> bool:
        classifier = getattr(self.database_manager, "is_sqlite_lock_error", None)
        if callable(classifier):
            try:
                return bool(classifier(error))
            except Exception:
                pass

        message = str(error).lower()
        return "locked" in message or "busy" in message

    def _compute_backoff_seconds(self, attempt: int, policy: SQLiteConcurrencyPolicy) -> float:
        exponent = max(0, attempt - 1)
        raw_backoff_ms = int(policy.retry_base_backoff_ms * (policy.retry_backoff_multiplier ** exponent))
        bounded_backoff_ms = min(policy.retry_max_backoff_ms, raw_backoff_ms)
        return bounded_backoff_ms / 1000.0

    def _enqueue_telemetry_write(
        self,
        db_path: str,
        sql: str,
        params: tuple[Any, ...],
        *,
        is_many: bool = False,
    ) -> None:
        policy = self._policy_for_db(db_path)
        with self._queue_lock:
            if len(self._telemetry_queue) >= policy.telemetry_queue_max_size:
                self._telemetry_queue.popleft()
                self._metrics["telemetry_dropped"] = int(self._metrics["telemetry_dropped"]) + 1
                self._observe("telemetry_drop_oldest", db_path=db_path, queue_max_size=policy.telemetry_queue_max_size)

            self._telemetry_queue.append((db_path, sql, params, is_many))
            self._metrics["telemetry_enqueued"] = int(self._metrics["telemetry_enqueued"]) + 1

    def _flush_telemetry_queue_if_due(self, db_path: str) -> None:
        policy = self._policy_for_db(db_path)
        now = time.time()
        with self._queue_lock:
            queue_size = len(self._telemetry_queue)

        if queue_size == 0:
            return

        interval_s = policy.telemetry_flush_interval_ms / 1000.0
        if queue_size >= policy.telemetry_queue_max_size:
            self.flush_telemetry_queue(db_path)
            return

        if interval_s <= 0:
            self.flush_telemetry_queue(db_path)
            return

        elapsed = now - self._last_flush_ts
        if elapsed >= interval_s:
            self.flush_telemetry_queue(db_path)

    def _observe(self, event_name: str, **payload: Any) -> None:
        observer = getattr(self.database_manager, "observe_sqlite_concurrency_event", None)
        if callable(observer):
            try:
                observer(event_name, payload)
                return
            except Exception:
                pass
        logger.debug("[SQLiteDriver] %s %s", event_name, payload)

    def _get_write_lock(self, db_path: str) -> threading.RLock:
        with self._write_lock_pool_guard:
            lock = self._write_lock_pool.get(db_path)
            if lock is None:
                lock = threading.RLock()
                self._write_lock_pool[db_path] = lock
            return lock
