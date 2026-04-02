"""
BaseRepository — Minimal data access abstraction
==================================================

RESPONSIBILITY:
- Provide convenience methods for common DB operations
- Delegate all connection management to DatabaseManager (SSOT)
- NEVER manipulate PRAGMA, timeouts, or connection lifecycle

CRITICAL: Zero direct sqlite3.connect() calls. Period.

TRACE_ID: FIX-BASE-REPO-CLEANUP-2026-04-01
"""

import logging
import sqlite3
from typing import Optional, List, Dict, Any, Generator, Callable, TypeVar
from contextlib import contextmanager

from .database_manager import get_database_manager

T = TypeVar('T')  # Generic return type for _execute_serialized

logger = logging.getLogger(__name__)


class BaseRepository:
    """
    Base class for all database repositories (mixins).
    Provides convenience wrappers around DatabaseManager.
    """

    def __init__(self, db_path: Optional[str] = None) -> None:
        """
        Initialize repository with optional db_path override.

        Args:
            db_path: Database path. Defaults to global/aethelgard.db
        """
        if db_path is None:
            import os
            db_path = os.path.join(
                os.path.dirname(__file__), "global", "aethelgard.db"
            )
        self.db_path: str = db_path
        self.db_manager = get_database_manager()
        self._ensure_db_directory()

    def _ensure_db_directory(self) -> None:
        """Ensure database directory exists (skip for :memory: databases)."""
        import os
        # Skip for in-memory databases (both ":memory:" and ":memory:_UUID")
        if ":memory:" in self.db_path:
            return
        db_dir = os.path.dirname(self.db_path)
        if db_dir:  # Only create if dirname is not empty
            os.makedirs(db_dir, exist_ok=True)

    def get_connection(self) -> sqlite3.Connection:
        """
        Get a database connection from the pool.
        NEVER close it directly (DatabaseManager manages lifecycle).

        Returns:
            sqlite3.Connection (pooled, thread-safe)
        """
        return self.db_manager.get_connection(self.db_path)

    def execute_query(self, sql: str, params: tuple[Any, ...] = ()) -> List[Dict[str, Any]]:
        """
        Execute a SELECT query (read-only).

        Args:
            sql: SQL SELECT statement
            params: Query parameters

        Returns:
            List of dicts (rows)
        """
        try:
            return self.db_manager.execute_query(self.db_path, sql, params)
        except Exception as e:
            logger.error(f"Query failed on {self.db_path}: {e}")
            raise

    def execute_update(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        """
        Execute INSERT/UPDATE/DELETE (write operation with auto-commit).

        Args:
            sql: SQL statement
            params: Parameters

        Returns:
            Rows affected or last insert rowid
        """
        try:
            return self.db_manager.execute_update(self.db_path, sql, params)
        except Exception as e:
            logger.error(f"Update failed on {self.db_path}: {e}")
            raise

    @contextmanager
    def transaction(self) -> Generator[sqlite3.Connection, None, None]:
        """
        Context manager for transactions.
        Auto-commits on success, rolls back on error.

        Usage:
            with repo.transaction() as conn:
                cursor = conn.cursor()
                cursor.execute("INSERT ...")
        """
        with self.db_manager.transaction(self.db_path) as conn:
            yield conn

    def get_db_health(self) -> Dict[str, Any]:
        """
        Check database health.

        Returns:
            Health status dict
        """
        return self.db_manager.health_check()

    # ──────────────────────────────────────────────────────────────────────────────
    # BACKWARDS COMPATIBILITY: Old-style methods (delegated to DatabaseManager)
    # These are for legacy code that uses _get_conn() + cursor pattern
    # DEPRECATED: Use execute_query(), execute_update(), or transaction() instead
    # ──────────────────────────────────────────────────────────────────────────────

    def _get_conn(self) -> sqlite3.Connection:
        """
        DEPRECATED: Legacy method for compatibility with existing code.
        Returns a pooled connection from DatabaseManager.

        NOTE: DO NOT CLOSE THIS CONNECTION manually.
        The connection is managed by DatabaseManager and shared across the app.

        Returns:
            sqlite3.Connection from pool
        """
        return self.get_connection()

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        """
        DEPRECATED: Legacy method (NO-OP for backwards compatibility).
        DatabaseManager handles connection lifecycle automatically.
        This method is a no-op; do not call it.

        Args:
            conn: Connection (ignored; for backwards compat only)
        """
        pass  # NO-OP: DatabaseManager manages pool lifecycle

    def _execute_serialized(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """
        Execute a function with serialized DB access.
        Compatible with DatabaseManager pooling.

        This is a legacy method wrapper that executes func with a connection
        from the pool. No actual serialization occurs (DatabaseManager handles
        that at the pool level via check_same_thread=False + busy_timeout).

        Args:
            func: Callable that takes (conn, *args, **kwargs) as parameters
            *args: Positional arguments passed to func
            **kwargs: Keyword arguments passed to func

        Returns:
            Result of func()
        """
        with self.transaction() as conn:
            return func(conn, *args, **kwargs)
