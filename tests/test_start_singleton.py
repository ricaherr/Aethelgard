"""
Tests: start.py — Singleton Lock & Capital from DB
  HU 10.3: PID lockfile prevents duplicate processes
  HU 10.4: initial_capital reads from sys_config.account_balance
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from start import _acquire_singleton_lock, _release_singleton_lock, _read_initial_capital


# ── _acquire_singleton_lock ───────────────────────────────────────────────────

class TestSingletonLock:
    def test_creates_lockfile_when_absent(self, tmp_path):
        lock = tmp_path / "aethelgard.lock"
        result = _acquire_singleton_lock(lock)
        assert result is True
        assert lock.exists()
        assert lock.read_text().strip() == str(os.getpid())

    def test_acquires_stale_lock(self, tmp_path):
        """Lockfile with a dead PID should be overwritten."""
        lock = tmp_path / "aethelgard.lock"
        lock.write_text("999999999")  # PID that doesn't exist
        result = _acquire_singleton_lock(lock)
        assert result is True
        assert lock.read_text().strip() == str(os.getpid())

    def test_rejects_active_lock(self, tmp_path):
        """Lockfile with another live PID should block acquisition."""
        lock = tmp_path / "aethelgard.lock"
        rival_pid = os.getpid() + 1  # different from current process
        lock.write_text(str(rival_pid))
        with patch("psutil.pid_exists", return_value=True):
            result = _acquire_singleton_lock(lock)
        assert result is False

    def test_release_removes_lockfile(self, tmp_path):
        lock = tmp_path / "aethelgard.lock"
        lock.write_text(str(os.getpid()))
        _release_singleton_lock(lock)
        assert not lock.exists()

    def test_release_noop_when_missing(self, tmp_path):
        lock = tmp_path / "aethelgard.lock"
        _release_singleton_lock(lock)  # should not raise


# ── _read_initial_capital ──────────────────────────────────────────────────────

class TestReadInitialCapital:
    def test_reads_account_balance_from_config(self):
        storage = MagicMock()
        storage.get_sys_config.return_value = {"account_balance": 8386.09}
        capital = _read_initial_capital(storage)
        assert capital == pytest.approx(8386.09)

    def test_fallback_when_key_missing(self):
        storage = MagicMock()
        storage.get_sys_config.return_value = {}
        capital = _read_initial_capital(storage)
        assert capital == pytest.approx(10000.0)

    def test_fallback_on_storage_exception(self):
        storage = MagicMock()
        storage.get_sys_config.side_effect = Exception("DB error")
        capital = _read_initial_capital(storage)
        assert capital == pytest.approx(10000.0)

    def test_fallback_when_balance_zero(self):
        """Zero balance is treated as invalid — fall back to default."""
        storage = MagicMock()
        storage.get_sys_config.return_value = {"account_balance": 0}
        capital = _read_initial_capital(storage)
        assert capital == pytest.approx(10000.0)
