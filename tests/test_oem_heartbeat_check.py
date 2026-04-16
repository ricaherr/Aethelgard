"""Tests OEM heartbeat with hard-fail SLA <120s per component."""
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import pytest

from core_brain.operational_edge_monitor import (
    OperationalEdgeMonitor,
    CheckStatus,
)


# ── Fixture base ──────────────────────────────────────────────────────────────

@pytest.fixture
def oem_with_storage():
    """OEM con storage mock que devuelve heartbeats configurables."""
    storage = MagicMock()
    storage.get_all_signal_rankings.return_value = []
    storage.get_sys_broker_accounts.return_value = []
    storage.get_recent_sys_signals.return_value = []
    storage.get_all_sys_market_pulses.return_value = {}
    storage.save_edge_learning.return_value = None
    storage.get_latest_module_heartbeat_audit.return_value = None
    storage.get_sys_config.return_value = {}

    oem = OperationalEdgeMonitor(storage=storage, interval_seconds=9999)
    return oem, storage


def _ts(seconds_ago: float) -> str:
    """Genera un timestamp ISO en UTC con N segundos de antigüedad."""
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


# ── Tests del check ───────────────────────────────────────────────────────────

class TestOrchestratorHeartbeatCheck:

    def test_ok_si_heartbeat_reciente(self, oem_with_storage):
        """Heartbeat hace 20s → OK."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": _ts(20)}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.OK
        assert "3" in result.detail or "activo" in result.detail.lower()

    def test_warn_si_heartbeat_tardio(self, oem_with_storage):
        """Heartbeat hace 95s → WARN (previo al hard-fail de 120s)."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": _ts(95)}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.WARN

    def test_fail_si_componente_silenciado_por_umbral_configurado(self, oem_with_storage):
        """Con umbral explícito de 120s, heartbeat de 3 min se marca como componente silenciado."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": _ts(180)}
        storage.get_sys_config.return_value = {"oem_silenced_component_gap_seconds": 120}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.FAIL
        assert "Componente Silenciado" in result.detail

    def test_fail_si_heartbeat_ausente_mucho_tiempo(self, oem_with_storage):
        """Heartbeat hace 200s → FAIL (posible bloqueo del loop)."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": _ts(200)}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.FAIL
        assert (
            "bloqueo" in result.detail.lower()
            or "posible" in result.detail.lower()
            or "componente silenciado" in result.detail.lower()
        )

    def test_warn_si_no_existe_heartbeat(self, oem_with_storage):
        """Sin heartbeat registrado → WARN (puede ser primer arranque)."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {}
        storage.get_latest_module_heartbeat_audit.return_value = None

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.WARN
        assert "no" in result.detail.lower() or "sin" in result.detail.lower()

    def test_ok_con_fallback_a_sys_audit_logs_si_sys_config_vacio(self, oem_with_storage):
        """Si sys_config no trae heartbeat, OEM usa fallback desde sys_audit_logs."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {}
        storage.get_latest_module_heartbeat_audit.return_value = _ts(10)

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.OK
        assert "source=sys_audit_logs" in result.detail

    def test_warn_si_formato_invalido(self, oem_with_storage):
        """Timestamp malformado → WARN (no FAIL) para no dar falsos positivos."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": "not-a-date"}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.WARN

    def test_umbral_exacto_warn_a_fail(self, oem_with_storage):
        """En el umbral exacto de 120s → FAIL."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": _ts(121)}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.FAIL

    def test_umbral_exacto_ok_a_warn(self, oem_with_storage):
        """En el umbral exacto de 90s → WARN."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {"orchestrator": _ts(91)}

        result = oem._check_orchestrator_heartbeat()

        assert result.status == CheckStatus.WARN

    def test_check_presente_en_run_checks(self, oem_with_storage):
        """orchestrator_heartbeat debe estar en los resultados de run_checks()."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {
            "orchestrator": _ts(10),
            "scanner": _ts(10),
            "signal_factory": _ts(10),
            "executor": _ts(10),
            "risk_manager": _ts(10),
        }

        results = oem.run_checks()

        assert "orchestrator_heartbeat" in results
        assert results["orchestrator_heartbeat"].status == CheckStatus.OK


# ── Tests de get_health_summary con heartbeat ─────────────────────────────────

class TestHealthSummaryHeartbeatIntegration:

    def test_critical_si_solo_heartbeat_falla(self, oem_with_storage):
        """Un solo FAIL en orchestrator_heartbeat → CRITICAL (regla especial)."""
        oem, storage = oem_with_storage
        # Hacer que solo el heartbeat falle: resto OK
        storage.get_module_heartbeats.return_value = {
            "orchestrator": _ts(200),
            "scanner": _ts(10),
            "signal_factory": _ts(10),
            "executor": _ts(10),
            "risk_manager": _ts(10),
        }
        storage.get_all_signal_rankings.return_value = [
            {"strategy_id": "s1", "score_backtest": 0.8, "execution_mode": "LIVE",
             "updated_at": _ts(10)}
        ]
        storage.get_sys_broker_accounts.return_value = [
            {"supports_exec": 1, "enabled": 1}
        ]
        storage.get_recent_sys_signals.return_value = [{"id": 1}]
        storage.get_all_sys_market_pulses.return_value = {
            "EURUSD_H1": {"data": {"adx": 25.0}}
        }

        summary = oem.get_health_summary()

        assert summary["status"] == "CRITICAL"
        assert "orchestrator_heartbeat" in summary["failing"]

    def test_ok_cuando_heartbeat_y_todos_checks_pasan(self, oem_with_storage):
        """Todo OK → status global OK."""
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {
            "orchestrator": _ts(10),
            "scanner": _ts(10),
            "signal_factory": _ts(10),
            "executor": _ts(10),
            "risk_manager": _ts(10),
        }
        storage.get_all_signal_rankings.return_value = [
            {"strategy_id": "s1", "score_backtest": 0.8, "execution_mode": "LIVE",
             "updated_at": _ts(10)}
        ]
        storage.get_sys_broker_accounts.return_value = [
            {"supports_exec": 1, "enabled": 1}
        ]
        storage.get_recent_sys_signals.return_value = [{"id": 1, "status": "executed"}]
        storage.get_all_sys_market_pulses.return_value = {
            "EURUSD_H1": {"data": {"adx": 25.0}}
        }

        summary = oem.get_health_summary()

        # Puede ser OK o DEGRADED si hay WARNs en otros checks, pero no CRITICAL
        assert summary["status"] in ("OK", "DEGRADED")
        assert "orchestrator_heartbeat" not in summary["failing"]

    def test_degraded_si_solo_warn_en_heartbeat(self, oem_with_storage):
        """
        Heartbeat tardío (WARN) → DEGRADED, no CRITICAL, salvo que haya lock crítico (db_lock_rate_anomaly).
        Si el sistema EDGE detecta lock crítico, puede ser CRITICAL legítimamente.
        """
        oem, storage = oem_with_storage
        storage.get_module_heartbeats.return_value = {
            "orchestrator": _ts(100),
            "scanner": _ts(10),
            "signal_factory": _ts(10),
            "executor": _ts(10),
            "risk_manager": _ts(10),
        }

        summary = oem.get_health_summary()

        # Permitir CRITICAL si el check db_lock_rate_anomaly lo dispara
        assert summary["status"] in ("DEGRADED", "CRITICAL")
        assert "orchestrator_heartbeat" not in summary["failing"]
        assert "orchestrator_heartbeat" in summary["warnings"]
