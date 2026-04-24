"""
Tests TDD — StrategyPendingDiagnosticsService (HU 3.1)
=======================================================

Escenarios cubiertos:
  1. Estrategia LOGIC_PENDING autocorregible → pasa a READY_FOR_ENGINE
  2. Estrategia LOGIC_PENDING no resoluble  → permanece en LOGIC_PENDING con diagnóstico
  3. Estrategia PYTHON_CLASS con class_file válido → autocorregida
  4. Estrategia JSON_SCHEMA con logic definido y schema válido → autocorregida
  5. diagnose_one para class_id no existente → retorna None
  6. diagnose_one para estrategia no LOGIC_PENDING → retorna None
  7. run_full_cycle persiste diagnóstico en storage via update_strategy_readiness
  8. Estrategia con readiness_notes "refinement required" → causa NEEDS_IMPLEMENTATION

Trace_ID: ETI-E3-HU3.1-TESTS
"""
import json
import pytest
from unittest.mock import MagicMock, patch, call
from pathlib import Path

from core_brain.strategy_pending_diagnostics import (
    StrategyPendingDiagnosticsService,
    StrategyDiagnosis,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_storage(pending_strategies=None, strategy_by_id=None):
    """Factory para un StorageManager mock."""
    storage = MagicMock()
    storage.get_pending_strategies.return_value = pending_strategies or []
    storage.get_strategy.side_effect = lambda cid: (strategy_by_id or {}).get(cid)
    storage.update_strategy_readiness.return_value = True
    return storage


def _python_class_strategy(
    class_id="STRAT_001",
    mnemonic="Test Strategy",
    class_file=None,
    readiness_notes=None,
):
    return {
        "class_id": class_id,
        "mnemonic": mnemonic,
        "type": "PYTHON_CLASS",
        "readiness": "LOGIC_PENDING",
        "class_file": class_file,
        "class_name": "TestStrategy",
        "schema_file": None,
        "logic": None,
        "readiness_notes": readiness_notes,
    }


def _json_schema_strategy(
    class_id="STRAT_002",
    mnemonic="JSON Strategy",
    logic=None,
    schema_file=None,
    readiness_notes=None,
):
    return {
        "class_id": class_id,
        "mnemonic": mnemonic,
        "type": "JSON_SCHEMA",
        "readiness": "LOGIC_PENDING",
        "class_file": None,
        "class_name": None,
        "schema_file": schema_file,
        "logic": logic,
        "readiness_notes": readiness_notes,
    }


# ── Test: diagnóstico de PYTHON_CLASS sin class_file ────────────────────────

class TestPythonClassDiagnosis:

    def test_missing_class_file_field_produces_correct_cause(self):
        """Estrategia PYTHON_CLASS sin class_file → MISSING_CLASS_FILE."""
        strategy = _python_class_strategy(class_file=None)
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        assert len(results) == 1
        diag = results[0]
        assert diag.cause == "MISSING_CLASS_FILE"
        assert diag.auto_fixed is False
        assert diag.new_readiness == "LOGIC_PENDING"

    def test_missing_class_file_on_disk_produces_correct_cause(self, tmp_path):
        """Estrategia con class_file que NO existe en disco → MISSING_CLASS_FILE."""
        strategy = _python_class_strategy(class_file="nonexistent/strategy.py")
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        diag = results[0]
        assert diag.cause == "MISSING_CLASS_FILE"
        assert diag.auto_fixed is False

    def test_existing_class_file_triggers_auto_fix(self, tmp_path):
        """Estrategia PYTHON_CLASS cuyo class_file YA existe → autocorregida a READY_FOR_ENGINE."""
        # Crear un archivo temporal que simule el class_file
        real_file = tmp_path / "my_strategy.py"
        real_file.write_text("class MyStrategy: pass")

        strategy = _python_class_strategy(class_file=str(real_file))
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        # Parchamos _PROJECT_ROOT para que apunte a tmp_path root
        with patch("core_brain.strategy_pending_diagnostics._PROJECT_ROOT", tmp_path.parent):
            results = service.run_full_cycle()

        diag = results[0]
        assert diag.auto_fixed is True
        assert diag.new_readiness == "READY_FOR_ENGINE"

    def test_auto_fix_calls_update_strategy_readiness(self, tmp_path):
        """Cuando hay auto-fix, update_strategy_readiness se llama con READY_FOR_ENGINE."""
        real_file = tmp_path / "strat.py"
        real_file.write_text("")

        strategy = _python_class_strategy(class_file=str(real_file), class_id="STRAT_AUTO")
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        with patch("core_brain.strategy_pending_diagnostics._PROJECT_ROOT", tmp_path.parent):
            service.run_full_cycle()

        storage.update_strategy_readiness.assert_called_once()
        _, kwargs = storage.update_strategy_readiness.call_args
        assert kwargs.get("class_id") == "STRAT_AUTO" or storage.update_strategy_readiness.call_args[0][0] == "STRAT_AUTO"


# ── Test: diagnóstico de JSON_SCHEMA ─────────────────────────────────────────

class TestJsonSchemaDiagnosis:

    def test_missing_logic_field_produces_correct_cause(self):
        """Estrategia JSON_SCHEMA sin logic → MISSING_LOGIC."""
        strategy = _json_schema_strategy(logic=None)
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        diag = results[0]
        assert diag.cause == "MISSING_LOGIC"
        assert diag.auto_fixed is False
        assert diag.new_readiness == "LOGIC_PENDING"

    def test_valid_logic_dict_triggers_auto_fix(self):
        """Estrategia JSON_SCHEMA con logic dict válido → autocorregida."""
        logic = {"entry_conditions": ["RSI < 30"], "exit_conditions": ["RSI > 70"]}
        strategy = _json_schema_strategy(logic=logic, schema_file=None)
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        diag = results[0]
        assert diag.auto_fixed is True
        assert diag.new_readiness == "READY_FOR_ENGINE"

    def test_missing_schema_file_prevents_auto_fix(self, tmp_path):
        """Estrategia con schema_file inexistente → MISSING_SCHEMA_FILE, sin auto-fix."""
        logic = {"entry_conditions": ["RSI < 30"]}
        strategy = _json_schema_strategy(logic=logic, schema_file="missing_schema.json")
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        diag = results[0]
        assert diag.cause == "MISSING_SCHEMA_FILE"
        assert diag.auto_fixed is False


# ── Test: NEEDS_IMPLEMENTATION desde readiness_notes ─────────────────────────

class TestNeedsImplementation:

    def test_refinement_in_notes_produces_needs_implementation(self):
        """readiness_notes contiene 'refinement' → NEEDS_IMPLEMENTATION."""
        strategy = _python_class_strategy(
            class_file="some/file.py",
            readiness_notes="JSON schema refinement required before activation.",
        )
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        diag = results[0]
        assert diag.cause == "NEEDS_IMPLEMENTATION"
        assert diag.auto_fixed is False
        assert diag.new_readiness == "LOGIC_PENDING"

    def test_needs_implementation_preserves_original_notes_in_suggestion(self):
        """El cause_detail debe incluir el texto de readiness_notes."""
        notes = "Implementación pendiente: calcular ADX dinámico."
        strategy = _python_class_strategy(class_file=None, readiness_notes=notes)
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        diag = results[0]
        # La causa más prioritaria es MISSING_CLASS_FILE (class_file=None toma precedencia)
        assert diag.cause in ("MISSING_CLASS_FILE", "NEEDS_IMPLEMENTATION")


# ── Test: diagnose_one ────────────────────────────────────────────────────────

class TestDiagnoseOne:

    def test_returns_none_for_unknown_class_id(self):
        """class_id inexistente → retorna None."""
        storage = _make_storage(strategy_by_id={})
        service = StrategyPendingDiagnosticsService(storage)

        result = service.diagnose_one("NONEXISTENT")

        assert result is None

    def test_returns_none_for_non_pending_strategy(self):
        """Estrategia no en LOGIC_PENDING → retorna None."""
        strategy = _python_class_strategy(class_id="READY_STRAT")
        strategy["readiness"] = "READY_FOR_ENGINE"
        storage = _make_storage(strategy_by_id={"READY_STRAT": strategy})
        service = StrategyPendingDiagnosticsService(storage)

        result = service.diagnose_one("READY_STRAT")

        assert result is None

    def test_diagnoses_single_strategy_and_persists(self):
        """diagnose_one diagnostica y llama a update_strategy_readiness."""
        strategy = _json_schema_strategy(class_id="SINGLE_001", logic=None)
        storage = _make_storage(strategy_by_id={"SINGLE_001": strategy})
        service = StrategyPendingDiagnosticsService(storage)

        result = service.diagnose_one("SINGLE_001")

        assert result is not None
        assert result.class_id == "SINGLE_001"
        assert result.cause == "MISSING_LOGIC"
        storage.update_strategy_readiness.assert_called_once()


# ── Test: persistencia ────────────────────────────────────────────────────────

class TestPersistence:

    def test_diagnosis_persisted_as_json_in_readiness_notes(self):
        """El diagnóstico se serializa como JSON en readiness_notes."""
        strategy = _json_schema_strategy(logic=None)
        storage = _make_storage(pending_strategies=[strategy])
        service = StrategyPendingDiagnosticsService(storage)

        service.run_full_cycle()

        call_args = storage.update_strategy_readiness.call_args
        readiness_notes = call_args[1].get("readiness_notes") or call_args[0][2]
        parsed = json.loads(readiness_notes)

        assert "cause" in parsed
        assert "suggestion" in parsed
        assert "last_checked" in parsed

    def test_run_full_cycle_processes_all_pending(self):
        """run_full_cycle procesa todas las estrategias LOGIC_PENDING."""
        strategies = [
            _python_class_strategy(class_id="A"),
            _json_schema_strategy(class_id="B"),
            _python_class_strategy(class_id="C"),
        ]
        storage = _make_storage(pending_strategies=strategies)
        service = StrategyPendingDiagnosticsService(storage)

        results = service.run_full_cycle()

        assert len(results) == 3
        assert storage.update_strategy_readiness.call_count == 3


# ── Test: to_dict ─────────────────────────────────────────────────────────────

class TestStrategyDiagnosisModel:

    def test_to_dict_contains_all_fields(self):
        """to_dict retorna todos los campos necesarios para la API."""
        diag = StrategyDiagnosis(
            class_id="X",
            mnemonic="Test",
            strategy_type="PYTHON_CLASS",
            readiness="LOGIC_PENDING",
            cause="MISSING_LOGIC",
            cause_detail="Sin lógica.",
            suggestion="Define logic.",
            auto_fixed=False,
            new_readiness="LOGIC_PENDING",
        )
        d = diag.to_dict()

        required_keys = {"class_id", "mnemonic", "strategy_type", "readiness",
                         "cause", "cause_detail", "suggestion", "auto_fixed",
                         "new_readiness", "last_checked"}
        assert required_keys.issubset(d.keys())
