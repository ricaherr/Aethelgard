"""
Test Suite for Multi-Timeframe Confluence Analyzer
Validates that signals are reinforced or penalized based on multi-timeframe alignment

EDGE Feature: This system learns optimal weights via EdgeTuner
"""
import pytest
from datetime import datetime
from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from core_brain.confluence import MultiTimeframeConfluenceAnalyzer


class TestMultiTimeframeConfluence:
    """Tests for timeframe alignment scoring"""
    
    def test_bullish_signal_reinforced_by_aligned_timeframes(self):
        """
        M5 BUY signal should be REINFORCED when higher timeframes also bullish
        
        Scenario:
        - M5: BUY signal (score=70)
        - M15, H1, H4: All in TREND (bullish)
        - D1: TREND (bullish)
        
        Expected: Score increases due to perfect alignment
        """
        analyzer = MultiTimeframeConfluenceAnalyzer()
        
        # Create primary signal (M5 timeframe)
        signal = Signal(
            symbol="EURUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.70,  # 70% score
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            timeframe="M5",
            metadata={
                "strategy_id": "oliver_velez",
                "score": 70.0
            }
        )
        
        # Timeframe regimes (all bullish - perfect alignment)
        timeframe_regimes = {
            "M15": MarketRegime.TREND,
            "H1": MarketRegime.TREND,
            "H4": MarketRegime.TREND,
            "D1": MarketRegime.TREND
        }
        
        # Apply confluence
        adjusted_signal = analyzer.analyze_confluence(signal, timeframe_regimes)
        
        # Score should INCREASE (70 + bonuses from alignment)
        assert adjusted_signal.confidence > 0.70
        assert adjusted_signal.metadata["confluence_bonus"] > 0
        assert adjusted_signal.metadata["confluence_analysis"]["alignment"] == "STRONG"
    
    def test_bullish_signal_penalized_by_bearish_higher_timeframes(self):
        """
        M5 BUY signal should be PENALIZED when D1 is bearish
        
        Scenario:
        - M5: BUY signal (score=75)
        - D1: RANGE or CRASH (bearish context)
        
        Expected: Score decreases or signal blocked
        """
        analyzer = MultiTimeframeConfluenceAnalyzer()
        
        signal = Signal(
            symbol="EURUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            timeframe="M5",
            metadata={
                "strategy_id": "oliver_velez",
                "score": 75.0
            }
        )
        
        # D1 in downtrend - conflicts with M5 BUY
        timeframe_regimes = {
            "M15": MarketRegime.RANGE,
            "H1": MarketRegime.RANGE,
            "H4": MarketRegime.CRASH,  # Strong downtrend
            "D1": MarketRegime.CRASH   # Strong downtrend
        }
        
        adjusted_signal = analyzer.analyze_confluence(signal, timeframe_regimes)
        
        # Score should DECREASE due to counter-trend
        assert adjusted_signal.confidence < 0.75
        assert adjusted_signal.metadata["confluence_bonus"] < 0  # Negative bonus = penalty
        assert adjusted_signal.metadata["confluence_analysis"]["alignment"] in ["WEAK", "CONFLICTING"]
    
    def test_neutral_timeframes_do_not_affect_signal(self):
        """
        RANGE/NORMAL regimes should have minimal impact on signal score
        
        Scenario:
        - M5: BUY signal (score=80)
        - All higher timeframes: RANGE/NORMAL
        
        Expected: Score stays mostly unchanged
        """
        analyzer = MultiTimeframeConfluenceAnalyzer()
        
        signal = Signal(
            symbol="EURUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.80,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            timeframe="M5",
            metadata={"score": 80.0}
        )
        
        # All timeframes neutral
        timeframe_regimes = {
            "M15": MarketRegime.RANGE,
            "H1": MarketRegime.NORMAL,
            "H4": MarketRegime.RANGE,
            "D1": MarketRegime.NORMAL
        }
        
        adjusted_signal = analyzer.analyze_confluence(signal, timeframe_regimes)
        
        # Score should stay approximately the same (±2%)
        assert abs(adjusted_signal.confidence - 0.80) < 0.02
        assert adjusted_signal.metadata["confluence_analysis"]["alignment"] == "NEUTRAL"
    
    def test_weighted_scoring_favors_higher_timeframes(self):
        """
        H4 and D1 should have MORE weight than M15
        
        Scenario:
        - M5: BUY (score=70)
        - M15: CRASH (bearish, low weight)
        - H4, D1: TREND (bullish, high weight)
        
        Expected: H4/D1 bullish dominates over M15 bearish
        """
        analyzer = MultiTimeframeConfluenceAnalyzer()
        
        signal = Signal(
            symbol="EURUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.70,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            timeframe="M5",
            metadata={"score": 70.0}
        )
        
        # M15 bearish but H4/D1 bullish (higher weight)
        timeframe_regimes = {
            "M15": MarketRegime.CRASH,  # Weight: 15%
            "H1": MarketRegime.TREND,   # Weight: 20%
            "H4": MarketRegime.TREND,   # Weight: 15%
            "D1": MarketRegime.TREND    # Weight: 10%
        }
        
        adjusted_signal = analyzer.analyze_confluence(signal, timeframe_regimes)
        
        # Overall should be positive (H4/D1 outweigh M15)
        assert adjusted_signal.confidence >= 0.70  # At least neutral
        assert adjusted_signal.metadata["confluence_bonus"] >= -5  # Small penalty at most
    
    def test_confluence_metadata_contains_full_analysis(self):
        """
        Metadata should include detailed breakdown for transparency
        
        Expected fields:
        - confluence_bonus: Total bonus/penalty applied
        - confluence_analysis: Detailed breakdown
        - original_score: Score before confluence
        - adjusted_score: Score after confluence
        """
        analyzer = MultiTimeframeConfluenceAnalyzer()
        
        signal = Signal(
            symbol="EURUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            timeframe="M5",
            metadata={"score": 75.0}
        )
        
        timeframe_regimes = {
            "M15": MarketRegime.TREND,
            "H1": MarketRegime.RANGE,
            "H4": MarketRegime.TREND,
            "D1": MarketRegime.NORMAL
        }
        
        adjusted_signal = analyzer.analyze_confluence(signal, timeframe_regimes)
        
        # Verify metadata structure
        assert "confluence_bonus" in adjusted_signal.metadata
        assert "confluence_analysis" in adjusted_signal.metadata
        assert "original_score" in adjusted_signal.metadata
        assert "adjusted_score" in adjusted_signal.metadata
        
        analysis = adjusted_signal.metadata["confluence_analysis"]
        assert "alignment" in analysis
        assert "timeframe_contributions" in analysis
        assert "total_weight_applied" in analysis


