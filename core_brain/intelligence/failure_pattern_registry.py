"""
failure_pattern_registry.py — Failure Correlation Learning (PHASE 4)

Responsibility:
  - Auto-learn correlations between ExecutionFailureReason and variables
  - Variables: Asset, Timeframe, Session, Regime, Time-of-day
  - Detect patterns like: "EURUSD always gets VETO_SLIPPAGE during ASIA session"
  - Compute failure penalty (-0-30%) for signal contextual score
  - Update patterns periodically (e.g., every N trades or hourly)

Architecture:
  - Consumes: sys_execution_feedback table (failure history)
  - Returns: Failure penalty (0.0-0.3) for given symbol/TF/context
  - Persists: ml_patterns via sys_config table (SSOT)
  - Learning: Runs async, non-blocking (doesn't interrupt trading)

Rule:
  - NO broker/connector imports (agnostic rule #4)
  - ALL persistence via StorageManager (SSOT rule #15)
  - <30KB file limit (mass rule #4)
  - 100% type hints (quality rule #5)
  - No manual triggers, fully autonomous
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
import json

logger = logging.getLogger(__name__)


@dataclass
class FailurePattern:
    """Identified failure pattern."""
    key: str  # e.g., "EURUSD_ASIA_SLIPPAGE" or "GBPUSD_M5_VETO_SPREAD"
    symbol: str
    timeframe: Optional[str]  # None if applies to all TFs
    session: Optional[str]  # None if applies to all sessions
    failure_reason: str  # ExecutionFailureReason value
    occurrence_count: int
    failure_rate: float  # 0-1 (how often this pattern occurs)
    penalty: float  # 0.0-0.3 (penalty for contextual score)
    last_updated: str  # ISO timestamp
    confidence: float  # 0-1 (how confident we are in this pattern)


class FailurePatternRegistry:
    """
    Autonomous learning of failure patterns and correlations.

    PHASE 4 Implementation:
      - Analyzes execution_feedback history to identify failure correlations
      - Learns patterns: "EURUSD fails with SLIPPAGE during ASIA"
      - Computes penalty for signals that would match failure pattern
      - Updates patterns automatically (non-blocking)
    """

    # Configuration
    MIN_PATTERN_OCCURRENCES = 5  # Min samples to consider pattern significant
    PATTERN_UPDATE_INTERVAL_HOURS = 4  # Re-analyze patterns every N hours
    MAX_PENALTY = 0.3  # Max penalty for contextual score (30%)
    
    # Failure reason severity weights (lower = more likely to penalize)
    FAILURE_SEVERITY = {
        "LIQUIDITY_INSUFFICIENT": 1.0,  # Always penalize, high severity
        "VETO_SLIPPAGE": 0.9,  # High severity
        "VETO_SPREAD": 0.8,  # Moderate severity
        "PRICE_FETCH_ERROR": 0.7,  # Technical, might be transient
        "CONNECTION_ERROR": 0.6,  # Network issue, might be transient
        "ORDER_REJECTED": 0.8,  # Broker veto
        "TIMEOUT": 0.5,  # Usually transient
        "UNKNOWN": 0.4,  # Low confidence
    }

    def __init__(self, storage_manager: Any):
        """
        Args:
            storage_manager: StorageManager for persistence and feedback history
        """
        self.storage = storage_manager
        self.logger = logging.getLogger(self.__class__.__name__)
        self._patterns_cache: Dict[str, FailurePattern] = {}
        self._last_pattern_update: Optional[datetime] = None

    async def compute_penalty(
        self,
        symbol: str,
        timeframe: str,
        market_context: Dict[str, Any],
    ) -> float:
        """
        Compute failure penalty for a signal in current context.

        Penalty calculation:
          - No pattern match: penalty = 0.0
          - Pattern match found: penalty = 0.0-0.3 based on failure_rate × severity

        Args:
            symbol: Asset symbol (e.g., "EURUSD")
            timeframe: Timeframe (e.g., "M5")
            market_context: Dict with session, regime, volatility, etc.

        Returns:
            Penalty as float ratio (0.0-0.3)
        """
        try:
            # Step 1: Ensure patterns are fresh
            await self._ensure_patterns_fresh()

            # Step 2: Look for matching patterns
            session = market_context.get("session", None)
            regime = market_context.get("regime", None)

            matching_patterns = self._find_matching_patterns(
                symbol, timeframe, session, regime
            )

            if not matching_patterns:
                return 0.0  # No penalty if no failure pattern

            # Step 3: Aggregate penalty from all matching patterns
            total_penalty = sum(p.penalty for p in matching_patterns)

            # Step 4: Clamp to max
            penalty = min(total_penalty, self.MAX_PENALTY)

            if penalty > 0.0:
                self.logger.info(
                    f"[FAILURE_PATTERN] {symbol} {timeframe}: "
                    f"Penalty={penalty:.3f} from {len(matching_patterns)} pattern(s) "
                    f"(session={session}, regime={regime})"
                )

            return penalty

        except Exception as e:
            self.logger.error(f"Error computing failure penalty: {e}")
            return 0.0  # Safe default on error

    def _find_matching_patterns(
        self,
        symbol: str,
        timeframe: str,
        session: Optional[str],
        regime: Optional[str],
    ) -> List[FailurePattern]:
        """
        Find patterns that match current context.

        Matching rules:
          - Symbol must match
          - Timeframe matches if pattern.timeframe is not None
          - Session matches if pattern.session is not None
          - Confidence >= 0.5
        """
        matching = []

        for pattern in self._patterns_cache.values():
            # Check symbol
            if pattern.symbol != symbol:
                continue

            # Check timeframe (if pattern specifies one)
            if pattern.timeframe and pattern.timeframe != timeframe:
                continue

            # Check session (if pattern specifies one)
            if pattern.session and pattern.session != session:
                continue

            # Check confidence threshold
            if pattern.confidence < 0.5:
                continue

            matching.append(pattern)

        return matching

    async def _ensure_patterns_fresh(self, force: bool = False) -> None:
        """
        Ensure failure patterns are up-to-date.

        Updates patterns if:
          - Cache is empty
          - Last update was > PATTERN_UPDATE_INTERVAL_HOURS ago
          - force=True
        """
        now = datetime.now(timezone.utc)

        # Check if update needed
        update_needed = (
            force
            or not self._patterns_cache
            or (
                self._last_pattern_update
                and (
                    now - self._last_pattern_update
                ).total_seconds() > self.PATTERN_UPDATE_INTERVAL_HOURS * 3600
            )
        )

        if not update_needed:
            return

        # Step 1: Load patterns from DB
        try:
            patterns_json = await self.storage.get_config_value(
                "ml_patterns.failure_registry"
            )
            if patterns_json:
                patterns_dict = json.loads(patterns_json)
                self._patterns_cache = {
                    key: FailurePattern(**data)
                    for key, data in patterns_dict.items()
                }
        except Exception as e:
            self.logger.warning(f"Failed to load patterns from DB: {e}")

        # Step 2: Re-analyze failure history (async, non-blocking)
        self.logger.info("[FAILURE_PATTERN] Starting pattern analysis...")
        await self._analyze_failure_correlations()

        self._last_pattern_update = now

    async def _analyze_failure_correlations(self) -> None:
        """
        Analyze execution_feedback history and extract failure patterns.

        For each (symbol, [timeframe], [session]) combination:
          - Count failures
          - Calculate failure_rate
          - Identify dominant failure_reason
          - Compute penalty based on severity + rate
          - Save to patterns cache
        """
        try:
            # Query failure history (last 7 days)
            failure_records = await self.storage.query(
                """
                SELECT symbol, timeframe, session, failure_reason, COUNT(*) as count
                FROM sys_execution_feedback
                WHERE created_at > datetime('now', '-7 days')
                GROUP BY symbol, timeframe, session, failure_reason
                ORDER BY count DESC
                """
            )

            if not failure_records:
                self.logger.info("[FAILURE_PATTERN] No failure records found")
                return

            # Process records into patterns
            new_patterns: Dict[str, FailurePattern] = {}

            # Group by (symbol, timeframe, session)
            pattern_groups: Dict[Tuple, List] = {}
            for record in failure_records:
                symbol, timeframe, session, reason, count = record
                key = (symbol, timeframe, session)
                if key not in pattern_groups:
                    pattern_groups[key] = []
                pattern_groups[key].append((reason, count))

            # Create patterns for significant failure groups
            for (symbol, timeframe, session), failures in pattern_groups.items():
                # Only consider patterns with >= min occurrences
                total_count = sum(count for _, count in failures)
                if total_count < self.MIN_PATTERN_OCCURRENCES:
                    continue

                # Get dominant failure reason
                dominant_reason = max(failures, key=lambda x: x[1])[0]
                dominant_count = sum(
                    count for reason, count in failures if reason == dominant_reason
                )

                # Calculate failure rate and penalty
                failure_rate = dominant_count / total_count
                severity = self.FAILURE_SEVERITY.get(dominant_reason, 0.5)
                penalty = failure_rate * severity * self.MAX_PENALTY

                # Create pattern key
                pattern_key = f"{symbol}_{timeframe or 'ANY'}_{session or 'ANY'}"

                # Create pattern object
                pattern = FailurePattern(
                    key=pattern_key,
                    symbol=symbol,
                    timeframe=timeframe,
                    session=session,
                    failure_reason=dominant_reason,
                    occurrence_count=dominant_count,
                    failure_rate=failure_rate,
                    penalty=penalty,
                    last_updated=datetime.now(timezone.utc).isoformat(),
                    confidence=min(dominant_count / 10.0, 1.0),  # Confidence grows with count
                )

                new_patterns[pattern_key] = pattern

                self.logger.debug(
                    f"[FAILURE_PATTERN] Pattern: {pattern_key} "
                    f"(reason={dominant_reason}, rate={failure_rate:.2%}, penalty={penalty:.3f})"
                )

            # Update cache
            self._patterns_cache.update(new_patterns)

            # Persist patterns to DB
            await self._persist_patterns(new_patterns)

            self.logger.info(
                f"[FAILURE_PATTERN] Analysis complete: {len(new_patterns)} patterns found"
            )

        except Exception as e:
            self.logger.error(f"Error analyzing failure correlations: {e}")

    async def _persist_patterns(self, patterns: Dict[str, FailurePattern]) -> None:
        """
        Persist failure patterns to sys_config table.

        Storage key: "ml_patterns.failure_registry"
        Value: JSON dict of patterns
        """
        try:
            patterns_json = json.dumps(
                {
                    key: {
                        "key": p.key,
                        "symbol": p.symbol,
                        "timeframe": p.timeframe,
                        "session": p.session,
                        "failure_reason": p.failure_reason,
                        "occurrence_count": p.occurrence_count,
                        "failure_rate": p.failure_rate,
                        "penalty": p.penalty,
                        "last_updated": p.last_updated,
                        "confidence": p.confidence,
                    }
                    for key, p in patterns.items()
                }
            )

            # Use update_sys_config (StorageManager provides this)
            self.storage.update_sys_config({"ml_patterns.failure_registry": patterns_json})

            self.logger.info(
                f"[FAILURE_PATTERN] Persisted {len(patterns)} patterns to DB"
            )

        except Exception as e:
            self.logger.warning(f"Failed to persist patterns: {e}")


async def trigger_pattern_analysis(registry: FailurePatternRegistry) -> None:
    """
    Trigger pattern analysis (callable periodically by scheduler).

    Can be called every N hours or after every trade.
    """
    await registry._ensure_patterns_fresh(force=True)
    logger.info("[FAILURE_PATTERN] Manual analysis triggered and completed")
