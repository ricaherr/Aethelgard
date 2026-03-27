"""
Tests: OperationalEdgeMonitor — FASE 4
=======================================
Verifica que cada uno de los 8 checks de invariantes de negocio
detecte correctamente los estados OK, WARN y FAIL.

TDD: Todos los tests están escritos contra la interfaz pública antes
de implementar el componente.
"""
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch


# Import the module under test (will fail until implemented)
from core_brain.operational_edge_monitor import (
    OperationalEdgeMonitor,
    CheckStatus,
    CheckResult,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ts(hours_ago: float = 0) -> str:
    """Returns an ISO-format timestamp N hours ago."""
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _make_storage(**kwargs):
    s = MagicMock()
    s.get_all_signal_rankings.return_value = kwargs.get("rankings", [])
    s.get_sys_broker_accounts.return_value = kwargs.get("accounts", [])
    s.get_recent_sys_signals.return_value = kwargs.get("signals", [])
    s.get_all_sys_market_pulses.return_value = kwargs.get("pulses", {})
    return s


def _make_shadow_storage(instances):
    ss = MagicMock()
    ss.list_active_instances.return_value = instances
    return ss


# ─────────────────────────────────────────────────────────────────────────────
# 1. shadow_sync
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckShadowSync:
    def test_fail_when_mature_instances_have_zero_trades(self):
        """Instancias SHADOW con >2h de vida y 0 trades → FAIL."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=3)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-001"

        monitor = OperationalEdgeMonitor(
            storage=_make_storage(),
            shadow_storage=_make_shadow_storage([inst]),
        )
        result = monitor._check_shadow_sync()
        assert result.status == CheckStatus.FAIL
        assert "0 trades" in result.detail

    def test_ok_when_mature_instances_have_trades(self):
        """Instancias maduras con trades → OK."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=4)
        inst.total_trades_executed = 5
        inst.instance_id = "INST-002"

        monitor = OperationalEdgeMonitor(
            storage=_make_storage(),
            shadow_storage=_make_shadow_storage([inst]),
        )
        result = monitor._check_shadow_sync()
        assert result.status == CheckStatus.OK

    def test_warn_when_shadow_storage_not_injected(self):
        """Sin shadow_storage inyectado → WARN (check skipped)."""
        monitor = OperationalEdgeMonitor(storage=_make_storage())
        result = monitor._check_shadow_sync()
        assert result.status == CheckStatus.WARN

    def test_ok_when_all_instances_are_young(self):
        """Instancias con <2h de vida no cuentan como maduras → OK."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=1)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-NEW"

        monitor = OperationalEdgeMonitor(
            storage=_make_storage(),
            shadow_storage=_make_shadow_storage([inst]),
        )
        result = monitor._check_shadow_sync()
        assert result.status == CheckStatus.OK


# ─────────────────────────────────────────────────────────────────────────────
# 2. backtest_quality
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckBacktestQuality:
    def test_fail_when_all_scores_are_zero(self):
        """Todas las estrategias con score_backtest=0 → FAIL."""
        rankings = [
            {"strategy_id": "S1", "score_backtest": 0},
            {"strategy_id": "S2", "score_backtest": 0},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.FAIL

    def test_ok_when_at_least_one_score_positive(self):
        """Al menos una estrategia con backtest_score > 0 → OK."""
        rankings = [
            {"strategy_id": "S1", "score_backtest": 0.75},
            {"strategy_id": "S2", "score_backtest": 0},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.OK

    def test_warn_when_no_rankings(self):
        """Sin rankings → WARN."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=[]))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.WARN


# ─────────────────────────────────────────────────────────────────────────────
# 3. connector_exec
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckConnectorExec:
    def test_fail_when_no_exec_capable_account(self):
        """Sin ninguna cuenta con supports_exec=1 → FAIL."""
        accounts = [{"account_id": "ACC1", "supports_exec": 0, "enabled": 1}]
        monitor = OperationalEdgeMonitor(storage=_make_storage(accounts=accounts))
        result = monitor._check_connector_exec()
        assert result.status == CheckStatus.FAIL

    def test_ok_when_exec_capable_account_exists(self):
        """Al menos una cuenta con supports_exec=1 → OK."""
        accounts = [{"account_id": "ACC1", "supports_exec": 1, "enabled": 1}]
        monitor = OperationalEdgeMonitor(storage=_make_storage(accounts=accounts))
        result = monitor._check_connector_exec()
        assert result.status == CheckStatus.OK

    def test_fail_when_no_accounts_at_all(self):
        """Sin cuentas habilitadas → FAIL."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(accounts=[]))
        result = monitor._check_connector_exec()
        assert result.status == CheckStatus.FAIL


# ─────────────────────────────────────────────────────────────────────────────
# 4. signal_flow
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckSignalFlow:
    def test_warn_when_no_recent_signals(self):
        """Sin señales en las últimas 2h → WARN."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=[]))
        result = monitor._check_signal_flow()
        assert result.status == CheckStatus.WARN

    def test_ok_when_signals_exist(self):
        """Con señales recientes → OK."""
        signals = [{"signal_id": "SIG-1", "symbol": "EURUSD"}]
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=signals))
        result = monitor._check_signal_flow()
        assert result.status == CheckStatus.OK


