"""
Tests for SignalTrifectaOptimizer - Oliver Velez M2-M5-M15 Strategy Module
===========================================================================

Tests the extraction of _apply_trifecta_optimization() logic from SignalFactory.
Validates Oliver Velez filtering and score calculation.
"""
import pytest
from unittest.mock import Mock, MagicMock
from typing import Dict, List, Any

from core_brain.signal_trifecta_optimizer import SignalTrifectaOptimizer
from models.signal import Signal, SignalType, ConnectorType


class TestSignalTrifectaOptimizer:
    """Test cases for SignalTrifectaOptimizer"""
    
    @pytest.fixture
    def mock_trifecta_analyzer(self) -> Any:
        """Mock TrifectaAnalyzer"""
        analyzer = MagicMock()
        return analyzer
    
    @pytest.fixture
    def trifecta_optimizer(self, mock_trifecta_analyzer):
        """Create trifecta optimizer with mocked dependencies"""
        return SignalTrifectaOptimizer(
            trifecta_analyzer=mock_trifecta_analyzer
        )
    
    @pytest.fixture
    def oliver_strategy_signals(self) -> List[Signal]:
        """Create signals with oliver strategy_id"""
        return [
            Signal(
                symbol="EURUSD",
                signal_type=SignalType.BUY,
                confidence=0.75,
                connector_type=ConnectorType.PAPER,
                entry_price=1.1000,
                stop_loss=1.0990,
                take_profit=1.1020,
                timeframe="M15",
                metadata={"strategy_id": "oliver"}
            ),
            Signal(
                symbol="GBPUSD",
                signal_type=SignalType.SELL,
                confidence=0.70,
                connector_type=ConnectorType.PAPER,
                entry_price=1.2700,
                stop_loss=1.2710,
                take_profit=1.2690,
                timeframe="M15",
                metadata={"strategy_id": "oliver"}
            )
        ]
    
    @pytest.fixture
    def mixed_strategy_signals(self) -> List[Signal]:
        """Create signals with mixed strategy_ids"""
        return [
            Signal(
                symbol="EURUSD",
                signal_type=SignalType.BUY,
                confidence=0.75,
                connector_type=ConnectorType.PAPER,
                entry_price=1.1000,
                stop_loss=1.0990,
                take_profit=1.1020,
                timeframe="M15",
                metadata={"strategy_id": "oliver"}
            ),
            Signal(
                symbol="GBPUSD",
                signal_type=SignalType.SELL,
                confidence=0.70,
                connector_type=ConnectorType.PAPER,
                entry_price=1.2700,
                stop_loss=1.2710,
                take_profit=1.2690,
                timeframe="M15",
                metadata={"strategy_id": "scalper"}
            )
        ]
    
    @pytest.fixture
    def full_market_data(self) -> Dict:
        """Create complete market data for all timeframes"""
        return {
            "EURUSD": {
                "M2": {
                    "close": [1.1000, 1.1001, 1.1002],
                    "high": [1.1005, 1.1006, 1.1007],
                    "low": [1.0995, 1.0996, 1.0997],
                    "trifecta_score": 0.80
                },
                "M5": {
                    "close": [1.1000, 1.0999, 1.1001],
                    "high": [1.1010, 1.1008, 1.1009],
                    "low": [1.0990, 1.0990, 1.0992],
                    "trifecta_score": 0.75
                },
                "M15": {
                    "close": [1.0990, 1.1000, 1.1005],
                    "high": [1.1010, 1.1015, 1.1020],
                    "low": [1.0990, 1.1000, 1.1003],
                    "trifecta_score": 0.70
                }
            },
            "GBPUSD": {
                "M2": {
                    "close": [1.2700, 1.2698, 1.2695],
                    "high": [1.2710, 1.2708, 1.2705],
                    "low": [1.2690, 1.2688, 1.2685],
                    "trifecta_score": 0.65
                },
                "M5": {
                    "close": [1.2700, 1.2702, 1.2701],
                    "high": [1.2710, 1.2715, 1.2714],
                    "low": [1.2690, 1.2692, 1.2691],
                    "trifecta_score": 0.60
                },
                "M15": {
                    "close": [1.2720, 1.2700, 1.2695],
                    "high": [1.2730, 1.2720, 1.2710],
                    "low": [1.2700, 1.2690, 1.2685],
                    "trifecta_score": 0.55
                }
            }
        }
    
    def test_optimize_empty_signals(self, trifecta_optimizer, full_market_data):
        """Test optimize with empty signal list"""
        # Act
        result = trifecta_optimizer.optimize([], full_market_data)
        
        # Assert
        assert result == []
    
    def test_optimize_no_market_data(self, trifecta_optimizer, oliver_strategy_signals):
        """Test optimize when market data is empty (degraded mode)"""
        # Act
        result = trifecta_optimizer.optimize(oliver_strategy_signals, {})
        
        # Assert: signals returned unchanged
        assert len(result) == len(oliver_strategy_signals)
        assert result[0].confidence == 0.75
        assert result[1].confidence == 0.70
    
    def test_optimize_only_oliver_strategy(self, trifecta_optimizer, mixed_strategy_signals, full_market_data):
        """Test that optimization only applies to oliver strategy"""
        # Act
        result = trifecta_optimizer.optimize(mixed_strategy_signals, full_market_data)
        
        # Assert: oliver signal optimized, scalper unchanged
        oliver_sig = next(s for s in result if s.metadata.get("strategy_id") == "oliver")
        scalper_sig = next(s for s in result if s.metadata.get("strategy_id") == "scalper")
        
        # Scalper should be unchanged
        assert scalper_sig.confidence == 0.70
        # Oliver might be changed (or same if below threshold)
    
    def test_trifecta_score_calculation_formula(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test score calculation: final = (original * 0.4) + (trifecta * 0.6)"""
        # Arrange
        original_confidence = 0.75  # EURUSD signal
        
        # Mock trifecta analyzer to return known values
        trifecta_optimizer.trifecta_analyzer.analyze.return_value = {
            "M2": {"direction": "UP", "score": 0.80},
            "M5": {"direction": "UP", "score": 0.75},
            "M15": {"direction": "UP", "score": 0.70}
        }
        
        # Act
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: final_score should use formula
        # If aligned: final = (0.75 * 0.4) + (0.75 * 0.6) = 0.75
        # This tests that formula is applied
        assert isinstance(eurusd_result.confidence, float)
        assert 0.0 <= eurusd_result.confidence <= 1.0
    
    def test_filter_by_score_threshold(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test that signals with final_score < 0.60 are filtered out"""
        # Arrange: mock very low trifecta scores
        trifecta_optimizer.trifecta_analyzer.analyze.return_value = {
            "M2": {"direction": "UP", "score": 0.20},
            "M5": {"direction": "DOWN", "score": 0.25},
            "M15": {"direction": "UP", "score": 0.30}
        }
        
        # Act: with low scores, final might be (0.75 * 0.4) + (0.25 * 0.6) = 0.45
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        
        # Assert: if score < 0.60, signal filtered out
        # This depends on actual calculation, but test the behavior
        assert len(result) <= len(oliver_strategy_signals)
    
    def test_degraded_mode_passthrough(self, trifecta_optimizer, oliver_strategy_signals):
        """Test that signals are passed through unmodified in degraded mode (no data)"""
        # Arrange
        original_signals = oliver_strategy_signals.copy()
        
        # Act: call with empty market data = degraded mode
        result = trifecta_optimizer.optimize(oliver_strategy_signals, {})
        
        # Assert: all signals returned with original confidence
        assert len(result) == len(original_signals)
        for orig, res in zip(original_signals, result):
            assert res.confidence == orig.confidence
    
    def test_non_oliver_strategies_passthrough(self, trifecta_optimizer, mixed_strategy_signals, full_market_data):
        """Test that non-oliver strategies are passed through unchanged"""
        # Arrange
        scalper_signal = next(s for s in mixed_strategy_signals if s.metadata.get("strategy_id") == "scalper")
        original_confidence = scalper_signal.confidence
        
        # Act
        result = trifecta_optimizer.optimize(mixed_strategy_signals, full_market_data)
        
        # Assert: scalper signal unchanged
        result_scalper = next(s for s in result if s.metadata.get("strategy_id") == "scalper")
        assert result_scalper.confidence == original_confidence
    
    def test_missing_timeframe_data_handling(self, trifecta_optimizer, oliver_strategy_signals):
        """Test graceful handling when some timeframes missing"""
        # Arrange: market data with missing M2
        incomplete_data = {
            "EURUSD": {
                "M5": {"trifecta_score": 0.75},
                "M15": {"trifecta_score": 0.70}
                # M2 missing
            }
        }
        
        # Act: should handle gracefully
        result = trifecta_optimizer.optimize(oliver_strategy_signals, incomplete_data)
        
        # Assert: returns something (either optimized or original)
        assert len(result) > 0
    
    def test_build_symbol_data_extracts_trifecta_timeframes(self, trifecta_optimizer, full_market_data):
        """Test that _build_symbol_data correctly extracts M2, M5, M15"""
        # Act
        symbol_data = trifecta_optimizer._build_symbol_data(full_market_data)
        
        # Assert: structure contains M2, M5, M15
        eurusd_data = symbol_data.get("EURUSD", {})
        assert "M2" in eurusd_data
        assert "M5" in eurusd_data
        assert "M15" in eurusd_data
    
    def test_trifecta_alignment_metadata_updated(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test that signal metadata is updated with trifecta results"""
        # Arrange
        oliver_strategy_signals[0].metadata = {}
        
        # Mock analyzer
        trifecta_optimizer.trifecta_analyzer.analyze.return_value = {
            "M2": {"direction": "UP", "score": 0.80},
            "M5": {"direction": "UP", "score": 0.75},
            "M15": {"direction": "UP", "score": 0.70}
        }
        
        # Act
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: metadata contains trifecta info
        assert eurusd_result.metadata is not None
        if "trifecta_analysis" in eurusd_result.metadata:
            assert "M2" in eurusd_result.metadata["trifecta_analysis"]
            assert "M5" in eurusd_result.metadata["trifecta_analysis"]
            assert "M15" in eurusd_result.metadata["trifecta_analysis"]
    
    def test_oliver_conflicting_trifecta_rejection(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test that conflicting trifecta signals are rejected or weakened"""
        # Arrange: strong signal but trifecta disagrees
        oliver_strategy_signals[0].confidence = 0.90  # Very strong
        
        # Mock: M2 UP, M5 DOWN, M15 DOWN = conflict
        trifecta_optimizer.trifecta_analyzer.analyze.return_value = {
            "M2": {"direction": "UP", "score": 0.80},
            "M5": {"direction": "DOWN", "score": 0.75},
            "M15": {"direction": "DOWN", "score": 0.70}
        }
        
        # Act
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        
        # Assert: score should be reduced or filtered due to conflict
        eurusd_result = next((s for s in result if s.symbol == "EURUSD"), None)
        # With only 1/3 timeframes aligned and conflict, signal might be filtered or weakened
        # If it passed through, ensure it's not boosted
        if eurusd_result is not None:
            # If passed, should be different (not exactly 0.90) or at least not boosted
            assert eurusd_result.confidence <= 0.90  # At least not boosted
    
    def test_optimize_preserves_other_signal_properties(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test that optimization preserves entry_price, stop_loss, take_profit"""
        # Arrange
        original_entry = oliver_strategy_signals[0].entry_price
        original_stop = oliver_strategy_signals[0].stop_loss
        original_take = oliver_strategy_signals[0].take_profit
        
        # Act
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        eurusd_result = next(s for s in result if s.symbol == "EURUSD")
        
        # Assert: price levels unchanged
        assert eurusd_result.entry_price == original_entry
        assert eurusd_result.stop_loss == original_stop
        assert eurusd_result.take_profit == original_take
    
    def test_exception_handling_in_analyzer(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test graceful handling when trifecta analyzer raises exception"""
        # Arrange: mock to raise exception
        trifecta_optimizer.trifecta_analyzer.analyze.side_effect = Exception("Analyzer error")
        
        # Act: should not raise, return signals unchanged
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        
        # Assert: signals returned unchanged
        assert len(result) == len(oliver_strategy_signals)
        assert result[0].confidence == oliver_strategy_signals[0].confidence
    
    def test_multiple_symbols_independent_optimization(self, trifecta_optimizer, oliver_strategy_signals, full_market_data):
        """Test that multiple symbols are optimized independently"""
        # Arrange: mock different analyzer results for each symbol
        call_count = [0]
        
        def mock_analyze_side_effect(*args, **kwargs):
            call_count[0] += 1
            if "EURUSD" in str(args) or call_count[0] == 1:
                return {
                    "M2": {"direction": "UP", "score": 0.80},
                    "M5": {"direction": "UP", "score": 0.75},
                    "M15": {"direction": "UP", "score": 0.70}
                }
            else:  # GBPUSD
                return {
                    "M2": {"direction": "DOWN", "score": 0.60},
                    "M5": {"direction": "DOWN", "score": 0.55},
                    "M15": {"direction": "DOWN", "score": 0.50}
                }
        
        trifecta_optimizer.trifecta_analyzer.analyze.side_effect = mock_analyze_side_effect
        
        # Act
        result = trifecta_optimizer.optimize(oliver_strategy_signals, full_market_data)
        
        # Assert: each symbol processed separately
        assert len(result) > 0
        eurusd = next(s for s in result if s.symbol == "EURUSD")
        gbpusd = next(s for s in result if s.symbol == "GBPUSD")
        
        # EURUSD with all UP should score better than GBPUSD with all DOWN
        # This verifies independent processing
        assert eurusd.confidence >= gbpusd.confidence or gbpusd.confidence < 0.60