class TestConfluenceEdgeLearning:
    """Tests for EDGE integration (auto-learning of weights)"""
    
    def test_analyzer_loads_weights_from_dynamic_params(self):
        """
        Weights should be loaded from dynamic_params.json
        EdgeTuner will optimize these based on win_rate
        """
        analyzer = MultiTimeframeConfluenceAnalyzer(config_path="config/dynamic_params.json")
        
        # Should have loaded weights (or defaults)
        assert hasattr(analyzer, 'weights')
        assert "M15" in analyzer.weights
        assert "H1" in analyzer.weights
        assert "H4" in analyzer.weights
        assert "D1" in analyzer.weights
        
        # Weights should sum to reasonable range (not >100%)
        total_weight = sum(analyzer.weights.values())
        assert 0 < total_weight <= 100
    
    def test_analyzer_can_update_weights_from_edge_tuner(self):
        """
        EdgeTuner should be able to update confluence weights
        based on backtest results
        
        This enables the system to LEARN optimal weighting
        """
        analyzer = MultiTimeframeConfluenceAnalyzer()
        
        # Simulate EdgeTuner updating weights
        new_weights = {
            "M15": 12.0,  # Learned: M15 less important
            "H1": 25.0,   # Learned: H1 very important
            "H4": 18.0,
            "D1": 15.0
        }
        
        analyzer.update_weights(new_weights)
        
        # Verify weights were updated
        assert analyzer.weights["M15"] == 12.0
        assert analyzer.weights["H1"] == 25.0
    
    def test_disabled_confluence_returns_original_signal_unchanged(self):
        """
        If confluence is disabled via config flag, return signal as-is
        
        This allows A/B testing: some signals use confluence, others don't
        EdgeTuner can compare performance
        """
        analyzer = MultiTimeframeConfluenceAnalyzer(enabled=False)
        
        signal = Signal(
            symbol="EURUSD=X",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type=ConnectorType.PAPER,
            entry_price=1.1000,
            stop_loss=1.0950,
            take_profit=1.1100,
            timeframe="M5",
            metadata={"score": 75.0}
        )
        
        timeframe_regimes = {
            "D1": MarketRegime.CRASH  # Should penalize, but disabled
        }
        
        adjusted_signal = analyzer.analyze_confluence(signal, timeframe_regimes)
        
        # Should return IDENTICAL signal (no changes)
        assert adjusted_signal.confidence == 0.75
        assert "confluence_bonus" not in adjusted_signal.metadata
