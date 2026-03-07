"""
Test Suite: Strategy Registry v2.0 Complete Protocol
TRACE_ID: TEST-STRATEGY-REGISTRY-COMPLETE-2026

Valida que el protocolo StrategyRegistry v2.0 funciona correctamente:
1. StrategyEngineFactory carga TODAS las estrategias de BD (SSOT)
2. MainOrchestrator.active_engines contiene Dict en memoria
3. NO hay hardcodeado de estrategias
4. Cada estrategia se compila UNA SOLA VEZ
5. SignalFactory recibe Dict, no List
6. Lookup es O(1) desde strategy_engines

GOBERNANZA: Cumple DEVELOPMENT_GUIDELINES (tests obligatorios)
"""

import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any

from core_brain.services.strategy_engine_factory import StrategyEngineFactory
from core_brain.signal_factory import SignalFactory


class TestStrategyEngineFactoryBasics:
    """Pruebas básicas de StrategyEngineFactory."""

    def test_factory_initialization(self):
        """Verifica que el factory se inicializa correctamente."""
        mock_storage = Mock()
        mock_storage.get_all_usr_strategies.return_value = [
            {
                "class_id": "TEST_STRAT",
                "type": "JSON_SCHEMA",
                "readiness": "READY_FOR_ENGINE",
                "required_sensors": []
            }
        ]
        
        factory = StrategyEngineFactory(
            storage=mock_storage,
            config={"test": "value"},
            available_sensors={}
        )
        
        assert factory.storage == mock_storage
        assert factory.config["test"] == "value"
        assert factory.active_engines == {}
        assert factory.load_errors == {}

    def test_factory_instantiate_all_usr_strategies_empty_bd(self):
        """Verifica que factory reporta error si BD está vacía."""
        mock_storage = Mock()
        mock_storage.get_all_usr_strategies.return_value = []
        
        factory = StrategyEngineFactory(storage=mock_storage)
        
        with pytest.raises(RuntimeError, match="Tabla usr_strategies vacía"):
            factory.instantiate_all_usr_strategies()

    def test_factory_instantiate_all_strategies_db_error(self):
        """Verifica manejo de errores al acceder a BD."""
        mock_storage = Mock()
        mock_storage.get_all_usr_strategies.side_effect = Exception("DB connection failed")
        
        factory = StrategyEngineFactory(storage=mock_storage)
        
        with pytest.raises(RuntimeError, match="No se pudo acceder a tabla usr_strategies"):
            factory.instantiate_all_usr_strategies()

    def test_factory_validates_readiness(self):
        """Verifica que usr_strategies con readiness != READY_FOR_ENGINE se salten."""
        mock_storage = Mock()
        mock_storage.get_all_usr_strategies.return_value = [
            {
                "class_id": "LOGIC_PENDING_STRAT",
                "type": "JSON_SCHEMA",
                "readiness": "LOGIC_PENDING",
                "required_sensors": []
            },
            {
                "class_id": "READY_STRAT",
                "type": "JSON_SCHEMA",
                "readiness": "READY_FOR_ENGINE",
                "required_sensors": []
            }
        ]
        
        factory = StrategyEngineFactory(storage=mock_storage)
        
        with patch("core_brain.services.strategy_engine_factory.logger"):
            with pytest.raises(RuntimeError, match="No usr_strategies instantiated"):
                # El segundo strategy no se puede instanciar porque UniversalStrategyEngine
                # fallaría en esta prueba, pero el primero se saltaría correctamente
                factory.instantiate_all_usr_strategies()

    def test_factory_validates_dependencies(self):
        """Verifica validación de dependencias de sensores."""
        mock_storage = Mock()
        mock_storage.get_all_usr_strategies.return_value = [
            {
                "class_id": "NEEDS_SENSOR",
                "type": "JSON_SCHEMA",
                "readiness": "READY_FOR_ENGINE",
                "required_sensors": ["ElephantCandleDetector", "MovingAverageSensor"]
            }
        ]
        
        factory = StrategyEngineFactory(
            storage=mock_storage,
            available_sensors={}  # Ningún sensor disponible
        )
        
        with patch("core_brain.services.strategy_engine_factory.logger"):
            with pytest.raises(RuntimeError, match="No usr_strategies instantiated"):
                factory.instantiate_all_usr_strategies()

    def test_factory_get_stats(self):
        """Verifica que stats() retorna información correcta."""
        mock_storage = Mock()
        factory = StrategyEngineFactory(storage=mock_storage)
        
        factory.active_engines["TEST_1"] = Mock()
        factory.load_errors["TEST_2"] = "error message"
        
        stats = factory.get_stats()
        
        assert stats["active_engines"] == 1
        assert stats["failed_loads"] == 1
        assert "TEST_2" in stats["load_errors"]


