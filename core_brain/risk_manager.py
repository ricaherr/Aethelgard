"""
Risk Manager Module
Manages position sizing, risk allocation, and lockdown mode
Implements 1% base risk with dynamic adjustments based on market regime
"""
from typing import Optional, Dict
from datetime import datetime
import logging
from models.signal import MarketRegime

logger = logging.getLogger(__name__)


class RiskManager:
    """
    Manages trading risk with adaptive position sizing and lockdown protection.
    
    Features:
    - Base 1% risk per trade in normal conditions
    - Reduced 0.5% risk in VOLATILE/RANGE/CRASH regimes
    - Lockdown mode after 3 consecutive losses
    - Dynamic capital tracking
    """
    
    def __init__(
        self,
        initial_capital: float,
        base_risk_pct: float = 1.0,
        volatile_risk_pct: float = 0.5,
        max_consecutive_losses: int = 3
    ):
        """
        Initialize RiskManager
        
        Args:
            initial_capital: Starting capital amount
            base_risk_pct: Base risk percentage per trade (default 1.0%)
            volatile_risk_pct: Risk percentage in volatile regimes (default 0.5%)
            max_consecutive_losses: Max losses before lockdown (default 3)
        """
        self.capital = initial_capital
        self.base_risk_pct = base_risk_pct
        self.volatile_risk_pct = volatile_risk_pct
        self.max_consecutive_losses = max_consecutive_losses
        
        self.consecutive_losses = 0
        self.is_locked = False
        
        logger.info(
            f"RiskManager initialized: Capital=${initial_capital:,.2f}, "
            f"Base Risk={base_risk_pct}%, Volatile Risk={volatile_risk_pct}%"
        )
    
    def calculate_position_size(
        self,
        regime: MarketRegime,
        entry_price: float,
        stop_loss: float,
        direction: str = "LONG"
    ) -> float:
        """
        Calculate position size based on regime and risk parameters
        
        Args:
            regime: Current market regime
            entry_price: Entry price for the trade
            stop_loss: Stop loss price
            direction: Trade direction ("LONG" or "SHORT"), default "LONG"
        
        Returns:
            Position size in units/contracts (0 if locked or invalid params)
        """
        # Check lockdown
        if self.is_locked:
            logger.warning("Position size = 0: Account is in LOCKDOWN mode")
            return 0.0
        
        # Validate stop loss placement based on direction
        if direction == "LONG" and stop_loss >= entry_price:
            logger.warning("Position size = 0: Invalid SL for LONG (SL must be < entry)")
            return 0.0
        
        if direction == "SHORT" and stop_loss <= entry_price:
            logger.warning("Position size = 0: Invalid SL for SHORT (SL must be > entry)")
            return 0.0
        
        # Calculate risk per unit
        risk_per_unit = abs(entry_price - stop_loss)
        
        if risk_per_unit <= 0:
            logger.warning("Position size = 0: Zero risk calculated")
            return 0.0
        
        # Get risk percentage based on regime
        risk_pct = self.get_current_risk_pct(regime)
        
        # Calculate risk amount in currency
        risk_amount = self.capital * (risk_pct / 100.0)
        
        # Calculate position size
        position_size = risk_amount / risk_per_unit
        
        logger.debug(
            f"Position calc: Regime={regime.value}, Risk={risk_pct}%, "
            f"Amount=${risk_amount:.2f}, Size={position_size:.2f}"
        )
        
        return position_size
    
    def get_current_risk_pct(self, regime: MarketRegime) -> float:
        """
        Get risk percentage based on current market regime
        
        Args:
            regime: Current market regime
        
        Returns:
            Risk percentage to use
        """
        # Reduce risk in volatile/uncertain conditions
        volatile_regimes = {MarketRegime.RANGE, MarketRegime.CRASH}
        
        if regime in volatile_regimes:
            return self.volatile_risk_pct
        
        return self.base_risk_pct
    
    def record_trade_result(self, is_win: bool, pnl: float) -> None:
        """
        Record trade result and update risk state
        
        Args:
            is_win: Whether the trade was profitable
            pnl: Profit/Loss amount (positive or negative)
        """
        # Update capital
        self.capital += pnl
        
        if is_win:
            # Reset losses counter on win
            self.consecutive_losses = 0
            logger.info(f"WIN: PnL=${pnl:+.2f}, Capital=${self.capital:,.2f}")
        else:
            # Increment losses
            self.consecutive_losses += 1
            logger.warning(
                f"LOSS: PnL=${pnl:+.2f}, Capital=${self.capital:,.2f}, "
                f"Consecutive losses: {self.consecutive_losses}"
            )
            
            # Check for lockdown
            if self.consecutive_losses >= self.max_consecutive_losses:
                self.is_locked = True
                logger.error(
                    f"LOCKDOWN ACTIVATED: {self.consecutive_losses} consecutive losses. "
                    f"Trading disabled until manual unlock."
                )
    
    def can_trade(self) -> bool:
        """
        Check if trading is allowed
        
        Returns:
            True if trading allowed, False if locked
        """
        return not self.is_locked
    
    def unlock(self) -> None:
        """
        Manually unlock lockdown mode and reset losses counter
        """
        self.is_locked = False
        self.consecutive_losses = 0
        logger.info("Lockdown manually UNLOCKED. Trading resumed.")
    
    def get_status(self) -> Dict:
        """
        Get current risk manager status
        
        Returns:
            Dictionary with current state information
        """
        trades_until_lockdown = max(0, self.max_consecutive_losses - self.consecutive_losses)
        
        return {
            'capital': self.capital,
            'consecutive_losses': self.consecutive_losses,
            'is_locked': self.is_locked,
            'base_risk_pct': self.base_risk_pct,
            'volatile_risk_pct': self.volatile_risk_pct,
            'trades_until_lockdown': trades_until_lockdown
        }
