"""
test_edge_lockdown_degradation.py — TDD: ETI EDGE_Lockdown_Degradation_Granular_2026-04-16

Criterios de aceptación (spec §5):
  [AC-1] El sistema nunca detiene la gestión de operaciones abiertas.
  [AC-2] Solo se degradan módulos afectados (SignalFactory, Scanner, Backtest).
  [AC-3] "Close-only mode" funcional y testeado.
  [AC-4] Fallback de logging/auditoría robusto.
  [AC-5] Auto-reversión EDGE implementada.
  [AC-6] Tests TDD pasan.

Naming: test_<componente>_<comportamiento>
"""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch, AsyncMock

import pytest

from core_brain.close_only_guard import CloseOnlyGuard
from core_brain.services.order_gate import OrderGate
from core_brain.resilience import (
    EdgeAction,
    EdgeEventReport,
    ResilienceLevel,
    SystemPosture,
)
from core_brain.resilience_manager import ResilienceManager
from models.signal import Signal, SignalType, ConnectorType


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_storage() -> MagicMock:
    """Minimal StorageManager mock."""
    storage = MagicMock()
    conn = MagicMock()
    conn.execute.return_value = None
    conn.commit.return_value = None
    storage._get_conn.return_value = conn
    return storage


def _make_lockdown_report(scope: str = "AnomalySentinel") -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.GLOBAL,
        scope=scope,
        action=EdgeAction.LOCKDOWN,
        reason="Flash crash detectado — test",
    )


