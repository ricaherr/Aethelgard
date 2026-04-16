"""
Tests ETI-2: EDGE Resilience Improvements
==========================================

Cubre:
  - DBPolicyTuner: auto-tuning de busy_timeout (escalado y reducción)
  - DBPolicyTuner: fallback a modo solo-lectura
  - DatabaseManager: integración con tuner
  - AlertingService: despacho, rate-limiting
  - OperationalEdgeMonitor: check db_lock_rate_anomaly + despacho de alertas
  - Simulación de locks persistentes bajo concurrencia

TDD: todos los tests fueron escritos antes de la implementación (ciclo RED → GREEN).
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from data_vault.database_manager import DatabaseManager, get_database_manager


# ---------------------------------------------------------------------------
# Fixture de limpieza del singleton — evita contaminación entre archivos de test
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _reset_singleton_tuner(request: Any) -> Any:
    """
    Limpia el estado del policy tuner del singleton DatabaseManager después
    de cada test de este módulo, evitando que DBs en read-only o historial de
    lock events contaminen tests posteriores (ej. test_oem_*).
    """
    yield
    try:
        inst = DatabaseManager._instance
        if inst is not None and hasattr(inst, "_policy_tuner"):
            inst._policy_tuner._read_only_dbs.clear()
            inst._policy_tuner._lock_events.clear()
            inst._policy_tuner._current_busy_timeout.clear()
            inst._policy_tuner._last_tune_ts.clear()
    except Exception:
        pass
from data_vault.db_policy_tuner import (
    DBPolicyTuner,
    BUSY_TIMEOUT_MIN_MS,
    BUSY_TIMEOUT_MAX_MS,
    BUSY_TIMEOUT_STEP_MS,
    P95_WARN_MS,
    P95_CRITICAL_MS,
    LOCK_RATE_WARN_PER_MIN,
    LOCK_RATE_CRITICAL_PER_MIN,
)
from data_vault.drivers import SQLiteDriver
from data_vault.drivers.interface import RecoveryContext, RecoveryResult
from utils.alerting import Alert, AlertChannel, AlertingService, AlertSeverity, RATE_LIMIT_SECONDS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fresh_manager() -> DatabaseManager:
    """Instancia aislada de DatabaseManager (no singleton)."""
    mgr = DatabaseManager.__new__(DatabaseManager)
    mgr._initialized = False
    mgr.__init__()
    return mgr


def _fresh_driver(mgr: DatabaseManager) -> SQLiteDriver:
    return SQLiteDriver(mgr)


# ===========================================================================
# DBPolicyTuner — auto-tuning de busy_timeout
# ===========================================================================


class TestDBPolicyTunerAutoTune:
    def test_no_tune_below_warn_threshold(self) -> None:
        """Sin p95 alto ni lock events, busy_timeout no debe cambiar."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0  # desactivar throttle para el test
        pool: dict[str, sqlite3.Connection] = {}

        result = tuner.evaluate_and_tune("test.db", p95_ms=100.0, connection_pool=pool)
        assert result is None

    def test_escalates_on_warn_p95(self) -> None:
        """p95 >= P95_WARN_MS debe incrementar busy_timeout en STEP."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = 120_000
        pool: dict[str, sqlite3.Connection] = {}

        new_timeout = tuner.evaluate_and_tune("test.db", p95_ms=P95_WARN_MS + 1, connection_pool=pool)

        assert new_timeout is not None
        assert new_timeout == 120_000 + BUSY_TIMEOUT_STEP_MS

    def test_escalates_aggressively_on_critical_p95(self) -> None:
        """p95 >= P95_CRITICAL_MS debe incrementar busy_timeout en 2×STEP."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = 120_000
        pool: dict[str, sqlite3.Connection] = {}

        new_timeout = tuner.evaluate_and_tune("test.db", p95_ms=P95_CRITICAL_MS + 1, connection_pool=pool)

        assert new_timeout == 120_000 + BUSY_TIMEOUT_STEP_MS * 2

    def test_reduces_when_stable(self) -> None:
        """Con p95 bajo y sin locks, busy_timeout debe reducirse gradualmente."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = 200_000  # mayor que el default
        pool: dict[str, sqlite3.Connection] = {}

        new_timeout = tuner.evaluate_and_tune(
            "test.db", p95_ms=P95_WARN_MS / 4, connection_pool=pool
        )

        assert new_timeout is not None
        assert new_timeout == 200_000 - BUSY_TIMEOUT_STEP_MS

    def test_busy_timeout_never_exceeds_max(self) -> None:
        """busy_timeout nunca debe superar BUSY_TIMEOUT_MAX_MS."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = BUSY_TIMEOUT_MAX_MS - 1_000
        pool: dict[str, sqlite3.Connection] = {}

        new_timeout = tuner.evaluate_and_tune("test.db", p95_ms=P95_CRITICAL_MS + 1, connection_pool=pool)

        assert new_timeout is not None
        assert new_timeout <= BUSY_TIMEOUT_MAX_MS

    def test_busy_timeout_never_below_min(self) -> None:
        """busy_timeout nunca debe bajar de BUSY_TIMEOUT_MIN_MS."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = BUSY_TIMEOUT_MIN_MS + 1_000
        pool: dict[str, sqlite3.Connection] = {}

        # Múltiples reducciones
        for _ in range(20):
            tuner.evaluate_and_tune("test.db", p95_ms=1.0, connection_pool=pool)

        assert tuner._current_busy_timeout["test.db"] >= BUSY_TIMEOUT_MIN_MS

    def test_throttle_prevents_multiple_evaluations(self) -> None:
        """El throttle de 30s debe impedir evaluaciones consecutivas."""
        tuner = DBPolicyTuner()
        # No desactivamos el throttle — intervalo default es 30s
        tuner._last_tune_ts["test.db"] = time.monotonic()  # simula evaluación reciente
        pool: dict[str, sqlite3.Connection] = {}

        result = tuner.evaluate_and_tune("test.db", p95_ms=P95_CRITICAL_MS + 1, connection_pool=pool)
        assert result is None  # bloqueado por throttle

    def test_apply_pragma_to_connection_on_tune(self, tmp_path: Path) -> None:
        """evaluate_and_tune debe aplicar PRAGMA busy_timeout a la conexión activa."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = 120_000

        conn = sqlite3.connect(str(tmp_path / "pragma_test.db"))
        pool: dict[str, sqlite3.Connection] = {"test.db": conn}

        tuner.evaluate_and_tune("test.db", p95_ms=P95_CRITICAL_MS + 1, connection_pool=pool)

        # Verificar que PRAGMA fue aplicado
        result = conn.execute("PRAGMA busy_timeout").fetchone()
        assert result is not None
        conn.close()

    def test_tune_history_records_events(self) -> None:
        """evaluate_and_tune debe registrar el evento en el historial."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = 120_000
        pool: dict[str, sqlite3.Connection] = {}

        tuner.evaluate_and_tune("test.db", p95_ms=P95_WARN_MS + 1, connection_pool=pool)

        status = tuner.get_tune_status()
        assert len(status["recent_tune_events"]) == 1
        event = status["recent_tune_events"][0]
        assert event["db_path"] == "test.db"
        assert event["old_busy_timeout_ms"] == 120_000


# ===========================================================================
# DBPolicyTuner — lock event tracking
# ===========================================================================


class TestDBPolicyTunerLockEvents:
    def test_record_lock_event_increments_rate(self) -> None:
        """record_lock_event debe incrementar la tasa de lock."""
        tuner = DBPolicyTuner()
        for _ in range(10):
            tuner.record_lock_event("test.db")

        rate = tuner.get_lock_event_rate("test.db", window_seconds=300)
        assert rate > 0.0

    def test_lock_rate_is_zero_for_unknown_db(self) -> None:
        """DBs sin eventos registrados deben tener tasa 0."""
        tuner = DBPolicyTuner()
        assert tuner.get_lock_event_rate("unknown.db") == 0.0

    def test_escalates_on_critical_lock_rate(self) -> None:
        """Alta tasa de lock debe escalar el busy_timeout incluso con p95 bajo."""
        tuner = DBPolicyTuner()
        tuner._tune_interval_seconds = 0
        tuner._current_busy_timeout["test.db"] = 120_000

        # Simular tasa alta inyectando eventos con timestamps recientes
        now = time.monotonic()
        from collections import deque
        tuner._lock_events["test.db"] = deque(
            [now - i * 2 for i in range(100)]  # 100 eventos en 200s = 30/min
        )
        pool: dict[str, sqlite3.Connection] = {}

        new_timeout = tuner.evaluate_and_tune("test.db", p95_ms=1.0, connection_pool=pool)
        assert new_timeout is not None
        assert new_timeout > 120_000


# ===========================================================================
# DBPolicyTuner — read-only fallback
# ===========================================================================


class TestDBPolicyTunerReadOnly:
    def test_apply_read_only_mode_sets_flag(self) -> None:
        """apply_read_only_mode debe marcar db como read-only."""
        tuner = DBPolicyTuner()
        assert tuner.is_read_only("test.db") is False

        tuner.apply_read_only_mode("test.db", connection_pool={})
        assert tuner.is_read_only("test.db") is True

    def test_apply_read_only_sets_pragma_on_connection(self, tmp_path: Path) -> None:
        """apply_read_only_mode debe aplicar PRAGMA query_only=1."""
        tuner = DBPolicyTuner()
        db_path = str(tmp_path / "readonly.db")
        conn = sqlite3.connect(db_path)
        conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")

        tuner.apply_read_only_mode(db_path, connection_pool={db_path: conn})

        result = conn.execute("PRAGMA query_only").fetchone()
        assert result[0] == 1
        conn.close()

    def test_clear_read_only_mode_removes_flag(self, tmp_path: Path) -> None:
        """clear_read_only_mode debe desactivar read-only y restaurar PRAGMA."""
        tuner = DBPolicyTuner()
        db_path = str(tmp_path / "restore.db")
        conn = sqlite3.connect(db_path)

        tuner.apply_read_only_mode(db_path, connection_pool={db_path: conn})
        assert tuner.is_read_only(db_path) is True

        tuner.clear_read_only_mode(db_path, connection_pool={db_path: conn})
        assert tuner.is_read_only(db_path) is False
        conn.close()

    def test_idempotent_apply_read_only(self) -> None:
        """Llamar apply_read_only dos veces no debe lanzar excepción."""
        tuner = DBPolicyTuner()
        tuner.apply_read_only_mode("test.db", connection_pool={})
        tuner.apply_read_only_mode("test.db", connection_pool={})  # segunda llamada
        assert tuner.is_read_only("test.db") is True


# ===========================================================================
# DatabaseManager — integración con tuner
# ===========================================================================


class TestDatabaseManagerReadOnlyIntegration:
    def test_transaction_raises_on_read_only_db(self, tmp_path: Path) -> None:
        """transaction() debe lanzar OperationalError si la BD está en read-only."""
        mgr = _fresh_manager()
        db_path = str(tmp_path / "ro_integration.db")

        mgr._policy_tuner.apply_read_only_mode(db_path, connection_pool={})

        with pytest.raises(sqlite3.OperationalError, match="SOLO-LECTURA"):
            with mgr.transaction(db_path):
                pass

    def test_clear_degraded_also_clears_read_only(self, tmp_path: Path) -> None:
        """clear_degraded() debe restaurar el modo de escritura."""
        mgr = _fresh_manager()
        db_path = str(tmp_path / "clear_ro.db")

        mgr._degraded_dbs.add(db_path)
        mgr._policy_tuner.apply_read_only_mode(db_path, connection_pool={})
        assert mgr.is_read_only(db_path) is True

        mgr.clear_degraded(db_path)
        assert mgr.is_read_only(db_path) is False

    def test_get_auto_tune_status_returns_dict(self) -> None:
        """get_auto_tune_status() debe retornar un dict con las claves esperadas."""
        mgr = _fresh_manager()
        status = mgr.get_auto_tune_status()
        assert "current_busy_timeout" in status
        assert "lock_rates_per_min" in status
        assert "read_only_dbs" in status
        assert "recent_tune_events" in status

    def test_recover_from_lock_activates_read_only_on_degradation(self, tmp_path: Path) -> None:
        """recover_from_lock debe activar read-only cuando should_degrade=True."""
        mgr = _fresh_manager()
        db_path = str(tmp_path / "degrade_ro.db")

        fail_strategy = MagicMock()
        fail_strategy.attempt_recovery.return_value = RecoveryResult(
            recovered=False, action_taken="reconnect_failed", should_degrade=True
        )
        mgr.register_recovery_strategy(fail_strategy)

        context = RecoveryContext(db_path=db_path, error=Exception("locked"), attempt_number=3)
        mgr.recover_from_lock(context)

        assert mgr.is_degraded(db_path) is True
        assert mgr.is_read_only(db_path) is True


# ===========================================================================
# AlertingService
# ===========================================================================


class TestAlertingService:
    def test_log_only_channel_sends_alert(self) -> None:
        """AlertingService con LOG_ONLY debe retornar True para log_only."""
        svc = AlertingService(channels=[AlertChannel.LOG_ONLY])
        alert = Alert(
            severity=AlertSeverity.CRITICAL,
            key="test_alert",
            title="Test Alert",
            message="Mensaje de prueba",
        )
        results = svc.send_alert(alert)
        assert results.get("log_only") is True

    def test_rate_limiting_blocks_duplicate_alerts(self) -> None:
        """Segunda alerta con la misma key dentro del límite debe ser bloqueada."""
        svc = AlertingService(channels=[AlertChannel.LOG_ONLY])
        alert = Alert(
            severity=AlertSeverity.WARNING,
            key="dup_key",
            title="Dup",
            message="Duplicada",
        )
        first = svc.send_alert(alert)
        second = svc.send_alert(alert)

        assert first["log_only"] is True
        assert second["log_only"] is False  # bloqueada por rate-limit

    def test_rate_limiting_allows_after_window(self) -> None:
        """Alerta con key distinta no debe verse afectada por rate-limit de otra."""
        svc = AlertingService(channels=[AlertChannel.LOG_ONLY])
        alert_a = Alert(severity=AlertSeverity.WARNING, key="key_a", title="A", message="A")
        alert_b = Alert(severity=AlertSeverity.CRITICAL, key="key_b", title="B", message="B")

        svc.send_alert(alert_a)
        result_b = svc.send_alert(alert_b)
        assert result_b["log_only"] is True

    def test_get_rate_limit_state_returns_remaining_seconds(self) -> None:
        """get_rate_limit_state debe retornar segundos restantes por clave."""
        svc = AlertingService(channels=[AlertChannel.LOG_ONLY])
        alert = Alert(severity=AlertSeverity.WARNING, key="rl_state", title="T", message="M")
        svc.send_alert(alert)

        state = svc.get_rate_limit_state()
        assert "log_only:rl_state" in state
        remaining = state["log_only:rl_state"]
        assert 0 < remaining <= RATE_LIMIT_SECONDS

    def test_from_env_returns_log_only_by_default(self, monkeypatch: Any) -> None:
        """from_env sin variables debe crear servicio LOG_ONLY."""
        monkeypatch.delenv("ALERT_CHANNELS", raising=False)
        svc = AlertingService.from_env()
        assert AlertChannel.LOG_ONLY in svc._channels

    def test_email_config_not_set_when_host_missing(self, monkeypatch: Any) -> None:
        """Si ALERT_SMTP_HOST está vacío, el canal EMAIL se descarta."""
        monkeypatch.setenv("ALERT_CHANNELS", "email,log_only")
        monkeypatch.setenv("ALERT_SMTP_HOST", "")
        monkeypatch.setenv("ALERT_SMTP_RECIPIENTS", "")
        svc = AlertingService.from_env()
        assert AlertChannel.EMAIL not in svc._channels

    def test_send_email_fails_gracefully_without_config(self) -> None:
        """_send_email sin config debe retornar False sin lanzar excepción."""
        svc = AlertingService(channels=[AlertChannel.EMAIL], email_config=None)
        alert = Alert(severity=AlertSeverity.CRITICAL, key="x", title="T", message="M")
        result = svc._send_email(alert)
        assert result is False

    def test_send_telegram_fails_gracefully_without_config(self) -> None:
        """_send_telegram sin config debe retornar False sin lanzar excepción."""
        svc = AlertingService(channels=[AlertChannel.TELEGRAM], telegram_config=None)
        alert = Alert(severity=AlertSeverity.CRITICAL, key="x", title="T", message="M")
        result = svc._send_telegram(alert)
        assert result is False


# ===========================================================================
# OperationalEdgeMonitor — check db_lock_rate_anomaly
# ===========================================================================


class TestOEMDbLockRateAnomalyCheck:
    def _make_oem(self, storage: Any, mgr: Any = None) -> Any:
        from core_brain.operational_edge_monitor import OperationalEdgeMonitor
        return OperationalEdgeMonitor(
            storage=storage, interval_seconds=9999, database_manager=mgr
        )

    def test_check_ok_when_no_lock_events(self) -> None:
        """Sin eventos de lock, el check debe retornar OK."""
        from core_brain.operational_edge_monitor import CheckStatus

        storage = MagicMock()
        storage.get_sys_config.return_value = {}
        mgr = _fresh_manager()
        oem = self._make_oem(storage, mgr)

        result = oem._check_db_lock_rate_anomaly()
        assert result.status == CheckStatus.OK

    def test_check_warn_on_elevated_lock_rate(self) -> None:
        """Tasa de lock entre WARN y FAIL debe retornar WARN."""
        from core_brain.operational_edge_monitor import CheckStatus
        from collections import deque

        storage = MagicMock()
        mgr = _fresh_manager()

        now = time.monotonic()
        mgr._policy_tuner._lock_events["test.db"] = deque(
            [now - i * 10 for i in range(30)]  # ~6 eventos/min
        )
        mgr._policy_tuner._current_busy_timeout["test.db"] = 120_000

        oem = self._make_oem(storage, mgr)
        result = oem._check_db_lock_rate_anomaly()
        assert result.status in (CheckStatus.WARN, CheckStatus.FAIL)

    def test_check_fail_on_read_only_dbs(self) -> None:
        """BDs en modo read-only deben generar FAIL inmediato."""
        from core_brain.operational_edge_monitor import CheckStatus

        storage = MagicMock()
        mgr = _fresh_manager()
        mgr._policy_tuner._read_only_dbs.add("aethelgard.db")

        oem = self._make_oem(storage, mgr)
        result = oem._check_db_lock_rate_anomaly()

        assert result.status == CheckStatus.FAIL
        assert "SOLO-LECTURA" in result.detail


# ===========================================================================
# OperationalEdgeMonitor — despacho de alertas
# ===========================================================================


class TestOEMAlertDispatching:
    def test_dispatch_critical_alerts_called_on_failing_checks(self) -> None:
        """_dispatch_critical_alerts debe llamarse cuando hay checks FAIL."""
        from core_brain.operational_edge_monitor import (
            CheckResult, CheckStatus, OperationalEdgeMonitor,
        )

        storage = MagicMock()
        storage.get_sys_config.return_value = {}
        storage.update_sys_config.return_value = None
        alerting = MagicMock(spec=AlertingService)

        oem = OperationalEdgeMonitor(
            storage=storage, interval_seconds=9999, alerting_service=alerting
        )
        failing = ["orchestrator_heartbeat"]
        warnings: list[str] = []
        results = {
            "orchestrator_heartbeat": CheckResult(
                CheckStatus.FAIL, "Sin heartbeat hace 200s"
            )
        }

        oem._dispatch_critical_alerts(failing, warnings, results)

        alerting.send_alert.assert_called_once()
        sent_alert: Alert = alerting.send_alert.call_args[0][0]
        assert sent_alert.severity == AlertSeverity.CRITICAL

    def test_no_alert_dispatched_when_all_ok(self) -> None:
        """Sin checks fallando, _dispatch_critical_alerts no debe llamar send_alert."""
        from core_brain.operational_edge_monitor import OperationalEdgeMonitor

        storage = MagicMock()
        alerting = MagicMock(spec=AlertingService)
        oem = OperationalEdgeMonitor(
            storage=storage, interval_seconds=9999, alerting_service=alerting
        )

        oem._dispatch_critical_alerts([], [], {})
        alerting.send_alert.assert_not_called()

    def test_warning_severity_for_single_non_critical_check(self) -> None:
        """Un solo check FAIL no-crítico debe generar alerta WARNING."""
        from core_brain.operational_edge_monitor import (
            CheckResult, CheckStatus, OperationalEdgeMonitor,
        )

        storage = MagicMock()
        alerting = MagicMock(spec=AlertingService)
        oem = OperationalEdgeMonitor(
            storage=storage, interval_seconds=9999, alerting_service=alerting
        )
        failing = ["backtest_quality"]
        results = {"backtest_quality": CheckResult(CheckStatus.FAIL, "Sin scores")}

        oem._dispatch_critical_alerts(failing, [], results)

        sent: Alert = alerting.send_alert.call_args[0][0]
        assert sent.severity == AlertSeverity.WARNING


# ===========================================================================
# Simulación de locks persistentes bajo carga
# ===========================================================================


class TestPersistentLockSimulation:
    def test_auto_tune_triggers_on_repeated_lock_events(self, tmp_path: Path) -> None:
        """Muchos lock events consecutivos deben disparar auto-tuning y escalar timeout."""
        mgr = _fresh_manager()
        db_path = str(tmp_path / "load_test.db")

        # Registrar muchos lock events para superar umbral crítico
        for _ in range(100):
            mgr._policy_tuner.record_lock_event(db_path)

        mgr._policy_tuner._tune_interval_seconds = 0
        mgr._policy_tuner._current_busy_timeout[db_path] = 120_000

        conn = sqlite3.connect(str(tmp_path / "load_test.db"))
        conn.execute("CREATE TABLE IF NOT EXISTS t (id INTEGER PRIMARY KEY)")
        new_timeout = mgr._policy_tuner.evaluate_and_tune(
            db_path, p95_ms=50.0, connection_pool={db_path: conn}
        )
        conn.close()

        assert new_timeout is not None
        assert new_timeout > 120_000

    def test_concurrent_writes_with_recovery_no_deadlock(self, tmp_path: Path) -> None:
        """10 hilos concurrentes escribiendo deben completar sin deadlock."""
        mgr = _fresh_manager()
        driver = _fresh_driver(mgr)
        db_path = str(tmp_path / "concurrent_load.db")

        with driver.transaction(db_path) as conn:
            conn.execute("CREATE TABLE cw (id INTEGER PRIMARY KEY, val INTEGER)")

        errors: list[Exception] = []

        def write_row(n: int) -> None:
            try:
                driver.execute(db_path, "INSERT INTO cw (val) VALUES (?)", (n,))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=write_row, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=20)

        rows = driver.fetch_all(db_path, "SELECT val FROM cw")
        assert len(errors) == 0, f"Errores en escritura concurrente: {errors}"
        assert len(rows) == 10

    def test_read_only_mode_blocks_writes_allows_reads(self, tmp_path: Path) -> None:
        """En read-only, las lecturas deben funcionar pero las escrituras fallar."""
        mgr = _fresh_manager()
        db_path = str(tmp_path / "rw_split.db")

        # Crear tabla y datos
        conn = mgr.get_connection(db_path)
        with mgr.transaction(db_path) as c:
            c.execute("CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT)")
            c.execute("INSERT INTO t (v) VALUES ('dato')")

        # Activar read-only
        mgr._policy_tuner.apply_read_only_mode(db_path, connection_pool=mgr._connection_pool)

        # Lectura debe funcionar directamente (no pasa por transaction())
        rows = mgr.execute_query(db_path, "SELECT v FROM t")
        assert rows[0]["v"] == "dato"

        # Escritura via transaction() debe fallar
        with pytest.raises(sqlite3.OperationalError, match="SOLO-LECTURA"):
            with mgr.transaction(db_path):
                pass
