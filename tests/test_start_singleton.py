"""
Tests: start.py — Singleton Lock, Capital from DB & Risk Seed
  HU 10.3: PID lockfile prevents duplicate processes
  HU 10.4: initial_capital reads from sys_config.account_balance
  HU 3.10: _seed_risk_config seeds risk_settings and dynamic_params idempotently
"""
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from start import _acquire_singleton_lock, _release_singleton_lock, _read_initial_capital, _seed_risk_config


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


# ── _seed_risk_config ─────────────────────────────────────────────────────────

class TestSeedRiskConfig:
    def test_seeds_default_values_when_absent(self):
        """When sys_config has neither key, both must be written."""
        storage = MagicMock()
        storage.get_sys_config.return_value = {}
        _seed_risk_config(storage)
        storage.update_sys_config.assert_called_once()
        written = storage.update_sys_config.call_args[0][0]
        assert "risk_settings" in written
        assert "dynamic_params" in written
        assert written["risk_settings"]["max_consecutive_losses"] == 3
        assert written["dynamic_params"]["risk_per_trade"] == pytest.approx(0.005)

    def test_seeds_only_missing_key(self):
        """If risk_settings already exists, only dynamic_params is written."""
        storage = MagicMock()
        storage.get_sys_config.return_value = {
            "risk_settings": {"max_consecutive_losses": 5}
        }
        _seed_risk_config(storage)
        written = storage.update_sys_config.call_args[0][0]
        assert "risk_settings" not in written
        assert "dynamic_params" in written

    def test_is_idempotent_when_both_present(self):
        """When both keys exist, update_sys_config must NOT be called."""
        storage = MagicMock()
        storage.get_sys_config.return_value = {
            "risk_settings": {"max_consecutive_losses": 3},
            "dynamic_params": {"risk_per_trade": 0.005},
        }
        _seed_risk_config(storage)
        storage.update_sys_config.assert_not_called()

    def test_survives_storage_exception(self):
        """Storage errors must be caught — no exception propagated."""
        storage = MagicMock()
        storage.get_sys_config.side_effect = Exception("DB error")
        _seed_risk_config(storage)  # must not raise
