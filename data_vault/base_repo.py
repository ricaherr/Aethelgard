import threading
import sqlite3
import os
import logging
import time
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime, timezone
from utils.time_utils import to_utc

logger = logging.getLogger(__name__)

# Register datetime adapter/converter to always use UTC ISO 8601
sqlite3.register_adapter(datetime, lambda dt: dt.astimezone(timezone.utc).isoformat())
sqlite3.register_converter("timestamp", lambda s: to_utc(s.decode()))

class BaseRepository:
    """
    Base class for all database repositories.
    Provides shared connection management and execution logic.
    """
    _db_lock = threading.Lock()

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "global", "aethelgard.db")
        self._persistent_conn = None
        if self.db_path == ":memory:":
            self._persistent_conn = self._get_conn()

    @property
    def conn(self) -> sqlite3.Connection:
        """Public accessor to get the database connection."""
        return self._get_conn()

    def _get_conn(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        if self._persistent_conn is not None:
            return self._persistent_conn
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        return conn

    def _close_conn(self, conn: sqlite3.Connection) -> None:
        """Close connection only if it's NOT the persistent connection"""
        if conn is not self._persistent_conn:
            conn.close()

    def execute_query(self, query: str, params: tuple = ()) -> List[Dict]:
        """Execute a SELECT query and return results as list of dicts"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def _execute_serialized(self, func: Callable, *args, retries: int = 5, backoff: float = 0.2, **kwargs) -> Any:
        """
        Ejecuta una función crítica de DB serializadamente, con retry/backoff si la DB está locked.
        El sleep de backoff se ejecuta FUERA del lock para no bloquear otros hilos.
        """
        last_exc = None
        for attempt in range(retries):
            with self._db_lock:
                conn = self._get_conn()
                try:
                    result = func(conn, *args, **kwargs)
                    return result
                except Exception as e:
                    last_exc = e
                    if 'locked' in str(e).lower():
                        logger.warning(f"DB locked, retrying ({attempt+1}/{retries})...")
                    else:
                        logger.error(f"DB error: {e}")
                        raise
                finally:
                    self._close_conn(conn)
            # Sleep FUERA del lock — otros hilos pueden continuar durante el backoff
            if last_exc and 'locked' in str(last_exc).lower():
                time.sleep(backoff * (attempt + 1))

        logger.error(f"DB error after retries: {last_exc}")
        if last_exc:
            raise last_exc
        raise RuntimeError("DB error after retries")
