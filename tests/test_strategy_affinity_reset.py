"""
test_strategy_affinity_reset.py — HU 3.7
=========================================

TDD para Reset Inteligente de Afinidad/Whitelist y UX LOGIC_PENDING.

Casos cubiertos (según spec):
1. test_reset_affinity_dynamic       — Reset exitoso en estrategia dinámica
2. test_reset_affinity_fixed         — Bloqueo de reset en estrategia fija
3. test_ui_feedback_causa_estructural — PendingStrategyResponse indica causa estructural correctamente
4. test_logging_reset_event          — Registro de evento de reset en readiness_notes
5. test_logging_failed_action        — Reset de estrategia fija no modifica DB

Trace_ID: CORE-LOGIC_PENDING-2026-04-23
"""
from __future__ import annotations

import json
from unittest.mock import MagicMock, call, patch

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_storage(affinity_mode: str = "dynamic") -> MagicMock:
    storage = MagicMock()
    storage.get_strategy_affinity_mode.return_value = affinity_mode
    storage.execute_query.return_value = [{"affinity_mode": affinity_mode}]
    storage.execute_update.return_value = None
    return storage


def _dynamic_strategy(class_id: str = "STRAT_DYN") -> dict:
    return {
        "class_id": class_id,
        "mnemonic": "DynStrat",
        "type": "PYTHON_CLASS",
        "readiness": "LOGIC_PENDING",
        "affinity_mode": "dynamic",
        "affinity_scores": {"EUR/USD": 0.8},
        "market_whitelist": ["EUR/USD"],
        "readiness_notes": None,
    }


def _fixed_strategy(class_id: str = "STRAT_FIX") -> dict:
    return {
        "class_id": class_id,
        "mnemonic": "FixStrat",
        "type": "PYTHON_CLASS",
        "readiness": "LOGIC_PENDING",
        "affinity_mode": "fixed",
        "affinity_scores": {"GBP/USD": 0.9},
        "market_whitelist": ["GBP/USD"],
        "readiness_notes": None,
    }


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestResetAffinityDynamic:
    """test_reset_affinity_dynamic — Reset exitoso en estrategia dinámica."""

    def test_reset_clears_affinity_and_whitelist(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "dynamic"}])
        repo.execute_update = MagicMock()

        result = repo.reset_affinity_and_whitelist("STRAT_DYN", reason="test reset")

        assert result is True
        update_call = repo.execute_update.call_args
        sql: str = update_call[0][0]
        assert "affinity_scores = '{}'" in sql
        assert "market_whitelist = '[]'" in sql

    def test_reset_logs_event_in_readiness_notes(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "dynamic"}])
        repo.execute_update = MagicMock()

        repo.reset_affinity_and_whitelist("STRAT_DYN", reason="operador solicitó reset")

        params = repo.execute_update.call_args[0][1]
        notes_json = params[0]
        notes = json.loads(notes_json)
        assert notes["action"] == "AFFINITY_RESET"
        assert "operador solicitó reset" in notes["reason"]
        assert "reset_at" in notes

    def test_affinity_mode_propagated_in_diagnosis(self) -> None:
        from core_brain.strategy_pending_diagnostics import StrategyPendingDiagnosticsService

        strategy = _dynamic_strategy()
        strategy["class_file"] = None

        storage = MagicMock()
        storage.get_pending_strategies.return_value = [strategy]
        storage.update_strategy_readiness.return_value = None

        service = StrategyPendingDiagnosticsService(storage)
        results = service.run_full_cycle()

        assert len(results) == 1
        assert results[0].affinity_mode == "dynamic"
        assert results[0].to_dict()["affinity_mode"] == "dynamic"


class TestResetAffinityFixed:
    """test_reset_affinity_fixed — Bloqueo de reset en estrategia fija."""

    def test_reset_returns_false_for_fixed_mode(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "fixed"}])
        repo.execute_update = MagicMock()

        result = repo.reset_affinity_and_whitelist("STRAT_FIX")

        assert result is False

    def test_reset_does_not_call_execute_update_for_fixed(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "fixed"}])
        repo.execute_update = MagicMock()

        repo.reset_affinity_and_whitelist("STRAT_FIX")

        repo.execute_update.assert_not_called()

    def test_endpoint_returns_403_for_fixed_strategy(self) -> None:
        """El endpoint reset-affinity devuelve 403 cuando affinity_mode='fixed'."""
        import asyncio
        from fastapi import HTTPException
        from core_brain.api.routers.strategy_pending import reset_strategy_affinity, ActionRequest

        fixed = _fixed_strategy()

        with patch(
            "core_brain.api.routers.strategy_pending._get_storage"
        ) as mock_get_storage:
            storage = MagicMock()
            storage.get_strategy.return_value = fixed
            mock_get_storage.return_value = storage

            with pytest.raises(HTTPException) as exc_info:
                asyncio.run(reset_strategy_affinity("STRAT_FIX", ActionRequest()))

            assert exc_info.value.status_code == 403
            assert "fixed" in exc_info.value.detail.lower()

    def test_fixed_affinity_mode_propagated_in_diagnosis(self) -> None:
        from core_brain.strategy_pending_diagnostics import StrategyPendingDiagnosticsService

        strategy = _fixed_strategy()
        strategy["class_file"] = None

        storage = MagicMock()
        storage.get_pending_strategies.return_value = [strategy]
        storage.update_strategy_readiness.return_value = None

        service = StrategyPendingDiagnosticsService(storage)
        results = service.run_full_cycle()

        assert results[0].affinity_mode == "fixed"


