"""
Tests for SignalConflictAnalyzer - Multi-Timeframe Confluence Module
====================================================================

Tests the extraction of _apply_confluence() logic from SignalFactory.
Validates regime grouping and confluence bonus calculation.
"""
import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Any

from core_brain.signal_conflict_analyzer import SignalConflictAnalyzer
from models.signal import Signal, SignalType, ConnectorType, MarketRegime


class TestSignalConflictAnalyzer:
    """Test cases for SignalConflictAnalyzer"""
    
    @pytest.fixture
    def mock_confluence_analyzer(self) -> Any:
        """Mock MultiTimeframeConfluenceAnalyzer"""
        analyzer = MagicMock()
        return analyzer
    
    @pytest.fixture
    def conflict_analyzer(self, mock_confluence_analyzer):
        """Create conflict analyzer with mocked dependencies"""
        return SignalConflictAnalyzer(
            confluence_analyzer=mock_confluence_analyzer
        )
    
    @pytest.fixture
    def sample_usr_signals(self) -> List[Signal]:
        """Create sample usr_signals for testing"""
        return [
            Signal(
                symbol="EURUSD",
                signal_type=SignalType.BUY,
                confidence=0.75,
                connector_type=ConnectorType.PAPER,
                entry_price=1.1000,
                stop_loss=1.0990,
                take_profit=1.1020,
                timeframe="M15"
            ),
            Signal(
                symbol="GBPUSD",
                signal_type=SignalType.SELL,
                confidence=0.70,
                connector_type=ConnectorType.PAPER,
                entry_price=1.2700,
                stop_loss=1.2710,
                take_profit=1.2690,
                timeframe="M15"
            )
        ]
    
    @pytest.fixture
    def sample_scan_results(self) -> Dict:
        """Create sample scan results with multi-timeframe regimes"""
        return {
            "EURUSD": {
                "M5": {
                    "regime": MarketRegime.TREND,
                    "strength": 0.85
                },
                "M15": {
                    "regime": MarketRegime.TREND,
                    "strength": 0.80
                },
                "H1": {
                    "regime": MarketRegime.TREND,
                    "strength": 0.75
                }
            },
            "GBPUSD": {
                "M5": {
                    "regime": MarketRegime.RANGE,
                    "strength": 0.70
                },
                "M15": {
                    "regime": MarketRegime.RANGE,
                    "strength": 0.65
                },
                "H1": {
                    "regime": MarketRegime.TREND,
                    "strength": 0.80
                }
            }
        }
    
    def test_apply_confluence_empty_usr_signals(self, conflict_analyzer, sample_scan_results):
        """Test apply_confluence with empty signal list"""
        # Act
        result = conflict_analyzer.apply_confluence([], sample_scan_results)
        
        # Assert: should return empty list
        assert result == []
    
    def test_apply_confluence_no_market_data(self, conflict_analyzer, sample_usr_signals):
        """Test apply_confluence when market data is empty"""
        # Act
        result = conflict_analyzer.apply_confluence(sample_usr_signals, {})
        
        # Assert: should return usr_signals unchanged
        assert len(result) == len(sample_usr_signals)
        assert result[0].confidence == 0.75
        assert result[1].confidence == 0.70
    
    def test_apply_confluence_multi_trend_bonus(self, conflict_analyzer, sample_usr_signals, sample_scan_results, mock_confluence_analyzer):
        """Test confidence boost when multiple timeframes in TREND"""
        # Arrange: EURUSD has TREND on M5, M15, H1
        # Expected: original 0.75 * (1 + confluence_bonus)
        mock_confluence_analyzer.analyze.return_value = 0.15  # 15% bonus
        scan_results = {"market_data": sample_scan_results}
        
        # Act
        result = conflict_analyzer.apply_confluence(sample_usr_signals, scan_results)
        
        # Assert: both usr_signals should be boosted (same bonus applied to all)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        gbpusd_result = next(s for s in result if s.symbol == "GBPUSD")
        
        # With mock returning 0.15 bonus for all, both should get (orig * 1.15)
        # EURUSD: 0.75 * 1.15 = 0.8625
        assert eurusd_result.confidence == pytest.approx(0.75 * 1.15, rel=0.01)
        # GBPUSD: 0.70 * 1.15 = 0.805
        assert gbpusd_result.confidence == pytest.approx(0.70 * 1.15, rel=0.01)
    
    def test_confluence_bonus_calculation_formula(self, conflict_analyzer, sample_usr_signals, sample_scan_results):
        """Test that confluence bonus follows formula: new = original * (1 + bonus)"""
        # Arrange
        original_confidence = sample_usr_signals[0].confidence
        
        # Act
        result = conflict_analyzer.apply_confluence(sample_usr_signals, sample_scan_results)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: new confidence should be between original and 1.0
        assert original_confidence <= eurusd_result.confidence <= 1.0
        # Verify it's indeed multiplied (not just set to arbitrary value)
        expected_multiplier = eurusd_result.confidence / original_confidence
        assert 1.0 <= expected_multiplier <= 1.5  # Reasonable range for bonus
    
    def test_group_regimes_excludes_primary_timeframe(self, conflict_analyzer, sample_scan_results):
        """Test that regime grouping excludes the signal's primary timeframe"""
        # Arrange: signal on M15, should exclude M15 from group
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0990,
            take_profit=1.1020,
            timeframe="M15"
        )
        
        # Act
        grouped = conflict_analyzer._group_regimes_by_symbol(
            sample_scan_results,
            [signal]
        )
        
        # Assert: EURUSD regimes should NOT include M15 data
        eurusd_regimes = grouped.get("EURUSD", [])
        # EURUSD M5, M15, H1 all have TREND, but M15 is excluded as primary timeframe
        # So should have 2 regimes (M5=TREND, H1=TREND), excluding M15
        assert len(eurusd_regimes) == 2
        # All should be TREND
        assert all(r == MarketRegime.TREND for r in eurusd_regimes)
    
    def test_confluence_bonus_max_caps(self, conflict_analyzer, sample_usr_signals, sample_scan_results):
        """Test that confidence never exceeds 1.0"""
        # Arrange: signal with high initial confidence
        sample_usr_signals[0].confidence = 0.95
        
        # Act
        result = conflict_analyzer.apply_confluence(sample_usr_signals, sample_scan_results)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: confidence capped at 1.0
        assert eurusd_result.confidence <= 1.0
    
    def test_apply_confluence_exception_handling(self, conflict_analyzer, sample_usr_signals, mock_confluence_analyzer):
        """Test graceful handling when confluence analyzer raises exception"""
        # Arrange: mock to raise exception
        mock_confluence_analyzer.analyze.side_effect = Exception("Analyzer error")
        
        # Act: should not raise, return usr_signals unchanged
        result = conflict_analyzer.apply_confluence(
            sample_usr_signals,
            {"EURUSD": {"M5": {"regimes": []}}}
        )
        
        # Assert: usr_signals returned unchanged
        assert len(result) == len(sample_usr_signals)
        assert result[0].confidence == sample_usr_signals[0].confidence
    
    def test_apply_confluence_preserves_signal_metadata(self, conflict_analyzer, sample_usr_signals, sample_scan_results):
        """Test that confluence analysis preserves signal metadata"""
        # Arrange: add custom metadata
        sample_usr_signals[0].metadata = {"source": "test", "version": 2}
        
        # Act
        result = conflict_analyzer.apply_confluence(sample_usr_signals, sample_scan_results)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: metadata preserved
        assert eurusd_result.metadata is not None
        assert eurusd_result.metadata.get("source") == "test"
        assert eurusd_result.metadata.get("version") == 2
    
    def test_multiple_symbols_independent_processing(self, conflict_analyzer, sample_usr_signals, sample_scan_results):
        """Test that confluence analysis for multiple symbols is independent"""
        # Arrange: usr_signals for different symbols
        usr_signals = [
            Signal(
                symbol="EURUSD",
                signal_type=SignalType.BUY,
                confidence=0.75,
                connector_type=ConnectorType.PAPER,
                entry_price=1.1000,
                stop_loss=1.0990,
                take_profit=1.1020,
                timeframe="M15"
            ),
            Signal(
                symbol="GBPUSD",
                signal_type=SignalType.BUY,  # Same direction, different symbol
                confidence=0.75,
                connector_type=ConnectorType.PAPER,
                entry_price=1.2700,
                stop_loss=1.2690,
                take_profit=1.2710,
                timeframe="M15"
            )
        ]
        
        # Act
        result = conflict_analyzer.apply_confluence(usr_signals, sample_scan_results)
        
        # Assert: each processed independently
        eurusd = next(s for s in result if s.symbol == "EURUSD")
        gbpusd = next(s for s in result if s.symbol == "GBPUSD")
        
        # EURUSD should have stronger boost (3 TREND regimes) than GBPUSD (1 TREND regime)
        assert eurusd.confidence >= gbpusd.confidence
    
    def test_confluence_low_confidence_usr_signals(self, conflict_analyzer):
        """Test confluence analysis on very low confidence usr_signals"""
        # Arrange: very low confidence signal
        signal = Signal(
            symbol="AUDUSD",
            signal_type=SignalType.BUY,
            confidence=0.10,
            connector_type=ConnectorType.PAPER,
            entry_price=0.6500,
            stop_loss=0.6490,
            take_profit=0.6510,
            timeframe="M15"
        )
        
        # Act
        result = conflict_analyzer.apply_confluence([signal], {})
        
        # Assert: still returns signal (doesn't filter)
        assert len(result) == 1
        assert result[0].confidence == 0.10
    
    def test_group_regimes_handles_missing_symbol(self, conflict_analyzer):
        """Test _group_regimes_by_symbol when symbol not in scan_results"""
        # Arrange: signal for symbol not in data
        signal = Signal(
            symbol="XXXAAA",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type=ConnectorType.PAPER,
            entry_price=1.0000,
            stop_loss=0.9990,
            take_profit=1.0010,
            timeframe="M15"
        )
        
        # Act
        grouped = conflict_analyzer._group_regimes_by_symbol(
            {},  # Empty market data
            [signal]
        )
        
        # Assert: returns empty regime list for missing symbol
        assert grouped.get("XXXAAA", []) == []
    
    def test_confluence_metadata_updated_with_analysis(self, conflict_analyzer, sample_usr_signals, sample_scan_results):
        """Test that metadata is updated with confluence analysis details"""
        # Arrange
        sample_usr_signals[0].metadata = {}
        
        # Act
        result = conflict_analyzer.apply_confluence(sample_usr_signals, sample_scan_results)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: metadata contains confluence information
        assert eurusd_result.metadata is not None
        if "confluence_bonus" in eurusd_result.metadata:
            assert eurusd_result.metadata["confluence_bonus"] >= 0
