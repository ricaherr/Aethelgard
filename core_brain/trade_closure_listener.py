"""
Trade Closure Listener - Autonomous Feedback Loop
==================================================

Listens for broker trade closure events and:
1. Saves trade results to DB (with retry logic for lock handling)
2. Updates RiskManager (record_trade_result)
3. Triggers EdgeTuner.adjust_parameters()
4. Triggers ThresholdOptimizer (confidence_threshold adaptation)
5. Maintains audit trail

Principle: Broker-agnostic. Receives standardized BrokerTradeClosedEvent.
"""
import logging
import asyncio
from typing import Optional, List
from datetime import datetime, timedelta
import time

from data_vault.storage import StorageManager
from core_brain.risk_manager import RiskManager
from core_brain.edge_tuner import EdgeTuner
from core_brain.threshold_optimizer import ThresholdOptimizer
from models.broker_event import BrokerTradeClosedEvent, BrokerEvent, BrokerEventType
from models.execution_mode import ExecutionMode, Provider, AccountType, BROKER_KEYWORDS_TO_PROVIDER, BROKER_KEYWORDS_TO_ACCOUNT_TYPE

logger = logging.getLogger(__name__)


class TradeClosureListener:
    """
    Autonomous listener for trade closure events.
    
    Responsibilities:
    1. Process trade closed events from any broker
    2. Persist usr_trades to DB (with retry on lock)
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
        threshold_optimizer: Optional[ThresholdOptimizer] = None,
        max_retries: int = 3,
        retry_backoff: float = 0.5
    ):
        """
        Initialize TradeClosureListener with dependency injection.
        
        Args:
            storage: StorageManager for DB persistence
            risk_manager: RiskManager for lockdown/risk tracking
            edge_tuner: EdgeTuner for parameter adjustment
            threshold_optimizer: ThresholdOptimizer for adaptive confidence thresholds
            max_retries: How many times to retry on DB lock
            retry_backoff: Seconds to wait between retries
        """
        self.storage = storage
        self.risk_manager = risk_manager
        self.edge_tuner = edge_tuner
        self.threshold_optimizer = threshold_optimizer
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        
        # Metrics for monitoring
        self.usr_trades_processed = 0
        self.usr_trades_saved = 0
        self.usr_trades_failed = 0
        self.tuner_adjustments = 0
        self.threshold_optimizations = 0
        
        logger.info(
            f"TradeClosureListener initialized: max_retries={max_retries}, "
            f"retry_backoff={retry_backoff}s | "
            f"ThresholdOptimizer: {'enabled' if threshold_optimizer else 'disabled'}"
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
        self.usr_trades_processed += 1
        
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
            self.usr_trades_failed += 1
            logger.error(
                f"[TRADE_CLOSED] FAILED after {self.max_retries} retries: "
                f"Symbol={trade_event.symbol} | Ticket={trade_event.ticket}"
            )
            return False
        
        self.usr_trades_saved += 1
        
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
        
        # === STEP 4: Traceability & Autonomous Learning (EDGE) ===
        # Trigger weight adjustment based on prediction error (Delta)
        await self._process_edge_feedback(trade_event)
        
        # Original parameter tuning (Legacy, periodic or on stress)
        if self.usr_trades_saved % 5 == 0 or self.risk_manager.consecutive_losses >= 3:
            await self._trigger_tuner(trade_event)
            
            # === STEP 4.5: Trigger Threshold Optimization (HU 7.1) ===
            if self.threshold_optimizer:
                await self._trigger_threshold_optimizer(
                    account_id=trade_event.account_id or "default",
                    trace_id=f"ADAPTIVE-THRESHOLD-{datetime.now().strftime('%Y%m%d%H%M')}"
                )
        
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
        Save trade to DB with exponential backoff retry on lock. Includes execution_mode and provider metadata.
        
        Implements resilience: If DB is locked, retry instead of failing.
        
        Args:
            trade: Trade data to save
        
        Returns:
            True if saved, False if failed after retries
        """
        # FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30: resolve context returns both mode and instance_id
        execution_mode, instance_id = await self._resolve_shadow_context(trade.signal_id)
        provider = self._map_broker_id_to_provider(trade.broker_id)
        account_type = await self._get_account_type(trade.broker_id)

        trade_data = {
            "id": trade.ticket,
            "signal_id": trade.signal_id,
            "instance_id": instance_id,  # FIX: required for calculate_instance_metrics_from_sys_trades
            "symbol": trade.symbol,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "profit_loss": trade.profit_loss,
            "profit": trade.profit_loss,  # Alias for compatibility
            "is_win": trade.is_win(),
            "pips": trade.pips,
            "exit_reason": trade.exit_reason,
            "close_time": trade.exit_time.isoformat(),
            "metadata": trade.metadata or {},
            # FASE D: New fields for routing & audit
            "execution_mode": execution_mode,
            "provider": provider,
            "account_type": account_type
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
    
    async def _resolve_shadow_context(
        self, signal_id: Optional[str]
    ) -> tuple:
        """Resolve (execution_mode, instance_id) for a trade being closed.

        FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30:
        The previous _get_execution_mode() never returned instance_id, causing
        sys_trades.instance_id = NULL for all SHADOW trades.
        Without instance_id, calculate_instance_metrics_from_sys_trades() always
        returns 0 trades, breaking the Darwinian evaluation cycle.

        Resolution order:
          1. Get strategy_id from signal metadata.
          2. Query sys_signal_ranking for execution_mode.
          3. If SHADOW (or ranking absent but active shadow instance exists):
             look up sys_shadow_instances for the active instance of that strategy.
          4. Fallback: (LIVE, None).

        Args:
            signal_id: Signal ID linked to the closed trade.

        Returns:
            Tuple (execution_mode: str, instance_id: Optional[str])
        """
        import json as _json

        if not signal_id:
            return ExecutionMode.LIVE.value, None

        try:
            signal = self.storage.get_signal_by_id(signal_id)
            if not signal:
                return ExecutionMode.LIVE.value, None

            # Extract strategy_id from signal metadata
            metadata = signal.get('metadata')
            if isinstance(metadata, str):
                try:
                    metadata = _json.loads(metadata)
                except (ValueError, TypeError):
                    metadata = {}

            strategy_id = metadata.get('strategy_id') if isinstance(metadata, dict) else None
            if not strategy_id:
                return ExecutionMode.LIVE.value, None

            # Try to get execution_mode from sys_signal_ranking
            mode = ExecutionMode.LIVE.value
            ranking = self.storage.get_signal_ranking(strategy_id)
            if ranking and 'execution_mode' in ranking:
                mode = ranking.get('execution_mode', ExecutionMode.LIVE.value)

            # For SHADOW mode (from ranking or inferred below), resolve instance_id
            instance_id = None
            if mode == ExecutionMode.SHADOW.value:
                instance_id = self._lookup_shadow_instance_id(strategy_id)
            elif mode == ExecutionMode.LIVE.value:
                # If ranking is absent, check whether an active SHADOW instance exists
                # for this strategy — if so, infer SHADOW mode to avoid losing trades
                candidate = self._lookup_shadow_instance_id(strategy_id)
                if candidate:
                    mode = ExecutionMode.SHADOW.value
                    instance_id = candidate

            logger.debug(
                "[ROUTING] Signal %s → Strategy %s → Mode %s → Instance %s",
                signal_id, strategy_id, mode, instance_id,
            )
            return mode, instance_id

        except Exception as e:
            logger.warning(f"Error resolving shadow context for signal {signal_id}: {e}")
            return ExecutionMode.LIVE.value, None

    def _lookup_shadow_instance_id(self, strategy_id: str) -> Optional[str]:
        """Query sys_shadow_instances for the most recent active instance of a strategy.

        FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30:
        Called by _resolve_shadow_context() to populate instance_id in trade_data.

        Args:
            strategy_id: Strategy to look up.

        Returns:
            instance_id string if found, None otherwise.
        """
        try:
            conn = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT instance_id FROM sys_shadow_instances
                WHERE strategy_id = ?
                  AND status NOT IN ('DEAD', 'PROMOTED_TO_REAL')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (strategy_id,),
            )
            row = cursor.fetchone()
            if row:
                return row[0] if isinstance(row, (list, tuple)) else row["instance_id"]
            return None
        except Exception as e:
            logger.warning(f"[SHADOW] Could not resolve instance_id for strategy {strategy_id}: {e}")
            return None
        finally:
            try:
                self.storage._close_conn(conn)
            except Exception:
                pass

    async def _get_execution_mode(self, signal_id: Optional[str]) -> str:
        """Get execution_mode (LIVE/SHADOW) from usr_performance if signal linked.

        Deprecated: use _resolve_shadow_context() which also returns instance_id.
        Kept for backward compatibility with any external callers.

        Args:
            signal_id: Signal ID to lookup

        Returns:
            ExecutionMode.LIVE if unknown or signal not linked, otherwise actual mode from usr_performance
        """
        mode, _ = await self._resolve_shadow_context(signal_id)
        return mode
    
    def _map_broker_id_to_provider(self, broker_id: str) -> str:
        """Map broker_id to provider constants (MT5, NT, FIX, INTERNAL).
        
        Uses centralized keyword mapping from models/execution_mode.py to avoid duplication.
        
        Args:
            broker_id: Broker identifier (MT5, NT8, etc.)
            
        Returns:
            Provider name: 'MT5', 'NT', 'FIX', or 'INTERNAL'
        """
        broker_lower = broker_id.lower() if broker_id else 'unknown'
        
        # Check keyword-based mapping first
        for keyword, provider in BROKER_KEYWORDS_TO_PROVIDER.items():
            if keyword in broker_lower:
                return provider.value
        
        # Default to MT5 for backward compatibility
        return Provider.MT5.value
    
    async def _get_account_type(self, broker_id: str) -> str:
        """Determine if account is REAL or DEMO based on broker_id.
        
        Uses centralized keyword mapping from models/execution_mode.py.
        
        Args:
            broker_id: Broker identifier
            
        Returns:
            'REAL' or 'DEMO'
        """
        try:
            broker_lower = broker_id.lower() if broker_id else 'unknown'
            
            # Check keyword-based mapping first
            for keyword, account_type in BROKER_KEYWORDS_TO_ACCOUNT_TYPE.items():
                if keyword in broker_lower:
                    return account_type.value
            
            # Default to REAL if not explicitly DEMO
            return AccountType.REAL.value
        except Exception as e:
            logger.warning(f"Error determining account_type for {broker_id}: {e}")
            return AccountType.REAL.value
    
    async def _process_edge_feedback(self, trade: BrokerTradeClosedEvent) -> None:
        """
        Fetch original signal info and trigger EdgeTuner feedback loop.
        Calculates Delta = Actual Result - Predicted Score.
        """
        try:
            if not trade.signal_id:
                return
            
            signal = self.storage.get_signal_by_id(trade.signal_id)
            if not signal:
                logger.debug(f"Signal {trade.signal_id} not found for feedback loop")
                return
            
            # Prediction inputs
            confidence = signal.get('confidence', 0.0)
            metadata = signal.get('metadata', {})
            regime = metadata.get('regime', 'UNKNOWN')
            
            # Prepare result data
            trade_result = {
                "is_win": trade.is_win(),
                "profit_loss": trade.profit_loss,
                "ticket": trade.ticket
            }
            
            # Trigger learning feedback
            result = self.edge_tuner.process_trade_feedback(
                trade_result=trade_result,
                predicted_score=confidence,
                regime=regime
            )
            
            if result.get('adjustment_made'):
                logger.info(f"[TUNER] [ADAPTIVE] Learning Adjustment: {result['learning']}")
            
            # FASE 2: Adjust confidence_threshold dynamically (Lite Confidence Profiling)
            # Allows SHADOW mode to learn true confidence calibration over time
            try:
                confidence_adj = self.edge_tuner.adjust_confidence_threshold(
                    predicted_score=confidence,
                    actual_result=float(trade_result["is_win"])
                )
                
                if confidence_adj.get('adjustment_made'):
                    logger.info(
                        f"[CONFIDENCE_LEARNING] Threshold adjusted: "
                        f"{confidence_adj['old_threshold']:.2f} → {confidence_adj['new_threshold']:.2f} "
                        f"(Delta={confidence_adj['delta']:.3f})"
                    )
            except Exception as e:
                logger.debug(f"[CONFIDENCE_LEARNING] Skipped: {e}")
                
        except Exception as e:
            logger.error(f"Error in edge feedback processing: {e}", exc_info=True)

    async def _trigger_tuner(self, trade: BrokerTradeClosedEvent) -> bool:
        """
        Trigger EdgeTuner parameter adjustment.
        
        Args:
            trade: Trade that triggered the tuning
        
        Returns:
            True if adjustment made, False if skipped
        """
        try:
            adjustment_result = self.edge_tuner.adjust_parameters(limit_usr_trades=100)
            
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
    
    async def _trigger_threshold_optimizer(
        self, account_id: str, trace_id: str
    ) -> bool:
        """
        Trigger ThresholdOptimizer to adaptively adjust confidence threshold.
        
        Activation Logic:
        - Every 5 successful usr_trades (periodic)
        - When consecutive losses >= 3 (loss streak detection)
        
        Args:
            account_id: Account to optimize
            trace_id: Trace ID for observability
        
        Returns:
            True if optimization triggered, False otherwise
        """
        if not self.threshold_optimizer:
            return False
        
        try:
            result = await self.threshold_optimizer.optimize_threshold(
                account_id=account_id,
                trace_id=trace_id
            )
            
            if result.get("delta") and abs(result["delta"]) > 1e-6:
                self.threshold_optimizations += 1
                reason = result.get("reason", "UNKNOWN")
                logger.info(
                    f"[THRESHOLD_OPTIMIZER] Confidence threshold optimized: "
                    f"{result['old_threshold']:.3f} → {result['new_threshold']:.3f} "
                    f"(Δ={result['delta']:+.3f}) | Reason: {reason} | Trace_ID: {trace_id}"
                )
                return True
            else:
                logger.debug(f"[THRESHOLD_OPTIMIZER] No adjustment needed ({result.get('reason')})")
                return False
        
        except Exception as e:
            logger.error(f"Error triggering threshold optimizer: {e}", exc_info=True)
            return False
    
    def get_metrics(self) -> dict:
        """
        Get listener metrics for monitoring.
        
        Returns:
            Dictionary with processed/saved/failed counts
        """
        return {
            "usr_trades_processed": self.usr_trades_processed,
            "usr_trades_saved": self.usr_trades_saved,
            "usr_trades_failed": self.usr_trades_failed,
            "tuner_adjustments": self.tuner_adjustments,
            "threshold_optimizations": self.threshold_optimizations,
            "success_rate": (
                self.usr_trades_saved / self.usr_trades_processed * 100
                if self.usr_trades_processed > 0 else 0.0
            )
        }
    
    def reset_metrics(self) -> None:
        """Reset metrics (useful for daily rollover)"""
        self.usr_trades_processed = 0
        self.usr_trades_saved = 0
        self.usr_trades_failed = 0
        self.tuner_adjustments = 0
        self.threshold_optimizations = 0
        logger.info("Listener metrics reset")
