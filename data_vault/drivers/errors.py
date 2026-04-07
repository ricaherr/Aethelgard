"""Persistence error model for backend-agnostic database drivers."""

from __future__ import annotations

import sqlite3


class PersistenceError(Exception):
    """Base error for all persistence driver failures."""


class PersistenceOperationalError(PersistenceError):
    """Operational backend failure (locks, unavailable DB, IO issues)."""


class PersistenceIntegrityError(PersistenceError):
    """Constraint/data integrity violation from backend."""


class PersistenceProgrammingError(PersistenceError):
    """Invalid query or malformed DB interaction."""


class PersistenceTransactionError(PersistenceError):
    """Transaction failed and rollback path was triggered."""


def normalize_persistence_error(error: Exception) -> PersistenceError:
    """Normalize backend-specific errors into persistence domain errors."""
    if isinstance(error, PersistenceError):
        return error
    if isinstance(error, sqlite3.IntegrityError):
        return PersistenceIntegrityError(str(error))
    if isinstance(error, sqlite3.OperationalError):
        return PersistenceOperationalError(str(error))
    if isinstance(error, sqlite3.ProgrammingError):
        return PersistenceProgrammingError(str(error))
    return PersistenceError(str(error))
