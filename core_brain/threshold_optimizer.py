"""
Confidence Threshold Optimizer (HU 7.1)
=======================================

Trace_ID: ADAPTIVE-THRESHOLD-2026-001
Dominio: 07 (Adaptive Learning)

Dynamically optimizes the confidence threshold for signal entry based on:
1. Equity Curve Feedback (recent trade history)
2. Consecutive Loss Detection (loss streak activation)
3. Safety Governor enforcement (smoothing + bounds)

Purpose:
- After 3+ consecutive losses → confidence threshold increases (stricter)
- On recovery (winning streak) → threshold can decrease slightly
- Never violates governance limits (min/max bounds, smoothing cap)
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass, field

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class EquityCurveAnalyzer:
    """
    Analyzes recent equity curve (trade history) to detect patterns.
    
    Responsibilities:
    - Calculate win rate from recent usr_trades
    - Detect consecutive loss streaks
    - Calculate maximum drawdown
    - Provide metrics for threshold optimization decision
    """
    usr_trades: List[Dict[str, Any]]
    lookback: int = 20
    
    # Cached metrics
    _win_rate: Optional[float] = field(default=None, init=False)
    _consecutive_losses: Optional[int] = field(default=None, init=False)
    _max_drawdown: Optional[float] = field(default=None, init=False)
    
    @property
    def total_usr_trades(self) -> int:
        """Total usr_trades in history."""
        return len(self.usr_trades)
    
    @property
    def win_rate(self) -> float:
        """
        Win rate calculation: wins / total_usr_trades.
        Returns 0.0 if no usr_trades.
        """
        if self._win_rate is not None:
            return self._win_rate
        
        if not self.usr_trades:
            self._win_rate = 0.0
            return 0.0
        
        wins = sum(1 for trade in self.usr_trades if trade.get("is_win", False))
        self._win_rate = wins / len(self.usr_trades)
        return self._win_rate
    
    @property
    def consecutive_losses(self) -> int:
        """
        Detect maximum consecutive loss streak in history.
        Returns highest consecutive losses found.
        """
        if self._consecutive_losses is not None:
            return self._consecutive_losses
        
        if not self.usr_trades:
            self._consecutive_losses = 0
            return 0
        
        max_streak = 0
        current_streak = 0
        
        for trade in self.usr_trades:
            is_win = trade.get("is_win", False)
            if not is_win:
                current_streak += 1
                max_streak = max(max_streak, current_streak)
            else:
                current_streak = 0
        
        self._consecutive_losses = max_streak
        return max_streak
    
    @property
    def max_drawdown(self) -> float:
        """
        Calculate maximum drawdown from equity curve.
        Returns negative or zero value (e.g., -0.15 for 15% drawdown).
        """
        if self._max_drawdown is not None:
            return self._max_drawdown
        
        if not self.usr_trades:
            self._max_drawdown = 0.0
            return 0.0
        
        cumulative = 0.0
        peak = 0.0
        max_dd = 0.0
        
        for trade in self.usr_trades:
            pnl = trade.get("pnl", 0.0)
            cumulative += pnl
            
            if cumulative > peak:
                peak = cumulative
            
            drawdown = cumulative - peak
            if drawdown < max_dd:
                max_dd = drawdown
        
        self._max_drawdown = max_dd if max_dd != 0 else 0.0
        return self._max_drawdown


class ThresholdOptimizer:
    """
    Autonomous confidence threshold optimizer based on equity curve feedback.
    
    Responsibilities:
    1. Load current threshold and governance parameters from Storage (SSOT)
    2. Analyze recent usr_trades via EquityCurveAnalyzer
    3. Detect loss streaks or recovery patterns
    4. Adjust threshold dynamically
    5. Apply Safety Governor (smoothing + bounds)
    6. Persist changes to Storage
    7. Log adjustments with Trace_ID for observability
    
    Governance Rules (Safety Governor):
    - Min threshold: configurable (default 0.50)
    - Max threshold: configurable (default 0.95)
    - Max smoothing: configurable (default 0.05 = 5% delta per cycle)
    - Consecutive loss trigger: configurable (default 3)
    
    Principles:
    - Inyección de Dependencias: Storage inyectado en __init__
    - SSOT: All parameters loaded from DB, never hardcoded
    - Anti-Overfitting: Safety Governor prevents erratic swings
    - Trazabilidad: Trace_ID in all logging
    """
    
    # Governance Constants (can be overridden via config)
    DEFAULT_THRESHOLD_MIN = 0.50
    DEFAULT_THRESHOLD_MAX = 0.95
    DEFAULT_SMOOTHING_MAX = 0.05
    DEFAULT_LOOKBACK_TRADES = 20
    DEFAULT_CONSECUTIVE_LOSS_THRESHOLD = 3
    
    def __init__(self, storage: StorageManager):
        """
        Initialize ThresholdOptimizer with dependency injection.
        
        Args:
            storage: StorageManager for persistence and parameter loading (SSOT)
        """
        self.storage = storage
        
        # Load parameters from Storage (SSOT - Single Source of Truth)
        params = self.storage.get_dynamic_params()
        
        self.current_threshold = params.get("confidence_threshold", 0.75)
        self.threshold_min = params.get("confidence_threshold_min", self.DEFAULT_THRESHOLD_MIN)
        self.threshold_max = params.get("confidence_threshold_max", self.DEFAULT_THRESHOLD_MAX)
        self.smoothing_max = params.get("confidence_smoothing_max", self.DEFAULT_SMOOTHING_MAX)
        self.lookback_usr_trades = params.get("equity_lookback_usr_trades", self.DEFAULT_LOOKBACK_TRADES)
        self.loss_threshold = params.get(
            "consecutive_loss_threshold", 
            self.DEFAULT_CONSECUTIVE_LOSS_THRESHOLD
        )
        
        logger.info(
            f"[THRESHOLD_OPTIMIZER] Initialized. "
            f"Current={self.current_threshold:.2f} | "
            f"Range=[{self.threshold_min:.2f}, {self.threshold_max:.2f}] | "
            f"Smoothing={self.smoothing_max:.2f} | "
            f"Lookback={self.lookback_usr_trades} usr_trades | "
            f"Loss threshold={self.loss_threshold}. "
            f"Trace_ID: ADAPTIVE-THRESHOLD-2026-001"
        )
    
    async def optimize_threshold(
        self, 
        account_id: str,
        trace_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Main optimization logic: analyze equity curve and adjust threshold.
        
        Workflow:
        1. Load recent usr_trades from Storage
        2. Analyze equity curve (win_rate, consecutive_losses, drawdown)
        3. Decide adjustment direction (increase/decrease/none)
        4. Apply Safety Governor (smoothing + bounds)
        5. Persist to Storage if changed
        6. Log with Trace_ID
        
        Args:
            account_id: Account to analyze
            trace_id: Trace ID for observability
        
        Returns:
            Dict with optimization results: {
                'old_threshold': float,
                'new_threshold': float,
                'delta': float,
                'reason': str,
                'win_rate': float,
                'consecutive_losses': int,
            }
        """
        trace_id = trace_id or "ADAPTIVE-THRESHOLD-2026-001"
        
        # Step 1: Load recent usr_trades
        usr_trades = self.storage.get_account_usr_trades(
            account_id=account_id,
            limit=self.lookback_usr_trades
        )
        
        if not usr_trades:
            logger.debug(f"[THRESHOLD_OPTIMIZER] No usr_trades to analyze for {account_id}")
            return {
                "old_threshold": self.current_threshold,
                "new_threshold": self.current_threshold,
                "delta": 0.0,
                "reason": "NO_TRADES",
                "win_rate": 0.0,
                "consecutive_losses": 0,
            }
        
        # Step 2: Analyze equity curve
        analyzer = EquityCurveAnalyzer(usr_trades=usr_trades, lookback=self.lookback_usr_trades)
        
        old_threshold = self.current_threshold
        adjustment_reason = "STABLE"
        proposed_threshold = self.current_threshold
        
        # Step 3: Decision logic based on patterns
        if analyzer.consecutive_losses >= self.loss_threshold:
            # Loss streak detected → INCREASE threshold (stricter)
            # Formula: increase by 3-5% based on streak severity
            severity = min(analyzer.consecutive_losses / self.loss_threshold, 2.0)
            adjustment = 0.03 + (0.02 * severity)
            proposed_threshold = self.current_threshold + adjustment
            adjustment_reason = f"LOSS_STREAK({analyzer.consecutive_losses})"
            
            logger.warning(
                f"[THRESHOLD_OPTIMIZER] Loss streak detected ({analyzer.consecutive_losses}). "
                f"Proposing increase: {self.current_threshold:.3f} + {adjustment:.3f} = {proposed_threshold:.3f}"
            )
        
        elif analyzer.win_rate >= 0.70 and analyzer.max_drawdown > -0.10:
            # Strong recovery: high win rate + manageable drawdown → DECREASE slightly (permissive)
            # Formula: decrease by 1-2% to reward good performance
            adjustment = -0.01
            proposed_threshold = self.current_threshold + adjustment
            adjustment_reason = f"RECOVERY(WR={analyzer.win_rate:.1%})"
            
            logger.info(
                f"[THRESHOLD_OPTIMIZER] Strong recovery detected (WR={analyzer.win_rate:.1%}). "
                f"Allowing slight decrease: {self.current_threshold:.3f} - 0.01 = {proposed_threshold:.3f}"
            )
        
        else:
            # Stable/mixed performance → minimal adjustment
            logger.debug(
                f"[THRESHOLD_OPTIMIZER] Stable performance. "
                f"WR={analyzer.win_rate:.1%} | Losses={analyzer.consecutive_losses} | DD={analyzer.max_drawdown:.1%}"
            )
        
        # Step 4: Apply Safety Governor (smoothing + bounds)
        new_threshold, governance_note = self._apply_governance_limits(
            proposed_threshold=proposed_threshold,
            current_threshold=self.current_threshold
        )
        
        delta = new_threshold - old_threshold
        
        # Step 5: Persist if changed
        if abs(delta) > 1e-6:
            self.current_threshold = new_threshold
            params = self.storage.get_dynamic_params()
            params["confidence_threshold"] = new_threshold
            self.storage.update_dynamic_params(params)
            
            # Step 6: Log adjustment with Trace_ID
            self.storage.log_threshold_adjustment(
                account_id=account_id,
                old_threshold=old_threshold,
                new_threshold=new_threshold,
                reason=adjustment_reason,
                governance_note=governance_note,
                win_rate=analyzer.win_rate,
                consecutive_losses=analyzer.consecutive_losses,
                trace_id=trace_id,
            )
            
            logger.info(
                f"[THRESHOLD_OPTIMIZER] Threshold updated: {old_threshold:.3f} → {new_threshold:.3f} "
                f"(Δ={delta:+.3f}) | Reason: {adjustment_reason} | Governor: {governance_note}. "
                f"Trace_ID: {trace_id}"
            )
        
        return {
            "old_threshold": old_threshold,
            "new_threshold": new_threshold,
            "delta": delta,
            "reason": adjustment_reason,
            "governance_applied": governance_note if abs(delta) > 1e-6 else "NONE",
            "win_rate": analyzer.win_rate,
            "consecutive_losses": analyzer.consecutive_losses,
            "max_drawdown": analyzer.max_drawdown,
            "trace_id": trace_id,
        }
    
    def _apply_governance_limits(
        self,
        proposed_threshold: float,
        current_threshold: Optional[float] = None,
    ) -> Tuple[float, str]:
        """
        Safety Governor: Enforces boundaries and smoothing constraints.
        
        Rules applied sequentially:
        1. SMOOTHING: Cap delta to smoothing_max per optimization cycle
        2. BOUNDS: Enforce min/max threshold bounds
        
        Args:
            proposed_threshold: Raw threshold from adjustment logic
            current_threshold: Current threshold (for smoothing calc)
        
        Returns:
            Tuple of (governed_threshold: float, reason_string: str)
            reason_string = "" if no governance needed, otherwise describes actions taken
        """
        if current_threshold is None:
            current_threshold = self.current_threshold
        
        governed = proposed_threshold
        reasons = []
        
        # Rule 1: SMOOTHING - Cap the delta per cycle
        delta = proposed_threshold - current_threshold
        if abs(delta) > self.smoothing_max:
            capped_delta = self.smoothing_max * (1.0 if delta > 0 else -1.0)
            governed = current_threshold + capped_delta
            reasons.append(
                f"SMOOTHING_LIMIT: raw_delta={delta:+.4f} capped to {capped_delta:+.4f}"
            )
        
        # Rule 2: BOUNDS - Enforce hard floor and ceiling
        if governed < self.threshold_min:
            reasons.append(f"BOUNDARY_FLOOR: {governed:.4f} → {self.threshold_min:.4f}")
            governed = self.threshold_min
        elif governed > self.threshold_max:
            reasons.append(f"BOUNDARY_CEILING: {governed:.4f} → {self.threshold_max:.4f}")
            governed = self.threshold_max
        
        reason_str = " | ".join(reasons) if reasons else ""
        
        if reason_str:
            logger.debug(f"[SAFETY_GOVERNOR] {reason_str}")
        
        return governed, reason_str
    
    def get_current_threshold(self) -> float:
        """Get current optimized threshold (readable by SignalFactory)."""
        return self.current_threshold
