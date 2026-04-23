"""
test_resilience_autotune.py — Tests TDD para ResilienceAutoTuner (HU 4.1).

Cubre:
  - Suavizado de parámetros tras falso positivo (recuperación prematura).
  - Endurecimiento tras erosión de EDGE post-recuperación.
  - Persistencia y carga de parámetros autoajustados.
  - Auditoría y trazabilidad de cada ajuste.
  - Integración con ResilienceManager (min_stability_cycles).

Trace_ID: ARCH-RESILIENCE-AUTOTUNE-V1
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest

from core_brain.resilience_autotune import (
    DEFAULT_PARAMS,
    PARAM_BOUNDS,
    ResilienceAutoTuner,
    _HARDEN_FACTOR,
    _SOFTEN_FACTOR,
)
from core_brain.resilience import EdgeAction, EdgeEventReport, ResilienceLevel, SystemPosture
from core_brain.close_only_guard import CloseOnlyGuard
from core_brain.resilience_manager import ResilienceManager


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_storage(stored_params: dict | None = None) -> MagicMock:
    """Crea un StorageManager mock con parámetros preconfigurados."""
    storage = MagicMock()
    storage.get_resilience_params.return_value = stored_params or {}
    storage.save_resilience_params.return_value = None
    return storage


def _make_tuner(stored_params: dict | None = None) -> ResilienceAutoTuner:
    return ResilienceAutoTuner(storage=_make_storage(stored_params))


def _make_report(action: EdgeAction = EdgeAction.LOCKDOWN) -> EdgeEventReport:
    return EdgeEventReport(
        level=ResilienceLevel.GLOBAL,
        scope="XAUUSD",
        action=action,
        reason="test event",
    )


# ── Test 1: suavizado tras falso positivo ─────────────────────────────────────

class TestSoftenAfterFalsePositive:
    """
    Dado: el sistema sale de LOCKDOWN demasiado rápido (cycles < min_stability_cycles).
    Esperado: los umbrales bajan un 10 % para reducir falsos positivos futuros.
    """

    def test_autotune_softens_caution_threshold_on_false_positive(self) -> None:
        tuner = _make_tuner()
        original = tuner.get_param("l0_caution_threshold")

        # cycles=1 < min_stability_cycles=3 → falso positivo
        changes = tuner.record_recovery(stability_cycles=1, edge_eroded=False, trace_id="T-001")

        assert "l0_caution_threshold" in changes
        new_val = tuner.get_param("l0_caution_threshold")
        assert new_val < original, "El umbral de CAUTION debe bajar tras falso positivo"

    def test_autotune_softens_degraded_threshold_on_false_positive(self) -> None:
        tuner = _make_tuner()
        original = tuner.get_param("l0_degraded_threshold")

        changes = tuner.record_recovery(stability_cycles=1, edge_eroded=False, trace_id="T-002")

        assert "l0_degraded_threshold" in changes
        assert tuner.get_param("l0_degraded_threshold") < original

    def test_autotune_softens_min_stability_cycles_on_false_positive(self) -> None:
        tuner = _make_tuner()
        original = tuner.get_param("min_stability_cycles")

        changes = tuner.record_recovery(stability_cycles=1, edge_eroded=False, trace_id="T-003")

        assert "min_stability_cycles" in changes
        assert tuner.get_param("min_stability_cycles") < original

    def test_autotune_no_changes_when_recovery_is_correct(self) -> None:
        """Recuperación con cycles >= min_cycles y sin erosión → sin ajuste."""
        tuner = _make_tuner()

        # cycles=3 == min_stability_cycles=3 → recuperación correcta
        changes = tuner.record_recovery(stability_cycles=3, edge_eroded=False, trace_id="T-004")

        assert changes == {}, "No debe haber ajuste si la recuperación es correcta"

    def test_autotune_soften_persists_to_storage(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        tuner.record_recovery(stability_cycles=1, edge_eroded=False, trace_id="T-005")

        storage.save_resilience_params.assert_called_once()
        _, kwargs = storage.save_resilience_params.call_args
        assert kwargs["trace_id"] == "T-005"
        assert "Falso positivo" in kwargs["reason"]


# ── Test 2: endurecimiento tras erosión de EDGE ───────────────────────────────

class TestHardenAfterEdgeErosion:
    """
    Dado: el EDGE se erosiona tras salir de LOCKDOWN (slippage/win-rate empeoró).
    Esperado: los umbrales suben un 15 % para recuperar más lentamente la próxima vez.
    """

    def test_autotune_hardens_caution_threshold_on_edge_erosion(self) -> None:
        tuner = _make_tuner()
        original = tuner.get_param("l0_caution_threshold")

        changes = tuner.record_recovery(stability_cycles=5, edge_eroded=True, trace_id="T-010")

        assert "l0_caution_threshold" in changes
        assert tuner.get_param("l0_caution_threshold") > original

    def test_autotune_hardens_spread_cooldown_on_edge_erosion(self) -> None:
        tuner = _make_tuner()
        original = tuner.get_param("spread_cooldown_seconds")

        changes = tuner.record_recovery(stability_cycles=5, edge_eroded=True, trace_id="T-011")

        assert "spread_cooldown_seconds" in changes
        assert tuner.get_param("spread_cooldown_seconds") > original

    def test_autotune_edge_erosion_takes_priority_over_false_positive(self) -> None:
        """edge_eroded=True debe endurecer incluso si cycles < min_cycles."""
        tuner = _make_tuner()
        original_caution = tuner.get_param("l0_caution_threshold")

        # cycles=1 (falso positivo) pero edge_eroded=True → endurecer (no suavizar)
        changes = tuner.record_recovery(stability_cycles=1, edge_eroded=True, trace_id="T-012")

        assert tuner.get_param("l0_caution_threshold") > original_caution, (
            "El endurecimiento tiene prioridad sobre el suavizado"
        )

    def test_autotune_harden_persists_to_storage(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        tuner.record_recovery(stability_cycles=5, edge_eroded=True, trace_id="T-013")

        storage.save_resilience_params.assert_called_once()
        _, kwargs = storage.save_resilience_params.call_args
        assert kwargs["trace_id"] == "T-013"
        assert "EDGE erosionado" in kwargs["reason"]

    def test_autotune_params_respect_hard_bounds_on_harden(self) -> None:
        """Tras muchos endurecimientoS, ningún parámetro supera su límite superior."""
        tuner = _make_tuner()
        for _ in range(20):
            tuner.record_recovery(stability_cycles=5, edge_eroded=True, trace_id="TX")

        for name, (lo, hi) in PARAM_BOUNDS.items():
            val = float(tuner.get_param(name))
            assert val <= hi, f"Parámetro {name}={val} supera límite superior {hi}"

    def test_autotune_params_respect_hard_bounds_on_soften(self) -> None:
        """Tras muchos suavizados, ningún parámetro cae por debajo de su límite inferior."""
        tuner = _make_tuner()
        for _ in range(20):
            tuner.record_recovery(stability_cycles=1, edge_eroded=False, trace_id="TX")

        for name, (lo, hi) in PARAM_BOUNDS.items():
            val = float(tuner.get_param(name))
            assert val >= lo, f"Parámetro {name}={val} cae bajo límite inferior {lo}"


# ── Test 3: persistencia y carga de parámetros ───────────────────────────────

class TestPersistenceAndLoad:
    """
    Verifica que los parámetros ajustados se persisten y se recargan correctamente.
    """

    def test_autotune_loads_stored_params_on_init(self) -> None:
        custom = {"l0_caution_threshold": 5, "min_stability_cycles": 7}
        tuner = _make_tuner(stored_params=custom)

        assert tuner.get_param("l0_caution_threshold") == 5
        assert tuner.get_param("min_stability_cycles") == 7

    def test_autotune_ignores_unknown_stored_keys(self) -> None:
        custom = {"l0_caution_threshold": 4, "unknown_key": 999}
        tuner = _make_tuner(stored_params=custom)

        assert tuner.get_param("l0_caution_threshold") == 4
        assert tuner.get_all_params().get("unknown_key") is None

    def test_autotune_falls_back_to_defaults_on_storage_error(self) -> None:
        storage = MagicMock()
        storage.get_resilience_params.side_effect = RuntimeError("DB down")
        tuner = ResilienceAutoTuner(storage=storage)

        for name, default in DEFAULT_PARAMS.items():
            assert tuner.get_param(name) == default

    def test_autotune_get_all_params_returns_full_map(self) -> None:
        tuner = _make_tuner()
        params = tuner.get_all_params()

        assert set(params.keys()) == set(DEFAULT_PARAMS.keys())

    def test_autotune_save_includes_full_params_dict(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        tuner.record_recovery(stability_cycles=1, edge_eroded=False, trace_id="T-020")

        _, kwargs = storage.save_resilience_params.call_args
        assert "params" in kwargs
        assert set(kwargs["params"].keys()) == set(DEFAULT_PARAMS.keys())


# ── Test 4: auditoría y trazabilidad ─────────────────────────────────────────

class TestAuditTrail:
    """
    Verifica que cada ajuste queda registrado con trace_id y justificación.
    """

    def test_autotune_no_persist_when_no_changes(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        # Recuperación correcta → sin cambios → sin persistencia
        tuner.record_recovery(stability_cycles=3, edge_eroded=False, trace_id="T-030")

        storage.save_resilience_params.assert_not_called()

    def test_autotune_persist_called_with_trace_id_on_harden(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        tuner.record_recovery(stability_cycles=5, edge_eroded=True, trace_id="TRC-999")

        storage.save_resilience_params.assert_called_once()
        _, kwargs = storage.save_resilience_params.call_args
        assert kwargs["trace_id"] == "TRC-999"

    def test_autotune_generates_trace_id_when_empty(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        tuner.record_recovery(stability_cycles=5, edge_eroded=True, trace_id="")

        _, kwargs = storage.save_resilience_params.call_args
        assert kwargs["trace_id"], "Debe generarse un trace_id si no se pasa ninguno"

    def test_autotune_reason_includes_cycle_count(self) -> None:
        storage = _make_storage()
        tuner = ResilienceAutoTuner(storage=storage)

        tuner.record_recovery(stability_cycles=2, edge_eroded=False, trace_id="T-031")

        _, kwargs = storage.save_resilience_params.call_args
        assert "cycles=2" in kwargs["reason"]


# ── Test 5: integración con ResilienceManager ─────────────────────────────────

class TestResilienceManagerIntegration:
    """
    Verifica que ResilienceManager respeta min_stability_cycles del AutoTuner
    y llama a record_recovery tras una reversión exitosa.
    """

    def _make_guard(self, revert_result: bool = True) -> CloseOnlyGuard:
        guard = MagicMock(spec=CloseOnlyGuard)
        guard.is_active = True
        guard.check_auto_revert.return_value = revert_result
        return guard

    def test_manager_blocks_revert_before_min_cycles(self) -> None:
        """Si min_stability_cycles=3 y solo se llamó 1 vez, la reversión debe bloquearse."""
        storage = _make_storage({"min_stability_cycles": 3})
        tuner = ResilienceAutoTuner(storage=storage)
        guard = self._make_guard(revert_result=True)

        manager = ResilienceManager(
            storage=MagicMock(),
            close_only_guard=guard,
            auto_tuner=tuner,
        )
        manager._current_posture = SystemPosture.STRESSED

        result = manager.try_auto_revert()

        assert result is False
        guard.check_auto_revert.assert_not_called()

    def test_manager_allows_revert_after_min_cycles(self) -> None:
        """Tras min_stability_cycles llamadas, la reversión debe proceder."""
        storage = _make_storage({"min_stability_cycles": 2})
        tuner = ResilienceAutoTuner(storage=storage)
        guard = self._make_guard(revert_result=True)

        manager = ResilienceManager(
            storage=MagicMock(),
            close_only_guard=guard,
            auto_tuner=tuner,
        )
        manager._current_posture = SystemPosture.STRESSED

        manager.try_auto_revert()   # ciclo 1 → bloqueado
        result = manager.try_auto_revert()  # ciclo 2 → permitido

        assert result is True
        guard.check_auto_revert.assert_called_once()

    def test_manager_calls_record_recovery_on_successful_revert(self) -> None:
        storage = _make_storage({"min_stability_cycles": 1})
        tuner = ResilienceAutoTuner(storage=storage)
        guard = self._make_guard(revert_result=True)
        tuner.record_recovery = MagicMock(return_value={})

        manager = ResilienceManager(
            storage=MagicMock(),
            close_only_guard=guard,
            auto_tuner=tuner,
        )
        manager._current_posture = SystemPosture.STRESSED

        manager.try_auto_revert(edge_eroded=True)

        tuner.record_recovery.assert_called_once()
        call_kwargs = tuner.record_recovery.call_args[1]
        assert call_kwargs["edge_eroded"] is True

    def test_manager_without_tuner_reverts_normally(self) -> None:
        """Sin AutoTuner, el comportamiento legacy de try_auto_revert no cambia."""
        guard = self._make_guard(revert_result=True)
        manager = ResilienceManager(
            storage=MagicMock(),
            close_only_guard=guard,
        )
        manager._current_posture = SystemPosture.STRESSED

        result = manager.try_auto_revert()

        assert result is True
        guard.check_auto_revert.assert_called_once()

    def test_manager_resets_cycle_count_on_stressed_entry(self) -> None:
        """Al entrar de nuevo a STRESSED, el contador de ciclos se reinicia."""
        storage = _make_storage({"min_stability_cycles": 3})
        tuner = ResilienceAutoTuner(storage=storage)
        guard = self._make_guard(revert_result=False)

        manager = ResilienceManager(
            storage=MagicMock(),
            close_only_guard=guard,
            auto_tuner=tuner,
        )

        # Simula entrada a STRESSED
        report = EdgeEventReport(
            level=ResilienceLevel.GLOBAL,
            scope="TEST",
            action=EdgeAction.LOCKDOWN,
            reason="test lockdown",
        )
        manager._current_posture = SystemPosture.NORMAL
        manager.process_report(report)

        assert manager._revert_attempt_count == 0
