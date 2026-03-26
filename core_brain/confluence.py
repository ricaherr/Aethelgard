"""
Multi-Timeframe Confluence Analyzer
Reinforces or penalizes usr_signals based on alignment across multiple timeframes

EDGE Integration: Weights are auto-learned via EdgeTuner based on backtest results
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional
from dataclasses import dataclass
import pandas as pd

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
    Analyzes multi-timeframe alignment to reinforce or penalize usr_signals.
    
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
    
    def __init__(self, storage: StorageManager, enabled: bool = True):
        """
        Args:
            storage: StorageManager instance (REQUIRED - DI).
            enabled: If False, bypass confluence analysis.
        """
        self.enabled = enabled
        self.storage = storage
        self.weights = self._load_weights()
        
        logger.info(
            f"MultiTimeframeConfluenceAnalyzer initialized. "
            f"Enabled: {enabled}, Weights: {self.weights}"
        )
    
    def _load_weights(self) -> Dict[str, float]:
        """
        Load confluence weights from DB (Single Source of Truth)
        Falls back to defaults if not found
        """
        try:
            dynamic_params = self.storage.get_dynamic_params()
            confluence_config = dynamic_params.get("confluence", {})
            
            if "weights" in confluence_config:
                weights = confluence_config["weights"]
                logger.info(f"Loaded EDGE-tuned confluence weights from DB: {weights}")
                return weights
            else:
                logger.info("No EDGE weights found in DB, using defaults")
                return self.DEFAULT_WEIGHTS.copy()
                
        except Exception as e:
            logger.warning(f"Error loading confluence weights from DB: {e}. Using defaults.")
            return self.DEFAULT_WEIGHTS.copy()
    
    def update_weights(self, new_weights: Dict[str, float]) -> None:
        """
        Update confluence weights (called by EdgeTuner after optimization)
        
        Args:
            new_weights: Optimized weights learned from backtest results
        """
        self.weights = new_weights.copy()
        logger.info(f"Confluence weights updated by EdgeTuner: {self.weights}")
        
        # Persist to config for next restart
        self._save_weights()
    
    def _save_weights(self) -> None:
        """Save weights to DB (SSOT)"""
        try:
            dynamic_params = self.storage.get_dynamic_params()
            
            # Update confluence section
            if "confluence" not in dynamic_params:
                dynamic_params["confluence"] = {}
            
            dynamic_params["confluence"]["weights"] = self.weights
            dynamic_params["confluence"]["last_updated"] = datetime.now().isoformat()
            
            # Save to DB
            self.storage.update_dynamic_params(dynamic_params)
            logger.info("Saved confluence weights to DB (SSOT)")
            
        except Exception as e:
            logger.error(f"Error saving confluence weights to DB: {e}")
    
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

        # Escalar bono según nivel de confianza base (S-9: Exploración Proporcional)
        scale_factor = 1.0 if original_score / 100.0 > 0.50 else (0.5 if original_score / 100.0 >= 0.40 else 0.0)
        scaled_bonus = self._scale_bonus_by_confidence(analysis.bonus, original_score / 100.0)

        # Apply bonus to score
        adjusted_score = min(100.0, max(0.0, original_score + scaled_bonus))

        # Update signal
        signal.confidence = adjusted_score / 100.0
        signal.metadata["confluence_bonus"] = scaled_bonus
        signal.metadata["confluence_scale_factor"] = scale_factor
        signal.metadata["confluence_bonus_raw"] = analysis.bonus
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
            # TREND indicates momentum/volatility, generally good for both directions
            # unless we have specific BULL/BEAR classification
            return +weight
        
        elif regime == MarketRegime.BULL:
            return +weight if is_buy else -weight

        elif regime == MarketRegime.BEAR:
            return -weight if is_buy else +weight
        
        elif regime == MarketRegime.CRASH:
            # CRASH conflicts with BUY usr_signals
            return -weight if is_buy else +weight
        
        elif regime in [MarketRegime.RANGE, MarketRegime.NORMAL]:
            # Neutral regimes don't affect signal
            return 0.0
        
        else:
            # Unknown regime, ignore
            return 0.0
    
    def _scale_bonus_by_confidence(self, bonus: float, confidence: float) -> float:
        """
        Escala el bono de confluencia según el nivel de confianza base de la señal.

        Protocolo "Exploración Activa" (S-9):
          - confidence < 0.40  → sin bono (señal muy débil, no invertir recursos)
          - confidence [0.40, 0.50] → bono al 50 % (señal prometedora, aprender con cautela)
          - confidence > 0.50  → bono completo (señal válida, refuerzo total)

        Args:
            bonus:      Bono bruto calculado por _calculate_confluence (puntos 0-100).
            confidence: Confianza original de la señal (escala 0.0-1.0).

        Returns:
            Bono escalado listo para aplicar al score ajustado.
        """
        if confidence > 0.50:
            return bonus
        if confidence >= 0.40:
            return bonus * 0.5
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
