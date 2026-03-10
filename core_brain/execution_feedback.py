"""
Execution Feedback Collector - Autonomous Learning Loop

Purpose:
- Collects execution failures/vetoes from ExecutionService
- Analyzes failure patterns (by symbol, strategy, time, reason)
- Provides data to SignalFactory for intelligent signal suppression
- Implements Dominio 10 (INFRA_RESILIENCY): Feedback integration for self-healing

Architecture:
- SSOT: Persists in DB (sys_execution_feedback table)
- In-Memory State: Rolling window of recent failures (last 100)
- Time-Windowed: Forgets old failures (>30 min)

Compliance:
- Dominio 10 (INFRA_RESILIENCY): Auto-Healing feedback loop
- Dominio 03 (ALPHA_GENERATION): Signal retraction on repeated failures
- DEVELOPMENT_GUIDELINES Rule 1.6: Service Layer pattern
- DEVELOPMENT_GUIDELINES Rule 1.5: sys_* naming (global feedback, not per-tenant)
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)


class ExecutionFailureReason(Enum):
    """Enumeration of execution failure causes."""
    PRICE_FETCH_ERROR = "PRICE_FETCH_ERROR"  # _get_current_price returned None
    LIQUIDITY_INSUFFICIENT = "LIQUIDITY_INSUFFICIENT"  # No bid/ask available
    VETO_SLIPPAGE = "VETO_SLIPPAGE"  # Slippage exceeded limit
    VETO_SPREAD = "VETO_SPREAD"  # Spread exceeded limit
    VETO_VOLATILITY = "VETO_VOLATILITY"  # Volatility too high
    CONNECTION_ERROR = "CONNECTION_ERROR"  # Broker connection failed
    ORDER_REJECTED = "ORDER_REJECTED"  # Broker rejected order
    TIMEOUT = "TIMEOUT"  # Execution timeout
    UNKNOWN = "UNKNOWN"  # Unknown cause


@dataclass
class ExecutionFeedback:
    """Atomic feedback from a single execution or veto.
    
    Attributes:
        feedback_id: Unique identifier for this feedback event
        signal_id: ID of the signal that was attempted
        symbol: Trading symbol (EURUSD, AAPL, etc.)
        strategy_name: Name of the strategy that generated signal
        reason: ExecutionFailureReason enum
        timestamp: When the failure occurred
        details: Additional context (slippage amount, spread, volatility, etc.)
    """
    feedback_id: str = field(default_factory=lambda: f"EXEC-FB-{uuid.uuid4().hex[:8].upper()}")
    signal_id: Optional[str] = None
    symbol: str = ""
    strategy_name: Optional[str] = None
    reason: ExecutionFailureReason = ExecutionFailureReason.UNKNOWN
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to DB-storable dict."""
        return {
            "feedback_id": self.feedback_id,
            "signal_id": self.signal_id,
            "symbol": self.symbol,
            "strategy": self.strategy_name,
            "reason": self.reason.value,
            "timestamp": self.timestamp.isoformat(),
            "details": str(self.details),
        }


