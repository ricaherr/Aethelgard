"""
Tests TDD: BacktestOrchestrator._is_on_cooldown() debe respetar el cooldown
adaptativo de OperationalModeManager cuando se inyecta como dependencia.

P1 — Sprint fix: tier-2 cooldown no era adaptativo.

RED state: falla porque:
  1. BacktestOrchestrator.__init__ no acepta `mode_manager`.
  2. _is_on_cooldown() usa self._cfg["cooldown_hours"] (24h fijo), ignora mode_manager.
"""
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from core_brain.backtest_orchestrator import BacktestOrchestrator
from core_brain.operational_mode_manager import OperationalContext, OperationalModeManager


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mode_manager_mock(cooldown_h: float) -> MagicMock:
    mode_manager = MagicMock(spec=OperationalModeManager)
    mode_manager.current_context = OperationalContext.BACKTEST_ONLY
    mode_manager.get_component_frequencies.return_value = {"backtest_cooldown_h": cooldown_h}
    return mode_manager


def _make_orchestrator(mode_manager=None) -> BacktestOrchestrator:
    storage = MagicMock()
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    storage._get_conn.return_value = conn
    # DB always returns cooldown_hours=24 — mode_manager must override this
    cursor.fetchone.return_value = (json.dumps({"cooldown_hours": 24}),)

    kwargs = dict(
        storage=storage,
        data_provider_manager=MagicMock(),
        scenario_backtester=MagicMock(),
    )
    if mode_manager is not None:
        kwargs["mode_manager"] = mode_manager
    return BacktestOrchestrator(**kwargs)


def _strategy_backtested_hours_ago(hours_ago: float) -> dict:
    ts = (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()
    return {"last_backtest_at": ts, "updated_at": ts, "mode": "BACKTEST"}


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestAdaptiveCooldown:
    def test_aggressive_mode_not_on_cooldown_after_2h(self):
        """AGGRESSIVE (cooldown=1h): backtested 2h ago → NOT on cooldown."""
        orc = _make_orchestrator(mode_manager=_make_mode_manager_mock(cooldown_h=1.0))
        strategy = _strategy_backtested_hours_ago(2.0)
        assert not orc._is_on_cooldown(strategy), (
            "Con mode_manager cooldown=1h y last_backtest=2h ago, NO debe bloquear"
        )

    def test_aggressive_mode_on_cooldown_under_1h(self):
        """AGGRESSIVE (cooldown=1h): backtested 30min ago → on cooldown."""
        orc = _make_orchestrator(mode_manager=_make_mode_manager_mock(cooldown_h=1.0))
        strategy = _strategy_backtested_hours_ago(0.5)
        assert orc._is_on_cooldown(strategy)

    def test_moderate_mode_uses_12h_cooldown(self):
        """MODERATE (cooldown=12h): backtested 2h ago → on cooldown."""
        orc = _make_orchestrator(mode_manager=_make_mode_manager_mock(cooldown_h=12.0))
        strategy = _strategy_backtested_hours_ago(2.0)
        assert orc._is_on_cooldown(strategy)

    def test_moderate_mode_not_on_cooldown_after_13h(self):
        """MODERATE (cooldown=12h): backtested 13h ago → NOT on cooldown."""
        orc = _make_orchestrator(mode_manager=_make_mode_manager_mock(cooldown_h=12.0))
        strategy = _strategy_backtested_hours_ago(13.0)
        assert not orc._is_on_cooldown(strategy)

    def test_fallback_to_24h_without_mode_manager(self):
        """Sin mode_manager, cooldown_hours=24h de config. Backtested 2h ago → ON cooldown."""
        orc = _make_orchestrator(mode_manager=None)
        strategy = _strategy_backtested_hours_ago(2.0)
        assert orc._is_on_cooldown(strategy), (
            "Sin mode_manager, debe usar 24h de config y 2h < 24h → cooldown activo"
        )

    def test_mode_manager_stored_as_attribute(self):
        """El mode_manager inyectado debe estar accesible como atributo."""
        mm = _make_mode_manager_mock(cooldown_h=1.0)
        orc = _make_orchestrator(mode_manager=mm)
        assert orc.mode_manager is mm