class TestUiFeedbackCausaEstructural:
    """test_ui_feedback_causa_estructural — Causa estructural expuesta en respuesta API."""

    def test_structural_causes_returned_in_list_response(self) -> None:
        """GET /strategy-pending devuelve causa estructural correctamente."""
        import asyncio
        from core_brain.api.routers.strategy_pending import list_pending_strategies

        strategy = {
            "class_id": "STRAT_001",
            "mnemonic": "Test",
            "type": "PYTHON_CLASS",
            "readiness": "LOGIC_PENDING",
            "affinity_mode": "dynamic",
            "description": None,
            "readiness_notes": json.dumps({
                "cause": "MISSING_CLASS_FILE",
                "cause_detail": "El archivo no existe.",
                "suggestion": "Crea el archivo.",
                "affinity_mode": "dynamic",
                "last_checked": "2026-04-23T00:00:00+00:00",
            }),
        }

        with patch(
            "core_brain.api.routers.strategy_pending._get_storage"
        ) as mock_get_storage:
            storage = MagicMock()
            storage.get_pending_strategies.return_value = [strategy]
            mock_get_storage.return_value = storage

            result = asyncio.run(list_pending_strategies())

        assert len(result) == 1
        resp = result[0]
        assert resp.cause == "MISSING_CLASS_FILE"
        assert resp.affinity_mode == "dynamic"
        assert resp.cause_detail == "El archivo no existe."

    def test_structural_cause_present_in_needs_implementation(self) -> None:
        """NEEDS_IMPLEMENTATION es causa estructural en el response."""
        import asyncio
        from core_brain.api.routers.strategy_pending import list_pending_strategies

        strategy = {
            "class_id": "STRAT_002",
            "mnemonic": "NeedsImpl",
            "type": "PYTHON_CLASS",
            "readiness": "LOGIC_PENDING",
            "affinity_mode": "fixed",
            "description": None,
            "readiness_notes": json.dumps({
                "cause": "NEEDS_IMPLEMENTATION",
                "cause_detail": "Pendiente de implementar lógica.",
                "suggestion": "Completa la implementación.",
                "affinity_mode": "fixed",
                "last_checked": "2026-04-23T00:00:00+00:00",
            }),
        }

        with patch(
            "core_brain.api.routers.strategy_pending._get_storage"
        ) as mock_get_storage:
            storage = MagicMock()
            storage.get_pending_strategies.return_value = [strategy]
            mock_get_storage.return_value = storage

            result = asyncio.run(list_pending_strategies())

        resp = result[0]
        assert resp.cause == "NEEDS_IMPLEMENTATION"
        assert resp.affinity_mode == "fixed"


class TestLoggingResetEvent:
    """test_logging_reset_event — Evento de reset registrado en readiness_notes."""

    def test_reset_event_contains_required_fields(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "dynamic"}])
        repo.execute_update = MagicMock()

        repo.reset_affinity_and_whitelist("STRAT_DYN", reason="test logging")

        params = repo.execute_update.call_args[0][1]
        notes = json.loads(params[0])

        assert notes["action"] == "AFFINITY_RESET"
        assert notes["reason"] == "test logging"
        assert "reset_at" in notes

    def test_reset_event_uses_default_reason_when_none(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "dynamic"}])
        repo.execute_update = MagicMock()

        repo.reset_affinity_and_whitelist("STRAT_DYN")

        params = repo.execute_update.call_args[0][1]
        notes = json.loads(params[0])
        assert notes["reason"]

    def test_diagnosis_includes_affinity_mode_in_readiness_notes(self) -> None:
        from core_brain.strategy_pending_diagnostics import StrategyPendingDiagnosticsService

        strategy = _dynamic_strategy()
        strategy["class_file"] = None

        storage = MagicMock()
        storage.get_pending_strategies.return_value = [strategy]
        storage.update_strategy_readiness.return_value = None

        service = StrategyPendingDiagnosticsService(storage)
        service.run_full_cycle()

        update_call = storage.update_strategy_readiness.call_args
        notes_json = update_call[1].get("readiness_notes") or update_call[0][2] if len(update_call[0]) > 2 else None
        if notes_json is None:
            notes_json = update_call[1]["readiness_notes"]
        notes = json.loads(notes_json)
        assert notes["affinity_mode"] == "dynamic"


class TestLoggingFailedAction:
    """test_logging_failed_action — Intento de reset en estrategia fija no modifica DB."""

    def test_fixed_reset_attempt_does_not_modify_db(self) -> None:
        from data_vault.strategies_db import StrategiesMixin

        repo = StrategiesMixin.__new__(StrategiesMixin)
        repo.execute_query = MagicMock(return_value=[{"affinity_mode": "fixed"}])
        repo.execute_update = MagicMock()

        result = repo.reset_affinity_and_whitelist("STRAT_FIX", reason="intento no autorizado")

        assert result is False
        repo.execute_update.assert_not_called()

    def test_endpoint_does_not_call_reset_for_fixed(self) -> None:
        import asyncio
        from fastapi import HTTPException
        from core_brain.api.routers.strategy_pending import reset_strategy_affinity, ActionRequest

        fixed = _fixed_strategy()

        with patch(
            "core_brain.api.routers.strategy_pending._get_storage"
        ) as mock_get_storage:
            storage = MagicMock()
            storage.get_strategy.return_value = fixed
            mock_get_storage.return_value = storage

            with pytest.raises(HTTPException):
                asyncio.run(reset_strategy_affinity("STRAT_FIX", ActionRequest()))

            storage.reset_affinity_and_whitelist.assert_not_called()