class ExecutionFeedbackCollector:
    """
    Autonomous feedback collector for execution failures.
    
    Responsibilities:
    1. Record ALL execution failures (price fetch, slippage veto, liquidity, etc.)
    2. Analyze failure patterns (rolling window analysis)
    3. Provide metrics: failure_rate_pct, failure_streak_count, etc.
    4. Persist in DB (sys_execution_feedback)
    5. Supply intelligence to SignalFactory for signal suppression
    
    Architecture:
    - In-Memory: Last 100 failures (for fast querying)
    - Persistent: All feedback in DB
    - Time-Windowed: Recent failures only (config: 30 min)
    """
    
    def __init__(self, storage: Any, window_size: int = 100, retention_minutes: int = 30):
        """
        Initialize feedback collector.
        
        Args:
            storage: StorageManager instance (for DB persistence)
            window_size: Max in-memory failures to keep
            retention_minutes: How long to consider feedback as "recent" (SSOT dynamic_params)
        """
        self.storage = storage
        self.window_size = window_size
        self.retention_minutes = retention_minutes
        
        # In-memory rolling window
        self._recent_feedback: List[ExecutionFeedback] = []
        
        # Pattern tracking (symbol -> failure count)
        self._symbol_failure_count: Dict[str, int] = defaultdict(int)
        self._strategy_failure_count: Dict[str, int] = defaultdict(int)
        self._reason_count: Dict[ExecutionFailureReason, int] = defaultdict(int)
        
        logger.info(
            f"ExecutionFeedbackCollector initialized "
            f"(window={window_size}, retention={retention_minutes}min)"
        )
    
    async def record_failure(
        self,
        signal_id: Optional[str],
        symbol: str,
        strategy_name: Optional[str],
        reason: ExecutionFailureReason,
        details: Optional[Dict[str, Any]] = None
    ) -> ExecutionFeedback:
        """
        Record an execution failure.
        
        Args:
            signal_id: ID of failed signal
            symbol: Trading symbol
            strategy_name: Name of strategy that generated signal
            reason: Why execution failed
            details: Additional context
        
        Returns:
            ExecutionFeedback instance (persisted)
        """
        feedback = ExecutionFeedback(
            signal_id=signal_id,
            symbol=symbol,
            strategy_name=strategy_name,
            reason=reason,
            details=details or {}
        )
        
        # Add to in-memory window
        self._recent_feedback.append(feedback)
        if len(self._recent_feedback) > self.window_size:
            self._recent_feedback.pop(0)  # Remove oldest
        
        # Update pattern counters
        self._symbol_failure_count[symbol] += 1
        if strategy_name:
            self._strategy_failure_count[strategy_name] += 1
        self._reason_count[reason] += 1
        
        # Persist to DB
        try:
            await self._persist_feedback(feedback)
        except Exception as e:
            logger.error(f"Failed to persist execution feedback: {e}", exc_info=False)
        
        logger.warning(
            f"[EXEC-FEEDBACK] {symbol} | {strategy_name or 'unknown'} | "
            f"Reason: {reason.value} | Details: {details}"
        )
        
        return feedback
    
    async def _persist_feedback(self, feedback: ExecutionFeedback) -> None:
        """Persist feedback to sys_execution_feedback table (SSOT)."""
        try:
            # Create table if not exists
            await self._ensure_feedback_table()
            
            # Insert record using StorageManager pattern (_get_conn/_close_conn)
            conn = self.storage._get_conn()
            try:
                cursor = conn.cursor()
                query = """
                    INSERT INTO sys_execution_feedback 
                    (feedback_id, signal_id, symbol, strategy, reason, timestamp, details)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """
                params = (
                    feedback.feedback_id,
                    feedback.signal_id,
                    feedback.symbol,
                    feedback.strategy_name,
                    feedback.reason.value,
                    feedback.timestamp.isoformat(),
                    str(feedback.details),
                )
                cursor.execute(query, params)
                conn.commit()
            finally:
                self.storage._close_conn(conn)
            
        except Exception as e:
            logger.error(f"Error persisting feedback to DB: {e}")
    
    async def _ensure_feedback_table(self) -> None:
        """Create sys_execution_feedback table if not exists."""
        try:
            conn = self.storage._get_conn()
            try:
                cursor = conn.cursor()
                query = """
                    CREATE TABLE IF NOT EXISTS sys_execution_feedback (
                        feedback_id TEXT PRIMARY KEY,
                        signal_id TEXT,
                        symbol TEXT NOT NULL,
                        strategy TEXT,
                        reason TEXT NOT NULL,
                        timestamp TEXT NOT NULL,
                        details TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                cursor.execute(query)
                conn.commit()
            finally:
                self.storage._close_conn(conn)
        except Exception as e:
            logger.debug(f"Table already exists or error: {e}")
    
    def get_symbol_failure_metrics(self, symbol: str) -> Dict[str, Any]:
        """
        Get failure rate for a symbol (recent window).
        
        Returns:
            {
                'symbol': str,
                'failure_count': int,
                'failure_streak': int,  # Consecutive failures
                'recent_reasons': [list of reasons],
                'should_suppress': bool  # True if >3 recent failures
            }
        """
        # Count recent failures for this symbol
        recent_failures = [f for f in self._recent_feedback if f.symbol == symbol]
        
        # Check for streak (last N are all same symbol failures)
        streak = 0
        for f in reversed(self._recent_feedback):
            if f.symbol == symbol:
                streak += 1
            else:
                break
        
        # Collect recent failure reasons
        recent_reasons = [f.reason.value for f in recent_failures[-5:]]
        
        # Suppress if >3 recent failures
        should_suppress = len(recent_failures) > 3
        
        return {
            "symbol": symbol,
            "failure_count": len(recent_failures),
            "failure_streak": streak,
            "recent_reasons": recent_reasons,
            "should_suppress": should_suppress,
            "last_failure": recent_failures[-1].timestamp if recent_failures else None,
        }
    
    def get_strategy_failure_metrics(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get failure rate for a strategy (recent window).
        
        Returns similar structure to get_symbol_failure_metrics().
        """
        recent_failures = [
            f for f in self._recent_feedback 
            if f.strategy_name == strategy_name
        ]
        
        streak = 0
        for f in reversed(self._recent_feedback):
            if f.strategy_name == strategy_name:
                streak += 1
            else:
                break
        
        recent_reasons = [f.reason.value for f in recent_failures[-5:]]
        should_suppress = len(recent_failures) > 2  # Strategies: lower threshold
        
        return {
            "strategy": strategy_name,
            "failure_count": len(recent_failures),
            "failure_streak": streak,
            "recent_reasons": recent_reasons,
            "should_suppress": should_suppress,
            "last_failure": recent_failures[-1].timestamp if recent_failures else None,
        }
    
    def get_overall_stats(self) -> Dict[str, Any]:
        """Get overall execution health snapshot."""
        total_recent = len(self._recent_feedback)
        
        # Most common failure reasons
        reason_ranking = sorted(
            self._reason_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:3]  # Top 3
        
        return {
            "total_recent_failures": total_recent,
            "window_size": self.window_size,
            "symbols_affected": len(self._symbol_failure_count),
            "strategies_affected": len(self._strategy_failure_count),
            "top_failure_reasons": [
                (reason.value, count) for reason, count in reason_ranking
            ],
            "collected_since": (
                self._recent_feedback[0].timestamp.isoformat()
                if self._recent_feedback else "no data"
            ),
        }
    
    def cleanup_old_feedback(self, before_timestamp: Optional[datetime] = None) -> int:
        """
        Remove feedback older than retention window.
        Called periodically to prune old data.
        
        Returns:
            Number of feedback records removed
        """
        if before_timestamp is None:
            before_timestamp = datetime.now(timezone.utc) - timedelta(minutes=self.retention_minutes)
        
        # Remove from in-memory
        original_count = len(self._recent_feedback)
        self._recent_feedback = [
            f for f in self._recent_feedback 
            if f.timestamp > before_timestamp
        ]
        removed_count = original_count - len(self._recent_feedback)
        
        # Cleanup DB
        try:
            query = """
                DELETE FROM sys_execution_feedback 
                WHERE timestamp < ?
            """
            self.storage.execute(query, (before_timestamp.isoformat(),))
        except Exception as e:
            logger.debug(f"DB cleanup error: {e}")
        
        logger.info(f"Cleanup: Removed {removed_count} old feedback records")
        return removed_count
