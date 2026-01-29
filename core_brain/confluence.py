"""
Multi-Timeframe Confluence Analyzer
Reinforces or penalizes signals based on alignment across multiple timeframes

EDGE Integration: Weights are auto-learned via EdgeTuner based on backtest results
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass

from models.signal import Signal, SignalType, MarketRegime

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceAnalysis:
    """Result of confluence analysis"""
    alignment: str  # "STRONG", "WEAK", "NEUTRAL", "CONFLICTING"
    bonus: float  # Total bonus/penalty applied to signal score
    timeframe_contributions: Dict[str, float]  # Breakdown by timeframe
    total_weight_applied: float  # Sum of weights that contributed


class MultiTimeframeConfluenceAnalyzer:
    """
    Analyzes multi-timeframe alignment to reinforce or penalize signals.
    
    Key Concepts:
    - Primary signal comes from lowest timeframe (M5)
    - Higher timeframes VALIDATE or CONFLICT with primary signal
    - Weighted scoring: higher timeframes have more impact
    - EDGE: Weights auto-tune based on historical win_rate
    
    Default Weights (can be learned):
    - M15: 15% influence
    - H1:  20% influence (most important for validation)
    - H4:  15% influence
    - D1:  10% influence (trend context only)
    """
    
    DEFAULT_WEIGHTS = {
        "M15": 15.0,
        "H1": 20.0,
        "H4": 15.0,
        "D1": 10.0
    }
    
    def __init__(self, config_path: Optional[str] = None, enabled: bool = True):
        """
        Args:
            config_path: Path to dynamic_params.json (for EDGE learning)
            enabled: If False, bypass confluence analysis (for A/B testing)
        """
        self.enabled = enabled
        self.config_path = Path(config_path) if config_path else Path("config/dynamic_params.json")
        self.weights = self._load_weights()
        
        logger.info(
            f"MultiTimeframeConfluenceAnalyzer initialized. "
            f"Enabled: {enabled}, Weights: {self.weights}"
        )
    
    def _load_weights(self) -> Dict[str, float]:
        """
        Load confluence weights from config (EdgeTuner updates these)
        Falls back to defaults if not found
        """
        if not self.config_path.exists():
            logger.info("No config found, using default confluence weights")
            return self.DEFAULT_WEIGHTS.copy()
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            confluence_config = config.get("confluence", {})
            
            if "weights" in confluence_config:
                weights = confluence_config["weights"]
                logger.info(f"Loaded EDGE-tuned confluence weights: {weights}")
                return weights
            else:
                logger.info("No EDGE weights found, using defaults")
                return self.DEFAULT_WEIGHTS.copy()
                
        except Exception as e:
            logger.warning(f"Error loading confluence config: {e}. Using defaults.")
            return self.DEFAULT_WEIGHTS.copy()
    
    def update_weights(self, new_weights: Dict[str, float]):
        """
        Update confluence weights (called by EdgeTuner after optimization)
        
        Args:
            new_weights: Optimized weights learned from backtest results
        """
        self.weights = new_weights.copy()
        logger.info(f"Confluence weights updated by EdgeTuner: {self.weights}")
        
        # Persist to config for next restart
        self._save_weights()
    
    def _save_weights(self):
        """Save weights to dynamic_params.json"""
        try:
            # Load existing config
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
            else:
                config = {}
            
            # Update confluence section
            if "confluence" not in config:
                config["confluence"] = {}
            
            config["confluence"]["weights"] = self.weights
            config["confluence"]["last_updated"] = str(pd.Timestamp.now())
            
            # Save
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Saved confluence weights to {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error saving confluence weights: {e}")
    
    def analyze_confluence(
        self, 
        signal: Signal, 
        timeframe_regimes: Dict[str, MarketRegime]
    ) -> Signal:
        """
        Adjust signal score based on multi-timeframe alignment.
        
        Args:
            signal: Primary signal (from M5 or lowest timeframe)
            timeframe_regimes: Dict of {timeframe: MarketRegime} for higher timeframes
                Example: {"M15": TREND, "H1": RANGE, "H4": TREND, "D1": NORMAL}
        
        Returns:
            Signal with adjusted confidence and confluence metadata
        """
        # If disabled, return original signal unchanged
        if not self.enabled:
            return signal
        
        original_score = signal.confidence * 100
        signal.metadata["original_score"] = original_score
        
        # Calculate confluence bonus/penalty
        analysis = self._calculate_confluence(signal, timeframe_regimes)
        
        # Apply bonus to score
        adjusted_score = min(100.0, max(0.0, original_score + analysis.bonus))
        
        # Update signal
        signal.confidence = adjusted_score / 100.0
        signal.metadata["confluence_bonus"] = analysis.bonus
        signal.metadata["adjusted_score"] = adjusted_score
        signal.metadata["confluence_analysis"] = {
            "alignment": analysis.alignment,
            "timeframe_contributions": analysis.timeframe_contributions,
            "total_weight_applied": analysis.total_weight_applied
        }
        
        logger.info(
            f"[{signal.symbol}] Confluence: {analysis.alignment} | "
            f"Score: {original_score:.1f} → {adjusted_score:.1f} "
            f"(bonus: {analysis.bonus:+.1f})"
        )
        
        return signal
    
    def _calculate_confluence(
        self, 
        signal: Signal, 
        timeframe_regimes: Dict[str, MarketRegime]
    ) -> ConfluenceAnalysis:
        """
        Calculate confluence bonus based on timeframe alignment
        
        Logic:
        - Aligned TREND: +weight (reinforcement)
        - Aligned RANGE/NORMAL: 0 (neutral)
        - Counter-trend CRASH: -weight (penalty)
        - Missing timeframe: ignored
        """
        total_bonus = 0.0
        contributions = {}
        total_weight_used = 0.0
        
        is_buy_signal = signal.signal_type == SignalType.BUY
        
        for timeframe, regime in timeframe_regimes.items():
            # Get weight for this timeframe
            weight = self.weights.get(timeframe, 0.0)
            
            if weight == 0:
                continue  # Timeframe not configured
            
            # Calculate contribution
            contribution = self._regime_contribution(regime, is_buy_signal, weight)
            contributions[timeframe] = contribution
            total_bonus += contribution
            total_weight_used += abs(weight)
        
        # Determine alignment classification
        alignment = self._classify_alignment(total_bonus, total_weight_used)
        
        return ConfluenceAnalysis(
            alignment=alignment,
            bonus=total_bonus,
            timeframe_contributions=contributions,
            total_weight_applied=total_weight_used
        )
    
    def _regime_contribution(
        self, 
        regime: MarketRegime, 
        is_buy: bool, 
        weight: float
    ) -> float:
        """
        Calculate how much a specific regime contributes to confluence
        
        Returns:
            Positive value: reinforcement
            Negative value: penalty
            Zero: neutral
        """
        if regime == MarketRegime.TREND:
            # TREND aligns with BUY signals
            return +weight if is_buy else -weight
        
        elif regime == MarketRegime.CRASH:
            # CRASH conflicts with BUY signals
            return -weight if is_buy else +weight
        
        elif regime in [MarketRegime.RANGE, MarketRegime.NORMAL]:
            # Neutral regimes don't affect signal
            return 0.0
        
        else:
            # Unknown regime, ignore
            return 0.0
    
    def _classify_alignment(self, total_bonus: float, total_weight: float) -> str:
        """
        Classify alignment strength based on total bonus
        
        Returns:
            "STRONG": >50% of max possible bonus
            "WEAK": 10-50% of max possible bonus
            "NEUTRAL": ±10% (no strong alignment)
            "CONFLICTING": <-10% (counter-trend)
        """
        if total_weight == 0:
            return "NEUTRAL"
        
        # Normalize bonus as percentage of max possible
        alignment_pct = (total_bonus / total_weight) * 100
        
        if alignment_pct > 50:
            return "STRONG"
        elif alignment_pct > 10:
            return "WEAK"
        elif alignment_pct < -10:
            return "CONFLICTING"
        else:
            return "NEUTRAL"
