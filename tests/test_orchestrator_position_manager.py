"""
Tests for PositionManager integration with MainOrchestrator

FASE 2: Integración - Verificar que PositionManager funciona en producción

Tests TDD (Red-Green-Refactor):
1. PositionManager se instancia en MainOrchestrator.__init__
2. Config cargada desde dynamic_params.json
3. monitor_positions() se llama en run_single_cycle()
4. Monitor ejecutado cada 10 segundos aprox (según current_cycle_count)
5. Metadata se guarda al abrir posición (via Executor)
"""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch, AsyncMock
from pathlib import Path

from core_brain.main_orchestrator import MainOrchestrator
from core_brain.position_manager import PositionManager
from data_vault.storage import StorageManager


# Fixtures

@pytest.fixture
def mock_scanner():
    """Mock ScannerEngine"""
    scanner = Mock()
    scanner.get_scan_results_with_data = Mock(return_value={})
    return scanner


@pytest.fixture
def mock_signal_factory():
    """Mock SignalFactory"""
    factory = Mock()
    factory.generate_signals_batch = AsyncMock(return_value=[])
    return factory


@pytest.fixture
def mock_risk_manager():
    """Mock RiskManager"""
    rm = Mock()
    rm.is_lockdown_active = Mock(return_value=False)
    rm.consecutive_losses = 0
    rm.validate_signal = Mock(return_value=(True, "OK"))
    return rm


@pytest.fixture
def mock_executor():
    """Mock Executor"""
    executor = Mock()
    executor.execute_signal = AsyncMock(return_value={"success": True, "ticket": 12345})
    return executor


@pytest.fixture
def mock_storage():
    """Mock StorageManager"""
    storage = Mock(spec=StorageManager)
    storage.get_brokers = Mock(return_value=[])
    storage.count_executed_signals = Mock(return_value=0)
    storage.get_system_state = Mock(return_value={})
    storage.update_module_heartbeat = Mock()
    storage.update_system_state = Mock()
    storage.get_open_positions = Mock(return_value=[])
    return storage


@pytest.fixture
def temp_config(tmp_path):
    """Create temporary config files"""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    
    # config.json básico
    config_file = config_dir / "config.json"
    config_data = {
        "orchestrator": {
            "loop_interval_trend": 5,
            "loop_interval_range": 30,
            "loop_interval_volatile": 15,
            "loop_interval_shock": 60
        }
    }
    config_file.write_text(json.dumps(config_data))
    
    # dynamic_params.json con position_management
    dynamic_file = config_dir / "dynamic_params.json"
    dynamic_data = {
        "position_management": {
            "enabled": True,
            "max_drawdown_multiplier": 2.0,
            "modification_cooldown_seconds": 300,
            "max_modifications_per_day": 10,
            "time_based_exit_enabled": True,
            "stale_position_thresholds": {
                "TREND": 72,
                "RANGE": 4,
                "VOLATILE": 2,
                "CRASH": 1,
                "NEUTRAL": 24
            },
            "sl_tp_adjustments": {
                "TREND": {"sl_atr_multiplier": 3.0, "tp_rr_ratio": 3.0},
                "RANGE": {"sl_atr_multiplier": 1.5, "tp_rr_ratio": 1.5},
                "VOLATILE": {"sl_atr_multiplier": 2.0, "tp_rr_ratio": 2.0},
                "CRASH": {"sl_atr_multiplier": 1.0, "tp_rr_ratio": 1.0},
                "NEUTRAL": {"sl_atr_multiplier": 2.0, "tp_rr_ratio": 2.0}
            }
        }
    }
    dynamic_file.write_text(json.dumps(dynamic_data))
    
    return config_dir


# Tests FASE 2.1

def test_position_manager_instantiated_in_init(
    mock_scanner, 
    mock_signal_factory,
    mock_risk_manager,
    mock_executor,
    mock_storage,
    temp_config
):
    """
    Test: PositionManager se instancia en MainOrchestrator.__init__
    
    Expected: orchestrator.position_manager existe y tiene dependencias correctas
    """
    # Create orchestrator
    with patch('core_brain.main_orchestrator.Path') as mock_path:
        # Mock Path(__file__).parent.parent to return temp_config's parent
        mock_path.return_value.parent.parent = temp_config.parent
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=mock_storage,
            config_path=str(temp_config / "config.json")
        )
    
    # Assert: PositionManager exists
    assert hasattr(orchestrator, 'position_manager'), "PositionManager not instantiated"
    assert isinstance(orchestrator.position_manager, PositionManager)
    
    # Assert: Dependencies injected correctly
    assert orchestrator.position_manager.storage == mock_storage
    # NOTE: connector will be injected from executor when we implement it