def _make_signal(signal_type: SignalType, symbol: str = "XAUUSD") -> Signal:
    return Signal(
        symbol=symbol,
        signal_type=signal_type,
        connector_type=ConnectorType.METATRADER5,
        timeframe="H1",
        entry_price=1900.0,
        stop_loss=1880.0,
        take_profit=1930.0,
        confidence=0.8,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# CloseOnlyGuard tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestCloseOnlyGuard:
    """[AC-1][AC-3] CloseOnlyGuard unit tests."""

    def test_close_only_guard_inicial_inactivo(self):
        """El guard arranca desactivado."""
        guard = CloseOnlyGuard()
        assert guard.is_active is False

    def test_close_only_guard_activate_bloquea_apertura(self):
        """[AC-3] Tras activación, can_open_position() → False."""
        guard = CloseOnlyGuard()
        guard.activate()
        assert guard.can_open_position() is False

    def test_close_only_guard_activate_permite_cierre(self):
        """[AC-1] Tras activación, can_close_position() → True siempre."""
        guard = CloseOnlyGuard()
        guard.activate()
        assert guard.can_close_position() is True

    def test_close_only_guard_inactivo_permite_apertura(self):
        """Sin activar, can_open_position() → True."""
        guard = CloseOnlyGuard()
        assert guard.can_open_position() is True

    def test_close_only_guard_deactivate_restaura_apertura(self):
        """Deactivate restaura can_open_position() a True."""
        guard = CloseOnlyGuard()
        guard.activate()
        guard.deactivate()
        assert guard.can_open_position() is True

    def test_close_only_guard_auto_revert_cuando_condicion_normalizada(self):
        """[AC-5] check_auto_revert() desactiva si callback retorna True."""
        guard = CloseOnlyGuard(auto_revert_check_fn=lambda: True)
        guard.activate()
        reverted = guard.check_auto_revert()
        assert reverted is True
        assert guard.is_active is False

    def test_close_only_guard_auto_revert_no_revierte_si_sigue_activo(self):
        """[AC-5] check_auto_revert() NO desactiva si condición sigue activa."""
        guard = CloseOnlyGuard(auto_revert_check_fn=lambda: False)
        guard.activate()
        reverted = guard.check_auto_revert()
        assert reverted is False
        assert guard.is_active is True

    def test_close_only_guard_auto_revert_no_opera_si_inactivo(self):
        """check_auto_revert() no hace nada si el guard ya está inactivo."""
        guard = CloseOnlyGuard(auto_revert_check_fn=lambda: True)
        reverted = guard.check_auto_revert()
        assert reverted is False

    def test_close_only_guard_auto_revert_exception_en_callback_no_falla(self):
        """[AC-4] Excepción en callback → retorna False, no propaga excepción."""
        def bad_check():
            raise RuntimeError("fallo de red")

        guard = CloseOnlyGuard(auto_revert_check_fn=bad_check)
        guard.activate()
        reverted = guard.check_auto_revert()  # no debe lanzar
        assert reverted is False
        assert guard.is_active is True  # sigue activo


# ═══════════════════════════════════════════════════════════════════════════════
# OrderGate tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestOrderGate:
    """[AC-3] OrderGate — bloquea BUY/SELL, permite CLOSE en close-only mode."""

    def _gate_active(self) -> OrderGate:
        guard = CloseOnlyGuard()
        guard.activate()
        return OrderGate(close_only_guard=guard)

    def _gate_normal(self) -> OrderGate:
        return OrderGate(close_only_guard=CloseOnlyGuard())

    def test_order_gate_bloquea_buy_en_close_only(self):
        """[AC-3] BUY rechazado cuando close-only activo."""
        gate = self._gate_active()
        allowed, reason = gate.is_allowed(_make_signal(SignalType.BUY))
        assert allowed is False
        assert "BUY" in reason

    def test_order_gate_bloquea_sell_en_close_only(self):
        """[AC-3] SELL rechazado cuando close-only activo."""
        gate = self._gate_active()
        allowed, reason = gate.is_allowed(_make_signal(SignalType.SELL))
        assert allowed is False
        assert "SELL" in reason

    def test_order_gate_permite_close_en_close_only(self):
        """[AC-1] CLOSE permitido incluso en close-only mode."""
        gate = self._gate_active()
        allowed, reason = gate.is_allowed(_make_signal(SignalType.CLOSE))
        assert allowed is True
        assert reason == ""

    def test_order_gate_permite_buy_en_modo_normal(self):
        """Sin close-only, BUY pasa."""
        gate = self._gate_normal()
        allowed, _ = gate.is_allowed(_make_signal(SignalType.BUY))
        assert allowed is True

    def test_order_gate_permite_sell_en_modo_normal(self):
        """Sin close-only, SELL pasa."""
        gate = self._gate_normal()
        allowed, _ = gate.is_allowed(_make_signal(SignalType.SELL))
        assert allowed is True


# ═══════════════════════════════════════════════════════════════════════════════
# ResilienceManager — Degradación Granular
# ═══════════════════════════════════════════════════════════════════════════════

class TestResilienceManagerGranularDegradation:
    """[AC-2] Solo se degradan módulos afectados."""

    def _manager(self, **kwargs) -> ResilienceManager:
        return ResilienceManager(storage=_make_storage(), **kwargs)

    def test_resilience_manager_degrade_module_registra_modulo(self):
        """degrade_module() registra el módulo como degradado."""
        mgr = self._manager()
        mgr.degrade_module("SignalFactory")
        assert mgr.is_module_degraded("SignalFactory") is True

    def test_resilience_manager_restore_module_elimina_degradacion(self):
        """restore_module() elimina al módulo del registro de degradados."""
        mgr = self._manager()
        mgr.degrade_module("SignalFactory")
        mgr.restore_module("SignalFactory")
        assert mgr.is_module_degraded("SignalFactory") is False

    def test_resilience_manager_modulo_no_degradado_por_defecto(self):
        """Un módulo no tocado no aparece como degradado."""
        mgr = self._manager()
        assert mgr.is_module_degraded("PositionManager") is False

    def test_resilience_manager_lockdown_degrada_modulos_no_criticos(self):
        """[AC-2] LOCKDOWN → SignalFactory, Scanner, Backtest se degradan."""
        guard = CloseOnlyGuard()
        mgr = self._manager(close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())
        assert mgr.is_module_degraded("SignalFactory") is True
        assert mgr.is_module_degraded("Scanner") is True
        assert mgr.is_module_degraded("Backtest") is True

    def test_resilience_manager_lockdown_no_degrada_position_manager(self):
        """[AC-1] LOCKDOWN → PositionManager NUNCA se degrada."""
        guard = CloseOnlyGuard()
        mgr = self._manager(close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())
        assert mgr.is_module_degraded("PositionManager") is False

    def test_resilience_manager_lockdown_no_degrada_executor(self):
        """[AC-1] LOCKDOWN → Executor NUNCA se degrada."""
        guard = CloseOnlyGuard()
        mgr = self._manager(close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())
        assert mgr.is_module_degraded("Executor") is False

    def test_resilience_manager_lockdown_no_degrada_risk_manager(self):
        """[AC-1] LOCKDOWN → RiskManager NUNCA se degrada."""
        guard = CloseOnlyGuard()
        mgr = self._manager(close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())
        assert mgr.is_module_degraded("RiskManager") is False


# ═══════════════════════════════════════════════════════════════════════════════
# ResilienceManager — Close-Only Mode
# ═══════════════════════════════════════════════════════════════════════════════

class TestResilienceManagerCloseOnly:
    """[AC-3] Close-only mode activado en LOCKDOWN."""

    def _manager_with_guard(self) -> tuple[ResilienceManager, CloseOnlyGuard]:
        guard = CloseOnlyGuard()
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        return mgr, guard

    def test_resilience_manager_lockdown_activa_close_only(self):
        """[AC-3] LOCKDOWN → close_only_mode=True."""
        mgr, guard = self._manager_with_guard()
        mgr.process_report(_make_lockdown_report())
        assert mgr.close_only_mode is True

    def test_resilience_manager_no_lockdown_no_close_only(self):
        """Sin LOCKDOWN, close_only_mode permanece False."""
        mgr, guard = self._manager_with_guard()
        report = EdgeEventReport(
            level=ResilienceLevel.ASSET,
            scope="XAUUSD",
            action=EdgeAction.MUTE,
            reason="test",
        )
        mgr.process_report(report)
        assert mgr.close_only_mode is False

    def test_resilience_manager_sin_guard_inyectado_lockdown_no_falla(self):
        """[AC-4] Sin guard inyectado, LOCKDOWN no lanza excepción."""
        mgr = ResilienceManager(storage=_make_storage())  # sin guard
        report = _make_lockdown_report()
        posture = mgr.process_report(report)  # no debe lanzar
        assert posture == SystemPosture.STRESSED


# ═══════════════════════════════════════════════════════════════════════════════
# ResilienceManager — Auto-Reversión
# ═══════════════════════════════════════════════════════════════════════════════

class TestResilienceManagerAutoReversion:
    """[AC-5] Auto-reversión cuando la condición se normaliza."""

    def test_resilience_manager_try_auto_revert_restaura_modulos(self):
        """[AC-5] try_auto_revert() restaura módulos degradados si condición OK."""
        guard = CloseOnlyGuard(auto_revert_check_fn=lambda: True)
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())

        assert mgr.is_module_degraded("SignalFactory") is True
        assert mgr.close_only_mode is True

        reverted = mgr.try_auto_revert()

        assert reverted is True
        assert mgr.close_only_mode is False
        assert mgr.is_module_degraded("SignalFactory") is False
        assert mgr.is_module_degraded("Scanner") is False
        assert mgr.is_module_degraded("Backtest") is False

    def test_resilience_manager_try_auto_revert_no_revierte_si_condicion_activa(self):
        """[AC-5] try_auto_revert() no actúa si condición sigue activa."""
        guard = CloseOnlyGuard(auto_revert_check_fn=lambda: False)
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())

        reverted = mgr.try_auto_revert()

        assert reverted is False
        assert mgr.close_only_mode is True
        assert mgr.is_module_degraded("SignalFactory") is True

    def test_resilience_manager_try_auto_revert_sin_guard_retorna_false(self):
        """Sin guard inyectado, try_auto_revert() retorna False sin error."""
        mgr = ResilienceManager(storage=_make_storage())
        reverted = mgr.try_auto_revert()
        assert reverted is False


