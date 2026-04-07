"""SQLite driver implementation for the agnostic persistence contract."""

from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Any, Generator

from data_vault.database_manager import DatabaseManager

from .errors import PersistenceTransactionError, normalize_persistence_error
from .interface import IDatabaseDriver

logger = logging.getLogger(__name__)


class SQLiteDriver(IDatabaseDriver):
    """Adapter that delegates SQLite operations to DatabaseManager."""

    def __init__(self, database_manager: DatabaseManager) -> None:
        self.database_manager = database_manager

    def get_connection(self, db_path: str) -> sqlite3.Connection:
        try:
            return self.database_manager.get_connection(db_path)
        except Exception as error:  # pragma: no cover - normalized for callers
            raise normalize_persistence_error(error) from error

    def execute(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> int:
        try:
            return self.database_manager.execute_update(db_path, sql, params)
        except Exception as error:
            raise normalize_persistence_error(error) from error

    def execute_many(self, db_path: str, sql: str, param_list: list[tuple[Any, ...]]) -> int:
        try:
            return self.database_manager.execute_many(db_path, sql, param_list)
        except Exception as error:
            raise normalize_persistence_error(error) from error

    def fetch_one(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        try:
            conn = self.database_manager.get_connection(db_path)
            cursor = conn.cursor()
            cursor.execute(sql, params)
            row = cursor.fetchone()
            if row is None:
                return None
            return dict(row)
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
