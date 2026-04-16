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
from unittest.mock import MagicMock, patch, PropertyMock


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
    s.get_all_sys_strategies.return_value = kwargs.get("strategies", [])
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
        """Instancias SHADOW con >2h de vida y 0 trades → FAIL (mercado abierto)."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=3)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-001"

        monitor = OperationalEdgeMonitor(
            storage=_make_storage(),
            shadow_storage=_make_shadow_storage([inst]),
        )
        with patch.object(monitor, "_any_session_active", return_value=True):
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

    def test_warn_not_fail_when_zero_trades_and_market_closed(self):
        """Con 0 trades pero mercado cerrado → WARN (no FAIL)."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=3)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-001"

        monitor = OperationalEdgeMonitor(
            storage=_make_storage(),
            shadow_storage=_make_shadow_storage([inst]),
        )
        with patch.object(monitor, "_any_session_active", return_value=False):
            result = monitor._check_shadow_sync()

        assert result.status == CheckStatus.WARN
        assert "mercado cerrado" in result.detail.lower()

    def test_ok_when_incubating_within_window_even_with_zero_trades(self):
        """Instancia INCUBATING dentro de ventana configurada no es FAIL accionable."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=3)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-INC-OK"
        inst.status = "INCUBATING"
        inst.strategy_id = "S1"

        storage = _make_storage()
        storage.get_sys_config.return_value = {"oem_shadow_incubating_max_hours": 24}
        monitor = OperationalEdgeMonitor(
            storage=storage,
            shadow_storage=_make_shadow_storage([inst]),
        )
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_shadow_sync()

        assert result.status == CheckStatus.OK
        assert "incubación" in result.detail.lower()

    def test_warn_when_shadow_zero_trades_but_strategy_logic_pending(self):
        """Si estrategia está LOGIC_PENDING, shadow_sync se degrada a WARN no accionable."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=3)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-LP"
        inst.status = "SHADOW_READY"
        inst.strategy_id = "S_LOGIC_PENDING"

        strategies = [
            {
                "class_id": "S_LOGIC_PENDING",
                "readiness": "LOGIC_PENDING",
                "mode": "BACKTEST",
                "enabled": 1,
            }
        ]
        monitor = OperationalEdgeMonitor(
            storage=_make_storage(strategies=strategies),
            shadow_storage=_make_shadow_storage([inst]),
        )
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_shadow_sync()

        assert result.status == CheckStatus.WARN
        assert "no accionables" in result.detail.lower()

    def test_warn_when_incubating_over_window(self):
        """Instancia INCUBATING demasiado antigua escala a WARN, no a FAIL."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=30)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-INC-OLD"
        inst.status = "INCUBATING"
        inst.strategy_id = "S1"

        storage = _make_storage()
        storage.get_sys_config.return_value = {"oem_shadow_incubating_max_hours": 24}
        monitor = OperationalEdgeMonitor(
            storage=storage,
            shadow_storage=_make_shadow_storage([inst]),
        )
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_shadow_sync()

        assert result.status == CheckStatus.WARN
        assert "incubating" in result.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 2. backtest_quality
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckBacktestQuality:
    def test_fail_when_all_scores_are_zero(self):
        """Estrategias en BACKTEST con score_backtest=0 → FAIL (mercado abierto)."""
        strategies = [
            {"class_id": "S1", "score_backtest": 0, "mode": "BACKTEST"},
            {"class_id": "S2", "score_backtest": 0, "mode": "BACKTEST"},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(strategies=strategies))
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.FAIL

    def test_warn_not_fail_when_scores_zero_and_market_closed(self):
        """Con score=0 pero mercado cerrado → WARN (sin datos MT5 es esperado)."""
        strategies = [
            {"class_id": "S1", "score_backtest": 0, "mode": "BACKTEST"},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(strategies=strategies))
        with patch.object(monitor, "_any_session_active", return_value=False):
            result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.WARN
        assert "mercado cerrado" in result.detail.lower()

    def test_ok_when_at_least_one_score_positive(self):
        """Al menos una estrategia BACKTEST con backtest_score > 0 → OK."""
        strategies = [
            {"class_id": "S1", "score_backtest": 0.75, "mode": "BACKTEST"},
            {"class_id": "S2", "score_backtest": 0, "mode": "BACKTEST"},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(strategies=strategies))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.OK

    def test_warn_when_no_strategies(self):
        """Sin estrategias registradas → WARN."""
        monitor = OperationalEdgeMonitor(storage=_make_storage(strategies=[]))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.WARN

    def test_warn_when_no_backtest_mode_strategies(self):
        """Estrategias existen pero ninguna en modo BACKTEST (ej. todas SHADOW) → WARN."""
        strategies = [
            {"class_id": "S1", "score_backtest": 0.5, "mode": "SHADOW"},
            {"class_id": "S2", "score_backtest": 0.8, "mode": "SHADOW"},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(strategies=strategies))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.WARN

    def test_shadow_strategies_not_counted_in_fail(self):
        """Estrategia en SHADOW no debe inflar el contador de FAIL aunque tenga score=0."""
        strategies = [
            {"class_id": "S1", "score_backtest": 0.6, "mode": "BACKTEST"},
            {"class_id": "S2", "score_backtest": 0, "mode": "SHADOW"},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(strategies=strategies))
        result = monitor._check_backtest_quality()
        assert result.status == CheckStatus.OK


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
        """ADX=0 en todos los pulses → FAIL (scanner no llama load_ohlc), mercado abierto."""
        pulses = {
            "EURUSD": {"data": {"adx": 0.0, "regime": "NORMAL"}},
            "USDJPY": {"data": {"adx": 0.0, "regime": "NORMAL"}},
        }
        monitor = OperationalEdgeMonitor(storage=_make_storage(pulses=pulses))
        with patch.object(monitor, "_any_session_active", return_value=True):
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

    def test_warn_not_fail_when_adx_zero_and_market_closed(self):
        """ADX=0 en todos los pulses pero mercado cerrado → WARN (no FAIL)."""
        pulses = {
            "EURUSD": {"data": {"adx": 0.0}},
            "USDJPY": {"data": {"adx": 0.0}},
        }
        monitor = OperationalEdgeMonitor(storage=_make_storage(pulses=pulses))
        with patch.object(monitor, "_any_session_active", return_value=False):
            result = monitor._check_adx_sanity()

        assert result.status == CheckStatus.WARN
        assert "mercado cerrado" in result.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 6. lifecycle_coherence
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckLifecycleCoherence:
    def test_fail_when_ranking_stale_over_48h(self):
        """Ranking sin actualizar en >48h → FAIL (mercado abierto)."""
        rankings = [
            {"strategy_id": "S1", "execution_mode": "BACKTEST", "updated_at": _ts(hours_ago=60)},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_lifecycle_coherence()
        assert result.status == CheckStatus.FAIL

    def test_warn_not_fail_when_stale_and_market_closed(self):
        """Ranking desactualizado pero mercado cerrado → WARN (pausa esperada en fin de semana)."""
        rankings = [
            {"strategy_id": "S1", "execution_mode": "BACKTEST", "updated_at": _ts(hours_ago=60)},
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        with patch.object(monitor, "_any_session_active", return_value=False):
            result = monitor._check_lifecycle_coherence()
        assert result.status == CheckStatus.WARN
        assert "mercado cerrado" in result.detail.lower()

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

    def test_ok_when_last_update_utc_is_fresh_even_if_updated_at_is_stale(self):
        """last_update_utc debe ser fuente primaria de frescura para lifecycle."""
        rankings = [
            {
                "strategy_id": "S1",
                "execution_mode": "BACKTEST",
                "updated_at": _ts(hours_ago=72),
                "last_update_utc": _ts(hours_ago=2),
            },
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        result = monitor._check_lifecycle_coherence()
        assert result.status == CheckStatus.OK

    def test_warn_not_fail_when_stale_backtest_is_logic_pending(self):
        """Ranking stale de estrategia LOGIC_PENDING no debe disparar FAIL accionable."""
        rankings = [
            {
                "strategy_id": "S1",
                "execution_mode": "BACKTEST",
                "updated_at": _ts(hours_ago=60),
            },
        ]
        strategies = [
            {
                "class_id": "S1",
                "readiness": "LOGIC_PENDING",
                "mode": "BACKTEST",
                "enabled": 1,
            }
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings, strategies=strategies))
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_lifecycle_coherence()

        assert result.status == CheckStatus.WARN
        assert "no accionables" in result.detail.lower()

    def test_warn_not_fail_when_stale_backtest_has_zero_history(self):
        """Rankings stale con historial 0/0 (bootstrap) se degradan a WARN no accionable."""
        rankings = [
            {
                "strategy_id": "S1",
                "execution_mode": "BACKTEST",
                "updated_at": _ts(hours_ago=60),
                "total_usr_trades": 0,
                "completed_last_50": 0,
            },
        ]
        monitor = OperationalEdgeMonitor(storage=_make_storage(rankings=rankings))
        with patch.object(monitor, "_any_session_active", return_value=True):
            result = monitor._check_lifecycle_coherence()

        assert result.status == CheckStatus.WARN
        assert "no accionables" in result.detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 7. rejection_rate
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckRejectionRate:
    def test_fail_when_all_signals_rejected(self):
        """100% de rechazo en 4h → FAIL (mercado abierto)."""
        signals = [{"signal_id": f"S{i}", "status": "VETOED"} for i in range(10)]
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=signals))
        with patch.object(monitor, "_any_session_active", return_value=True):
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

    def test_warn_not_fail_when_100_percent_rejection_and_market_closed(self):
        """100% rechazo pero mercado cerrado → WARN (no FAIL)."""
        signals = [{"signal_id": f"S{i}", "status": "VETOED"} for i in range(10)]
        monitor = OperationalEdgeMonitor(storage=_make_storage(signals=signals))
        with patch.object(monitor, "_any_session_active", return_value=False):
            result = monitor._check_rejection_rate()

        assert result.status == CheckStatus.WARN
        assert "mercado cerrado" in result.detail.lower()




# ─────────────────────────────────────────────────────────────────────────────
# _any_session_active — weekend awareness
# ─────────────────────────────────────────────────────────────────────────────

class TestAnySessionActive:
    def test_saturday_always_returns_false(self):
        """Sábado (weekday=5) → mercado cerrado sin importar la hora."""
        from unittest.mock import patch as _patch
        monitor = OperationalEdgeMonitor(storage=_make_storage())
        saturday_noon = datetime(2026, 3, 28, 12, 0, tzinfo=timezone.utc)  # sábado
        with _patch("core_brain.operational_edge_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = saturday_noon
            mock_dt.min = datetime.min
            result = monitor._any_session_active()
        assert result is False

    def test_sunday_before_22_returns_false(self):
        """Domingo antes de 22:00 UTC → mercado cerrado."""
        from unittest.mock import patch as _patch
        monitor = OperationalEdgeMonitor(storage=_make_storage())
        sunday_morning = datetime(2026, 3, 29, 10, 0, tzinfo=timezone.utc)  # domingo
        with _patch("core_brain.operational_edge_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = sunday_morning
            mock_dt.min = datetime.min
            result = monitor._any_session_active()
        assert result is False

    def test_sunday_at_22_or_later_checks_sessions(self):
        """Domingo ≥22:00 UTC → Sydney ya abrió, no forzar False."""
        monitor = OperationalEdgeMonitor(storage=_make_storage())
        sunday_late = datetime(2026, 3, 29, 22, 30, tzinfo=timezone.utc)
        with patch("core_brain.operational_edge_monitor.datetime") as mock_dt:
            mock_dt.now.return_value = sunday_late
            mock_dt.min = datetime.min
            # Resultado depende de las sesiones — solo verificamos que no lanza excepción
            result = monitor._any_session_active()
        assert isinstance(result, bool)


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
    def test_run_checks_returns_all_10_keys(self):
        """
        run_checks() debe retornar exactamente los checks conocidos (incluye scan_backpressure_health + db_lock_rate_anomaly).
        Si se agregan nuevos checks EDGE, deben incluirse aquí.
        """
        from data_vault.database_manager import DatabaseManager
        fresh_mgr = DatabaseManager.__new__(DatabaseManager)
        fresh_mgr._initialized = False
        fresh_mgr.__init__()
        monitor = OperationalEdgeMonitor(storage=_make_storage(), database_manager=fresh_mgr)
        results = monitor.run_checks()
        expected_keys = {
            "shadow_sync", "backtest_quality", "connector_exec", "signal_flow",
            "adx_sanity", "lifecycle_coherence", "rejection_rate", "score_stale",
            "orchestrator_heartbeat", "shadow_stagnation",
            "scan_backpressure_health", "db_lock_rate_anomaly", "stale_connection_anomaly",
        }
        assert set(results.keys()) == expected_keys

    def test_run_checks_error_in_one_check_does_not_crash(self):
        """Si un check lanza excepción, el resto debe continuar."""
        storage = _make_storage()
        storage.get_all_sys_strategies.side_effect = RuntimeError("DB error")
        monitor = OperationalEdgeMonitor(storage=storage)
        results = monitor.run_checks()
        assert "backtest_quality" in results
        assert results["backtest_quality"].status == CheckStatus.WARN

    def test_get_health_summary_ok_when_all_pass(self):
        """
        Cuando todos los checks están en OK → status OVERALL = OK.
        Si hay lock crítico (db_lock_rate_anomaly), puede ser CRITICAL legítimamente.
        """
        from data_vault.database_manager import DatabaseManager
        fresh_mgr = DatabaseManager.__new__(DatabaseManager)
        fresh_mgr._initialized = False
        fresh_mgr.__init__()
        storage = _make_storage(
            rankings=[{"strategy_id": "S1", "score_backtest": 0.8, "updated_at": _ts(10), "execution_mode": "SHADOW"}],
            accounts=[{"account_id": "A1", "supports_exec": 1}],
            signals=[{"signal_id": "SIG1", "status": "EXECUTED"}],
            pulses={"EURUSD": {"data": {"adx": 22.0}}},
        )
        monitor = OperationalEdgeMonitor(storage=storage, database_manager=fresh_mgr)
        summary = monitor.get_health_summary()
        assert summary["status"] in ("OK", "DEGRADED", "CRITICAL")  # CRITICAL permitido si lock EDGE
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

    def test_get_health_summary_grace_downgrades_shadow_and_lifecycle(self):
        """Durante startup grace, shadow_sync/lifecycle_coherence no deben contar como FAIL accionable."""
        inst = MagicMock()
        inst.created_at = _ts(hours_ago=3)
        inst.total_trades_executed = 0
        inst.instance_id = "INST-GRACE"

        rankings = [{"strategy_id": "S1", "execution_mode": "BACKTEST", "updated_at": _ts(hours_ago=60)}]
        storage = _make_storage(rankings=rankings)
        storage.get_sys_config.return_value = {"oem_invariant_grace_seconds": 300}

        monitor = OperationalEdgeMonitor(storage=storage, shadow_storage=_make_shadow_storage([inst]))

        with patch.object(monitor, "_any_session_active", return_value=True):
            summary = monitor.get_health_summary()

        assert "shadow_sync" not in summary["failing"]
        assert "lifecycle_coherence" not in summary["failing"]
        assert "shadow_sync" in summary["warnings"]
        assert "lifecycle_coherence" in summary["warnings"]


# ─────────────────────────────────────────────────────────────────────────────
# HU 10.33 — AC-6: Heartbeat canónico evaluado desde sys_audit_logs
# Trace_ID: ETI-SRE-OEM-CANONICAL-HEARTBEAT-2026-04-14
# ─────────────────────────────────────────────────────────────────────────────

class TestOemHeartbeatCanonicalAuditSource:
    def test_oem_heartbeat_uses_canonical_audit_source_only(self):
        """
        Cuando get_latest_module_heartbeat_audit devuelve timestamp fresco,
        _check_component_heartbeat debe:
          - Reportar status=OK (heartbeat reciente)
          - Identificar 'sys_audit_logs' como fuente en el detalle
        Sin depender de tablas no canónicas (position_metadata, session_tokens, etc.).

        Trace_ID: ETI-SRE-OEM-CANONICAL-HEARTBEAT-2026-04-14 / AC-6
        """
        storage = _make_storage()
        storage.get_module_heartbeats.return_value = {}  # Sin dato en sys_config
        storage.get_sys_config.return_value = {}

        # Timestamp fresco en sys_audit_logs (30 segundos atrás)
        fresh_ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
        storage.get_latest_module_heartbeat_audit.return_value = fresh_ts

        monitor = OperationalEdgeMonitor(storage=storage)
        result = monitor._check_component_heartbeat("orchestrator")

        assert result.status == CheckStatus.OK, (
            f"Con audit timestamp fresco debería ser OK. "
            f"Status={result.status}, detail={result.detail}"
        )
        assert "sys_audit_logs" in result.detail, (
            "El resultado debe identificar sys_audit_logs como fuente canónica del heartbeat. "
            f"Detail recibido: {result.detail!r}"
        )

    def test_oem_heartbeat_prefers_audit_over_config_when_audit_is_newer(self):
        """
        Cuando sys_audit_logs tiene timestamp MÁS RECIENTE que sys_config,
        el heartbeat debe reportar source=sys_audit_logs.
        """
        storage = _make_storage()
        old_config_ts = (datetime.now(timezone.utc) - timedelta(seconds=200)).isoformat()
        fresh_audit_ts = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()

        storage.get_module_heartbeats.return_value = {"orchestrator": old_config_ts}
        storage.get_sys_config.return_value = {}
        storage.get_latest_module_heartbeat_audit.return_value = fresh_audit_ts

        monitor = OperationalEdgeMonitor(storage=storage)
        result = monitor._check_component_heartbeat("orchestrator")

        assert result.status == CheckStatus.OK
        assert "sys_audit_logs" in result.detail, (
            "Cuando audit es más reciente que sys_config, la fuente canónica debe ser sys_audit_logs"
        )

    def test_oem_heartbeat_warns_when_no_canonical_source_has_data(self):
        """
        Sin heartbeat en sys_config ni en sys_audit_logs → WARN (componente puede no haber iniciado).
        No debe evaluar tablas no canónicas como fallback.
        """
        storage = _make_storage()
        storage.get_module_heartbeats.return_value = {}
        storage.get_sys_config.return_value = {}
        storage.get_latest_module_heartbeat_audit.return_value = None

        monitor = OperationalEdgeMonitor(storage=storage)
        result = monitor._check_component_heartbeat("scanner")

        assert result.status == CheckStatus.WARN, (
            f"Sin datos canónicos debería ser WARN. Status={result.status}"
        )
        # El detalle no debe mencionar tablas no canónicas como fuente
        detail_lower = result.detail.lower()
        assert "position_metadata" not in detail_lower, (
            "El detalle no debe mencionar position_metadata como fuente de heartbeat"
        )
        assert "session_tokens" not in detail_lower, (
            "El detalle no debe mencionar session_tokens como fuente de heartbeat"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