# ═══════════════════════════════════════════════════════════════════════════════
# ResilienceManager — Fallback de Auditoría
# ═══════════════════════════════════════════════════════════════════════════════

class TestResilienceManagerAuditFallback:
    """[AC-4] Fallback robusto cuando el storage de auditoría falla."""

    def test_resilience_manager_audit_fallback_continua_si_db_falla(self):
        """[AC-4] Si el DB lanza en INSERT, el sistema continúa sin excepción."""
        storage = MagicMock()
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB bloqueada")
        storage._get_conn.return_value = conn

        mgr = ResilienceManager(storage=storage)
        report = _make_lockdown_report()
        posture = mgr.process_report(report)  # no debe lanzar

        assert posture == SystemPosture.STRESSED

    def test_resilience_manager_audit_fallback_loguea_advertencia(self, caplog):
        """[AC-4] Cuando DB falla, se loguea un WARNING con el error."""
        storage = MagicMock()
        conn = MagicMock()
        conn.execute.side_effect = Exception("DB test error")
        storage._get_conn.return_value = conn

        mgr = ResilienceManager(storage=storage)
        with caplog.at_level(logging.WARNING, logger="core_brain.resilience_manager"):
            mgr.process_report(_make_lockdown_report())

        assert any("persist" in r.message.lower() or "audit" in r.message.lower()
                   for r in caplog.records)


# ═══════════════════════════════════════════════════════════════════════════════
# _guard_suite — LOCKDOWN activa close-only, NO cancel_all
# ═══════════════════════════════════════════════════════════════════════════════

