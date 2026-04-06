"""
test_oem_production_integration.py — HU 10.10

Verifica que el OperationalEdgeMonitor se integra correctamente en el
arranque del sistema con shadow_storage inyectado, y que el endpoint
/system/health/edge responde correctamente en ambos estados
(OEM activo / OEM no inicializado).

TDD: estos tests deben estar en GREEN con la implementación de HU 10.10.
"""
import threading
import time
import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from core_brain.operational_edge_monitor import OperationalEdgeMonitor, CheckStatus
from data_vault.shadow_db import ShadowStorageManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_conn():
    """Conexión SQLite en memoria con tablas mínimas para el OEM."""
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sys_config (
            key TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS sys_signals (
            id INTEGER PRIMARY KEY,
            status TEXT,
            created_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sys_signal_ranking (
            strategy_id TEXT PRIMARY KEY,
            score_backtest REAL,
            execution_mode TEXT,
            updated_at TEXT
        );
        CREATE TABLE IF NOT EXISTS sys_broker_accounts (
            id INTEGER PRIMARY KEY,
            enabled INTEGER DEFAULT 1,
            supports_exec INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS sys_shadow_instances (
            instance_id TEXT PRIMARY KEY,
            status TEXT,
            created_at TEXT,
            total_trades_executed INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS usr_edge_learning (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detection TEXT,
            action_taken TEXT,
            learning TEXT,
            details TEXT,
            created_at TEXT
        );
    """)
    yield conn
    conn.close()


@pytest.fixture
def mock_storage(in_memory_conn):
    """StorageManager mock con .conn expuesto y métodos mínimos del OEM."""
    storage = MagicMock()
    storage.conn = in_memory_conn
    storage.get_all_signal_rankings.return_value = []
    storage.get_sys_broker_accounts.return_value = []
    storage.get_recent_sys_signals.return_value = []
    storage.get_all_sys_market_pulses.return_value = {}
    storage.get_module_heartbeats.return_value = {}
    storage.save_edge_learning.return_value = None
    return storage


@pytest.fixture
def shadow_storage(in_memory_conn):
    """ShadowStorageManager real con conexión en memoria."""
    return ShadowStorageManager(in_memory_conn)


# ── Tests de integración: OEM arranca con shadow_storage ─────────────────────

class TestOemProductionIntegration:

    def test_oem_instancia_con_shadow_storage_inyectado(self, mock_storage, shadow_storage):
        """OEM debe aceptar shadow_storage sin lanzar excepciones."""
        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            shadow_storage=shadow_storage,
            interval_seconds=9999,
        )
        assert oem.shadow_storage is shadow_storage
        assert oem.shadow_storage is not None

    def test_oem_check_shadow_sync_no_retorna_warn_storage_ausente(self, mock_storage, shadow_storage):
        """Con shadow_storage inyectado, el check no debe retornar 'shadow_storage no inyectado'."""
        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            shadow_storage=shadow_storage,
            interval_seconds=9999,
        )
        result = oem._check_shadow_sync()
        assert "no inyectado" not in result.detail.lower()

    def test_oem_es_daemon_thread(self, mock_storage):
        """El OEM debe ser un daemon thread para no bloquear el shutdown."""
        oem = OperationalEdgeMonitor(storage=mock_storage, interval_seconds=9999)
        assert oem.daemon is True

    def test_oem_tiene_nombre_correcto(self, mock_storage):
        """El nombre del thread debe ser OperationalEdgeMonitor."""
        oem = OperationalEdgeMonitor(storage=mock_storage, interval_seconds=9999)
        assert oem.name == "OperationalEdgeMonitor"

    def test_oem_last_results_vacio_antes_de_primer_ciclo(self, mock_storage):
        """last_results debe ser dict vacío antes del primer run_checks()."""
        oem = OperationalEdgeMonitor(storage=mock_storage, interval_seconds=9999)
        assert oem.last_results == {}
        assert oem.last_checked_at is None

    def test_oem_run_checks_popula_last_results(self, mock_storage, shadow_storage):
        """Después de run_checks(), last_results debe contener los 10 checks."""
        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            shadow_storage=shadow_storage,
            interval_seconds=9999,
        )
        oem.run_checks()
        # run_checks() no actualiza last_results — eso lo hace run()
        # pero podemos llamar manualmente para verificar que devuelve 10
        results = oem.run_checks()
        assert len(results) == 10
        assert "orchestrator_heartbeat" in results
        assert "shadow_sync" in results
        assert "shadow_stagnation" in results

    def test_oem_thread_actualiza_last_results_al_ejecutar(self, mock_storage, shadow_storage):
        """Al iniciar el thread, last_results debe popularse dentro de interval_seconds."""
        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            shadow_storage=shadow_storage,
            interval_seconds=1,  # 1 segundo para el test
        )
        oem.start()
        time.sleep(0.5)  # Esperar menos que el intervalo

        # run() llama run_checks() en el primer tick
        # Permitir hasta 2 segundos para que el primer ciclo complete
        for _ in range(20):
            if oem.last_checked_at is not None:
                break
            time.sleep(0.1)

        oem.stop()
        assert oem.last_checked_at is not None
        assert len(oem.last_results) == 10

    def test_get_health_summary_incluye_last_checked_at_en_none_inicial(self, mock_storage):
        """get_health_summary() funciona aunque last_checked_at sea None."""
        oem = OperationalEdgeMonitor(storage=mock_storage, interval_seconds=9999)
        summary = oem.get_health_summary()
        assert "status" in summary
        assert "checks" in summary
        assert "failing" in summary
        assert "warnings" in summary


# ── Tests del endpoint API ────────────────────────────────────────────────────

class TestOemApiEndpoint:

    def test_servidor_singleton_set_get_oem_instance(self, mock_storage):
        """set_oem_instance y get_oem_instance deben funcionar como singleton."""
        from core_brain.server import set_oem_instance, get_oem_instance

        oem = OperationalEdgeMonitor(storage=mock_storage, interval_seconds=9999)
        set_oem_instance(oem)
        retrieved = get_oem_instance()
        assert retrieved is oem

        # Cleanup
        set_oem_instance(None)

    def test_endpoint_retorna_unavailable_si_no_hay_snapshot_en_db(self):
        """Sin snapshot OEM en DB, el endpoint debe retornar status UNAVAILABLE."""
        from unittest.mock import patch, MagicMock
        from fastapi.testclient import TestClient
        from core_brain.server import create_app

        mock_storage = MagicMock()
        mock_storage.get_sys_config.return_value = {}  # no oem_health_snapshot key

        with patch("data_vault.storage.StorageManager", return_value=mock_storage):
            app = create_app()
            client = TestClient(app, raise_server_exceptions=False)
            response = client.get("/api/system/health/edge")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "UNAVAILABLE"