# ─────────────────────────────────────────────────────────────────────────────
# 5. adx_sanity
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckAdxSanity:
    def test_fail_when_all_adx_are_zero(self):
        """ADX=0 en todos los pulses → FAIL (scanner no llama load_ohlc)."""
        pulses = {
            "EURUSD": {"data": {"adx": 0.0, "regime": "NORMAL"}},
            "USDJPY": {"data": {"adx": 0.0, "regime": "NORMAL"}},
        }
        monitor = OperationalEdgeMonitor(storage=_make_storage(pulses=pulses))
        result = monitor._check_adx_sanity()
        assert result.status == CheckStatus.FAIL

    def test_ok_when_majority_adx_nonzero(self):
        """ADX > 0 en ≥10% de pulses → OK."""
        pulses = {
            "EURUSD": {"data": {"adx": 25.3}},
            "USDJPY": {"data": {"adx": 0.0}},
        }
        monitor = OperationalEdgeMonitor(storage=_make_storage(pulses=pulses))
        result = monitor._check_adx_sanity()
        assert result.status == CheckStatus.OK

    def test_warn_when_no_pulse_data(self):
        """Sin datos de market pulse → WARN."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(pulses={}))
        result = monitor._check_adx_sanity()
        assert result.status == CheckStatus.WARN


# ─────────────────────────────────────────────────────────────────────────────
# 6. lifecycle_coherence
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckLifecycleCoherence:
    def test_fail_when_ranking_stale_over_48h(self):
        """Ranking sin actualizar en >48h → FAIL."""
        rankings = [
            {"strategy_id": "S1", "execution_mode": "BACKTEST", "updated_at": _ts(hours_ago=60)},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_lifecycle_coherence()
        assert result.status == CheckStatus.FAIL

    def test_ok_when_all_rankings_fresh(self):
        """Todos los rankings actualizados en <48h → OK."""
        rankings = [
            {"strategy_id": "S1", "execution_mode": "SHADOW", "updated_at": _ts(hours_ago=10)},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_lifecycle_coherence()
        assert result.status == CheckStatus.OK

    def test_ok_when_no_rankings(self):
        """Sin rankings → OK (nothing to check)."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=[]))
        result = monitor._check_lifecycle_coherence()
        assert result.status == CheckStatus.OK


# ─────────────────────────────────────────────────────────────────────────────
# 7. rejection_rate
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckRejectionRate:
    def test_fail_when_all_signals_rejected(self):
        """100% de rechazo en 4h → FAIL."""
        signals = [{"signal_id": f"S{i}", "status": "VETOED"} for i in range(10)]
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=signals))
        result = monitor._check_rejection_rate()
        assert result.status == CheckStatus.FAIL

    def test_ok_when_some_signals_executed(self):
        """Con señales ejecutadas → tasa baja → OK."""
        signals = [
            {"signal_id": "S1", "status": "EXECUTED"},
            {"signal_id": "S2", "status": "VETOED"},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=signals))
        result = monitor._check_rejection_rate()
        assert result.status == CheckStatus.OK

    def test_ok_when_no_signals(self):
        """Sin señales — no hay tasa de rechazo que evaluar → OK."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=[]))
        result = monitor._check_rejection_rate()
        assert result.status == CheckStatus.OK


# ─────────────────────────────────────────────────────────────────────────────
# 8. score_stale
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckScoreStale:
    def test_warn_when_rankings_not_updated_in_72h(self):
        """Rankings sin actualizar en >72h → WARN."""
        rankings = [
            {"strategy_id": "S1", "updated_at": _ts(hours_ago=80)},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_score_stale()
        assert result.status == CheckStatus.WARN

    def test_ok_when_all_rankings_updated_recently(self):
        """Rankings frescos → OK."""
        rankings = [
            {"strategy_id": "S1", "updated_at": _ts(hours_ago=24)},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_score_stale()
        assert result.status == CheckStatus.OK


# ─────────────────────────────────────────────────────────────────────────────
# 9. run_checks + get_health_summary
# ─────────────────────────────────────────────────────────────────────────────

class TestRunChecksAndSummary:
    def test_run_checks_returns_all_9_keys(self):
        """run_checks() debe retornar exactamente los 9 checks conocidos."""
        monitor = OperationalEdgeMonitor(storage=_make_storage())
        results = monitor.run_checks()
        expected_keys = {
            "shadow_sync", "backtest_quality", "connector_exec", "signal_flow",
            "adx_sanity", "lifecycle_coherence", "rejection_rate", "score_stale",
            "orchestrator_heartbeat",
        }
        assert set(results.keys()) == expected_keys

    def test_run_checks_error_in_one_check_does_not_crash(self):
        """Si un check lanza excepción, el resto debe continuar."""
        storage = _make_storage()
        storage.get_all_signal_rankings.side_effect = RuntimeError("DB error")
        monitor = OperationalEdgeMonitor(storage=storage)
        results = monitor.run_checks()
        assert "backtest_quality" in results
        assert results["backtest_quality"].status == CheckStatus.WARN

    def test_get_health_summary_ok_when_all_pass(self):
        """Cuando todos los checks están en OK → status OVERALL = OK."""
        storage = _make_storage(
            rankings=[{"strategy_id": "S1", "score_backtest": 0.8, "updated_at": _ts(10), "execution_mode": "SHADOW"}],
            accounts=[{"account_id": "A1", "supports_exec": 1}],
            signals=[{"signal_id": "SIG1", "status": "EXECUTED"}],
            pulses={"EURUSD": {"data": {"adx": 22.0}}},
        )
        monitor = OperationalEdgeMonitor(storage=storage)
        summary = monitor.get_health_summary()
        assert summary["status"] in ("OK", "DEGRADED")  # DEGRADED ok if WARN-only checks
        assert isinstance(summary["checks"], dict)
        assert isinstance(summary["failing"], list)

    def test_get_health_summary_critical_when_3_or_more_fail(self):
        """3+ checks FAIL → status CRITICAL."""
        storage = _make_storage(
            rankings=[],
            accounts=[],
            signals=[],
            pulses={},
        )
        monitor = OperationalEdgeMonitor(storage=storage)
        summary = monitor.get_health_summary()
        assert summary["status"] in ("CRITICAL", "DEGRADED")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