class TestGuardSuiteLockdown:
    """[AC-1][AC-3] write_anomaly_lockdown activa close-only, no para sistema."""

    @pytest.mark.asyncio
    async def test_guard_suite_lockdown_activa_close_only(self):
        """
        [AC-3] Close-only mode se activa vía ResilienceManager.process_report() al recibir
        LOCKDOWN — no mediante una llamada directa desde write_anomaly_lockdown (que causaba
        duplicación). El guard suite solo loguea y persiste el registro de auditoría.
        """
        from core_brain.orchestrators._guard_suite import write_anomaly_lockdown

        guard = CloseOnlyGuard()
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)

        # Simula el flujo real: process_report activa close-only ANTES de que
        # _guard_suite sea invocado.
        mgr.process_report(_make_lockdown_report())
        assert guard.is_active is True  # activado por process_report, no por guard suite

        orch = MagicMock()
        orch.storage = _make_storage()
        orch.resilience_manager = mgr

        # write_anomaly_lockdown ya no reactiva el protocolo (evita duplicación).
        # El guard sigue activo después de la llamada.
        await write_anomaly_lockdown(orch, trace_id="TEST-TRACE-001")
        assert guard.is_active is True

    @pytest.mark.asyncio
    async def test_guard_suite_lockdown_no_llama_cancel_all(self):
        """[AC-1] write_anomaly_lockdown NO llama cancel_all_pending_orders en el executor."""
        from core_brain.orchestrators._guard_suite import write_anomaly_lockdown

        orch = MagicMock()
        orch.storage = _make_storage()
        orch.resilience_manager = ResilienceManager(storage=_make_storage())
        executor_mock = AsyncMock()
        orch.executor = executor_mock

        await write_anomaly_lockdown(orch, trace_id="TEST-TRACE-002")

        executor_mock.cancel_all_pending_orders.assert_not_called()

    @pytest.mark.asyncio
    async def test_guard_suite_lockdown_sin_resilience_manager_no_falla(self):
        """[AC-4] Si orch no tiene resilience_manager, el lockdown no lanza excepción."""
        from core_brain.orchestrators._guard_suite import write_anomaly_lockdown

        orch = MagicMock()
        orch.storage = _make_storage()
        del orch.resilience_manager  # simula orquestador sin el atributo

        await write_anomaly_lockdown(orch, trace_id="TEST-TRACE-003")  # no debe lanzar


# ═══════════════════════════════════════════════════════════════════════════════
# Integración: Flash crash con posiciones abiertas
# ═══════════════════════════════════════════════════════════════════════════════

class TestFlashCrashIntegration:
    """[AC-1][AC-2][AC-3] Simulación de flash crash con operaciones abiertas."""

    def test_flash_crash_no_bloquea_cierre_de_posiciones(self):
        """
        Simula flash crash: LOCKDOWN activado → OrderGate permite CLOSE
        → posiciones abiertas pueden cerrarse.
        """
        guard = CloseOnlyGuard()
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        gate = OrderGate(close_only_guard=guard)

        # Flash crash → LOCKDOWN
        mgr.process_report(_make_lockdown_report())

        assert mgr.current_posture == SystemPosture.STRESSED
        assert mgr.close_only_mode is True

        # Señal de cierre debe pasar
        close_signal = _make_signal(SignalType.CLOSE, symbol="XAUUSD")
        allowed, _ = gate.is_allowed(close_signal)
        assert allowed is True

    def test_flash_crash_bloquea_nuevas_entradas(self):
        """
        Flash crash: LOCKDOWN activado → OrderGate bloquea BUY y SELL.
        """
        guard = CloseOnlyGuard()
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        gate = OrderGate(close_only_guard=guard)

        mgr.process_report(_make_lockdown_report())

        buy_signal = _make_signal(SignalType.BUY, symbol="EURUSD")
        sell_signal = _make_signal(SignalType.SELL, symbol="GBPUSD")

        assert gate.is_allowed(buy_signal)[0] is False
        assert gate.is_allowed(sell_signal)[0] is False

    def test_flash_crash_solo_degrada_modulos_no_criticos(self):
        """
        Flash crash: solo SignalFactory/Scanner/Backtest degradados.
        PositionManager, RiskManager, Executor permanecen activos.
        """
        guard = CloseOnlyGuard()
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        mgr.process_report(_make_lockdown_report())

        # Degradados
        assert mgr.is_module_degraded("SignalFactory") is True
        assert mgr.is_module_degraded("Scanner") is True
        assert mgr.is_module_degraded("Backtest") is True

        # Protegidos
        assert mgr.is_module_degraded("PositionManager") is False
        assert mgr.is_module_degraded("RiskManager") is False
        assert mgr.is_module_degraded("Executor") is False

    def test_flash_crash_auto_reversion_completa(self):
        """
        [AC-5] Condición se normaliza → auto-reversión restaura sistema.
        """
        guard = CloseOnlyGuard(auto_revert_check_fn=lambda: True)
        mgr = ResilienceManager(storage=_make_storage(), close_only_guard=guard)
        gate = OrderGate(close_only_guard=guard)

        # Activar lockdown
        mgr.process_report(_make_lockdown_report())
        assert mgr.close_only_mode is True

        # Condición normalizada → auto-revert
        mgr.try_auto_revert()
        assert mgr.close_only_mode is False

        # Ahora BUY debe pasar el gate
        buy_signal = _make_signal(SignalType.BUY)
        allowed, _ = gate.is_allowed(buy_signal)
        assert allowed is True