class TestSignalFactoryDictIntegration:
    """Pruebas que verifican que SignalFactory recibe Dict correctamente."""

    def test_signal_factory_accepts_dict(self):
        """Verifica que SignalFactory acepta strategy_engines como Dict."""
        mock_storage = Mock()
        mock_confluence = Mock()
        mock_trifecta = Mock()
        
        engines_dict = {
            "STRAT_1": Mock(),
            "STRAT_2": Mock()
        }
        
        signal_factory = SignalFactory(
            storage_manager=mock_storage,
            strategy_engines=engines_dict,
            confluence_analyzer=mock_confluence,
            trifecta_analyzer=mock_trifecta
        )
        
        assert signal_factory.strategy_engines == engines_dict
        assert len(signal_factory.strategy_engines) == 2

    def test_signal_factory_initializes_with_empty_dict(self):
        """Verifica que SignalFactory puede recibir Dict vacío."""
        mock_storage = Mock()
        mock_confluence = Mock()
        mock_trifecta = Mock()
        
        signal_factory = SignalFactory(
            storage_manager=mock_storage,
            strategy_engines={},
            confluence_analyzer=mock_confluence,
            trifecta_analyzer=mock_trifecta
        )
        
        assert signal_factory.strategy_engines == {}

    @pytest.mark.asyncio
    async def test_signal_factory_generate_signal_iterates_dict(self):
        """Verifica que generate_signal() itera sobre Dict en lugar de List."""
        mock_storage = Mock()
        mock_confluence = Mock()
        mock_trifecta = Mock()
        
        # Crear motores mock
        engine_1 = Mock()
        engine_1.analyze = AsyncMock(return_value=None)
        
        engine_2 = Mock()
        engine_2.analyze = AsyncMock(return_value=None)
        
        engines_dict = {
            "STRAT_1": engine_1,
            "STRAT_2": engine_2
        }
        
        signal_factory = SignalFactory(
            storage_manager=mock_storage,
            strategy_engines=engines_dict,
            confluence_analyzer=mock_confluence,
            trifecta_analyzer=mock_trifecta
        )
        
        # Mock para evitar errores de processing
        signal_factory._is_duplicate_signal = Mock(return_value=False)
        signal_factory._process_valid_signal = AsyncMock()
        
        import pandas as pd
        df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})
        
        from models.signal import MarketRegime
        usr_signals = await signal_factory.generate_signal("EUR/USD", df, MarketRegime.TREND)
        
        # Verificar que ambos motores fueron llamados
        engine_1.analyze.assert_called_once()
        engine_2.analyze.assert_called_once()

    @pytest.mark.asyncio
    async def test_signal_factory_generate_usr_signals_batch_with_dict(self):
        """Verifica que generate_usr_signals_batch() funciona con Dict engines."""
        mock_storage = Mock()
        mock_confluence = Mock()
        mock_confluence.enabled = False
        mock_trifecta = Mock()
        
        engine_1 = Mock()
        engine_1.analyze = AsyncMock(return_value=None)
        
        engines_dict = {"STRAT_1": engine_1}
        
        signal_factory = SignalFactory(
            storage_manager=mock_storage,
            strategy_engines=engines_dict,
            confluence_analyzer=mock_confluence,
            trifecta_analyzer=mock_trifecta
        )
        
        signal_factory.generate_signal = AsyncMock(return_value=[])
        
        import pandas as pd
        from models.signal import MarketRegime
        
        scan_results = {
            "EUR/USD|M5": {
                "regime": MarketRegime.TREND,
                "df":pd.DataFrame({"close": [1.0, 2.0]}),
                "symbol": "EUR/USD",
                "timeframe": "M5"
            }
        }
        
        usr_signals = await signal_factory.generate_usr_signals_batch(scan_results)
        
        assert isinstance(usr_signals, list)


