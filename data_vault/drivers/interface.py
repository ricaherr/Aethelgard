"""Driver interface for backend-agnostic persistence operations."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from typing import Any


class IDatabaseDriver(ABC):
    """Minimal persistence contract consumed by repositories/storage."""

    @abstractmethod
    def get_connection(self, db_path: str) -> sqlite3.Connection:
        """Return an active backend connection handle."""

    @abstractmethod
    def execute(
        self,
        db_path: str,
        sql: str,
        params: tuple[Any, ...] = (),
        *,
        write_mode: str = "critical",
    ) -> int:
        """Execute INSERT/UPDATE/DELETE statement and return affected count or row id."""

    @abstractmethod
    def execute_many(
        self,
        db_path: str,
        sql: str,
        param_list: list[tuple[Any, ...]],
        *,
        write_mode: str = "critical",
    ) -> int:
        """Execute batch statement with homogeneous parameter tuples."""

    @abstractmethod
    def fetch_one(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Execute SELECT query and return one row as dict."""

    @abstractmethod
    def fetch_all(self, db_path: str, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Execute SELECT query and return all rows as dict list."""

    @abstractmethod
    def transaction(self, db_path: str) -> AbstractContextManager[sqlite3.Connection]:
        """Return context manager handling commit/rollback semantics."""

    @abstractmethod
    def health_check(self) -> dict[str, Any]:
        """Return health details for active backend connections."""
