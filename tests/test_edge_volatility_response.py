"""
tests/test_edge_volatility_response.py — TDD: Respuesta EDGE ante Volatilidad Extrema
=======================================================================================

ETI_ID: EDGE_Volatility_Response_2026-04-16

Cubre:
  - Emisión de eventos en AnomalySentinel (LOCKDOWN, WARNING, NONE)
  - Transiciones de estado en VolatilityResponseManager
  - Auto-reversión tras N lecturas NONE consecutivas
  - Despacho de alertas y persistencia de estado en sys_config
  - Propagación de Trace_ID
  - Integración OEM ↔ VRM
"""

import pytest
from unittest.mock import MagicMock, call

from core_brain.services.anomaly_sentinel import AnomalySentinel, DefenseProtocol, VolatilityEvent
from core_brain.services.edge_volatility_responder import (
    VolatilityResponseManager,
    VolatilityResponseState,
)
from utils.alerting import AlertSeverity


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {}
    storage.update_sys_config.return_value = None
    storage.log_audit_event.return_value = None
    return storage


@pytest.fixture
def mock_alerting():
    from utils.alerting import AlertingService
    svc = MagicMock(spec=AlertingService)
    svc.send_alert.return_value = {"log_only": True}
    return svc


@pytest.fixture
def sentinel(mock_storage):
    return AnomalySentinel(storage=mock_storage, zscore_threshold=3.0, tick_window=15)


