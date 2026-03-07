"""
Tests for SignalDeduplicator - Signal Deduplication Module
===========================================================

Tests the extraction of _is_duplicate_signal() logic from SignalFactory.
Validates symbol normalization, position checking, and MT5 reconciliation.
"""
import pytest
from unittest.mock import Mock, MagicMock, AsyncMock
from datetime import datetime
from typing import Any

from core_brain.signal_deduplicator import SignalDeduplicator
from data_vault.storage import StorageManager
from models.signal import Signal, SignalType, ConnectorType


class TestSignalDeduplicator:
    """Test cases for SignalDeduplicator"""
    
    @pytest.fixture
    def mock_storage(self) -> Any:
        """Mock StorageManager for deduplicator"""
        storage = MagicMock(spec=StorageManager)
        # Default: no duplicates, no open usr_positions
        storage.has_open_position.return_value = False
        storage.has_recent_signal.return_value = False
        storage.get_open_operations.return_value = []
        return storage
    
    @pytest.fixture
    def mock_mt5_connector(self) -> Any:
        """Mock MT5Connector for reconciliation"""
        connector = MagicMock()
        # Default: MT5 has matching usr_positions
        connector.get_open_usr_positions.return_value = [
            {'symbol': 'EURUSD', 'ticket': 12345},
            {'symbol': 'GBPUSD', 'ticket': 12346},
        ]
        return connector
    
    @pytest.fixture
    def deduplicator(self, mock_storage):
        """Create deduplicator with mocked dependencies"""
        return SignalDeduplicator(
            storage_manager=mock_storage,
            mt5_connector=None  # Default: no MT5
        )
    
    @pytest.fixture
    def deduplicator_with_mt5(self, mock_storage, mock_mt5_connector):
        """Create deduplicator with MT5 support"""
        return SignalDeduplicator(
            storage_manager=mock_storage,
            mt5_connector=mock_mt5_connector
        )
    
    @pytest.fixture
    def sample_signal(self) -> Signal:
        """Create a sample signal for testing"""
        return Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020,
            metadata={"score": 85}
        )
    
    def test_is_duplicate_no_duplicates(self, deduplicator, sample_signal):
        """Test that signal is NOT a duplicate when no existing usr_signals/usr_positions"""
        # Arrange: storage returns False for all checks
        assert deduplicator.is_duplicate(sample_signal) is False
    
    def test_is_duplicate_recent_signal_detected(self, deduplicator, mock_storage, sample_signal):
        """Test that duplicate is detected when recent signal exists"""
        # Arrange: has_recent_signal returns True
        mock_storage.has_recent_signal.return_value = True
        
        # Act & Assert
        assert deduplicator.is_duplicate(sample_signal) is True
        mock_storage.has_recent_signal.assert_called_once()
    
    def test_is_duplicate_open_position_detected(self, deduplicator, mock_storage, sample_signal):
        """Test that duplicate is detected when open position exists"""
        # Arrange: has_open_position returns True
        mock_storage.has_open_position.return_value = True
        
        # Act & Assert
        assert deduplicator.is_duplicate(sample_signal) is True
        mock_storage.has_open_position.assert_called_once()
    
    def test_symbol_normalization_yahoo_format(self, deduplicator):
        """Test normalization of Yahoo Finance format symbols"""
        # Arrange: signal with Yahoo notation
        signal_yahoo = Signal(
            symbol="GBPUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.80,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.2700,
            stop_loss=1.2690,
            take_profit=1.2710
        )
        
        # Act: normalize_symbol
        normalized = deduplicator._normalize_symbol(signal_yahoo)
        
        # Assert: Yahoo suffix removed
        assert normalized == "GBPUSD"
        assert "=X" not in normalized
    
    def test_signal_type_extraction(self, deduplicator, sample_signal):
        """Test extraction of signal type value from enum"""
        # Act
        signal_type_str = deduplicator._get_signal_type_str(sample_signal)
        
        # Assert
        assert signal_type_str == "BUY"
        assert isinstance(signal_type_str, str)
    
    def test_open_position_without_mt5_connector(self, deduplicator, mock_storage, sample_signal):
        """Test handling of open position when MT5 connector not available"""
        # Arrange: position exists, MT5 not available
        mock_storage.has_open_position.return_value = True
        
        # Act & Assert: should return True (block signal)
        assert deduplicator.is_duplicate(sample_signal) is True
    
    def test_mt5_reconciliation_ghost_position_cleanup(self, deduplicator_with_mt5, mock_storage, mock_mt5_connector, sample_signal):
        """Test detection and cleanup of ghost usr_positions"""
        # Arrange: position in DB but not in MT5
        mock_storage.has_open_position.return_value = True
        mock_storage.get_open_operations.return_value = [
            {
                'id': 'sig_001',
                'symbol': 'EURUSD'
            }
        ]
        mock_mt5_connector.get_open_usr_positions.return_value = []  # Empty = ghost position
        
        # Act
        result = deduplicator_with_mt5.is_duplicate(sample_signal)
        
        # Assert: ghost position cleanup called
        mock_storage._clear_ghost_position_inline.assert_called_once_with('EURUSD')
        assert result is False  # Signal allowed after cleanup
    
    def test_mt5_reconciliation_real_position_blocked(self, deduplicator_with_mt5, mock_storage, mock_mt5_connector, sample_signal):
        """Test blocking of signal when real MT5 position exists"""
        # Arrange: position exists both in DB and MT5
        mock_storage.has_open_position.return_value = True
        mock_storage.get_open_operations.return_value = [
            {
                'id': 'sig_001',
                'symbol': 'EURUSD'
            }
        ]
        mock_mt5_connector.get_open_usr_positions.return_value = [
            {'symbol': 'EURUSD', 'ticket': 12345}
        ]
        
        # Act
        result = deduplicator_with_mt5.is_duplicate(sample_signal)
        
        # Assert: signal rejected, no cleanup
        mock_storage._clear_ghost_position_inline.assert_not_called()
        assert result is True  # Signal blocked
    
    def test_timeframe_specific_duplicate_detection(self, deduplicator, mock_storage, sample_signal):
        """Test that deduplication respects timeframe parameter"""
        # Arrange: signal with specific timeframe
        sample_signal.timeframe = "M5"
        
        # Act
        deduplicator.is_duplicate(sample_signal)
        
        # Assert: timeframe passed to storage
        mock_storage.has_open_position.assert_called_once_with('EURUSD', 'M5')
    
    def test_multiple_usr_signals_same_symbol_different_timeframes(self, deduplicator, mock_storage):
        """Test that same symbol on different timeframes are NOT duplicates"""
        # Arrange: two usr_signals, same symbol, different timeframes
        signal_m5 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020,
            timeframe="M5"
        )
        
        signal_h1 = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.85,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020,
            timeframe="H1"
        )
        
        # Act: check dedup for both
        dup_m5 = deduplicator.is_duplicate(signal_m5)
        dup_h1 = deduplicator.is_duplicate(signal_h1)
        
        # Assert: both return False (not duplicates of each other)
        assert dup_m5 is False
        assert dup_h1 is False
        
        # Verify storage was called with different timeframes
        calls = mock_storage.has_open_position.call_args_list
        assert len(calls) == 2
        assert calls[0][0][1] == "M5"
        assert calls[1][0][1] == "H1"
    
    def test_edge_learning_recorded_on_ghost_cleanup(self, deduplicator_with_mt5, mock_storage, mock_mt5_connector):
        """Test that edge learning is recorded when ghost position is cleaned"""
        # Arrange: setup ghost position scenario
        signal = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.SELL,
            confidence=0.80,
            connector_type=ConnectorType.METATRADER5,
            entry_price=1.2700,
            stop_loss=1.2710,
            take_profit=1.2690
        )
        
        mock_storage.has_open_position.return_value = True
        mock_storage.get_open_operations.return_value = [
            {'id': 'sig_ghost_001', 'symbol': 'GBPUSD'}
        ]
        mock_mt5_connector.get_open_usr_positions.return_value = []
        
        # Act
        deduplicator_with_mt5.is_duplicate(signal)
        
        # Assert: edge learning called
        mock_storage.save_edge_learning.assert_called_once()
        call_args = mock_storage.save_edge_learning.call_args
        assert 'Discrepancia DB vs MT5' in call_args[1]['detection']
        assert 'Limpieza de registros fantasma' in call_args[1]['action_taken']
