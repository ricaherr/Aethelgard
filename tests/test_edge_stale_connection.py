"""
Tests TDD — EDGE Stale Connection Response
==========================================

Convención: test_<componente>_<comportamiento>

Cobertura:
  - DatabaseManager.register_stale_hook: registro y emisión de eventos
  - DatabaseManager._emit_stale_event: despacho a múltiples hooks
  - OperationalEdgeMonitor._on_stale_connection: registro, tasa, alertas
  - OperationalEdgeMonitor._check_stale_connection_anomaly: lógica de check
  - OperationalEdgeMonitor._handle_stale_degradation: degradación y reversión
  - OperationalEdgeMonitor.clear_stale_degraded: reversión automática
  - Integración: hook DatabaseManager → OEM response

ETI: EDGE_StaleConnection_Response_2026-04-16
"""
import threading
import time
from collections import deque
from typing import Any, List, Tuple
from unittest.mock import MagicMock, patch

import pytest

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _make_storage() -> MagicMock:
    """StorageManager mock con métodos mínimos para OEM."""
    storage = MagicMock()
    storage.get_sys_config.return_value = {}
    storage.update_sys_config.return_value = None
    storage.get_module_heartbeats.return_value = {}
    return storage


def _make_alerting() -> MagicMock:
    """AlertingService mock que registra llamadas."""
    alerting = MagicMock()
    alerting.send_alert.return_value = {"log_only": True}
    return alerting


def _make_db_manager() -> MagicMock:
    """DatabaseManager mock con stubs necesarios."""
    mgr = MagicMock()
    mgr.register_stale_hook.return_value = None
    mgr.get_auto_tune_status.return_value = {
        "lock_rates_per_min": {},
        "read_only_dbs": [],
        "current_busy_timeout": {},
        "recent_tune_events": [],
    }
    mgr._policy_tuner = MagicMock()
    mgr._connection_pool = {}
    return mgr


@pytest.fixture
def oem(tmp_path):
    """OEM con mocks inyectados y sin hilo de fondo."""
    from core_brain.operational_edge_monitor import OperationalEdgeMonitor

    storage = _make_storage()
    alerting = _make_alerting()
    db_mgr = _make_db_manager()

    monitor = OperationalEdgeMonitor(
        storage=storage,
        interval_seconds=9999,  # Sin loop automático
        alerting_service=alerting,
        database_manager=db_mgr,
    )
    monitor._storage = storage
    monitor._alerting_mock = alerting
    monitor._db_mgr_mock = db_mgr
    return monitor


# ─────────────────────────────────────────────────────────────────────────────
# Tests: DatabaseManager — register_stale_hook y _emit_stale_event
# ─────────────────────────────────────────────────────────────────────────────


