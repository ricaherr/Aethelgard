"""
test_oem_repair_flags.py — HU 10.14: OEM Response Engine

Verifica el mecanismo completo de repair flags:
  1. OEM._write_repair_flags() escribe los flags correctos según qué checks fallan
  2. MainOrchestrator._consume_oem_repair_flags() lee los flags y aplica acciones
  3. /system/audit/repair escribe flags reales (no simula)
  4. Checks no accionables NO generan flags (no auto-reparables)
"""
import json
import sqlite3
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_brain.operational_edge_monitor import (
    OperationalEdgeMonitor,
    CheckResult,
    CheckStatus,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_storage(**config_values) -> MagicMock:
    storage = MagicMock()
    storage.get_all_signal_rankings.return_value = []
    storage.get_recent_sys_signals.return_value = []
    storage.get_all_sys_market_pulses.return_value = {}
    storage.get_sys_broker_accounts.return_value = []
    storage.get_sys_config.return_value = {}
    storage.get_module_heartbeats.return_value = {}
    storage.update_sys_config.return_value = None
    return storage


def _make_oem_with_failing(*failing_checks: str) -> tuple:
    """Retorna (oem, storage_mock) con los checks especificados en FAIL."""
    storage = _make_storage()
    oem = OperationalEdgeMonitor(storage=storage, shadow_storage=None, interval_seconds=300)
    oem._started_at_utc = datetime.now(timezone.utc) - timedelta(hours=2)
    oem.last_checked_at = datetime.now(timezone.utc).isoformat()

    # Simular resultados con los checks indicados en FAIL
    results = {
        check: CheckResult(CheckStatus.FAIL, f"Test FAIL: {check}")
        for check in failing_checks
    }
    return oem, storage, results


# ── Tests: _write_repair_flags ─────────────────────────────────────────────────

class TestWriteRepairFlags:

    def test_backtest_quality_fail_escribe_force_backtest(self):
        """backtest_quality FAIL → escribe oem_repair_force_backtest."""
        oem, storage, _ = _make_oem_with_failing("backtest_quality")
        oem._write_repair_flags(failing=["backtest_quality"], warnings=[])

        storage.update_sys_config.assert_called_once()
        written = storage.update_sys_config.call_args[0][0]
        assert "oem_repair_force_backtest" in written

    def test_lifecycle_coherence_fail_escribe_force_backtest(self):
        """lifecycle_coherence FAIL → escribe oem_repair_force_backtest."""
        oem, storage, _ = _make_oem_with_failing("lifecycle_coherence")
        oem._write_repair_flags(failing=["lifecycle_coherence"], warnings=[])

        written = storage.update_sys_config.call_args[0][0]
        assert "oem_repair_force_backtest" in written

    def test_adx_sanity_fail_escribe_force_ohlc_reload(self):
        """adx_sanity FAIL → escribe oem_repair_force_ohlc_reload."""
        oem, storage, _ = _make_oem_with_failing("adx_sanity")
        oem._write_repair_flags(failing=["adx_sanity"], warnings=[])

        written = storage.update_sys_config.call_args[0][0]
        assert "oem_repair_force_ohlc_reload" in written

    def test_score_stale_warn_escribe_force_ranking(self):
        """score_stale WARN → escribe oem_repair_force_ranking."""
        oem, storage, _ = _make_oem_with_failing()
        oem._write_repair_flags(failing=[], warnings=["score_stale"])

        written = storage.update_sys_config.call_args[0][0]
        assert "oem_repair_force_ranking" in written

    def test_shadow_sync_fail_no_escribe_ningun_flag(self):
        """shadow_sync FAIL → sin auto-reparación (requiere diagnóstico humano)."""
        oem, storage, _ = _make_oem_with_failing("shadow_sync")
        oem._write_repair_flags(failing=["shadow_sync"], warnings=[])

        # No debe haber escrito ningún flag de repair
        storage.update_sys_config.assert_not_called()

    def test_signal_flow_warn_no_escribe_ningun_flag(self):
        """signal_flow WARN → sin auto-reparación (puede ser correcto fuera de sesión)."""
        oem, storage, _ = _make_oem_with_failing()
        oem._write_repair_flags(failing=[], warnings=["signal_flow"])

        storage.update_sys_config.assert_not_called()

    def test_adx_sanity_warn_no_escribe_ningun_flag(self):
        """adx_sanity WARN no debe armar repair loop automático."""
        oem, storage, _ = _make_oem_with_failing()
        oem._write_repair_flags(failing=[], warnings=["adx_sanity"])

        storage.update_sys_config.assert_not_called()

    def test_rejection_rate_fail_no_escribe_ningun_flag(self):
        """rejection_rate FAIL → sin auto-reparación (causa puede ser legítima)."""
        oem, storage, _ = _make_oem_with_failing("rejection_rate")
        oem._write_repair_flags(failing=["rejection_rate"], warnings=[])

        storage.update_sys_config.assert_not_called()

    def test_orchestrator_heartbeat_fail_no_escribe_ningun_flag(self):
        """orchestrator_heartbeat FAIL → no se puede reiniciar el loop desde un daemon thread."""
        oem, storage, _ = _make_oem_with_failing("orchestrator_heartbeat")
        oem._write_repair_flags(failing=["orchestrator_heartbeat"], warnings=[])

        storage.update_sys_config.assert_not_called()

    def test_multiples_checks_accionables_no_duplican_flag(self):
        """backtest_quality + lifecycle_coherence → solo UN flag force_backtest."""
        oem, storage, _ = _make_oem_with_failing()
        oem._write_repair_flags(
            failing=["backtest_quality", "lifecycle_coherence"],
            warnings=[]
        )

        written = storage.update_sys_config.call_args[0][0]
        # El flag debe aparecer una sola vez (no duplicado)
        assert list(written.keys()).count("oem_repair_force_backtest") == 1

    def test_sin_fallos_no_escribe_nada(self):
        """Sin checks fallidos ni warnings accionables → no escribe en sys_config."""
        oem, storage, _ = _make_oem_with_failing()
        oem._write_repair_flags(failing=[], warnings=[])

        storage.update_sys_config.assert_not_called()

    def test_flags_contienen_timestamp_iso(self):
        """Los flags escritos deben tener un timestamp ISO válido."""
        oem, storage, _ = _make_oem_with_failing()
        oem.last_checked_at = "2026-03-28T10:00:00+00:00"
        oem._write_repair_flags(failing=["backtest_quality"], warnings=[])

        written = storage.update_sys_config.call_args[0][0]
        value = written["oem_repair_force_backtest"]
        # Debe ser un string de timestamp parseable
        assert isinstance(value, str)
        datetime.fromisoformat(value)  # no debe lanzar excepción

    def test_lifecycle_coherence_fail_dentro_gracia_no_escribe_flag(self):
        """Durante startup grace, lifecycle_coherence FAIL se degrada a WARN y no escribe flags."""
        storage = _make_storage()
        storage.get_sys_config.return_value = {"oem_invariant_grace_seconds": 300}

        oem = OperationalEdgeMonitor(storage=storage, shadow_storage=None, interval_seconds=300)
        oem.last_checked_at = datetime.now(timezone.utc).isoformat()

        failing, warnings, graced = oem._apply_startup_grace(
            failing=["lifecycle_coherence"],
            warnings=[],
        )
        oem._write_repair_flags(failing=failing, warnings=warnings)

        assert failing == []
        assert "lifecycle_coherence" in warnings
        assert graced == ["lifecycle_coherence"]
        storage.update_sys_config.assert_not_called()

    def test_lifecycle_coherence_fail_fuera_gracia_si_escribe_flag(self):
        """Fuera de startup grace, lifecycle_coherence FAIL sí genera force_backtest."""
        storage = _make_storage()
        storage.get_sys_config.return_value = {"oem_invariant_grace_seconds": 300}

        oem = OperationalEdgeMonitor(storage=storage, shadow_storage=None, interval_seconds=300)
        oem._started_at_utc = datetime.now(timezone.utc) - timedelta(minutes=10)
        oem.last_checked_at = datetime.now(timezone.utc).isoformat()

        failing, warnings, graced = oem._apply_startup_grace(
            failing=["lifecycle_coherence"],
            warnings=[],
        )
        oem._write_repair_flags(failing=failing, warnings=warnings)

        assert graced == []
        written = storage.update_sys_config.call_args[0][0]
        assert "oem_repair_force_backtest" in written

    def test_lifecycle_coherence_warn_no_accionable_no_escribe_flag(self):
        """Si lifecycle_coherence llega como WARN no accionable, no debe armar force_backtest."""
        oem, storage, _ = _make_oem_with_failing()
        oem._write_repair_flags(failing=[], warnings=["lifecycle_coherence"])

        storage.update_sys_config.assert_not_called()


# ── Tests: _consume_oem_repair_flags (MainOrchestrator) ──────────────────────

class TestConsumeRepairFlags:
    """
    Verifica que MainOrchestrator._consume_oem_repair_flags() aplica las acciones
    correctas al leer cada flag y los limpia después de consumirlos.
    """

    def _make_orchestrator(self, config: dict) -> MagicMock:
        """Crea un mock del MainOrchestrator con el sys_config especificado."""
        from core_brain.main_orchestrator import MainOrchestrator
        storage = MagicMock()
        storage.get_sys_config.return_value = config
        storage.update_sys_config.return_value = None

        orch = MagicMock(spec=MainOrchestrator)
        orch.storage = storage
        orch._last_backtest_run = datetime.now(timezone.utc)
        orch._last_ranking_cycle = datetime.now(timezone.utc)
        orch._ranking_interval = 300
        orch.scanner = MagicMock()
        orch.scanner.last_scan_time = {"EURUSD_M15": 12345.0}

        # Usamos el método real del orchestrator sobre el mock
        orch._consume_oem_repair_flags = lambda: MainOrchestrator._consume_oem_repair_flags(orch)
        return orch

    @pytest.mark.asyncio
    async def test_force_backtest_resetea_last_backtest_run(self):
        """Flag force_backtest → _last_backtest_run = None."""
        orch = self._make_orchestrator({"oem_repair_force_backtest": "2026-03-28T10:00:00+00:00"})
        await orch._consume_oem_repair_flags()

        assert orch._last_backtest_run is None

    @pytest.mark.asyncio
    async def test_force_ohlc_reload_limpia_last_scan_time(self):
        """Flag force_ohlc_reload → scanner.last_scan_time.clear()."""
        orch = self._make_orchestrator({"oem_repair_force_ohlc_reload": "2026-03-28T10:00:00+00:00"})
        await orch._consume_oem_repair_flags()

        assert len(orch.scanner.last_scan_time) == 0

    @pytest.mark.asyncio
    async def test_force_ranking_adelanta_last_ranking_cycle(self):
        """Flag force_ranking → _last_ranking_cycle queda en el pasado."""
        orch = self._make_orchestrator({"oem_repair_force_ranking": "2026-03-28T10:00:00+00:00"})
        before = datetime.now(timezone.utc)
        await orch._consume_oem_repair_flags()

        # El ranking cycle debe estar suficientemente en el pasado para disparar
        elapsed = (before - orch._last_ranking_cycle).total_seconds()
        assert elapsed > orch._ranking_interval

    @pytest.mark.asyncio
    async def test_flags_se_limpian_despues_de_consumir(self):
        """Después de consumir, los flags se escriben como None en sys_config."""
        orch = self._make_orchestrator({"oem_repair_force_backtest": "2026-03-28T10:00:00+00:00"})
        await orch._consume_oem_repair_flags()

        orch.storage.update_sys_config.assert_called_once()
        cleared = orch.storage.update_sys_config.call_args[0][0]
        assert cleared.get("oem_repair_force_backtest") is None

    @pytest.mark.asyncio
    async def test_sin_flags_no_modifica_nada(self):
        """Sin flags en sys_config → no altera ningún atributo del orchestrator."""
        orch = self._make_orchestrator({})
        original_backtest = orch._last_backtest_run
        original_scan = dict(orch.scanner.last_scan_time)

        await orch._consume_oem_repair_flags()

        assert orch._last_backtest_run == original_backtest
        assert dict(orch.scanner.last_scan_time) == original_scan
        orch.storage.update_sys_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_flag_none_no_es_accionable(self):
        """Flag con valor None (ya consumido) no dispara acción."""
        orch = self._make_orchestrator({"oem_repair_force_backtest": None})
        original = orch._last_backtest_run
        await orch._consume_oem_repair_flags()

        assert orch._last_backtest_run == original


# ── Tests: endpoint /system/audit/repair ─────────────────────────────────────

class TestRepairEndpoint:

    @pytest.mark.asyncio
    async def test_stage_backtest_quality_escribe_flag_real(self):
        """stage=backtest_quality → escribe oem_repair_force_backtest en DB."""
        mock_storage = MagicMock()
        mock_storage.update_sys_config.return_value = None

        with patch("core_brain.api.routers.system._get_storage", return_value=mock_storage), \
             patch("core_brain.api.routers.system._broadcast_thought", new_callable=AsyncMock):
            from core_brain.api.routers.system import repair_integrity_vector
            result = await repair_integrity_vector({"stage": "backtest_quality"})

        assert result["success"] is True
        assert result["action"] == "oem_repair_force_backtest"
        written = mock_storage.update_sys_config.call_args[0][0]
        assert "oem_repair_force_backtest" in written

    @pytest.mark.asyncio
    async def test_stage_adx_sanity_escribe_flag_ohlc(self):
        """stage=adx_sanity → escribe oem_repair_force_ohlc_reload en DB."""
        mock_storage = MagicMock()
        with patch("core_brain.api.routers.system._get_storage", return_value=mock_storage), \
             patch("core_brain.api.routers.system._broadcast_thought", new_callable=AsyncMock):
            from core_brain.api.routers.system import repair_integrity_vector
            result = await repair_integrity_vector({"stage": "adx_sanity"})

        assert result["action"] == "oem_repair_force_ohlc_reload"

    @pytest.mark.asyncio
    async def test_stage_shadow_sync_retorna_human_required(self):
        """stage=shadow_sync → no auto-reparable, retorna human_required."""
        mock_storage = MagicMock()
        with patch("core_brain.api.routers.system._get_storage", return_value=mock_storage), \
             patch("core_brain.api.routers.system._broadcast_thought", new_callable=AsyncMock):
            from core_brain.api.routers.system import repair_integrity_vector
            result = await repair_integrity_vector({"stage": "shadow_sync"})

        assert result["success"] is False
        assert result["action"] == "human_required"
        mock_storage.update_sys_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_stage_vacio_levanta_400(self):
        """Sin stage → HTTPException 400."""
        from fastapi import HTTPException
        from core_brain.api.routers.system import repair_integrity_vector
        with pytest.raises(HTTPException) as exc_info:
            await repair_integrity_vector({})
        assert exc_info.value.status_code == 400
