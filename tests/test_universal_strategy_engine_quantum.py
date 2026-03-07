"""
Test: UniversalStrategyEngine Refactor (QUANTUM LEAP)
Trace_ID: TEST-UNIVERSAL-ENGINE-REAL

Validación que el motor:
1. Lee dinámicamente del Registry (config/strategy_registry.json)
2. Valida readiness (READY_FOR_ENGINE vs LOGIC_PENDING)
3. Procesa señales basándose en parámetros JSON, NO en código hardcodeado
4. Bloquea estrategias LOGIC_PENDING
5. NO instancia OliverVelezStrategy

Pruebas:
- test_registry_loader_loads_usr_strategies
- test_readiness_validator_blocks_pending
- test_execute_from_registry_finds_strategy
- test_execute_from_registry_blocks_logic_pending
- test_execute_from_registry_not_found
- test_ready_usr_strategies_returns_only_ready
"""
import pytest
import json
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core_brain.universal_strategy_engine import (
    UniversalStrategyEngine,
    RegistryLoader,
    StrategyReadinessValidator,
    ExecutionMode,
)


# ============================================================================
# FIXTURES (Module-level for sharing across all test classes)
# ============================================================================

@pytest.fixture
def mock_storage():
    """Mock StorageManager with strategy methods.
    
    Used by: TestRegistryLoader, TestUniversalStrategyEngineQuantum, TestNoOliverVelezHardcoding
    """
    storage = Mock()
    
    # Strategy data from BD
    usr_strategies_from_db = [
        {
            "class_id": "MOM_BIAS_0001",
            "strategy_id": "MOM_BIAS_0001",
            "mnemonic": "MOM_BIAS_MOMENTUM_STRIKE",
            "readiness": "READY_FOR_ENGINE",
            "readiness_notes": "Logica comprobada",
            "affinity_scores": {"EUR/USD": 0.65},
            "market_whitelist": ["EUR/USD", "GBP/USD"],
        },
        {
            "class_id": "LIQ_SWEEP_0001",
            "strategy_id": "LIQ_SWEEP_0001",
            "mnemonic": "LIQ_SWEEP_SCALPING_REVERSAL",
            "readiness": "READY_FOR_ENGINE",
            "readiness_notes": "Logica comprobada",
            "affinity_scores": {"EUR/USD": 0.92},
            "market_whitelist": ["EUR/USD", "GBP/USD"],
        },
        {
            "class_id": "STRUC_SHIFT_0001",
            "strategy_id": "STRUC_SHIFT_0001",
            "mnemonic": "STRUC_SHIFT_STRUCTURE_BREAK",
            "readiness": "READY_FOR_ENGINE",
            "readiness_notes": "Logica comprobada",
            "affinity_scores": {"EUR/USD": 0.89},
            "market_whitelist": ["EUR/USD"],
        },
        {
            "class_id": "BRK_OPEN_0001",
            "strategy_id": "BRK_OPEN_0001",
            "mnemonic": "BRK_OPEN_NY_STRIKE",
            "readiness": "LOGIC_PENDING",
            "readiness_notes": "JSON schema refinement required",
            "affinity_scores": {"EUR/USD": 0.92},
            "market_whitelist": ["EUR/USD"],
        },
    ]
    
    storage.get_all_usr_strategies.return_value = usr_strategies_from_db
    storage.get_strategy.side_effect = lambda strategy_id: next(
        (s for s in usr_strategies_from_db if s.get("class_id") == strategy_id), None
    )
    storage.get_usr_strategies_by_readiness.side_effect = lambda readiness: [
        s for s in usr_strategies_from_db if s.get("readiness") == readiness
    ]
    
    return storage