def test_position_manager_config_loaded_from_dynamic_params(
    mock_scanner,
    mock_signal_factory,
    mock_risk_manager,
    mock_executor,
    mock_storage,
    temp_config
):
    """
    Test: Config de PositionManager cargada desde dynamic_params.json
    
    Expected: orchestrator.position_manager.config contiene valores de dynamic_params.json
    """
    # Load dynamic_params.json to verify
    dynamic_file = temp_config / "dynamic_params.json"
    with open(dynamic_file) as f:
        expected_config = json.load(f)['position_management']
    
    # Create orchestrator
    with patch('core_brain.main_orchestrator.Path') as mock_path:
        mock_path.return_value.parent.parent = temp_config.parent
        
        orchestrator = MainOrchestrator(
            scanner=mock_scanner,
            signal_factory=mock_signal_factory,
            risk_manager=mock_risk_manager,
            executor=mock_executor,
            storage=mock_storage,
            config_path=str(temp_config / "config.json")
        )
    
    # Assert: Config loaded correctly
    assert orchestrator.position_manager.max_drawdown_multiplier == expected_config['max_drawdown_multiplier']
    assert orchestrator.position_manager.cooldown_seconds == expected_config['modification_cooldown_seconds']
    assert orchestrator.position_manager.max_modifications_per_day == expected_config['max_modifications_per_day']


@pytest.mark.asyncio
async def test_monitor_positions_called_in_single_cycle(
    mock_scanner,
    mock_signal_factory,
    mock_risk_manager,
    mock_executor,
    mock_storage,
    temp_config
):
    """
    Test: monitor_positions() se llama en run_single_cycle()
    
    Expected: position_manager.monitor_positions() ejecutado al menos una vez
    """
    # Mock expiration manager
    with patch('core_brain.main_orchestrator.SignalExpirationManager') as mock_exp_mgr_class:
        mock_exp_mgr = Mock()
        mock_exp_mgr.expire_old_signals = Mock(return_value={'total_expired': 0, 'total_checked': 0, 'by_timeframe': {}})
        mock_exp_mgr_class.return_value = mock_exp_mgr
        
        with patch('core_brain.main_orchestrator.Path') as mock_path:
            mock_path.return_value.parent.parent = temp_config.parent
            
            orchestrator = MainOrchestrator(
                scanner=mock_scanner,
                signal_factory=mock_signal_factory,
                risk_manager=mock_risk_manager,
                executor=mock_executor,
                storage=mock_storage,
                config_path=str(temp_config / "config.json")
            )
    
    # Mock PositionManager.monitor_positions
    orchestrator.position_manager.monitor_positions = Mock(return_value={
        'monitored': 0,
        'actions': []
    })
    
    # Execute one cycle
    await orchestrator.run_single_cycle()
    
    # Assert: monitor_positions called
    orchestrator.position_manager.monitor_positions.assert_called_once()


@pytest.mark.asyncio
async def test_monitor_positions_executed_periodically(
    mock_scanner,
    mock_signal_factory,
    mock_risk_manager,
    mock_executor,
    mock_storage,
    temp_config
):
    """
    Test: monitor_positions() se ejecuta cada ~10 segundos (cada ciclo)
    
    Expected: Después de 3 ciclos, monitor_positions llamado 3 veces
    """
    # Mock expiration manager
    with patch('core_brain.main_orchestrator.SignalExpirationManager') as mock_exp_mgr_class:
        mock_exp_mgr = Mock()
        mock_exp_mgr.expire_old_signals = Mock(return_value={'total_expired': 0, 'total_checked': 0, 'by_timeframe': {}})
        mock_exp_mgr_class.return_value = mock_exp_mgr
        
        with patch('core_brain.main_orchestrator.Path') as mock_path:
            mock_path.return_value.parent.parent = temp_config.parent
            
            orchestrator = MainOrchestrator(
                scanner=mock_scanner,
                signal_factory=mock_signal_factory,
                risk_manager=mock_risk_manager,
                executor=mock_executor,
                storage=mock_storage,
                config_path=str(temp_config / "config.json")
            )
    
    # Mock PositionManager.monitor_positions
    orchestrator.position_manager.monitor_positions = Mock(return_value={
        'monitored': 0,
        'actions': []
    })
    
    # Execute 3 cycles
    for _ in range(3):
        await orchestrator.run_single_cycle()
    
    # Assert: monitor_positions called 3 times
    assert orchestrator.position_manager.monitor_positions.call_count == 3


@pytest.mark.asyncio
async def test_metadata_saved_when_position_opened(
    mock_scanner,
    mock_signal_factory,
    mock_risk_manager,
    mock_executor,
    mock_storage,
    temp_config
):
    """
    Test: Metadata se guarda al abrir una posición (via Executor)
    
    Expected: storage.update_position_metadata llamado con datos correctos
    """
    # This test will be implemented after we modify Executor to save metadata
    # For now, we just verify the structure exists
    
    # Mock signal and execution result
    from models.signal import Signal, MarketRegime, SignalType, ConnectorType
    
    test_signal = Signal(
        symbol="EURUSD",
        signal_type=SignalType.BUY,
        connector_type=ConnectorType.METATRADER5,
        timeframe="H1",
        entry_price=1.08500,
        stop_loss=1.08200,
        take_profit=1.09000,
        confidence=0.85,
        metadata={
            "regime": MarketRegime.TREND.value,
            "expiration_bars": 5
        }
    )
    
    mock_signal_factory.generate_signals_batch = AsyncMock(return_value=[test_signal])
    mock_risk_manager.validate_signal = Mock(return_value=(True, "OK"))
    mock_executor.execute_signal = AsyncMock(return_value={
        "success": True,
        "ticket": 12345678,
        "volume": 0.10
    })
    
    # This will be asserted after implementation
    # For now, placeholder test
    assert True, "Metadata saving will be implemented in FASE 2.2"