class TestDatabaseManagerStaleHook:
    def test_database_manager_registra_hook_correctamente(self):
        """register_stale_hook almacena el callback en la lista interna."""
        from data_vault.database_manager import DatabaseManager

        mgr = DatabaseManager()
        initial_count = len(mgr._stale_hooks)
        callback = MagicMock()
        mgr.register_stale_hook(callback)
        assert len(mgr._stale_hooks) == initial_count + 1

    def test_database_manager_emit_invoca_todos_los_hooks(self):
        """_emit_stale_event llama a todos los hooks registrados con db_path y trace_id."""
        from data_vault.database_manager import DatabaseManager

        mgr = DatabaseManager()
        # Usar instancia aislada sin hooks previos
        mgr._stale_hooks = []

        cb1 = MagicMock()
        cb2 = MagicMock()
        mgr.register_stale_hook(cb1)
        mgr.register_stale_hook(cb2)

        mgr._emit_stale_event("test.db", "STALE-ABC123")

        cb1.assert_called_once_with("test.db", "STALE-ABC123")
        cb2.assert_called_once_with("test.db", "STALE-ABC123")

    def test_database_manager_hook_exception_no_propaga(self):
        """Un hook que lanza excepción no interrumpe la emisión al resto."""
        from data_vault.database_manager import DatabaseManager

        mgr = DatabaseManager()
        mgr._stale_hooks = []

        def bad_hook(db_path, trace_id):
            raise RuntimeError("hook error")

        good_cb = MagicMock()
        mgr.register_stale_hook(bad_hook)
        mgr.register_stale_hook(good_cb)

        # No debe propagar excepción
        mgr._emit_stale_event("test.db", "STALE-XYZ")

        good_cb.assert_called_once_with("test.db", "STALE-XYZ")

    def test_database_manager_get_connection_emite_evento_stale(self):
        """get_connection emite evento stale cuando la conexión existente no es healthy."""
        from data_vault.database_manager import DatabaseManager

        mgr = DatabaseManager()
        mgr._stale_hooks = []

        received: List[Tuple[str, str]] = []

        def capture(db_path, trace_id):
            received.append((db_path, trace_id))

        mgr.register_stale_hook(capture)

        # Insertar una conexión "muerta" directamente en el pool
        # _is_connection_healthy captura sqlite3.OperationalError/ProgrammingError
        import sqlite3 as _sqlite3
        dead_conn = MagicMock()
        dead_conn.cursor.side_effect = _sqlite3.OperationalError("connection closed")
        mgr._connection_pool[":memory:_stale_test"] = dead_conn
        mgr._health_timestamps[":memory:_stale_test"] = time.time()

        # get_connection debe detectar la conexión muerta y emitir el evento
        try:
            mgr.get_connection(":memory:_stale_test")
        except Exception:
            pass  # La reconexión a :memory: puede fallar; lo importante es el evento

        assert len(received) == 1
        assert received[0][0] == ":memory:_stale_test"
        assert received[0][1].startswith("STALE-")

        # Cleanup
        mgr._connection_pool.pop(":memory:_stale_test", None)
        mgr._health_timestamps.pop(":memory:_stale_test", None)


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OEM — _on_stale_connection
# ─────────────────────────────────────────────────────────────────────────────


class TestOemOnStaleConnection:
    def test_oem_on_stale_registra_evento_en_log(self, oem):
        """_on_stale_connection añade el evento al deque interno."""
        oem._on_stale_connection("test.db", "STALE-001")
        assert len(oem._stale_event_log) == 1
        ts, db, tid = oem._stale_event_log[0]
        assert db == "test.db"
        assert tid == "STALE-001"

    def test_oem_on_stale_bajo_umbral_no_alerta(self, oem):
        """Un único evento no supera el umbral de alerta."""
        oem._on_stale_connection("test.db", "STALE-001")
        # Alertas solo si rate >= WARN threshold
        for call_args in oem._alerting.send_alert.call_args_list:
            alert = call_args[0][0]
            assert "stale" not in alert.key.lower() or "warn" not in alert.key.lower()

    def test_oem_on_stale_supera_warn_envia_alerta_warning(self, oem):
        """Superar STALE_CONN_WARN_PER_MIN dispara alerta WARNING."""
        # Inyectar eventos suficientes en la ventana
        from utils.alerting import AlertSeverity

        warn_threshold = oem.STALE_CONN_WARN_PER_MIN
        window = oem.STALE_CONN_WINDOW_SECONDS
        # Necesitamos ceil(warn_threshold * window / 60) eventos
        needed = int(warn_threshold * window / 60) + 1
        for i in range(needed):
            oem._stale_event_log.append((time.monotonic(), "prod.db", f"STALE-{i:03d}"))

        oem._on_stale_connection("prod.db", "STALE-TRIGGER")

        sent_keys = [c[0][0].key for c in oem._alerting.send_alert.call_args_list]
        assert any("stale_conn_warn" in k or "stale_conn_critical" in k for k in sent_keys)

    def test_oem_on_stale_supera_fail_envia_alerta_critical(self, oem):
        """Superar STALE_CONN_FAIL_PER_MIN dispara alerta CRITICAL."""
        from utils.alerting import AlertSeverity

        fail_threshold = oem.STALE_CONN_FAIL_PER_MIN
        window = oem.STALE_CONN_WINDOW_SECONDS
        needed = int(fail_threshold * window / 60) + 1
        for i in range(needed):
            oem._stale_event_log.append((time.monotonic(), "prod.db", f"STALE-{i:03d}"))

        oem._on_stale_connection("prod.db", "STALE-CRITICAL")

        sent_keys = [c[0][0].key for c in oem._alerting.send_alert.call_args_list]
        assert any("stale_conn_critical" in k for k in sent_keys)

        severities = [c[0][0].severity for c in oem._alerting.send_alert.call_args_list]
        assert AlertSeverity.CRITICAL in severities

    def test_oem_on_stale_supera_degradacion_activa_readonly(self, oem):
        """Superar STALE_CONN_DEGRADE_THRESHOLD activa modo solo-lectura."""
        threshold = oem.STALE_CONN_DEGRADE_THRESHOLD
        for i in range(threshold):
            oem._stale_event_log.append((time.monotonic(), "prod.db", f"STALE-{i:03d}"))

        oem._on_stale_connection("prod.db", "STALE-DEGRADE")

        assert "prod.db" in oem._stale_degraded_dbs
        oem._db_mgr_mock._policy_tuner.apply_read_only_mode.assert_called()


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OEM — _check_stale_connection_anomaly
# ─────────────────────────────────────────────────────────────────────────────


