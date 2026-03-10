"""
dedup_learner.py — Weekly Self-Learning for Deduplication Windows (PHASE 3)

Responsibility:
  - Analyze historical signal gaps (SSOT from sys_dedup_events)
  - Calculate optimal dedup windows per (symbol, timeframe, strategy)
  - Apply governance guardrails (±30% change, 10%-300% bounds)
  - Persist learned windows to sys_dedup_rules (SSOT)
  - Log all adjustments with trace_id for auditing

Rule:
  - NO broker imports (agnosis rule #4)
  - ALL persistence via StorageManager (SSOT rule #15)
  - Dependency injection: storage passed from MainOrchestrator
  - Execute weekly (Sundays 22:00 UTC)
"""

import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
from dataclasses import dataclass
import statistics
import numpy as np
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class DedupLearningResult:
    """Result of a single dedup window learning session."""
    symbol: str
    timeframe: str
    strategy: str
    window_old: int
    window_new: int
    window_optimal: int
    gap_count: int
    gap_median: float
    change_pct: float
    was_applied: bool
    reason_blocked: Optional[str] = None
    trace_id: str = ""


class DedupLearner:
    """
    PHASE 3: Weekly self-learning for intelligent deduplication windows.
    
    Workflow:
      1. Collect all signal gaps from last 7 days (from sys_dedup_events)
      2. Group by (symbol, timeframe, strategy)
      3. For each group: calculate gap distribution
      4. Propose optimal window: percentile_50 × 0.8
      5. Apply governance guardrails
      6. Persist to sys_dedup_rules + audit log
    """

    # --- Governance Guardrails ---
    MIN_CHANGE_PCT = -30.0   # Maximum decrease allowed
    MAX_CHANGE_PCT = +30.0   # Maximum increase allowed
    MIN_WINDOW_PCT = 10.0    # Floor: 10% of base_window
    MAX_WINDOW_PCT = 300.0   # Ceiling: 300% of base_window
    MIN_OBSERVATIONS = 5     # Don't learn if < 5 gaps observed
    LEARNING_MARGIN = 0.8    # Use percentile_50 × 0.8 for conservatism

    def __init__(self, storage_manager):
        """
        Args:
            storage_manager: StorageManager instance (SSOT for all persistence)
        """
        self.storage = storage_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def run_weekly_learning_cycle(self) -> Dict[str, List[DedupLearningResult]]:
        """
        Main entry point: runs full weekly learning cycle.
        
        Returns:
            {
                "learned": [List of successfully learned windows],
                "blocked": [List of proposed but rejected adjustments],
                "skipped": [List of groups with insufficient data],
                "total_processed": int
            }
        """
        
        results = {
            "learned": [],
            "blocked": [],
            "skipped": [],
            "total_processed": 0
        }
        
        learning_id = f"DEDUP-LEARNING-{datetime.utcnow().isoformat()}"
        
        self.logger.info(f"[DEDUP_LEARNER] Starting weekly learning cycle: {learning_id}")
        
        try:
            # Step 1: Collect gap data from last 7 days
            gap_data = await self._collect_gap_data(days=7)
            
            if not gap_data:
                self.logger.info("[DEDUP_LEARNER] No gap data collected. Skipping learning cycle.")
                return results
            
            # Step 2: Group by (symbol, timeframe, strategy)
            groups = self._group_by_key(gap_data)
            
            # Step 3: Analyze each group and propose window
            for (symbol, timeframe, strategy), gaps in groups.items():
                results["total_processed"] += 1
                
                # Check minimum observations
                if len(gaps) < self.MIN_OBSERVATIONS:
                    result = DedupLearningResult(
                        symbol=symbol,
                        timeframe=timeframe,
                        strategy=strategy,
                        window_old=0,
                        window_new=0,
                        window_optimal=0,
                        gap_count=len(gaps),
                        gap_median=0.0,
                        change_pct=0.0,
                        was_applied=False,
                        reason_blocked=f"Insufficient observations ({len(gaps)} < {self.MIN_OBSERVATIONS})",
                        trace_id=learning_id
                    )
                    results["skipped"].append(result)
                    continue
                
                # Analyze gap distribution
                learning_result = await self._analyze_and_propose_window(
                    symbol, timeframe, strategy, gaps, learning_id
                )
                
                if learning_result.was_applied:
                    results["learned"].append(learning_result)
                elif learning_result.reason_blocked:
                    results["blocked"].append(learning_result)
                else:
                    results["skipped"].append(learning_result)
        
        except Exception as e:
            self.logger.error(f"[DEDUP_LEARNER] Error in learning cycle: {e}")
        
        # Summary logging
        self.logger.info(
            f"[DEDUP_LEARNER] Cycle complete: {len(results['learned'])} learned, "
            f"{len(results['blocked'])} blocked, {len(results['skipped'])} skipped"
        )
        
        return results

    async def _collect_gap_data(self, days: int = 7) -> List[Dict]:
        """
        Collect all signal gaps from last N days.
        
        Returns:
            List of dicts: {symbol, timeframe, strategy, gap_minutes, created_at}
        """
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        try:
            # Query sys_dedup_events table (contains when signals were deduplicated)
            gap_records = await self.storage.get_dedup_events_since(cutoff_date)
            
            if not gap_records:
                self.logger.debug("[DEDUP_LEARNER] No dedup events found in last 7 days")
                return []
            
            # Transform to gap format (time between consecutive events)
            gaps = []
            for record in gap_records:
                gaps.append({
                    "symbol": record.get("symbol"),
                    "timeframe": record.get("timeframe"),
                    "strategy": record.get("strategy"),
                    "gap_minutes": record.get("gap_minutes"),  # Already calculated by DB
                    "created_at": record.get("created_at")
                })
            
            self.logger.debug(f"[DEDUP_LEARNER] Collected {len(gaps)} gap records")
            return gaps
        
        except Exception as e:
            self.logger.error(f"[DEDUP_LEARNER] Error collecting gap data: {e}")
            return []

    def _group_by_key(self, gaps: List[Dict]) -> Dict[Tuple, List[float]]:
        """
        Group gaps by (symbol, timeframe, strategy).
        
        Returns:
            {(symbol, timeframe, strategy): [gap_minutes, ...], ...}
        """
        groups = {}
        
        for gap in gaps:
            key = (
                gap.get("symbol"),
                gap.get("timeframe"),
                gap.get("strategy")
            )
            
            if key not in groups:
                groups[key] = []
            
            groups[key].append(gap.get("gap_minutes"))
        
        return groups

    async def _analyze_and_propose_window(
        self,
        symbol: str,
        timeframe: str,
        strategy: str,
        gaps: List[float],
        learning_id: str
    ) -> DedupLearningResult:
        """
        Analyze gap distribution and propose new window.
        """
        
        # Calculate statistics
        gap_median = statistics.median(gaps)
        gap_mean = statistics.mean(gaps)
        gap_std = statistics.stdev(gaps) if len(gaps) > 1 else 0.0
        
        # Get current window
        current_rule = await self.storage.get_dedup_rule(symbol, timeframe, strategy)
        window_old = current_rule.get("current_window_minutes", 5) if current_rule else 5
        base_window = current_rule.get("base_window_minutes", 5) if current_rule else 5
        
        # Propose optimal window
        window_optimal = int(gap_median * self.LEARNING_MARGIN)
        
        # Apply governance guardrails
        change_pct = ((window_optimal - window_old) / window_old) * 100 if window_old > 0 else 0.0
        
        result = DedupLearningResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy=strategy,
            window_old=window_old,
            window_new=0,
            window_optimal=window_optimal,
            gap_count=len(gaps),
            gap_median=gap_median,
            change_pct=change_pct,
            was_applied=False,
            trace_id=learning_id
        )
        
        # Check ±30% change rate limit
        if change_pct < self.MIN_CHANGE_PCT or change_pct > self.MAX_CHANGE_PCT:
            result.reason_blocked = (
                f"Change rate {change_pct:.1f}% exceeds ±{self.MAX_CHANGE_PCT}% limit"
            )
            return result
        
        # Check 10%-300% of base window bounds
        min_bound = int(base_window * self.MIN_WINDOW_PCT / 100.0)
        max_bound = int(base_window * self.MAX_WINDOW_PCT / 100.0)
        
        if window_optimal < min_bound or window_optimal > max_bound:
            result.reason_blocked = (
                f"Proposed window {window_optimal} outside bounds [{min_bound}, {max_bound}]"
            )
            return result
        
        # All guardrails passed - apply the learning
        result.window_new = window_optimal
        
        try:
            await self.storage.update_dedup_rule(
                symbol=symbol,
                timeframe=timeframe,
                strategy=strategy,
                current_window_minutes=window_optimal,
                data_points_observed=len(gaps),
                learning_enabled=True,
                trace_id=learning_id
            )
            
            result.was_applied = True
            
            self.logger.info(
                f"[DEDUP_LEARNER] Learned window for {symbol}/{timeframe}/{strategy}: "
                f"{window_old} → {window_optimal} min ({change_pct:+.1f}%) | "
                f"gaps={len(gaps)}, median={gap_median:.1f} min, trace_id={learning_id}"
            )
        
        except Exception as e:
            self.logger.error(f"[DEDUP_LEARNER] Error updating rule: {e}")
            result.reason_blocked = f"Database update failed: {str(e)}"
        
        return result


# Utility function for scheduled weekly execution
async def scheduled_weekly_dedup_learning(storage_manager: StorageManager) -> Dict[str, Any]:
    """
    Entry point for scheduler (runs every Sunday 22:00 UTC).
    
    Args:
        storage_manager: StorageManager instance
    
    Returns:
        Dict with learning results per (symbol, timeframe, strategy)
    """
    learner = DedupLearner(storage_manager)
    results = await learner.run_weekly_learning_cycle()
    return results