@pytest.fixture
def vrm(mock_storage, mock_alerting):
    return VolatilityResponseManager(
        storage=mock_storage,
        alerting_service=mock_alerting,
        auto_revert_consecutive=2,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _push_crash_ticks(sentinel: AnomalySentinel, n_baseline: int = 8) -> None:
    """Alimenta ticks con un crash extremo al final (Z-Score >> threshold)."""
    base = 1.1000
    for i in range(n_baseline):
        sentinel.push_tick(base + i * 0.0001)
    sentinel.push_tick(base - 0.06)  # caída brusca ~6% desde la base


def _push_elevated_ticks(sentinel: AnomalySentinel, n_baseline: int = 8) -> None:
    """Alimenta ticks con retorno elevado pero por debajo de LOCKDOWN."""
    base = 1.1000
    for i in range(n_baseline):
        sentinel.push_tick(base + i * 0.0001)
    sentinel.push_tick(base - 0.015)  # caída moderada


def _push_normal_ticks(sentinel: AnomalySentinel, n: int = 10) -> None:
    """Alimenta ticks con retornos normales."""
    base = 1.1000
    for i in range(n):
        sentinel.push_tick(base + i * 0.00005)


# ── Tests: emisión de eventos del AnomalySentinel ────────────────────────────

class TestAnomalySentinelEventEmission:

    def test_emits_lockdown_event_on_flash_crash(self, sentinel):
        events = []
        sentinel.register_listener(events.append)
        _push_crash_ticks(sentinel)

        sentinel.get_defense_protocol()

        assert len(events) == 1
        assert events[0].protocol == DefenseProtocol.LOCKDOWN
        assert events[0].z_score is not None
        assert abs(events[0].z_score) >= 3.0

    def test_event_carries_trace_id(self, sentinel):
        events = []
        sentinel.register_listener(events.append)
        _push_crash_ticks(sentinel)

        sentinel.get_defense_protocol()

        assert events[0].trace_id == sentinel.last_trace_id
        assert events[0].trace_id.startswith("SEN-")

    def test_no_event_on_normal_market(self, sentinel):
        events = []
        sentinel.register_listener(events.append)
        _push_normal_ticks(sentinel)

        sentinel.get_defense_protocol()

        assert len(events) == 0

    def test_emits_warning_on_spread_anomaly(self, mock_storage):
        sen = AnomalySentinel(storage=mock_storage, spread_ratio_threshold=2.0, tick_window=15)
        events = []
        sen.register_listener(events.append)
        for _ in range(8):
            sen.push_tick(1.1000, spread=0.001)
        sen.push_tick(1.1000, spread=0.010)  # 10× el promedio histórico

        sen.get_defense_protocol()

        assert len(events) == 1
        assert events[0].protocol == DefenseProtocol.WARNING
        assert events[0].spread_ratio is not None
        assert events[0].spread_ratio >= 2.0

    def test_all_listeners_notified(self, sentinel):
        received_a, received_b = [], []
        sentinel.register_listener(received_a.append)
        sentinel.register_listener(received_b.append)
        _push_crash_ticks(sentinel)

        sentinel.get_defense_protocol()

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_listener_exception_does_not_propagate(self, sentinel):
        def bad_listener(event):
            raise RuntimeError("listener falla")

        sentinel.register_listener(bad_listener)
        _push_crash_ticks(sentinel)

        result = sentinel.get_defense_protocol()

        assert result == DefenseProtocol.LOCKDOWN

    def test_event_has_timestamp(self, sentinel):
        events = []
        sentinel.register_listener(events.append)
        _push_crash_ticks(sentinel)

        sentinel.get_defense_protocol()

        assert events[0].timestamp != ""


# ── Tests: transiciones de estado del VRM ────────────────────────────────────

class TestVolatilityResponseManagerStateTransitions:

    def test_initial_state_is_normal(self, vrm):
        assert vrm.get_state() == VolatilityResponseState.NORMAL

    def test_transitions_to_lockdown_on_lockdown_event(self, vrm):
        event = VolatilityEvent("SEN-ABCD0001", DefenseProtocol.LOCKDOWN, 4.5, 0.0)

        vrm.on_volatility_event(event)

        assert vrm.get_state() == VolatilityResponseState.LOCKDOWN

    def test_transitions_to_elevated_on_warning_event(self, vrm):
        event = VolatilityEvent("SEN-WARN0001", DefenseProtocol.WARNING, 2.1, 0.0)

        vrm.on_volatility_event(event)

        assert vrm.get_state() == VolatilityResponseState.ELEVATED

    def test_stays_lockdown_when_warning_arrives_during_lockdown(self, vrm):
        lockdown = VolatilityEvent("SEN-LOCK0001", DefenseProtocol.LOCKDOWN, 5.0, 0.0)
        warning = VolatilityEvent("SEN-WARN0002", DefenseProtocol.WARNING, 2.5, 0.0)

        vrm.on_volatility_event(lockdown)
        vrm.on_volatility_event(warning)

        assert vrm.get_state() == VolatilityResponseState.LOCKDOWN


# ── Tests: auto-reversión ─────────────────────────────────────────────────────

class TestVolatilityResponseManagerAutoReversal:

    def test_auto_reverts_after_consecutive_none(self, vrm):
        event = VolatilityEvent("SEN-X001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)
        vrm.on_volatility_event(event)

        mock_sentinel = MagicMock()
        mock_sentinel.get_defense_protocol.return_value = DefenseProtocol.NONE
        mock_sentinel.last_trace_id = "SEN-REVERT01"

        vrm.check_auto_reversal(mock_sentinel)  # 1.º NONE
        assert vrm.get_state() == VolatilityResponseState.LOCKDOWN

        vrm.check_auto_reversal(mock_sentinel)  # 2.º NONE → revertir (consecutive=2)
        assert vrm.get_state() == VolatilityResponseState.NORMAL

    def test_resets_counter_when_anomaly_persists(self, vrm):
        event = VolatilityEvent("SEN-X002", DefenseProtocol.LOCKDOWN, 4.0, 0.0)
        vrm.on_volatility_event(event)

        mock_sentinel = MagicMock()
        mock_sentinel.get_defense_protocol.side_effect = [
            DefenseProtocol.NONE,
            DefenseProtocol.LOCKDOWN,  # reset
            DefenseProtocol.NONE,
        ]
        mock_sentinel.last_trace_id = "SEN-RESET01"

        vrm.check_auto_reversal(mock_sentinel)  # 1.º NONE
        vrm.check_auto_reversal(mock_sentinel)  # LOCKDOWN → reset contador
        vrm.check_auto_reversal(mock_sentinel)  # 1.º NONE de nuevo

        assert vrm.get_state() == VolatilityResponseState.LOCKDOWN

    def test_no_reversal_check_when_already_normal(self, vrm):
        mock_sentinel = MagicMock()
        mock_sentinel.last_trace_id = "SEN-NOP"

        vrm.check_auto_reversal(mock_sentinel)
        vrm.check_auto_reversal(mock_sentinel)

        assert vrm.get_state() == VolatilityResponseState.NORMAL
        mock_sentinel.get_defense_protocol.assert_not_called()

    def test_reverts_from_elevated_after_consecutive_none(self, vrm):
        event = VolatilityEvent("SEN-EL001", DefenseProtocol.WARNING, 2.0, 0.0)
        vrm.on_volatility_event(event)

        mock_sentinel = MagicMock()
        mock_sentinel.get_defense_protocol.return_value = DefenseProtocol.NONE
        mock_sentinel.last_trace_id = "SEN-ELREV"

        vrm.check_auto_reversal(mock_sentinel)
        vrm.check_auto_reversal(mock_sentinel)

        assert vrm.get_state() == VolatilityResponseState.NORMAL


# ── Tests: side-effects (alertas, persistencia, auditoría) ────────────────────

class TestVolatilityResponseManagerSideEffects:

    def test_dispatches_critical_alert_on_lockdown(self, vrm, mock_alerting):
        event = VolatilityEvent("SEN-CRT001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)

        vrm.on_volatility_event(event)

        mock_alerting.send_alert.assert_called_once()
        alert = mock_alerting.send_alert.call_args[0][0]
        assert alert.severity == AlertSeverity.CRITICAL

    def test_dispatches_warning_alert_on_elevated(self, vrm, mock_alerting):
        event = VolatilityEvent("SEN-WRN001", DefenseProtocol.WARNING, 2.1, 0.0)

        vrm.on_volatility_event(event)

        mock_alerting.send_alert.assert_called_once()
        alert = mock_alerting.send_alert.call_args[0][0]
        assert alert.severity == AlertSeverity.WARNING

    def test_no_duplicate_alert_on_repeated_lockdown(self, vrm, mock_alerting):
        event = VolatilityEvent("SEN-DUP001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)

        vrm.on_volatility_event(event)
        vrm.on_volatility_event(event)  # mismo estado → sin segunda alerta

        assert mock_alerting.send_alert.call_count == 1

    def test_persists_lockdown_state_in_sys_config(self, vrm, mock_storage):
        event = VolatilityEvent("SEN-PST001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)

        vrm.on_volatility_event(event)

        all_updates = [c[0][0] for c in mock_storage.update_sys_config.call_args_list]
        state_updates = [u for u in all_updates if "edge_volatility_state" in u]
        assert any(u["edge_volatility_state"] == "LOCKDOWN" for u in state_updates)

    def test_persists_reduced_risk_factor_on_lockdown(self, vrm, mock_storage):
        event = VolatilityEvent("SEN-RSK001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)

        vrm.on_volatility_event(event)

        all_updates = [c[0][0] for c in mock_storage.update_sys_config.call_args_list]
        risk_updates = [u for u in all_updates if "edge_volatility_risk_factor" in u]
        assert any(float(u["edge_volatility_risk_factor"]) < 1.0 for u in risk_updates)

    def test_trace_id_persisted_in_sys_config(self, vrm, mock_storage):
        trace_id = "SEN-TRACE0001"
        event = VolatilityEvent(trace_id, DefenseProtocol.LOCKDOWN, 4.0, 0.0)

        vrm.on_volatility_event(event)

        all_updates = [c[0][0] for c in mock_storage.update_sys_config.call_args_list]
        trace_updates = [u for u in all_updates if "edge_volatility_last_trace_id" in u]
        assert any(u["edge_volatility_last_trace_id"] == trace_id for u in trace_updates)

    def test_restores_risk_factor_on_auto_reversal(self, vrm, mock_storage):
        event = VolatilityEvent("SEN-R001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)
        vrm.on_volatility_event(event)
        mock_storage.reset_mock()

        mock_sentinel = MagicMock()
        mock_sentinel.get_defense_protocol.return_value = DefenseProtocol.NONE
        mock_sentinel.last_trace_id = "SEN-REV001"

        vrm.check_auto_reversal(mock_sentinel)
        vrm.check_auto_reversal(mock_sentinel)

        all_updates = [c[0][0] for c in mock_storage.update_sys_config.call_args_list]
        risk_updates = [u for u in all_updates if "edge_volatility_risk_factor" in u]
        assert any(float(u["edge_volatility_risk_factor"]) == 1.0 for u in risk_updates)

    def test_logs_audit_event_on_lockdown(self, vrm, mock_storage):
        event = VolatilityEvent("SEN-AUD001", DefenseProtocol.LOCKDOWN, 4.0, 0.0)

        vrm.on_volatility_event(event)

        mock_storage.log_audit_event.assert_called()
        audit_kwargs = mock_storage.log_audit_event.call_args[1]
        assert audit_kwargs.get("action") == "LOCKDOWN_RESPONSE"
        assert audit_kwargs.get("resource_id") == "SEN-AUD001"


# ── Tests: integración OEM ↔ VRM ─────────────────────────────────────────────

class TestOEMVolatilityIntegration:

    def test_oem_creates_vrm_when_sentinel_injected(self, mock_storage, mock_alerting):
        from core_brain.operational_edge_monitor import OperationalEdgeMonitor

        sen = AnomalySentinel(storage=mock_storage)
        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            alerting_service=mock_alerting,
            sentinel=sen,
        )

        assert oem._vrm is not None

    def test_oem_vrm_is_none_without_sentinel(self, mock_storage, mock_alerting):
        from core_brain.operational_edge_monitor import OperationalEdgeMonitor

        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            alerting_service=mock_alerting,
        )

        assert oem._vrm is None

    def test_oem_vrm_responds_to_crash_event(self, mock_storage, mock_alerting):
        from core_brain.operational_edge_monitor import OperationalEdgeMonitor

        sen = AnomalySentinel(storage=mock_storage, zscore_threshold=3.0)
        oem = OperationalEdgeMonitor(
            storage=mock_storage,
            alerting_service=mock_alerting,
            sentinel=sen,
        )

        _push_crash_ticks(sen)
        sen.get_defense_protocol()

        assert oem._vrm.get_state() == VolatilityResponseState.LOCKDOWN
