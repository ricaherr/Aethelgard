"""
Tests TDD: BacktestOrchestrator no debe dejar conexiones SQLite abiertas.

Bug: Los siguientes métodos abren conn = storage._get_conn() sin finally:storage._close_conn(conn):
  - _execute_backtest   (line ~267)
  - _update_strategy_scores (line ~1144)
  - _load_backtest_strategies (line ~1352)
  - _load_strategy            (line ~1374)

Consecuencia: Si ocurre una excepción, la conexión queda con una transacción
sin commit, bloqueando SQLite para todos los demás hilos.

Fix: Envolver cada bloque con try/finally: storage._close_conn(conn).

RED state: falla porque los métodos no llaman _close_conn en el path de excepción.
"""
import asyncio
import json
import pytest
from unittest.mock import MagicMock, patch, call


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_minimal_orchestrator():
    """Crea BacktestOrchestrator via __new__ con storage mockeado."""
    from core_brain.backtest_orchestrator import BacktestOrchestrator

    orc = object.__new__(BacktestOrchestrator)
    orc._cfg = {
        "cooldown_hours": 24,
        "default_timeframe": "H1",
        "confidence_k": 20,
        "score_weights": {"w_live": 0.50, "w_shadow": 0.30, "w_backtest": 0.20},
        "promotion_min_score": 0.75,
    }
    orc._tf_rr_index = {}
    orc.mode_manager = None
    orc.shadow_manager = None

    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value = cursor
    conn.execute.return_value = MagicMock(fetchone=MagicMock(return_value=[0]))

    storage = MagicMock()
    storage._get_conn.return_value = conn
    storage._close_conn = MagicMock()

    orc.storage = storage
    return orc, storage, conn


def _strategy(score_backtest=0.0):
    return {
        "class_id": "STRAT_TEST",
        "required_timeframes": ["H1"],
        "required_regime": None,
        "market_whitelist": ["EURUSD"],
        "execution_params": "{}",
        "parameter_overrides": "{}",
        "score_backtest": score_backtest,
        "score_shadow": 0.0,
        "score_live": 0.0,
    }


# ── C1: _execute_backtest ──────────────────────────────────────────────────────

class TestExecuteBacktestConnLeak:
    def test_close_conn_called_on_success(self):
        """_close_conn debe llamarse incluso cuando _execute_backtest tiene éxito."""
        orc, storage, conn = _make_minimal_orchestrator()
        strategy = _strategy()

        orc._get_symbols_for_backtest = MagicMock(return_value=["EURUSD"])
        orc._get_timeframes_for_backtest = MagicMock(return_value=["H1"])
        orc._passes_regime_prefilter = MagicMock(return_value=True)
        orc._build_strategy_for_backtest = MagicMock(return_value=MagicMock())
        orc._extract_parameter_overrides = MagicMock(return_value={})
        orc._build_scenario_slices = MagicMock(return_value=[MagicMock()])

        matrix = MagicMock()
        matrix.overall_score = 0.5
        matrix.total_trades = 10
        orc.backtester = MagicMock()
        orc.backtester.MIN_REGIME_SCORE = 0.75
        orc.backtester.run_scenario_backtest = MagicMock(return_value=matrix)

        orc._write_pair_affinity = MagicMock()
        orc._write_pair_coverage = MagicMock()
        orc._update_strategy_scores = MagicMock()
        orc._detect_overfitting_risk = MagicMock(return_value=False)
        orc._promote_to_shadow = MagicMock()

        asyncio.run(orc._execute_backtest(strategy))

        storage._close_conn.assert_called_once_with(conn)

    def test_close_conn_called_on_exception(self):
        """_close_conn debe llamarse incluso cuando run_scenario_backtest lanza excepción."""
        orc, storage, conn = _make_minimal_orchestrator()
        strategy = _strategy()

        orc._get_symbols_for_backtest = MagicMock(return_value=["EURUSD"])
        orc._get_timeframes_for_backtest = MagicMock(return_value=["H1"])
        orc._passes_regime_prefilter = MagicMock(return_value=True)
        orc._build_strategy_for_backtest = MagicMock(return_value=MagicMock())
        orc._extract_parameter_overrides = MagicMock(return_value={})
        orc._build_scenario_slices = MagicMock(return_value=[MagicMock()])

        orc.backtester = MagicMock()
        orc.backtester.MIN_REGIME_SCORE = 0.75
        orc.backtester.run_scenario_backtest = MagicMock(
            side_effect=Exception("simulated error")
        )

        orc._write_pair_affinity = MagicMock()
        orc._write_pair_coverage = MagicMock()
        orc._update_strategy_scores = MagicMock()
        orc._detect_overfitting_risk = MagicMock(return_value=False)
        orc._promote_to_shadow = MagicMock()

        # Puede lanzar o no — lo importante es que _close_conn se llame
        try:
            asyncio.run(orc._execute_backtest(strategy))
        except Exception:
            pass

        storage._close_conn.assert_called_once_with(conn), (
            "_close_conn debe llamarse en el path de excepción de _execute_backtest"
        )


