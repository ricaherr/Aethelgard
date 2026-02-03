"""
Trade Closure Listener - Autonomous Feedback Loop
==================================================

Listens for broker trade closure events and:
1. Saves trade results to DB (with retry logic for lock handling)
2. Updates RiskManager (record_trade_result)
3. Triggers EdgeTuner.adjust_parameters()
4. Maintains audit trail

Principle: Broker-agnostic. Receives standardized BrokerTradeClosedEvent.
"""
import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
import time

from data_vault.storage import StorageManager
from core_brain.risk_manager import RiskManager
from core_brain.tuner import EdgeTuner
from models.broker_event import BrokerTradeClosedEvent, BrokerEvent, BrokerEventType

logger = logging.getLogger(__name__)


class TradeClosureListener:
    """
    Autonomous listener for trade closure events.
    
    Responsibilities:
    1. Process trade closed events from any broker
    2. Persist trades to DB (with retry on lock)
    3. Update RiskManager state (lockdown, consecutive losses)
    4. Trigger parameter tuning when needed
    5. Maintain detailed audit trail
    
    Principles:
    - Dependency Injection: All dependencies passed in __init__
    - Broker Agnostic: Works with any broker via BrokerTradeClosedEvent interface
    - Resilient: Retry logic for DB locks
    - Auditable: Logs every event with clear format
    """
    
    def __init__(
        self,
        storage: StorageManager,
        risk_manager: RiskManager,
        edge_tuner: EdgeTuner,
        max_retries: int = 3,
        retry_backoff: float = 0.5
    ):
        """
        Initialize TradeClosureListener with dependency injection.
        
        Args:
            storage: StorageManager for DB persistence
            risk_manager: RiskManager for lockdown/risk tracking
            edge_tuner: EdgeTuner for parameter adjustment
            max_retries: How many times to retry on DB lock
            retry_backoff: Seconds to wait between retries
        """
        self.storage = storage
        self.risk_manager = risk_manager
        self.edge_tuner = edge_tuner
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        
        # Metrics for monitoring
        self.trades_processed = 0
        self.trades_saved = 0
        self.trades_failed = 0
        self.tuner_adjustments = 0
        
        logger.info(
            f"TradeClosureListener initialized: max_retries={max_retries}, "
            f"retry_backoff={retry_backoff}s"
        )
    
    async def _is_trade_already_processed(self, trade: BrokerTradeClosedEvent) -> bool:
        """
        Check if trade with this ticket_id has already been processed.
        
        This ensures idempotence: if the trade exists in DB, skip it.
        Protects against:
        - Duplicate event delivery from broker
        - System restart reprocessing old events
        - Network retry loops
        
        Args:
            trade: Trade to check
        
        Returns:
            True if already in DB, False if new
        """
        try:
            # Use StorageManager's public method (encapsulation)
            # No need to know about SQLite, connections, or schema
            exists = self.storage.trade_exists(ticket_id=trade.ticket)
            
            if exists:
                logger.debug(f"Trade {trade.ticket} already in DB - idempotent")
            
            return exists
        
        except Exception as e:
            logger.error(f"Error checking idempotence for {trade.ticket}: {e}")
            # On error, assume it's new and try to process
            # Better to duplicate than lose a trade
            return False
    
    async def handle_trade_closed_event(self, event: BrokerEvent) -> bool:
        """
        Main event handler for trade closure.
        
        Workflow:
        1. Validate event
        2. Check idempotence (already processed?)
        3. Save to DB (with retry on lock)
        4. Update RiskManager
        5. Trigger Tuner (periodic)
        6. Audit log
        
        Args:
            event: BrokerEvent wrapping trade closed data
        
        Returns:
            True if successful, False if failed after retries
        """
        # Validate event type
        if event.event_type != BrokerEventType.TRADE_CLOSED:
            logger.warning(f"Ignoring non-TRADE_CLOSED event: {event.event_type}")
            return False
        
        trade_event: BrokerTradeClosedEvent = event.data
        self.trades_processed += 1
        
        # === STEP 0: Check Idempotence (already processed?) ===
        if await self._is_trade_already_processed(trade_event):
            logger.info(
                f"[IDEMPOTENT] Trade already processed: "
                f"Ticket={trade_event.ticket} | Symbol={trade_event.symbol} | "
                f"Broker={trade_event.broker_id}"
            )
            return True  # Return True since it's already handled correctly
        
        # === STEP 1: Save to DB with retry logic ===
        saved = await self._save_trade_with_retry(trade_event)
        
        if not saved:
            self.trades_failed += 1
            logger.error(
                f"[TRADE_CLOSED] FAILED after {self.max_retries} retries: "
                f"Symbol={trade_event.symbol} | Ticket={trade_event.ticket}"
            )
            return False
        
        self.trades_saved += 1
        
        # === STEP 2: Update RiskManager ===
        is_win = trade_event.is_win()
        pnl = trade_event.profit_loss
        
        self.risk_manager.record_trade_result(is_win=is_win, pnl=pnl)
        
        # === STEP 3: Check for lockdown activation ===
        if self.risk_manager.is_locked():
            logger.error(
                f"[LOCKDOWN] RiskManager entered LOCKDOWN: "
                f"consecutive_losses={self.risk_manager.consecutive_losses}"
            )
        
        # === STEP 4: Trigger Tuner (periodic, not on every trade) ===
        # Only tune every 5 trades or on consecutive losses trigger
        if self.trades_saved % 5 == 0 or self.risk_manager.consecutive_losses >= 3:
            await self._trigger_tuner(trade_event)
        
        # === STEP 5: Audit Log ===
        result_str = "WIN" if is_win else "LOSS"
        logger.info(
            f"[TRADE_CLOSED] Symbol: {trade_event.symbol} | "
            f"Ticket: {trade_event.ticket} | "
            f"Result: {result_str} | "
            f"PnL: {pnl:+.2f} | "
            f"ExitReason: {trade_event.exit_reason} | "
            f"Broker: {trade_event.broker_id}"
        )
        
        return True
    
    async def _save_trade_with_retry(self, trade: BrokerTradeClosedEvent) -> bool:
        """
        Save trade to DB with exponential backoff retry on lock.
        
        Implements resilience: If DB is locked, retry instead of failing.
        
        Args:
            trade: Trade data to save
        
        Returns:
            True if saved, False if failed after retries
        """
        trade_data = {
            "id": trade.ticket,
            "signal_id": trade.signal_id,
            "symbol": trade.symbol,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "profit_loss": trade.profit_loss,
            "profit": trade.profit_loss,  # Alias for compatibility
            "is_win": trade.is_win(),
            "pips": trade.pips,
            "exit_reason": trade.exit_reason,
            "close_time": trade.exit_time.isoformat(),
            "metadata": trade.metadata or {}
        }
        
        for attempt in range(self.max_retries):
            try:
                self.storage.save_trade_result(trade_data)
                return True
            
            except Exception as e:
                error_msg = str(e).lower()
                
                # Check if it's a lock error (DB busy)
                is_lock_error = 'locked' in error_msg or 'busy' in error_msg
                
                if is_lock_error and attempt < self.max_retries - 1:
                    # Exponential backoff: 0.5s, 1.0s, 1.5s
                    wait_time = self.retry_backoff * (attempt + 1)
                    logger.warning(
                        f"DB locked (attempt {attempt + 1}/{self.max_retries}). "
                        f"Retrying in {wait_time}s... | Ticket: {trade.ticket}"
                    )
                    await asyncio.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"Failed to save trade {trade.ticket}: {e} | "
                        f"Attempt {attempt + 1}/{self.max_retries}"
                    )
                    return False
        
        return False
    
    async def _trigger_tuner(self, trade: BrokerTradeClosedEvent) -> bool:
        """
        Trigger EdgeTuner parameter adjustment.
        
        Args:
            trade: Trade that triggered the tuning
        
        Returns:
            True if adjustment made, False if skipped
        """
        try:
            adjustment_result = self.edge_tuner.adjust_parameters(limit_trades=100)
            
            if adjustment_result and "skipped_reason" not in adjustment_result:
                self.tuner_adjustments += 1
                trigger = adjustment_result.get("trigger", "unknown")
                logger.info(
                    f"[TUNER] Parameters adjusted: trigger={trigger} | "
                    f"adjustment_factor={adjustment_result.get('adjustment_factor', 'N/A')}"
                )
                return True
            else:
                reason = adjustment_result.get("skipped_reason") if adjustment_result else "unknown"
                logger.debug(f"[TUNER] Adjustment skipped: {reason}")
                return False
        
        except Exception as e:
            logger.error(f"Error triggering tuner: {e}", exc_info=True)
            return False
    
    def get_metrics(self) -> dict:
        """
        Get listener metrics for monitoring.
        
        Returns:
            Dictionary with processed/saved/failed counts
        """
        return {
            "trades_processed": self.trades_processed,
            "trades_saved": self.trades_saved,
            "trades_failed": self.trades_failed,
            "tuner_adjustments": self.tuner_adjustments,
            "success_rate": (
                self.trades_saved / self.trades_processed * 100
                if self.trades_processed > 0 else 0.0
            )
        }
    
    def reset_metrics(self) -> None:
        """Reset metrics (useful for daily rollover)"""
        self.trades_processed = 0
        self.trades_saved = 0
        self.trades_failed = 0
        self.tuner_adjustments = 0
        logger.info("Listener metrics reset")