class TestRegistryLoader:
    """Tests for RegistryLoader class (BBDD-based, not JSON file)."""
    
    def test_registry_loader_loads_usr_strategies_from_bd(self, mock_storage):
        """Verifica que RegistryLoader carga estrategias DESDE BD, no de JSON."""
        loader = RegistryLoader(mock_storage)
        registry = loader.load_registry()
        
        assert registry is not None
        assert "usr_strategies" in registry
        assert len(registry["usr_strategies"]) == 4  # 4 estrategias en BD mock
        
        # Verificar que hay estrategias READY_FOR_ENGINE
        strategy_ids = [s.get("class_id") for s in registry["usr_strategies"]]
        assert "MOM_BIAS_0001" in strategy_ids
        assert "LIQ_SWEEP_0001" in strategy_ids
        assert "STRUC_SHIFT_0001" in strategy_ids
    
    def test_registry_loader_caches_registry(self, mock_storage):
        """Verifica que RegistryLoader cachea el Registry."""
        loader = RegistryLoader(mock_storage)
        
        registry1 = loader.load_registry()
        registry2 = loader.load_registry()
        
        # Debe retornar la misma instancia (cache)
        assert registry1 is registry2
        # Verificar que solo llamó una vez a get_all_usr_strategies (por el cache)
        assert mock_storage.get_all_usr_strategies.call_count == 1
    
    def test_get_strategy_metadata_found(self, mock_storage):
        """Verifica que se puede obtener metadata de una estrategia conocida."""
        loader = RegistryLoader(mock_storage)
        
        metadata = loader.get_strategy_metadata("MOM_BIAS_0001")
        
        assert metadata is not None
        assert metadata["class_id"] == "MOM_BIAS_0001"
        assert metadata["mnemonic"] == "MOM_BIAS_MOMENTUM_STRIKE"
        assert metadata["readiness"] == "READY_FOR_ENGINE"
    
    def test_get_strategy_metadata_not_found(self, mock_storage):
        """Verifica que retorna None para estrategia desconocida."""
        loader = RegistryLoader(mock_storage)
        
        metadata = loader.get_strategy_metadata("NONEXISTENT_STRATEGY")
        
        assert metadata is None
    
    def test_get_ready_usr_strategies_filters_by_readiness(self, mock_storage):
        """Verifica que get_ready_usr_strategies retorna solo READY_FOR_ENGINE desde BD."""
        loader = RegistryLoader(mock_storage)
        
        ready_usr_strategies = loader.get_ready_usr_strategies()
        
        # Debe haber 3 estrategias READY_FOR_ENGINE en el mock
        assert len(ready_usr_strategies) == 3
        
        # Verificar que son las correctas
        ready_ids = [s.get("class_id") for s in ready_usr_strategies]
        assert "MOM_BIAS_0001" in ready_ids
        assert "LIQ_SWEEP_0001" in ready_ids
        assert "STRUC_SHIFT_0001" in ready_ids
        
        # Verificar que NO hay LOGIC_PENDING
        for strategy in ready_usr_strategies:
            assert strategy.get("readiness") == "READY_FOR_ENGINE"


class TestStrategyReadinessValidator:
    """Tests for StrategyReadinessValidator."""
    
    def test_validate_ready_for_engine(self):
        """Verifica que valida READY_FOR_ENGINE."""
        metadata = {
            "strategy_id": "MOM_BIAS_0001",
            "readiness": "READY_FOR_ENGINE",
            "readiness_notes": "Tested and ready"
        }
        
        is_ready, reason = StrategyReadinessValidator.validate(metadata)
        
        assert is_ready is True
        assert "lista para ejecución" in reason.lower()
    
    def test_validate_logic_pending(self):
        """Verifica que bloquea LOGIC_PENDING."""
        metadata = {
            "strategy_id": "BRK_OPEN_0001",
            "readiness": "LOGIC_PENDING",
            "readiness_notes": "JSON schema refinement required"
        }
        
        is_ready, reason = StrategyReadinessValidator.validate(metadata)
        
        assert is_ready is False
        assert "Lógica pendiente" in reason
    
    def test_validate_unknown_status(self):
        """Verifica que maneja estados desconocidos."""
        metadata = {
            "strategy_id": "UNKNOWN",
            "readiness": "INVALID_STATUS"
        }
        
        is_ready, reason = StrategyReadinessValidator.validate(metadata)
        
        assert is_ready is False
        assert "desconocido" in reason.lower()