# ── C2: _update_strategy_scores ───────────────────────────────────────────────

class TestUpdateStrategyScoresConnLeak:
    def test_close_conn_called_on_success(self):
        """_close_conn debe llamarse tras actualizar scores correctamente."""
        orc, storage, conn = _make_minimal_orchestrator()
        strategy = _strategy()

        conn.cursor.return_value.execute = MagicMock()
        conn.commit = MagicMock()

        orc._update_strategy_scores("STRAT_TEST", 0.70, strategy)

        storage._close_conn.assert_called_once_with(conn)

    def test_close_conn_called_on_db_exception(self):
        """_close_conn debe llamarse aunque cursor.execute falle."""
        orc, storage, conn = _make_minimal_orchestrator()
        strategy = _strategy()

        conn.cursor.return_value.execute = MagicMock(
            side_effect=Exception("database is locked")
        )

        orc._update_strategy_scores("STRAT_TEST", 0.70, strategy)

        storage._close_conn.assert_called_once_with(conn), (
            "_close_conn debe llamarse en el path de excepción de _update_strategy_scores"
        )


# ── C3: _load_backtest_strategies ─────────────────────────────────────────────

class TestLoadBacktestStrategiesConnLeak:
    def test_close_conn_called_on_success(self):
        """_close_conn debe llamarse tras cargar estrategias BACKTEST."""
        orc, storage, conn = _make_minimal_orchestrator()

        cursor = conn.cursor.return_value
        cursor.description = [
            ("class_id",), ("mnemonic",), ("market_whitelist",), ("affinity_scores",),
            ("execution_params",), ("mode",), ("score_backtest",), ("score_shadow",),
            ("score_live",), ("score",), ("updated_at",), ("last_backtest_at",),
            ("required_timeframes",), ("required_regime",),
        ]
        cursor.fetchall.return_value = []

        orc._load_backtest_strategies()

        storage._close_conn.assert_called_once_with(conn)

    def test_close_conn_called_on_exception(self):
        """_close_conn debe llamarse aunque la query falle."""
        orc, storage, conn = _make_minimal_orchestrator()

        conn.cursor.return_value.execute = MagicMock(
            side_effect=Exception("database is locked")
        )

        result = orc._load_backtest_strategies()

        assert result == []
        storage._close_conn.assert_called_once_with(conn), (
            "_close_conn debe llamarse en el path de excepción de _load_backtest_strategies"
        )


# ── C4: _load_strategy ────────────────────────────────────────────────────────

class TestLoadStrategyConnLeak:
    def test_close_conn_called_on_success(self):
        """_close_conn debe llamarse tras cargar una estrategia por class_id."""
        orc, storage, conn = _make_minimal_orchestrator()

        cursor = conn.cursor.return_value
        cursor.description = [
            ("class_id",), ("mnemonic",), ("market_whitelist",), ("affinity_scores",),
            ("execution_params",), ("mode",), ("score_backtest",), ("score_shadow",),
            ("score_live",), ("score",), ("updated_at",), ("last_backtest_at",),
            ("required_timeframes",), ("required_regime",),
        ]
        cursor.fetchone.return_value = None

        orc._load_strategy("STRAT_TEST")

        storage._close_conn.assert_called_once_with(conn)

    def test_close_conn_called_on_exception(self):
        """_close_conn debe llamarse aunque la query falle."""
        orc, storage, conn = _make_minimal_orchestrator()

        conn.cursor.return_value.execute = MagicMock(
            side_effect=Exception("database is locked")
        )

        result = orc._load_strategy("STRAT_TEST")

        assert result is None
        storage._close_conn.assert_called_once_with(conn), (
            "_close_conn debe llamarse en el path de excepción de _load_strategy"
        )
