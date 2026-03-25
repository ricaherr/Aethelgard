"""
test_operational_mode_manager.py

Verifica el comportamiento de OperationalModeManager:
- Detección correcta del contexto operacional (BACKTEST_ONLY / SHADOW_ACTIVE / LIVE_ACTIVE)
- Presupuesto de backtest adaptativo (AGGRESSIVE / MODERATE / CONSERVATIVE / DEFERRED)
- Frecuencias de componentes por contexto
- Persistencia de transiciones en sys_audit_logs
"""
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from core_brain.operational_mode_manager import (
    BacktestBudget,
    OperationalContext,
    OperationalModeManager,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_storage(strategies: list[dict] | None = None):
    """Storage mock con una BD :memory: que tiene sys_strategies y sys_audit_logs."""
    conn = sqlite3.connect(":memory:")
    conn.execute("""
        CREATE TABLE sys_strategies (
            class_id TEXT PRIMARY KEY,
            mode     TEXT NOT NULL DEFAULT 'BACKTEST'
        )
    """)
    conn.execute("""
        CREATE TABLE sys_audit_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            payload    TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()

    if strategies:
        conn.executemany(
            "INSERT INTO sys_strategies (class_id, mode) VALUES (?, ?)",
            [(s["class_id"], s["mode"]) for s in strategies],
        )
        conn.commit()

    storage = MagicMock()
    storage._get_conn.return_value = conn
    storage._close_conn.return_value = None
    return storage


# ─────────────────────────────────────────────────────────────────────────────
# Detección de contexto operacional
# ─────────────────────────────────────────────────────────────────────────────

class TestContextDetection:

    def test_all_backtest_returns_backtest_only(self):
        strategies = [
            {"class_id": "A", "mode": "BACKTEST"},
            {"class_id": "B", "mode": "BACKTEST"},
        ]
        mgr = OperationalModeManager(storage=_make_storage(strategies))
        assert mgr.detect_context() == OperationalContext.BACKTEST_ONLY

    def test_one_shadow_returns_shadow_active(self):
        strategies = [
            {"class_id": "A", "mode": "BACKTEST"},
            {"class_id": "B", "mode": "SHADOW"},
        ]
        mgr = OperationalModeManager(storage=_make_storage(strategies))
        assert mgr.detect_context() == OperationalContext.SHADOW_ACTIVE

    def test_one_live_returns_live_active(self):
        strategies = [
            {"class_id": "A", "mode": "SHADOW"},
            {"class_id": "B", "mode": "LIVE"},
        ]
        mgr = OperationalModeManager(storage=_make_storage(strategies))
        assert mgr.detect_context() == OperationalContext.LIVE_ACTIVE

    def test_live_takes_priority_over_shadow(self):
        strategies = [
            {"class_id": "A", "mode": "SHADOW"},
            {"class_id": "B", "mode": "LIVE"},
            {"class_id": "C", "mode": "BACKTEST"},
        ]
        mgr = OperationalModeManager(storage=_make_storage(strategies))
        assert mgr.detect_context() == OperationalContext.LIVE_ACTIVE

    def test_empty_strategies_returns_backtest_only(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        assert mgr.detect_context() == OperationalContext.BACKTEST_ONLY

    def test_all_live_returns_live_active(self):
        strategies = [
            {"class_id": "A", "mode": "LIVE"},
            {"class_id": "B", "mode": "LIVE"},
        ]
        mgr = OperationalModeManager(storage=_make_storage(strategies))
        assert mgr.detect_context() == OperationalContext.LIVE_ACTIVE


# ─────────────────────────────────────────────────────────────────────────────
# Presupuesto de backtest
# ─────────────────────────────────────────────────────────────────────────────

class TestBacktestBudget:

    def _mgr_with_context(self, context: OperationalContext, cpu: float = 20.0, ram: float = 40.0):
        mgr = OperationalModeManager(storage=_make_storage([]))
        mgr._current_context = context
        with patch("core_brain.operational_mode_manager.psutil") as mock_psutil:
            mock_psutil.cpu_percent.return_value = cpu
            mock_psutil.virtual_memory.return_value = MagicMock(percent=ram)
            return mgr.get_backtest_budget()

    def test_backtest_only_low_cpu_returns_aggressive(self):
        budget = self._mgr_with_context(OperationalContext.BACKTEST_ONLY, cpu=20.0, ram=40.0)
        assert budget == BacktestBudget.AGGRESSIVE

    def test_shadow_active_low_cpu_returns_moderate(self):
        budget = self._mgr_with_context(OperationalContext.SHADOW_ACTIVE, cpu=20.0, ram=40.0)
        assert budget == BacktestBudget.MODERATE

    def test_live_active_low_cpu_returns_conservative(self):
        budget = self._mgr_with_context(OperationalContext.LIVE_ACTIVE, cpu=20.0, ram=40.0)
        assert budget == BacktestBudget.CONSERVATIVE

    def test_high_cpu_returns_deferred_regardless_of_context(self):
        for context in OperationalContext:
            budget = self._mgr_with_context(context, cpu=85.0, ram=40.0)
            assert budget == BacktestBudget.DEFERRED, (
                f"Context={context}: expected DEFERRED with CPU=85%, got {budget}"
            )

    def test_high_ram_returns_deferred(self):
        budget = self._mgr_with_context(OperationalContext.BACKTEST_ONLY, cpu=20.0, ram=91.0)
        assert budget == BacktestBudget.DEFERRED

    def test_exact_cpu_threshold_not_deferred(self):
        """CPU exactamente en el umbral (80%) no es DEFERRED."""
        budget = self._mgr_with_context(OperationalContext.BACKTEST_ONLY, cpu=80.0, ram=40.0)
        assert budget != BacktestBudget.DEFERRED

    def test_above_cpu_threshold_is_deferred(self):
        """CPU por encima del umbral (80.1%) sí es DEFERRED."""
        budget = self._mgr_with_context(OperationalContext.BACKTEST_ONLY, cpu=80.1, ram=40.0)
        assert budget == BacktestBudget.DEFERRED


# ─────────────────────────────────────────────────────────────────────────────
# Frecuencias de componentes
# ─────────────────────────────────────────────────────────────────────────────

class TestComponentFrequencies:

    def test_scanner_suspended_in_backtest_only(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        freqs = mgr.get_component_frequencies(OperationalContext.BACKTEST_ONLY)
        # Scanner debe tener frecuencia muy reducida (intervalo largo en segundos)
        assert freqs["scanner_interval_s"] > freqs["scanner_interval_s_normal"]

    def test_signal_factory_suspended_in_backtest_only(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        freqs = mgr.get_component_frequencies(OperationalContext.BACKTEST_ONLY)
        assert freqs["signal_factory_enabled"] is False

    def test_closing_monitor_suspended_in_backtest_only(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        freqs = mgr.get_component_frequencies(OperationalContext.BACKTEST_ONLY)
        assert freqs["closing_monitor_enabled"] is False

    def test_all_components_enabled_in_live_active(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        freqs = mgr.get_component_frequencies(OperationalContext.LIVE_ACTIVE)
        assert freqs["signal_factory_enabled"] is True
        assert freqs["closing_monitor_enabled"] is True

    def test_all_components_enabled_in_shadow_active(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        freqs = mgr.get_component_frequencies(OperationalContext.SHADOW_ACTIVE)
        assert freqs["signal_factory_enabled"] is True
        assert freqs["closing_monitor_enabled"] is True

    def test_connectivity_always_enabled(self):
        mgr = OperationalModeManager(storage=_make_storage([]))
        for context in OperationalContext:
            freqs = mgr.get_component_frequencies(context)
            assert freqs["connectivity_enabled"] is True, (
                f"connectivity debe estar siempre activo — falló en contexto {context}"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia de transiciones
# ─────────────────────────────────────────────────────────────────────────────

class TestTransitionPersistence:

    def test_context_change_logged_to_audit(self):
        storage = _make_storage([
            {"class_id": "A", "mode": "BACKTEST"},
        ])
        mgr = OperationalModeManager(storage=storage)
        mgr._current_context = OperationalContext.SHADOW_ACTIVE  # simular contexto anterior

        # Forzar cambio detectando BACKTEST_ONLY
        mgr.detect_context()

        conn = storage._get_conn()
        rows = conn.execute("SELECT event_type FROM sys_audit_logs").fetchall()
        assert any("MODE_TRANSITION" in row[0] for row in rows)

    def test_no_log_when_context_unchanged(self):
        storage = _make_storage([
            {"class_id": "A", "mode": "BACKTEST"},
        ])
        mgr = OperationalModeManager(storage=storage)
        mgr.detect_context()  # primera llamada — establece contexto
        initial_count = storage._get_conn().execute(
            "SELECT COUNT(*) FROM sys_audit_logs"
        ).fetchone()[0]

        mgr.detect_context()  # segunda llamada — mismo contexto, no debe loguear
        final_count = storage._get_conn().execute(
            "SELECT COUNT(*) FROM sys_audit_logs"
        ).fetchone()[0]
        assert final_count == initial_count


# ─────────────────────────────────────────────────────────────────────────────
# Integración básica
# ─────────────────────────────────────────────────────────────────────────────

class TestIntegration:

    def test_full_cycle_backtest_to_shadow(self):
        """Simula ciclo completo: BACKTEST_ONLY → detectar → cambio a SHADOW_ACTIVE."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE sys_strategies (class_id TEXT, mode TEXT)")
        conn.execute("CREATE TABLE sys_audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT, payload TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)")
        conn.execute("INSERT INTO sys_strategies VALUES ('A', 'BACKTEST')")
        conn.commit()

        storage = MagicMock()
        storage._get_conn.return_value = conn
        storage._close_conn.return_value = None

        mgr = OperationalModeManager(storage=storage)
        ctx1 = mgr.detect_context()
        assert ctx1 == OperationalContext.BACKTEST_ONLY

        # Estrategia promovida a SHADOW
        conn.execute("UPDATE sys_strategies SET mode='SHADOW' WHERE class_id='A'")
        conn.commit()

        ctx2 = mgr.detect_context()
        assert ctx2 == OperationalContext.SHADOW_ACTIVE

        # Transición debe estar en audit_logs
        rows = conn.execute("SELECT event_type, payload FROM sys_audit_logs").fetchall()
        assert len(rows) >= 1
        assert "MODE_TRANSITION" in rows[0][0]

    def test_get_current_context_before_detect_raises_or_returns_default(self):
        """current_context antes de la primera detección retorna un valor por defecto."""
        mgr = OperationalModeManager(storage=_make_storage([]))
        # No debe lanzar excepción — retorna default
        ctx = mgr.current_context
        assert ctx in list(OperationalContext)
