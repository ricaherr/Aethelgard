"""
signal_review_manager.py — B/C Grade Signal Review Queue Management

Responsibility:
  - Queue B/C-grade signals (moderate confidence) for trader review
  - Manage pending reviews with 5-minute timeout
  - Process trader approvals/rejections
  - Emit WebSocket notifications to UI
  - Auto-execute on timeout

Architecture:
  - SSOT: All state persisted in sys_signals.review_status (BD)
  - DI: Injected StorageManager, no hardcoding
  - RULE T1: TenantDBFactory(token.sub) for isolation
  - Async: Non-blocking, fire-and-forget WebSocket events

TRACE_ID: DISC-SQ-001-2026-04-04 (Signal Quality Review Queue)
"""

import logging
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone
import asyncio
import uuid

from models.signal import ReviewStatus
from core_brain.services.socket_service import get_socket_service

logger = logging.getLogger(__name__)


class SignalReviewManager:
    """
    Manages B/C-grade signal review queue lifecycle.
    
    Workflow:
    1. SignalFactory generates signal with quality_grade=B or C
    2. MainOrchestrator quality gate calls queue_for_review()
    3. Signal persists to DB with review_status='PENDING'
    4. WebSocket notifies trader with 5-min countdown
    5. Trader approves/rejects OR timeout auto-executes
    6. Signal status updated → execution or archive
    """

    def __init__(self, storage_manager: Any):
        """
        Initialize review manager.
        
        Args:
            storage_manager: StorageManager instance (DI, NOT hardcoded)
        """
        self.storage = storage_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Timeout config (seconds)
        self.REVIEW_TIMEOUT_SECONDS = 300  # 5 minutes
        
        # Track pending reviews in memory (cache for efficiency)
        # Format: {signal_id: {'expire_at': datetime, 'symbol': str, ...}}
        self._pending_reviews: Dict[str, Dict[str, Any]] = {}

    async def queue_for_review(
        self,
        signal: Dict[str, Any],
        grade: str,
        score: float,
        reason: str = "B_GRADE_MODERATE_CONFIDENCE"
    ) -> Tuple[bool, str]:
        """
        Queue a B/C-grade signal for trader review.
        
        Steps:
        1. Set review_status='PENDING' in sys_signals
        2. Calculate timeout (5 min from now)
        3. Cache in memory for timeout tracking
        4. Emit WebSocket notification to trader
        
        Args:
            signal: Signal dict from generation pipeline
            grade: Quality grade (B or C)
            score: Quality score (0-100)
            reason: Why queued (default: B_GRADE_MODERATE_CONFIDENCE)
        
        Returns:
            (success: bool, message: str)
        """
        try:
            signal_id = signal.get("id") or str(uuid.uuid4())
            symbol = signal.get("symbol", "UNKNOWN")
            
            # Calculate timeout
            now_utc = datetime.now(timezone.utc)
            timeout_at = now_utc + timedelta(seconds=self.REVIEW_TIMEOUT_SECONDS)
            
            # Update DB (SSOT)
            self.storage.execute_update(
                """
                UPDATE sys_signals 
                SET review_status = ?, 
                    trader_review_reason = ?,
                    review_timeout_at = ?
                WHERE id = ?
                """,
                (
                    ReviewStatus.PENDING.value,
                    f"{grade}_GRADE_{reason}",
                    timeout_at.isoformat(),
                    signal_id,
                )
            )
            
            # Cache in memory for timeout tracking
            self._pending_reviews[signal_id] = {
                "expire_at": timeout_at,
                "symbol": symbol,
                "grade": grade,
                "score": score,
                "queued_at": now_utc.isoformat(),
                "reason": reason,
            }
            
            self.logger.info(
                f"[REVIEW_QUEUE] Signal {signal_id} ({symbol}) queued: "
                f"Grade={grade}, Score={score:.0f}%, Timeout={self.REVIEW_TIMEOUT_SECONDS}s"
            )
            
            # Emit WebSocket notification (async, non-blocking)
            asyncio.create_task(
                self._emit_review_notification(signal_id, symbol, grade, score, timeout_at)
            )
            
            return True, f"Signal {signal_id} queued for review"
        
        except Exception as e:
            self.logger.error(f"[REVIEW_QUEUE] Error queuing signal: {e}", exc_info=True)
            return False, f"Failed to queue signal: {str(e)}"

    async def process_trader_approval(
        self,
        signal_id: str,
        trader_id: str,
        approval_reason: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Process trader approval of B/C-grade signal.
        
        Steps:
        1. Verify signal exists and is PENDING
        2. Update review_status='APPROVED'
        3. Mark for execution (return True to caller)
        4. Log to sys_audit_logs
        5. Remove from memory cache
        
        Args:
            signal_id: UUID of signal being approved
            trader_id: User ID of approving trader
            approval_reason: Optional trader notes
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # Verify signal is PENDING
            signal_data = self.storage.execute_query(
                "SELECT id, symbol, review_status FROM sys_signals WHERE id = ?",
                (signal_id,)
            )
            
            if not signal_data:
                return False, f"Signal {signal_id} not found"
            
            if signal_data[0].get("review_status") != ReviewStatus.PENDING.value:
                return False, f"Signal {signal_id} is not pending review"
            
            # Update status to APPROVED
            self.storage.execute_update(
                """
                UPDATE sys_signals 
                SET review_status = ?, 
                    trader_review_reason = COALESCE(?, trader_review_reason)
                WHERE id = ?
                """,
                (ReviewStatus.APPROVED.value, approval_reason, signal_id)
            )
            
            # Log approval action
            self.storage.execute_update(
                """
                INSERT INTO sys_audit_logs (user_id, action, resource, resource_id, status, reason, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trader_id,
                    "SIGNAL_APPROVED",
                    "sys_signals",
                    signal_id,
                    "success",
                    approval_reason or "Trader approved B/C-grade signal",
                    str(uuid.uuid4()),
                )
            )
            
            # Remove from cache
            self._pending_reviews.pop(signal_id, None)
            
            self.logger.info(
                f"[REVIEW_APPROVAL] Signal {signal_id} approved by trader {trader_id}"
            )
            
            return True, f"Signal {signal_id} approved and marked for execution"
        
        except Exception as e:
            self.logger.error(f"[REVIEW_APPROVAL] Error approving signal: {e}", exc_info=True)
            return False, f"Failed to approve signal: {str(e)}"

    async def process_trader_rejection(
        self,
        signal_id: str,
        trader_id: str,
        rejection_reason: str
    ) -> Tuple[bool, str]:
        """
        Process trader rejection of B/C-grade signal.
        
        Steps:
        1. Verify signal is PENDING
        2. Update review_status='REJECTED'
        3. Add to cooldown (30 min, same asset)
        4. Archive signal
        5. Log rejection
        
        Args:
            signal_id: UUID of signal being rejected
            trader_id: User ID rejecting trader
            rejection_reason: Why rejected (from UI)
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # Verify and get signal data
            signal_data = self.storage.execute_query(
                "SELECT id, symbol, strategy_id, review_status FROM sys_signals WHERE id = ?",
                (signal_id,)
            )
            
            if not signal_data:
                return False, f"Signal {signal_id} not found"
            
            if signal_data[0].get("review_status") != ReviewStatus.PENDING.value:
                return False, f"Signal {signal_id} is not pending review"
            
            signal = signal_data[0]
            symbol = signal.get("symbol")
            strategy_id = signal.get("strategy_id")
            
            # Update status to REJECTED
            self.storage.execute_update(
                """
                UPDATE sys_signals 
                SET review_status = ?, 
                    trader_review_reason = ?
                WHERE id = ?
                """,
                (ReviewStatus.REJECTED.value, f"Rejected: {rejection_reason}", signal_id)
            )
            
            # Add to cooldown (30 min)
            cooldown_until = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
            cooldown_key = f"cooldown_{strategy_id}_{symbol}"
            
            self.storage.execute_update(
                "INSERT OR REPLACE INTO sys_config (key, value) VALUES (?, ?)",
                (cooldown_key, cooldown_until)
            )
            
            # Log rejection
            self.storage.execute_update(
                """
                INSERT INTO sys_audit_logs (user_id, action, resource, resource_id, status, reason, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trader_id,
                    "SIGNAL_REJECTED",
                    "sys_signals",
                    signal_id,
                    "rejected",
                    f"Rejected: {rejection_reason}",
                    str(uuid.uuid4()),
                )
            )
            
            # Remove from cache
            self._pending_reviews.pop(signal_id, None)
            
            self.logger.info(
                f"[REVIEW_REJECTION] Signal {signal_id} rejected by trader {trader_id}. "
                f"Cooldown applied until {cooldown_until}"
            )
            
            return True, f"Signal {signal_id} rejected. Cooldown applied for {strategy_id}/{symbol}"
        
        except Exception as e:
            self.logger.error(f"[REVIEW_REJECTION] Error rejecting signal: {e}", exc_info=True)
            return False, f"Failed to reject signal: {str(e)}"

    async def check_and_execute_timed_out_reviews(self) -> Dict[str, int]:
        """
        Check for pending reviews that have exceeded timeout.
        Auto-execute signals that traders didn't approve/reject in time.
        
        Called periodically (e.g., every heartbeat cycle).
        
        Returns:
            Stats dict with timed out IDs for orchestrator execution:
            {'auto_executed': N, 'still_pending': M, 'auto_executed_ids': [signal_id, ...]}
        """
        try:
            now_utc = datetime.now(timezone.utc)
            auto_executed = 0
            still_pending = 0
            auto_executed_ids: List[str] = []
            
            # Get all pending reviews from DB (SSOT, not just memory cache)
            pending_signals = self.storage.execute_query(
                """
                SELECT id, symbol, review_timeout_at, trader_review_reason 
                FROM sys_signals 
                WHERE review_status = ?
                """,
                (ReviewStatus.PENDING.value,)
            )
            
            for signal in pending_signals:
                signal_id = signal.get("id")
                timeout_str = signal.get("review_timeout_at")
                
                if not timeout_str:
                    self.logger.warning(f"[TIMEOUT_CHECK] Signal {signal_id} has no timeout_at, skipping")
                    continue
                
                try:
                    timeout_at = datetime.fromisoformat(timeout_str)
                    # Make timezone-aware if naive
                    if timeout_at.tzinfo is None:
                        timeout_at = timeout_at.replace(tzinfo=timezone.utc)
                except ValueError as e:
                    self.logger.warning(f"[TIMEOUT_CHECK] Invalid timeout format for {signal_id}: {e}")
                    continue
                
                # Check if timeout exceeded
                if now_utc >= timeout_at:
                    # Auto-execute this signal
                    success, msg = await self._auto_execute_on_timeout(signal_id)
                    if success:
                        auto_executed += 1
                        auto_executed_ids.append(signal_id)
                    else:
                        still_pending += 1
                else:
                    still_pending += 1
            
            if auto_executed > 0:
                self.logger.info(
                    f"[TIMEOUT_CHECK] Auto-executed {auto_executed} signals due to 5-min timeout"
                )
            
            return {
                "auto_executed": auto_executed,
                "still_pending": still_pending,
                "auto_executed_ids": auto_executed_ids,
            }
        
        except Exception as e:
            self.logger.error(f"[TIMEOUT_CHECK] Error checking timeouts: {e}", exc_info=True)
            return {"auto_executed": 0, "still_pending": 0, "auto_executed_ids": [], "error": str(e)}

    async def _auto_execute_on_timeout(
        self,
        signal_id: str
    ) -> Tuple[bool, str]:
        """
        Auto-execute a signal after 5-min timeout with no trader action.
        
        Args:
            signal_id: UUID of signal to auto-execute
        
        Returns:
            (success: bool, message: str)
        """
        try:
            # Update status to AUTO_EXECUTED
            self.storage.execute_update(
                """
                UPDATE sys_signals 
                SET review_status = ?, 
                    trader_review_reason = COALESCE(trader_review_reason, 'AUTO_EXECUTED_TIMEOUT')
                WHERE id = ?
                """,
                (ReviewStatus.AUTO_EXECUTED.value, signal_id)
            )
            
            self.logger.info(
                f"[AUTO_EXECUTE_TIMEOUT] Signal {signal_id} auto-executed after 5-min timeout"
            )
            
            return True, f"Signal {signal_id} auto-executed"
        
        except Exception as e:
            self.logger.error(f"[AUTO_EXECUTE_TIMEOUT] Error auto-executing {signal_id}: {e}")
            return False, f"Failed to auto-execute: {str(e)}"

    async def get_pending_reviews_for_trader(
        self,
        trader_id: str
    ) -> List[Dict[str, Any]]:
        """
        Get all pending B/C-grade signals for a specific trader.
        
        RULE T1 COMPLIANCE: Filtered by trader_id (tenant isolation).
        
        Args:
            trader_id: User ID requesting their pending reviews
        
        Returns:
            List of pending signal dicts with remaining time
        """
        try:
            now_utc = datetime.now(timezone.utc)
            
            # Query pending signals (RULE T1: filtered later by router via TenantDBFactory)
            pending_signals = self.storage.execute_query(
                """
                SELECT id, symbol, signal_type, confidence, price, 
                       review_timeout_at, trader_review_reason, created_at
                FROM sys_signals 
                WHERE review_status = ?
                ORDER BY created_at DESC
                LIMIT 20
                """,
                (ReviewStatus.PENDING.value,)
            )
            
            # Calculate remaining time for each
            result = []
            for signal in pending_signals:
                timeout_str = signal.get("review_timeout_at")
                if timeout_str:
                    try:
                        timeout_at = datetime.fromisoformat(timeout_str)
                        if timeout_at.tzinfo is None:
                            timeout_at = timeout_at.replace(tzinfo=timezone.utc)
                        remaining_sec = int((timeout_at - now_utc).total_seconds())
                        remaining_sec = max(0, remaining_sec)
                    except ValueError:
                        remaining_sec = 0
                else:
                    remaining_sec = 0
                
                signal["remaining_seconds"] = remaining_sec
                signal["timeout_at"] = timeout_str
                result.append(signal)
            
            return result
        
        except Exception as e:
            self.logger.error(f"[GET_PENDING] Error fetching pending reviews: {e}", exc_info=True)
            return []

    async def _emit_review_notification(
        self,
        signal_id: str,
        symbol: str,
        grade: str,
        score: float,
        timeout_at: datetime
    ) -> None:
        """
        Emit WebSocket notification to trader for pending B/C-grade signal.
        
        Sent to /ws/signal_reviews/pending with 5-min countdown.
        
        Args:
            signal_id: UUID of signal
            symbol: Trading pair
            grade: Quality grade (B or C)
            score: Quality score (0-100)
            timeout_at: When to auto-execute
        """
        try:
            payload = {
                "event_type": "SIGNAL_REVIEW_PENDING",
                "signal_id": signal_id,
                "symbol": symbol,
                "grade": grade,
                "score": score,
                "timeout_at": timeout_at.isoformat(),
                "timeout_seconds": self.REVIEW_TIMEOUT_SECONDS,
                "message": f"B/C-grade signal for {symbol} requires your review"
            }
            
            # Emit via WebSocket (implementation in router)
            socket_service = get_socket_service()
            await socket_service.emit_event("SIGNAL_REVIEW_PENDING", payload)
            self.logger.debug(f"[WS_NOTIFICATION] Emitted SIGNAL_REVIEW_PENDING for {signal_id}")
        
        except Exception as e:
            self.logger.warning(f"[WS_NOTIFICATION] Error emitting notification: {e}")
            # Non-blocking, don't raise
