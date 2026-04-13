"""
Tests TDD — StrategyEngineFactory: inyección de metadata snapshot DB-backed.

Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13

Cubre:
- test_factory_injects_strategy_metadata_snapshot:
    la factory lee sys_strategies y entrega snapshot DB-backed a una PYTHON_CLASS.
"""
import pytest
from unittest.mock import MagicMock, patch

from core_brain.services.strategy_engine_factory import StrategyEngineFactory


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_storage(affinity_scores=None, market_whitelist=None, mode="SHADOW"):
    """StorageManager mock con metadata estratégica lista."""
    storage = MagicMock()
    strategy_spec = {
        "class_id": "MOM_BIAS_0001",
        "type": "PYTHON_CLASS",
        "readiness": "READY_FOR_ENGINE",
        "class_file": "core_brain/strategies/mom_bias_0001.py",
        "class_name": "MomentumBias0001Strategy",
        "affinity_scores": affinity_scores or {"GBPJPY": 0.85, "EURUSD": 0.65},
        "market_whitelist": market_whitelist or [],
        "execution_params": "{}",
        "required_sensors": [],
    }
    storage.get_all_sys_strategies.return_value = [strategy_spec]
    storage.get_strategy_lifecycle_mode.return_value = mode
    storage.get_dynamic_params.return_value = {}
    return storage, strategy_spec


# ── Test: Factory inyecta snapshot ────────────────────────────────────────────

class TestFactoryInjectsMetadataSnapshot:
    """
    DADO una estrategia PYTHON_CLASS con metadata en sys_strategies,
    CUANDO la factory la instancia,
    ENTONCES la instancia expone el snapshot DB-backed (no constantes locales).
    """

    def test_factory_injects_strategy_metadata_snapshot(self):
        """
        La factory debe inyectar affinity_scores y market_whitelist desde DB
        a la instancia PYTHON_CLASS mediante apply_metadata_snapshot().
        """
        db_affinity = {"XAUUSD": 0.99, "EURUSD": 0.10}
        storage, spec = _make_storage(affinity_scores=db_affinity)

        factory = StrategyEngineFactory(storage=storage, config={}, available_sensors={})

        mock_instance = MagicMock()
        mock_instance.apply_metadata_snapshot = MagicMock()

        with patch.object(
            factory, "_instantiate_python_strategy", return_value=mock_instance
        ):
            factory._load_single_strategy(spec)

        mock_instance.apply_metadata_snapshot.assert_called_once()
        snapshot_arg = mock_instance.apply_metadata_snapshot.call_args[0][0]
        assert snapshot_arg["affinity_scores"] == db_affinity, (
            "El snapshot debe contener los affinity_scores leídos de DB"
        )

    def test_factory_injects_market_whitelist_from_db(self):
        """
        La factory debe inyectar market_whitelist desde DB al snapshot.
        """
        db_whitelist = ["XAUUSD", "BTCUSD"]
        storage, spec = _make_storage(market_whitelist=db_whitelist)

        factory = StrategyEngineFactory(storage=storage, config={}, available_sensors={})

        mock_instance = MagicMock()
        mock_instance.apply_metadata_snapshot = MagicMock()

        with patch.object(
            factory, "_instantiate_python_strategy", return_value=mock_instance
        ):
            factory._load_single_strategy(spec)

        snapshot_arg = mock_instance.apply_metadata_snapshot.call_args[0][0]
        assert snapshot_arg["market_whitelist"] == db_whitelist, (
            "El snapshot debe contener market_whitelist leído de DB"
        )

    def test_factory_skips_snapshot_injection_when_method_absent(self):
        """
        Si la instancia no implementa apply_metadata_snapshot,
        la factory no debe lanzar excepción (compatibilidad regresiva).
        """
        storage, spec = _make_storage()
        factory = StrategyEngineFactory(storage=storage, config={}, available_sensors={})

        mock_instance = MagicMock(spec=[])  # sin apply_metadata_snapshot

        with patch.object(
            factory, "_instantiate_python_strategy", return_value=mock_instance
        ):
            # No debe lanzar excepción
            factory._load_single_strategy(spec)

        assert "MOM_BIAS_0001" in factory.active_engines

    def test_factory_does_not_inject_snapshot_for_json_schema(self):
        """
        Para estrategias JSON_SCHEMA, no se debe llamar apply_metadata_snapshot
        (el UniversalStrategyEngine gestiona su propio caché).
        """
        storage = MagicMock()
        spec = {
            "class_id": "INST_FOOT_0001",
            "type": "JSON_SCHEMA",
            "readiness": "READY_FOR_ENGINE",
            "affinity_scores": {"EURUSD": 0.90},
            "market_whitelist": [],
            "logic": {"entry_rules": []},
        }
        storage.get_all_sys_strategies.return_value = [spec]
        storage.get_strategy_lifecycle_mode.return_value = "SHADOW"

        factory = StrategyEngineFactory(storage=storage, config={}, available_sensors={})

        mock_instance = MagicMock()
        mock_instance.apply_metadata_snapshot = MagicMock()

        with patch.object(
            factory, "_instantiate_json_schema_strategy", return_value=mock_instance
        ):
            factory._load_single_strategy(spec)

        mock_instance.apply_metadata_snapshot.assert_not_called(), (
            "JSON_SCHEMA no debe recibir snapshot: gestiona su propio caché"
        )
