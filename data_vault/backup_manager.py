"""
Database backup scheduler for Aethelgard.

Runs periodic backups using StorageManager configuration (DB-first).
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Dict

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class DatabaseBackupManager:
    """
    Periodic DB backup manager driven by dynamic_params.database_backup.

    Config schema (dynamic_params):
    {
      "database_backup": {
        "enabled": true,
        "interval_minutes": 1440,
        "backup_dir": "backups",
        "retention_count": 15
      }
    }
    """

    def __init__(self, storage: StorageManager, poll_seconds: int = 30):
        self.storage = storage
        self.poll_seconds = max(5, poll_seconds)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_backup_ts = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="db-backup-manager")
        self._thread.start()
        logger.info("DatabaseBackupManager started.")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        logger.info("DatabaseBackupManager stopped.")

    def _load_config(self) -> Dict[str, Any]:
        params = self.storage.get_dynamic_params()
        cfg = params.get("database_backup", {}) if isinstance(params, dict) else {}
        interval_days = cfg.get("interval_days")
        retention_days = cfg.get("retention_days")

        if interval_days is not None:
            interval_minutes = max(1, int(interval_days)) * 1440
        else:
            interval_minutes = max(1, int(cfg.get("interval_minutes", 1440)))

        if retention_days is not None:
            retention_count = max(1, int(retention_days))
        else:
            retention_count = max(1, int(cfg.get("retention_count", 15)))

        return {
            "enabled": bool(cfg.get("enabled", True)),
            "interval_minutes": interval_minutes,
            "backup_dir": cfg.get("backup_dir", "backups"),
            "retention_count": retention_count,
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                cfg = self._load_config()
                if cfg["enabled"]:
                    interval_seconds = cfg["interval_minutes"] * 60
                    now = time.time()
                    if now - self._last_backup_ts >= interval_seconds:
                        path = self.storage.create_db_backup(
                            backup_dir=cfg["backup_dir"],
                            retention_count=cfg["retention_count"],
                        )
                        if path:
                            self._last_backup_ts = now
            except Exception as e:
                logger.error("DatabaseBackupManager cycle error: %s", e)

            self._stop_event.wait(self.poll_seconds)
