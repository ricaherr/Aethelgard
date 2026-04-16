"""Driver interface for backend-agnostic persistence operations."""

from __future__ import annotations

import sqlite3
from abc import ABC, abstractmethod
from contextlib import AbstractContextManager
from dataclasses import dataclass, field
from typing import Any


@dataclass
class RecoveryContext:
    """Context passed to a recovery strategy when a lock or busy error is detected."""

    db_path: str
    error: Exception
    attempt_number: int
    operation_tag: str = ""


@dataclass
class RecoveryResult:
    """Outcome returned by a recovery strategy after an attempt."""

    recovered: bool
    action_taken: str
    should_degrade: bool = False
    error: str = field(default="")


class IDatabaseRecoveryStrategy(ABC):
    """
    Strategy interface for driver-specific lock recovery.

    Each driver backend (SQLite, Postgres, …) implements this contract so that
    DatabaseManager can orchestrate recovery without knowing backend internals.
    """

    @abstractmethod
    def is_lock_error(self, error: Exception) -> bool:
        """Return True when *error* is a transient or persistent lock/busy error."""

    @abstractmethod
    def attempt_recovery(self, context: RecoveryContext) -> RecoveryResult:
        """
        Attempt to recover from a lock condition described by *context*.

        Implementations may flush WAL, reconnect, or apply backend-specific
        remediation.  Must return a RecoveryResult describing the outcome.
        """


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
