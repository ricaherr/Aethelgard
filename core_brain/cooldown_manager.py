"""
cooldown_manager.py — Exponential Backoff Cooldown Management (HU 4.7)

Responsibility:
  - Calculate base cooldown time from ExecutionFailureReason enum
  - Apply exponential escalation (retry 1→2→3 = base×1 / base×2 / base×3)
  - Adjust for market volatility (zscore-based)
  - Persist active cooldowns to sys_cooldown_tracker (SSOT)
  - Check if signal is in active cooldown before executor attempts

Rule:
  - NO broker imports (agnosis #4)
  - ALL persistence via StorageManager (SSOT #15)
  - Dependency injection from MainOrchestrator
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionFailureReason(Enum):
    """Execution failure taxonomy (from execution_feedback.py)."""
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"
    SPREAD_TOO_WIDE = "SPREAD_TOO_WIDE"
    SLIPPAGE_EXCEEDED = "SLIPPAGE_EXCEEDED"
    ORDER_REJECTED = "ORDER_REJECTED"
    BROKER_CONNECTION_ERROR = "BROKER_CONNECTION_ERROR"
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    TIMEOUT = "TIMEOUT"
    POSITION_LIMIT_EXCEEDED = "POSITION_LIMIT_EXCEEDED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


@dataclass
class CooldownConfig:
    """Cooldown base times for each failure reason (minutes)."""
    LIQUIDITY_INSUFFICIENT: int = 5
    SPREAD_TOO_WIDE: int = 3
    SLIPPAGE_EXCEEDED: int = 2
    ORDER_REJECTED: int = 10
    BROKER_CONNECTION_ERROR: int = 15
    INSUFFICIENT_BALANCE: int = 60  # Requires manual review
    TIMEOUT: int = 5
    POSITION_LIMIT_EXCEEDED: int = 30
    UNKNOWN_ERROR: int = 20


class CooldownManager:
    """
    Manages intelligent cooldown application for failed signal executions.
    
    PHASE 1 Implementation:
      - ✅ Base cooldown mapping per failure reason
      - ✅ Exponential escalation (retry count multiplier)
      - ✅ Volatility adjustment factor
      - ✅ Persistence in sys_cooldown_tracker
      - ⏳ PHASE 2: Weekly learning of optimal cooldown times
      - ⏳ PHASE 3: Pattern analysis (e.g., certain brokers need longer cooldowns)
    """

    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: StorageManager instance (SSOT)
        """
        self.storage = storage_manager
        self.config = CooldownConfig()
        self.logger = logging.getLogger(self.__class__.__name__)
        
    async def apply_cooldown(
        self,
        signal_id: str,
        symbol: str,
        strategy: str,
        failure_reason: str,
        market_context: Dict
    ) -> Dict:
        """
        Calculate and apply cooldown for a failed signal execution.
        
        Args:
            signal_id: Unique signal identifier
            symbol: Trading symbol (e.g., EURUSD)
            strategy: Strategy name
            failure_reason: ExecutionFailureReason enum value
            market_context: Dict with volatility_zscore, regime, etc
            
        Returns:
            {
                "cooldown_minutes": int,
                "cooldown_expires": datetime,
                "retry_count": int,
                "escalation_applied": bool,
                "volatility_adjustment": float,
                "trace_id": str
            }
        """
        
        # Get current retry count (from DB if exists)
        existing_cooldown = await self.storage.get_active_cooldown(signal_id)
        retry_count = (existing_cooldown.get("retry_count", 0) if existing_cooldown else 0) + 1
        
        # Calculate base cooldown from mapping
        base_cooldown = await self._get_base_cooldown(failure_reason)
        
        # Apply exponential escalation
        escalation_multiplier = min(retry_count, 4)  # Cap at 4x (then escalate to manual)
        escalated_cooldown = base_cooldown * escalation_multiplier
        
        # Adjust for market volatility
        volatility_zscore = market_context.get("volatility_zscore", 0.0)
        vol_adjustment = self._calculate_volatility_adjustment(volatility_zscore, failure_reason)
        
        final_cooldown = int(escalated_cooldown * vol_adjustment)
        
        # Cap at max_cooldown per failure reason
        max_cooldown = await self._get_max_cooldown(failure_reason)
        if final_cooldown > max_cooldown:
            final_cooldown = max_cooldown
            cooldown_capped = True
        else:
            cooldown_capped = False
        
        # Calculate expiration time
        cooldown_expires = datetime.now(timezone.utc) + timedelta(minutes=final_cooldown)
        
        # Persistence (SSOT)
        trace_id = f"COOLDOWN-{signal_id}-{datetime.now(timezone.utc).isoformat()}"
        
        try:
            await self.storage.register_cooldown(
                signal_id=signal_id,
                symbol=symbol,
                strategy=strategy,
                failure_reason=failure_reason,
                retry_count=retry_count,
                cooldown_minutes=final_cooldown,
                cooldown_expires=cooldown_expires,
                volatility_zscore=volatility_zscore,
                regime=market_context.get("regime", "UNKNOWN"),
                trace_id=trace_id
            )
        except Exception as e:
            self.logger.error(f"Error persisting cooldown for {signal_id}: {e}")
            # Continue anyway, but log as critical
            trace_id += "-PERSIST_FAIL"
        
        # Log decision
        self.logger.warning(
            f"Cooldown applied for {signal_id} (strategy={strategy}, symbol={symbol}): "
            f"base={base_cooldown}min × escalation={escalation_multiplier} × vol_adj={vol_adjustment:.2f} = "
            f"{final_cooldown} min (expires {cooldown_expires.isoformat()}) "
            f"[retry #{retry_count}, reason={failure_reason}]"
        )
        
        # Check if should escalate to manual review
        if retry_count >= 4:
            self.logger.critical(
                f"Signal {signal_id} has failed {retry_count} times with reason {failure_reason} - "
                f"ESCALATING TO MANUAL REVIEW. Contact operator."
            )
        
        return {
            "cooldown_minutes": final_cooldown,
            "cooldown_expires": cooldown_expires,
            "retry_count": retry_count,
            "escalation_applied": escalation_multiplier > 1,
            "escalation_multiplier": escalation_multiplier,
            "volatility_adjustment": vol_adjustment,
            "capped": cooldown_capped,
            "max_cooldown": max_cooldown,
            "trace_id": trace_id
        }

    async def _get_base_cooldown(self, failure_reason: str) -> int:
        """
        Get base cooldown time for a failure reason.
        
        From mapping in 04_RISK_GOVERNANCE.md:
          LIQUIDITY_INSUFFICIENT: 5 min
          SPREAD_TOO_WIDE: 3 min
          etc.
        """
        
        mapping = {
            ExecutionFailureReason.LIQUIDITY_INSUFFICIENT.value: 5,
            ExecutionFailureReason.SPREAD_TOO_WIDE.value: 3,
            ExecutionFailureReason.SLIPPAGE_EXCEEDED.value: 2,
            ExecutionFailureReason.ORDER_REJECTED.value: 10,
            ExecutionFailureReason.BROKER_CONNECTION_ERROR.value: 15,
            ExecutionFailureReason.INSUFFICIENT_BALANCE.value: 60,
            ExecutionFailureReason.TIMEOUT.value: 5,
            ExecutionFailureReason.POSITION_LIMIT_EXCEEDED.value: 30,
            ExecutionFailureReason.UNKNOWN_ERROR.value: 20,
        }
        
        return mapping.get(failure_reason, 20)  # Default 20 min if unknown

    async def _get_max_cooldown(self, failure_reason: str) -> int:
        """Get maximum cap for cooldown (per failure reason)."""
        
        mapping = {
            ExecutionFailureReason.LIQUIDITY_INSUFFICIENT.value: 10,
            ExecutionFailureReason.SPREAD_TOO_WIDE.value: 8,
            ExecutionFailureReason.SLIPPAGE_EXCEEDED.value: 5,
            ExecutionFailureReason.ORDER_REJECTED.value: 20,
            ExecutionFailureReason.BROKER_CONNECTION_ERROR.value: 30,
            ExecutionFailureReason.INSUFFICIENT_BALANCE.value: 120,
            ExecutionFailureReason.TIMEOUT.value: 15,
            ExecutionFailureReason.POSITION_LIMIT_EXCEEDED.value: 60,
            ExecutionFailureReason.UNKNOWN_ERROR.value: 40,
        }
        
        return mapping.get(failure_reason, 60)

    def _calculate_volatility_adjustment(
        self,
        volatility_zscore: float,
        failure_reason: str
    ) -> float:
        """
        Adjust cooldown based on market volatility.
        
        Rules:
          - If zscore > 1.5 (stressed): multiply by 1.5x (wait longer)
          - If zscore < 0.5 (calm): multiply by 0.75x (wait less)
          - Otherwise: no adjustment (1.0x)
        
        Exception for certain reasons (e.g., INSUFFICIENT_BALANCE):
          - No volatility adjustment (fixed)
        """
        
        # Reasons that don't adjust for volatility (are systematic)
        no_vol_adjustment = [
            ExecutionFailureReason.INSUFFICIENT_BALANCE.value,
            ExecutionFailureReason.POSITION_LIMIT_EXCEEDED.value,
        ]
        
        if failure_reason in no_vol_adjustment:
            return 1.0
        
        # Volatility-sensitive reasons
        if volatility_zscore > 1.5:
            return 1.5  # Stressed market → wait longer
        elif volatility_zscore < 0.5:
            return 0.75  # Calm market → wait less
        else:
            return 1.0  # Normal → baseline

    async def check_active_cooldown(self, signal_id: str) -> Tuple[bool, Optional[Dict]]:
        """
        Check if signal is currently in active cooldown.
        
        Returns:
            (is_active: bool, cooldown_record: Dict or None)
        """
        
        try:
            cooldown = await self.storage.get_active_cooldown(signal_id)
            
            if not cooldown:
                return False, None
            
            expires = cooldown.get("cooldown_expires")
            if isinstance(expires, str):
                expires = datetime.fromisoformat(expires)
            
            is_active = datetime.now(timezone.utc) < expires
            
            if is_active:
                # Still in cooldown
                remaining_min = (expires - datetime.now(timezone.utc)).total_seconds() / 60
                return True, {
                    "expires_at": expires,
                    "remaining_minutes": round(remaining_min, 2),
                    "failure_reason": cooldown.get("failure_reason"),
                    "retry_count": cooldown.get("retry_count", 0)
                }
            else:
                # Cooldown expired
                return False, None
                
        except Exception as e:
            self.logger.error(f"Error checking cooldown for {signal_id}: {e}")
            return False, None

    async def clear_cooldown(self, signal_id: str) -> bool:
        """
        Clear an active cooldown (manual operator decision).
        
        Returns:
            bool: True if cleared successfully
        """
        
        try:
            self.storage.clear_cooldown(signal_id)
            self.logger.info(f"Cooldown cleared for signal {signal_id} (manual operator decision)")
            return True
        except Exception as e:
            self.logger.error(f"Error clearing cooldown for {signal_id}: {e}")
            return False

    async def get_cooldown_stats(self) -> Dict:
        """Return operational statistics (for monitoring)."""
        
        try:
            active_count = self.storage.count_active_cooldowns()
            
            return {
                "status": "PHASE_1_OPERATIONAL",
                "active_cooldowns": active_count,
                "escalation_enabled": True,
                "volatility_adjustment_enabled": True,
                "message": f"{active_count} signal(s) in active cooldown"
            }
        except Exception as e:
            self.logger.error(f"Error getting cooldown stats: {e}")
            return {
                "status": "ERROR",
                "message": str(e)
            }