class TestOemCheckStaleConnectionAnomaly:
    def test_check_stale_sin_eventos_retorna_ok(self, oem):
        """Sin eventos, el check retorna OK."""
        from core_brain.operational_edge_monitor import CheckStatus

        result = oem._check_stale_connection_anomaly()
        assert result.status == CheckStatus.OK

    def test_check_stale_db_degradada_retorna_fail(self, oem):
        """DB en estado degradado retorna FAIL."""
        from core_brain.operational_edge_monitor import CheckStatus

        oem._stale_degraded_dbs.add("prod.db")
        result = oem._check_stale_connection_anomaly()
        assert result.status == CheckStatus.FAIL
        assert "prod.db" in result.detail

    def test_check_stale_tasa_warn_retorna_warn(self, oem):
        """Tasa entre WARN y FAIL retorna WARN."""
        from core_brain.operational_edge_monitor import CheckStatus

        warn_threshold = oem.STALE_CONN_WARN_PER_MIN
        window = oem.STALE_CONN_WINDOW_SECONDS
        needed = int(warn_threshold * window / 60) + 1
        for i in range(needed):
            oem._stale_event_log.append((time.monotonic(), "prod.db", f"STALE-{i:03d}"))

        result = oem._check_stale_connection_anomaly()
        assert result.status in (CheckStatus.WARN, CheckStatus.FAIL)

    def test_check_stale_tasa_fail_retorna_fail(self, oem):
        """Tasa >= FAIL threshold retorna FAIL."""
        from core_brain.operational_edge_monitor import CheckStatus

        fail_threshold = oem.STALE_CONN_FAIL_PER_MIN
        window = oem.STALE_CONN_WINDOW_SECONDS
        needed = int(fail_threshold * window / 60) + 1
        for i in range(needed):
            oem._stale_event_log.append((time.monotonic(), "prod.db", f"STALE-{i:03d}"))

        result = oem._check_stale_connection_anomaly()
        assert result.status == CheckStatus.FAIL

    def test_check_stale_eventos_fuera_ventana_ignorados(self, oem):
        """Eventos más antiguos que STALE_CONN_WINDOW_SECONDS no cuentan."""
        from core_brain.operational_edge_monitor import CheckStatus

        old_ts = time.monotonic() - oem.STALE_CONN_WINDOW_SECONDS - 10
        for i in range(100):
            oem._stale_event_log.append((old_ts, "prod.db", f"OLD-{i:03d}"))

        result = oem._check_stale_connection_anomaly()
        assert result.status == CheckStatus.OK


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OEM — clear_stale_degraded (reversión)
# ─────────────────────────────────────────────────────────────────────────────


