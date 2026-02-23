"""
EdgeTuner - Autonomous Feedback Loop - Aethelgard
=================================================
Service responsible for self-calibration based on real trading results.
Implements the "Delta Feedback" logic:
Delta = Actual Result - Predicted Score (Confidence)
"""

import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
import numpy as np
from datetime import datetime, timezone

from data_vault.storage import StorageManager
from models.signal import MarketRegime

logger = logging.getLogger(__name__)

class EdgeTuner:
    """
    Autonomous tuning system that adjusts signal parameters and metric weights
    based on real-world performance feedback.
    
    Governance Rules (Milestone 6.2):
    - No metric weight in regime_configs can be below 10% or above 50%.
    - Weight changes are capped at 2% per learning event (smoothing) to prevent
      erratic behavior from a single losing trade (anti-overfitting).
    """

    # --- Governance Constants (Safety Governor) ---
    GOVERNANCE_MIN_WEIGHT = 0.10   # 10% floor
    GOVERNANCE_MAX_WEIGHT = 0.50   # 50% ceiling
    GOVERNANCE_MAX_SMOOTHING = 0.02  # Max 2% delta per learning event

    def __init__(self, storage: StorageManager, config_path: Optional[str] = None):
        """
        Args:
            storage: StorageManager for accessing trade results and configs
            config_path: Optional path for legacy JSON config persistence
        """
        self.storage = storage
        self.config_path = Path(config_path) if config_path else None
    
    # --- Weight Adjustment (Feedback Loop Logic) ---

    def process_trade_feedback(self, trade_result: Dict[str, Any], predicted_score: float, regime: str) -> Dict[str, Any]:
        """
        Calculates Prediction Error (Delta) and adjusts metric weights in regime_configs.
        
        Delta = Result - Predicted_Score
        Where Result is:
        1.0 for WIN
        0.0 for LOSS
        
        Args:
            trade_result: Dictionary containing trade outcome (profit, is_win, etc.)
            predicted_score: The confidence score generated when the signal was created (0.0 to 1.0)
            regime: Market regime when the trade was opened (TREND, RANGE, VOLATILE)
            
        Returns:
            Dictionary with adjustment details
        """
        is_win = trade_result.get('is_win', False)
        actual_result = 1.0 if is_win else 0.0
        
        # Calculate Prediction Error (Delta)
        delta = actual_result - (predicted_score / 100.0 if predicted_score > 1.0 else predicted_score)
        
        logger.info(f"[EDGE_TUNER] Processing feedback for {regime}: Result={actual_result}, Predicted={predicted_score}, Delta={delta:.4f}")
        
        adjustment_made = False
        learning_note = ""
        governance_note = ""

        if delta > 0.1:
            adjustment_made, governance_note = self._adjust_regime_weights(regime, delta, "positive")
            learning_note = f"Positive drift detected (Delta: {delta:.4f}). Increasing dominant metric weight."
        elif delta < -0.4:
            adjustment_made, governance_note = self._adjust_regime_weights(regime, delta, "negative")
            learning_note = f"Negative drift detected (Delta: {delta:.4f}). Penalizing current configuration."

        if adjustment_made:
            # Build action_taken: include SAFETY_GOVERNOR tag if governance was triggered
            if governance_note:
                action_taken = f"Weight adjusted [SAFETY_GOVERNOR: {governance_note}]"
            else:
                action_taken = f"Weight adjusted: {regime} regime recalibrated"

            self.storage.log_strategy_state_change(
                strategy_id="SYSTEM_TUNER",
                old_mode="ADAPTING",
                new_mode="CALIBRATED",
                trace_id=f"TUNE-{datetime.now().strftime('%Y%m%d%H%M')}",
                reason=action_taken,
                metrics={"delta": delta, "regime": regime, "predicted_score": predicted_score, "is_win": is_win}
            )

        return {
            "delta": delta,
            "adjustment_made": adjustment_made,
            "learning": learning_note
        }

    def apply_governance_limits(self, current_weight: float, proposed_weight: float) -> tuple[float, str]:
        """
        Safety Governor: Enforces learning boundaries to prevent overfitting.

        Applies two sequential constraints:
        1. Smoothing: Caps the delta per event to GOVERNANCE_MAX_SMOOTHING (2%).
        2. Boundaries: Clamps the final weight to [GOVERNANCE_MIN_WEIGHT, GOVERNANCE_MAX_WEIGHT].

        Args:
            current_weight: The metric's weight before this learning event.
            proposed_weight: The raw weight calculated by the learning algorithm.

        Returns:
            Tuple of (governed_weight: float, clamp_reason: str).
            clamp_reason is empty string if no governance was triggered.
        """
        governed = proposed_weight
        clamp_reason = []

        # Step 1: Smoothing — cap the magnitude of the change per event
        delta = proposed_weight - current_weight
        if abs(delta) > self.GOVERNANCE_MAX_SMOOTHING:
            governed = current_weight + (self.GOVERNANCE_MAX_SMOOTHING * (1 if delta > 0 else -1))
            clamp_reason.append(
                f"SMOOTHING LIMIT: raw_delta={delta:.4f} capped to {self.GOVERNANCE_MAX_SMOOTHING:.2f}"
            )

        # Step 2: Boundaries — enforce hard floor and ceiling
        if governed < self.GOVERNANCE_MIN_WEIGHT:
            clamp_reason.append(f"GOVERNANCE LIMIT [FLOOR]: {governed:.4f} -> {self.GOVERNANCE_MIN_WEIGHT:.4f}")
            governed = self.GOVERNANCE_MIN_WEIGHT
        elif governed > self.GOVERNANCE_MAX_WEIGHT:
            clamp_reason.append(f"GOVERNANCE LIMIT [CEILING]: {governed:.4f} -> {self.GOVERNANCE_MAX_WEIGHT:.4f}")
            governed = self.GOVERNANCE_MAX_WEIGHT

        reason_str = " | ".join(clamp_reason)
        if reason_str:
            logger.info(f"[SAFETY_GOVERNOR] {reason_str} (current={current_weight:.4f})")

        return governed, reason_str

    def _adjust_regime_weights(self, regime: str, delta: float, drift_type: str) -> tuple[bool, str]:
        """
        Adjusts weights in regime_configs table, enforcing governance limits.

        Returns:
            Tuple of (adjustment_made: bool, governance_note: str).
            governance_note contains the [SAFETY_GOVERNOR] reason if any limit was triggered.
        """
        try:
            configs = self.storage.get_regime_weights(regime)
            if not configs:
                return False, ""

            # Identify the dominant metric (highest current weight)
            dominant_metric = max(configs.items(), key=lambda x: float(x[1]))[0]

            current_weight = float(configs[dominant_metric])

            # Calculate raw proposed adjustment (0.01–0.05 based on delta magnitude)
            adjustment = min(0.05, max(0.01, abs(delta) * 0.1))

            if drift_type == "positive":
                raw_proposed = current_weight + adjustment
            else:
                raw_proposed = current_weight - adjustment

            # Apply governance: smoothing + boundary enforcement
            new_weight, governance_note = self.apply_governance_limits(current_weight, raw_proposed)

            if abs(new_weight - current_weight) > 1e-6:
                self.storage.update_regime_weight(regime, dominant_metric, f"{new_weight:.4f}")
                logger.info(
                    f"[EDGE_TUNER] Adjusted {regime}/{dominant_metric}: "
                    f"{current_weight:.4f} -> {new_weight:.4f} (drift={drift_type})"
                )
                return True, governance_note

            return False, governance_note
        except Exception as e:
            logger.error(f"Error adjusting regime weights: {e}")
            return False, ""

    # --- Legacy Parameter Adjustment Logic (Refactored from tuner.py) ---

    def _load_config(self) -> Dict:
        """Carga configuración desde Storage (SSOT)"""
        if self.config_path and self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if isinstance(loaded, dict):
                    return loaded
            except Exception as e:
                logger.warning("Failed to load tuner config from %s: %s", self.config_path, e)

        config = self.storage.get_dynamic_params()
        return config if isinstance(config, dict) and config else {}
    
    def _save_config(self, config: Dict) -> None:
        """Guarda configuración actualizada en Storage"""
        self.storage.update_dynamic_params(config)
        if self.config_path:
            try:
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
            except Exception as e:
                logger.warning("Failed to persist tuner config to %s: %s", self.config_path, e)
        logger.info("[OK] Configuración dinámica actualizada en DB")
    
    def _calculate_stats(self, trades: List[Dict]) -> Dict:
        """
        Calculates performance statistics for parameter tuning.
        """
        if not trades:
            return {"total_trades": 0, "win_rate": 0.0}
        
        wins = [t for t in trades if t.get("is_win", False)]
        losses = [t for t in trades if not t.get("is_win", True)]
        
        win_rate = len(wins) / len(trades) if trades else 0.0
        
        avg_pips_win = np.mean([t.get("pips", 0) for t in wins]) if wins else 0.0
        avg_pips_loss = abs(np.mean([t.get("pips", 0) for t in losses])) if losses else 0.0
        
        total_profit = sum([t.get("profit_loss", 0) for t in wins])
        total_loss = abs(sum([t.get("profit_loss", 0) for t in losses]))
        profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
        
        # Calculate consecutive streaks (most recent first)
        consecutive_losses = 0
        consecutive_wins = 0
        
        for trade in trades:
            if not trade.get("is_win", True):
                consecutive_losses += 1
                if consecutive_wins > 0:
                    break
            else:
                consecutive_wins += 1
                if consecutive_losses > 0:
                    break
        
        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "avg_pips_win": float(avg_pips_win),
            "avg_pips_loss": float(avg_pips_loss),
            "profit_factor": float(profit_factor),
            "consecutive_losses": consecutive_losses,
            "consecutive_wins": consecutive_wins
        }
    
    def adjust_parameters(self, limit_trades: int = 100) -> Optional[Dict]:
        """
        Analyzes recent results and adjusts technical parameters automatically.
        """
        config = self._load_config()
        
        if not config.get("tuning_enabled", False):
            return {"skipped_reason": "tuning_disabled"}
        
        trades = self.storage.get_recent_trades(limit=limit_trades)
        min_trades = config.get("min_trades_for_tuning", 20)
        
        if len(trades) < min_trades:
            return {"skipped_reason": "insufficient_data"}
        
        stats = self._calculate_stats(trades)
        
        # Save current params for comparison
        old_params = {
            "adx_threshold": config.get("adx_threshold", 25),
            "elephant_atr_multiplier": config.get("elephant_atr_multiplier", 0.3),
            "sma20_proximity_percent": config.get("sma20_proximity_percent", 1.5),
            "min_signal_score": config.get("min_signal_score", 60),
            "risk_per_trade": config.get("risk_per_trade", 0.01)
        }
        
        # === DETERMINE ADJUSTMENT MODE ===
        trigger = "normal_adjustment"
        adjustment_factor = 1.0
        
        target_win_rate = config.get("target_win_rate", 0.55)
        conservative_threshold = config.get("conservative_mode_threshold", 0.45)
        aggressive_threshold = config.get("aggressive_mode_threshold", 0.65)
        max_consecutive_losses = config.get('max_consecutive_losses', 3)
        
        if stats["consecutive_losses"] >= max_consecutive_losses:
            trigger = "consecutive_losses"
            adjustment_factor = 1.7
        elif stats["win_rate"] < conservative_threshold:
            trigger = "low_win_rate"
            adjustment_factor = 1.5
        elif stats["win_rate"] > aggressive_threshold:
            trigger = "high_win_rate"
            adjustment_factor = 0.7
        else:
            deviation = stats["win_rate"] - target_win_rate
            adjustment_factor = 1.0 - (deviation * 0.5)
        
        # === APPLY ADJUSTMENTS ===
        new_params = old_params.copy()
        new_params["adx_threshold"] = max(20, min(35, 25 * adjustment_factor))
        new_params["elephant_atr_multiplier"] = max(0.15, min(0.7, 0.3 * adjustment_factor))
        new_params["sma20_proximity_percent"] = max(0.8, min(2.5, 1.5 / adjustment_factor))
        new_params["min_signal_score"] = max(50, min(80, int(60 * adjustment_factor)))

        # Risk Per Trade: Dynamic EDGE
        base_risk = 0.01 
        if adjustment_factor >= 1.5:
            new_params["risk_per_trade"] = 0.005 
        elif adjustment_factor <= 0.7:
            new_params["risk_per_trade"] = 0.0125
        else:
            new_params["risk_per_trade"] = max(0.005, min(0.0125, base_risk / adjustment_factor))
        
        # Update config
        config.update(new_params)
        self._save_config(config)
        
        # Save adjustment to history
        adjustment_record = {
            "trigger": trigger,
            "old_params": old_params,
            "new_params": new_params,
            "stats": stats,
            "adjustment_factor": float(adjustment_factor),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        self.storage.save_tuning_adjustment(adjustment_record)
        logger.info(f"[EDGE_TUNER] Parameters adjusted via {trigger}. Adjustment factor: {adjustment_factor:.2f}")
        
        return adjustment_record

    # --- ADX/Volatility Grid-Search Calibration (Absorbed from ParameterTuner) ---

    def _calculate_false_positive_rate(
        self,
        states: List[Dict],
        adx_trend_threshold: float,
        adx_range_threshold: float,
        volatility_threshold: Optional[float] = None,
    ) -> float:
        """
        Calculates the false-positive rate for a given set of regime thresholds.

        A false positive is defined as a regime change that reverts within the
        following 5-10 candles.
        """
        if len(states) < 20:
            return 1.0  # Assume worst case without enough data

        false_positives = 0
        total_changes = 0
        sorted_states = sorted(states, key=lambda x: x.get("timestamp", ""))

        for i in range(len(sorted_states) - 10):
            current_regime = sorted_states[i].get("regime")
            if i > 0:
                previous_regime = sorted_states[i - 1].get("regime")
                if current_regime != previous_regime:
                    total_changes += 1
                    future_states = sorted_states[i + 1 : min(i + 11, len(sorted_states))]
                    if future_states:
                        persistence = sum(
                            1 for s in future_states if s.get("regime") == current_regime
                        )
                        if persistence < len(future_states) * 0.5:
                            false_positives += 1

        return false_positives / total_changes if total_changes > 0 else 0.0

    def _optimize_adx_thresholds(self, states: List[Dict]) -> tuple:
        """
        Finds optimal ADX thresholds via grid search to minimise false positives.

        Returns:
            Tuple of (adx_trend_threshold, adx_range_threshold, adx_range_exit_threshold)
        """
        if len(states) < 100:
            logger.warning("[EDGE_TUNER] Insufficient data for ADX optimisation; using defaults.")
            return (25.0, 20.0, 18.0)

        best_fpr = float("inf")
        best_thresholds = (25.0, 20.0, 18.0)

        for trend_thresh in np.arange(20.0, 35.0, 1.0):
            for range_thresh in np.arange(15.0, 25.0, 1.0):
                for exit_thresh in np.arange(15.0, 22.0, 1.0):
                    if not (exit_thresh < range_thresh < trend_thresh):
                        continue
                    fpr = self._calculate_false_positive_rate(states, trend_thresh, range_thresh)
                    if fpr < best_fpr:
                        best_fpr = fpr
                        best_thresholds = (float(trend_thresh), float(range_thresh), float(exit_thresh))

        logger.info(
            f"[EDGE_TUNER] ADX thresholds optimised: TREND={best_thresholds[0]}, "
            f"RANGE={best_thresholds[1]}, EXIT={best_thresholds[2]} (FPR: {best_fpr:.2%})"
        )
        return best_thresholds

    def _optimize_volatility_threshold(self, states: List[Dict]) -> float:
        """
        Optimises the volatility shock multiplier from historical CRASH regime data.
        """
        if len(states) < 100:
            logger.warning("[EDGE_TUNER] Insufficient data for volatility optimisation; using default.")
            return 5.0

        crash_states = [s for s in states if s.get("regime") == MarketRegime.CRASH.value]
        if len(crash_states) < 10:
            return 5.0

        crash_vols = [s.get("volatility", 0) for s in crash_states if s.get("volatility")]
        all_vols = [s.get("volatility", 0) for s in states if s.get("volatility")]

        if not crash_vols or not all_vols:
            return 5.0

        optimal = max(3.0, min(10.0, np.mean(crash_vols) / np.mean(all_vols)))
        logger.info(f"[EDGE_TUNER] Volatility multiplier optimised: {optimal:.2f}")
        return float(optimal)

    def auto_calibrate(self, limit: int = 1000, symbol: Optional[str] = None) -> Dict:
        """
        Runs full ADX/Volatility grid-search calibration using historical market states.

        This is a complementary calibration to adjust_parameters():
        - adjust_parameters()  → reacts to live trade win-rate (operational feedback)
        - auto_calibrate()     → optimises regime-detection thresholds from market history

        Args:
            limit:  Number of historical market state records to analyse.
            symbol: Optional symbol filter.

        Returns:
            Dictionary with the newly optimised configuration.
        """
        logger.info(f"[EDGE_TUNER] Starting auto-calibration with {limit} records...")
        current_config = self._load_config()

        states = self.storage.get_market_states(limit=limit, symbol=symbol)
        if len(states) < 100:
            logger.warning(
                f"[EDGE_TUNER] Only {len(states)} records available. "
                "At least 100 are needed for reliable calibration."
            )
            return current_config

        logger.info(f"[EDGE_TUNER] Analysing {len(states)} market states...")

        trend_thresh, range_thresh, exit_thresh = self._optimize_adx_thresholds(states)
        volatility_multiplier = self._optimize_volatility_threshold(states)

        new_config = {
            **current_config,
            "adx_trend_threshold": trend_thresh,
            "adx_range_threshold": range_thresh,
            "adx_range_exit_threshold": exit_thresh,
            "volatility_shock_multiplier": volatility_multiplier,
        }

        self._save_config(new_config)
        logger.info("[EDGE_TUNER] Auto-calibration completed successfully.")
        return new_config