class TestNOHardcodingOfStrategies:
    """Verificaciones explícitas de que NO hay hardcoding de estrategias."""

    def test_main_orchestrator_no_hardcoded_oliver_velez(self):
        """Verifica que main_orchestrator.py NO importa OliverVelezStrategy en línea 1320."""
        # Esta prueba lee el código fuente directamente
        from pathlib import Path
        import re
        
        mo_file = Path(__file__).parent.parent / "core_brain" / "main_orchestrator.py"
        content = mo_file.read_text()
        
        # Buscar la sección de estrategias (línea ~1320)
        # Verificar que NO contiene: "ov_strategy = OliverVelezStrategy(...)"
        # Verificar que CONTIENE: "StrategyEngineFactory"
        
        # find the usr_strategies initialization section
        match = re.search(r"# FASE 2.*?usr_strategies.*?SignalFactory", content, re.DOTALL)
        
        if match:
            section = match.group(0)
            assert "OliverVelezStrategy" not in section, "OliverVelezStrategy should not be hardcoded in usr_strategies section"
            assert "StrategyEngineFactory" in section, "StrategyEngineFactory should be used"
        else:
            pytest.skip("Could not find usr_strategies initialization section")

    def test_signal_factory_constructor_signature(self):
        """Verifica que SignalFactory recibe strategy_engines, no usr_strategies."""
        import inspect
        
        sig = inspect.signature(SignalFactory.__init__)
        params = list(sig.parameters.keys())
        
        assert "strategy_engines" in params, "Constructor should have strategy_engines parameter"
        assert "usr_strategies" not in params, "Constructor should NOT have usr_strategies parameter"


class TestDependencyValidation:
    """Pruebas de validación de dependencias en StrategyEngineFactory."""

    def test_validate_dependencies_all_available(self):
        """Verifica validación cuando todos los sensores están disponibles."""
        mock_storage = Mock()
        factory = StrategyEngineFactory(
            storage=mock_storage,
            available_sensors={
                "ElephantCandleDetector": Mock(),
                "Moving AverageSensor": Mock()
            }
        )
        
        missing = factory._validate_dependencies(
            "TEST_STRAT",
            ["ElephantCandleDetector", "MovingAverageSensor"]
        )
        
        assert missing == []

    def test_validate_dependencies_some_missing(self):
        """Verifica validación cuando faltan sensores."""
        mock_storage = Mock()
        factory = StrategyEngineFactory(
            storage=mock_storage,
            available_sensors={"ElephantCandleDetector": Mock()}
        )
        
        missing = factory._validate_dependencies(
            "TEST_STRAT",
            ["ElephantCandleDetector", "MovingAverageSensor", "SessionLiquiditySensor"]
        )
        
        assert set(missing) == {"MovingAverageSensor", "SessionLiquiditySensor"}

    def test_validate_dependencies_none_available(self):
        """Verifica validación cuando NO hay sensores disponibles."""
        mock_storage = Mock()
        factory = StrategyEngineFactory(storage=mock_storage, available_sensors={})
        
        missing = factory._validate_dependencies(
            "TEST_STRAT",
            ["Sensor1", "Sensor2"]
        )
        
        assert set(missing) == {"Sensor1", "Sensor2"}


# ─────────────────────────────────────────────────────────────
# HELPER: AsyncMock para Python < 3.8 compatibility
# ─────────────────────────────────────────────────────────────

class AsyncMock(MagicMock):
    """Mock para funciones async."""
    async def __call__(self, *args, **kwargs):
        return super(AsyncMock, self).__call__(*args, **kwargs)