class TestOemClearStaleDegraded:
    def test_clear_stale_degraded_elimina_db_del_set(self, oem):
        """clear_stale_degraded retira la DB del conjunto degradado."""
        oem._stale_degraded_dbs.add("prod.db")
        oem.clear_stale_degraded("prod.db")
        assert "prod.db" not in oem._stale_degraded_dbs

    def test_clear_stale_degraded_limpia_historial_de_eventos(self, oem):
        """clear_stale_degraded elimina del log los eventos de la DB revertida."""
        now = time.monotonic()
        oem._stale_event_log.extend([
            (now, "prod.db", "STALE-A"),
            (now, "other.db", "STALE-B"),
            (now, "prod.db", "STALE-C"),
        ])
        oem._stale_degraded_dbs.add("prod.db")

        oem.clear_stale_degraded("prod.db")

        remaining_dbs = [p for _, p, _ in oem._stale_event_log]
        assert "prod.db" not in remaining_dbs
        assert "other.db" in remaining_dbs

    def test_clear_stale_degraded_llama_clear_degraded_en_db_manager(self, oem):
        """clear_stale_degraded llama a mgr.clear_degraded() para revertir PRAGMA."""
        oem._stale_degraded_dbs.add("prod.db")
        oem.clear_stale_degraded("prod.db")
        oem._db_mgr_mock.clear_degraded.assert_called_once_with("prod.db")

    def test_clear_stale_degraded_check_retorna_ok_tras_reversion(self, oem):
        """Después de clear_stale_degraded, _check_stale_connection_anomaly retorna OK."""
        from core_brain.operational_edge_monitor import CheckStatus

        oem._stale_degraded_dbs.add("prod.db")
        oem.clear_stale_degraded("prod.db")

        result = oem._check_stale_connection_anomaly()
        assert result.status == CheckStatus.OK

    def test_clear_stale_degraded_db_inexistente_no_falla(self, oem):
        """clear_stale_degraded sobre una DB no degradada no lanza excepción."""
        oem.clear_stale_degraded("nonexistent.db")  # No debe lanzar


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OEM — get_stale_event_summary
# ─────────────────────────────────────────────────────────────────────────────


class TestOemStaleEventSummary:
    def test_stale_summary_sin_eventos(self, oem):
        """Sin eventos, el resumen tiene total_events=0 y rates vacíos."""
        summary = oem.get_stale_event_summary()
        assert summary["total_events"] == 0
        assert summary["rates_per_min"] == {}
        assert summary["degraded_dbs"] == []

    def test_stale_summary_con_eventos_recientes(self, oem):
        """Eventos dentro de la ventana aparecen en el resumen."""
        now = time.monotonic()
        oem._stale_event_log.extend([
            (now, "prod.db", "STALE-1"),
            (now, "prod.db", "STALE-2"),
            (now, "other.db", "STALE-3"),
        ])

        summary = oem.get_stale_event_summary()
        assert summary["total_events"] == 3
        assert "prod.db" in summary["rates_per_min"]
        assert "other.db" in summary["rates_per_min"]

    def test_stale_summary_incluye_dbs_degradadas(self, oem):
        """El resumen lista correctamente las BDs degradadas."""
        oem._stale_degraded_dbs.add("prod.db")
        summary = oem.get_stale_event_summary()
        assert "prod.db" in summary["degraded_dbs"]


# ─────────────────────────────────────────────────────────────────────────────
# Tests: OEM — check presente en run_checks
# ─────────────────────────────────────────────────────────────────────────────


class TestOemRunChecksIntegration:
    def test_run_checks_incluye_stale_connection_anomaly(self, oem):
        """run_checks() incluye el check stale_connection_anomaly."""
        # Mock todos los métodos de storage para evitar fallos de datos
        oem.storage.get_all_sys_strategies.return_value = []
        oem.storage.get_sys_broker_accounts.return_value = []
        oem.storage.get_recent_sys_signals.return_value = []
        oem.storage.get_all_sys_market_pulses.return_value = {}
        oem.storage.get_all_signal_rankings.return_value = []
        oem.storage.get_module_heartbeats.return_value = {}
        oem.storage.get_sys_config.return_value = {}

        results = oem.run_checks()
        assert "stale_connection_anomaly" in results

    def test_run_checks_stale_connection_anomaly_ok_sin_eventos(self, oem):
        """Sin eventos stale, el check stale_connection_anomaly retorna OK."""
        from core_brain.operational_edge_monitor import CheckStatus

        oem.storage.get_all_sys_strategies.return_value = []
        oem.storage.get_sys_broker_accounts.return_value = []
        oem.storage.get_recent_sys_signals.return_value = []
        oem.storage.get_all_sys_market_pulses.return_value = {}
        oem.storage.get_all_signal_rankings.return_value = []
        oem.storage.get_module_heartbeats.return_value = {}
        oem.storage.get_sys_config.return_value = {}

        results = oem.run_checks()
        assert results["stale_connection_anomaly"].status == CheckStatus.OK