class TestUniversalStrategyEngineQuantum:
    """Tests for refactored UniversalStrategyEngine (BBDD-based Registry)."""
    
    @pytest.fixture
    def mock_indicator_provider(self):
        """Mock indicator provider con métodos básicos."""
        provider = Mock()
        provider.calculate_rsi = Mock(return_value=50.0)
        provider.calculate_sma = Mock(return_value=100.0)
        return provider
    
    def test_engine_initialization(self, mock_indicator_provider, mock_storage):
        """Verifica inicialización del engine con DI de storage."""
        engine = UniversalStrategyEngine(
            mock_indicator_provider,
            mock_storage  # Inyectar storage, no registry_path
        )
        
        assert engine is not None
        assert engine._indicator_provider is not None
        assert engine._registry_loader is not None
        assert engine._storage is mock_storage
    
    @pytest.mark.asyncio
    async def test_execute_from_registry_finds_strategy(self, mock_indicator_provider, mock_storage):
        """Verifica que el engine encuentra estrategia en Registry BD."""
        engine = UniversalStrategyEngine(mock_indicator_provider, mock_storage)
        
        # Crear mock dataframe
        mock_df = Mock()
        mock_df.shape = (100, 4)
        
        # Ejecutar - debe encontrar la estrategia
        result = await engine.execute_from_registry(
            strategy_id="MOM_BIAS_0001",
            symbol="EURUSD",
            data_frame=mock_df
        )
        
        # Validar que fue encontrada (no STRATEGY_NOT_FOUND)
        assert result.strategy_id == "MOM_BIAS_0001"
    
    @pytest.mark.asyncio
    async def test_execute_from_registry_blocks_logic_pending(self, mock_indicator_provider, mock_storage):
        """Verifica que el engine BLOQUEA estrategias LOGIC_PENDING desde BD."""
        engine = UniversalStrategyEngine(mock_indicator_provider, mock_storage)
        
        mock_df = Mock()
        mock_df.shape = (100, 4)
        
        # Intentar ejecutar BRK_OPEN_0001 (LOGIC_PENDING en BD)
        result = await engine.execute_from_registry(
            strategy_id="BRK_OPEN_0001",
            symbol="EURUSD",
            data_frame=mock_df
        )
        
        # DEBE bloquearse
        assert result.execution_mode == ExecutionMode.READINESS_BLOCKED
        assert result.signal is None
    
    @pytest.mark.asyncio
    async def test_execute_from_registry_strategy_not_found(self, mock_indicator_provider, mock_storage):
        """Verifica que el engine retorna NOT_FOUND para estrategia inexistente."""
        engine = UniversalStrategyEngine(mock_indicator_provider, mock_storage)
        
        mock_df = Mock()
        
        result = await engine.execute_from_registry(
            strategy_id="NONEXISTENT_STRATEGY",
            symbol="EURUSD",
            data_frame=mock_df
        )
        
        assert result.execution_mode == ExecutionMode.NOT_FOUND
    
    def test_get_ready_usr_strategies_returns_only_ready(self, mock_indicator_provider, mock_storage):
        """Verifica que get_ready_usr_strategies retorna solo READY_FOR_ENGINE desde BD."""
        engine = UniversalStrategyEngine(mock_indicator_provider, mock_storage)
        
        ready_usr_strategies = engine.get_ready_usr_strategies()
        
        # Debe haber 3 estrategias READY_FOR_ENGINE
        assert len(ready_usr_strategies) == 3
        
        # Verificar que son las correctas
        ready_ids = [s.get("class_id") for s in ready_usr_strategies]
        assert "MOM_BIAS_0001" in ready_ids
        assert "LIQ_SWEEP_0001" in ready_ids
        assert "STRUC_SHIFT_0001" in ready_ids
        
        # Verificar que NO hay LOGIC_PENDING
        for strategy in ready_usr_strategies:
            assert strategy.get("readiness") == "READY_FOR_ENGINE"
    
    def test_registry_loader_uses_storage_not_json(self, mock_indicator_provider, mock_storage):
        """Verifica que RegistryLoader usa StorageManager, NO archivos JSON."""
        import inspect
        
        engine = UniversalStrategyEngine(mock_indicator_provider, mock_storage)
        loader = engine._registry_loader
        
        # El loader debe usar self.storage (StorageManager), no archivos
        assert hasattr(loader, 'storage')
        assert loader.storage is mock_storage
        
        # Llamar load_registry debe invocar storage.get_all_usr_strategies()
        registry = loader.load_registry()
        mock_storage.get_all_usr_strategies.assert_called()
        
        # Verificar que load_registry retorna estrategias desde BD
        assert "usr_strategies" in registry
        assert len(registry["usr_strategies"]) > 0


class TestNoOliverVelezHardcoding:
    """Tests para garantizar que OliverVelezStrategy no está hardcodeado."""
    
    def test_no_oliver_velez_import_in_engine(self):
        """Verifica que UniversalStrategyEngine NO importa OliverVelezStrategy."""
        import inspect
        
        # Obtener fuente del módulo
        source = inspect.getsource(__import__('core_brain.universal_strategy_engine'))
        
        # Verificar que NO menciona OliverVelezStrategy
        assert "OliverVelezStrategy" not in source
        assert "oliver_velez" not in source
    
    def test_registry_is_single_source_of_truth(self, mock_storage):
        """Verifica que la BD (StorageManager) es la única fuente de verdad en runtime.
        
        SSOT CORRECTION: JSON es SOLO para seed/migration.
        En runtime, StorageManager es la única fuente de verdad.
        """
        # Crear RegistryLoader con StorageManager DI (NO JSON file path)
        loader = RegistryLoader(mock_storage)
        registry = loader.load_registry()
        
        # Contar estrategias en Registry (obtenidas de BD)
        num_usr_strategies = len(registry.get("usr_strategies", []))
        
        # Verificar que es > 0
        assert num_usr_strategies > 0
        
        # Verificar que cada estrategia tiene readiness definido
        for strategy in registry["usr_strategies"]:
            assert "readiness" in strategy
            assert strategy["readiness"] in ["READY_FOR_ENGINE", "LOGIC_PENDING"]
        
        # Verificar que StorageManager fue llamado (no JSON fue leído)
        mock_storage.get_all_usr_strategies.assert_called_once()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
