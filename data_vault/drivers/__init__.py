"""Persistence drivers package."""

from __future__ import annotations

from typing import Optional

from data_vault.database_manager import get_database_manager

from .errors import (
    PersistenceError,
    PersistenceIntegrityError,
    PersistenceOperationalError,
    PersistenceProgrammingError,
    PersistenceTransactionError,
    normalize_persistence_error,
)
from .interface import IDatabaseDriver, IDatabaseRecoveryStrategy, RecoveryContext, RecoveryResult
from .sqlite_driver import SQLiteDriver

_driver_instance: Optional[IDatabaseDriver] = None


def get_database_driver() -> IDatabaseDriver:
    """Return singleton database driver for current runtime backend."""
    global _driver_instance
    if _driver_instance is None:
        _driver_instance = SQLiteDriver(get_database_manager())
    return _driver_instance


__all__ = [
    "IDatabaseDriver",
    "IDatabaseRecoveryStrategy",
    "RecoveryContext",
    "RecoveryResult",
    "SQLiteDriver",
    "get_database_driver",
    "PersistenceError",
    "PersistenceOperationalError",
    "PersistenceIntegrityError",
    "PersistenceProgrammingError",
    "PersistenceTransactionError",
    "normalize_persistence_error",
]
