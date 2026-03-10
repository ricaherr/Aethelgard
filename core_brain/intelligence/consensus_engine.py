"""
consensus_engine.py — Signal Density & Consensus Bonus Calculation (PHASE 4)

Responsibility:
  - Analyze density of signals in time window (e.g., 5 minutes)
  - Detect when multiple strategies generate same setup (consensus)
  - Compute consensus bonus (+0-20%) to be added to contextual score
  - Differentiate between STRONG consensus (>0.75) and WEAK consensus (0.50-0.75)

Architecture:
  - Consumes: Current signal + recent_signals from time window
  - Returns: Consensus bonus (0.0-0.2) as float ratio
  - Persists: Consensus events for learning (sys_consensus_events table)

Rule:
  - NO broker/connector imports (agnostic rule #4)
  - ALL persistence via StorageManager (SSOT rule #15)
  - <30KB file limit (mass rule #4)
  - 100% type hints (quality rule #5)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ConsensusAnalysis:
    """Result of consensus analysis."""
    signal_id: str
    symbol: str
    direction: str  # BUY or SELL
    consensus_detected: bool
    consensus_strength: float  # 0.0-1.0 (0.75+ is strong)
    participating_strategies: List[str]
    consensus_count: int  # Number of agreeing strategies
    bonus: float  # 0.0-0.2 (20% max)
    trace_id: str
    metadata: Dict[str, Any]


class ConsensusEngine:
    """
    Analyzes signal density and multi-strategy consensus.

    PHASE 4 Implementation:
      - Detects when multiple strategies generate same setup in time window
      - Computes consensus bonus based on agreement count and historical accuracy
      - Differentiates STRONG consensus (>0.75 agreement) from WEAK (0.50-0.75)
    """

    # Configuration
    CONSENSUS_WINDOW_MINUTES = 5  # Look for signals in last N minutes
    STRONG_CONSENSUS_THRESHOLD = 0.75  # score_avg(top strategies) > 75%
    WEAK_CONSENSUS_THRESHOLD = 0.50  # score_avg(top strategies) > 50%
    
    # Bonus tiers
    BONUS_STRONG_CONSENSUS = 0.20  # +20% bonus for A+ consensus
    BONUS_WEAK_CONSENSUS = 0.10  # +10% bonus for B/C consensus

    def __init__(self, storage_manager: Any):
        """
        Args:
            storage_manager: StorageManager for persistence and consensus history
        """
        self.storage = storage_manager
        self.logger = logging.getLogger(self.__class__.__name__)

    async def compute_bonus(
        self,
        current_signal: Dict[str, Any],
        recent_signals: Optional[List[Dict[str, Any]]] = None,
    ) -> float:
        """
        Compute consensus bonus for current signal.

        Bonus calculation:
          - No consensus detected: bonus = 0.0
          - Weak consensus (50-75%): bonus = 0.1
          - Strong consensus (>75%): bonus = 0.2

        Args:
            current_signal: Signal being assessed
            recent_signals: List of recent signals in time window (last 5 min)

        Returns:
            Bonus as float ratio (0.0-0.2)
        """
        if not recent_signals:
            return 0.0  # No consensus without recent signal history

        try:
            # Step 1: Extract current signal properties
            symbol = current_signal.get("symbol", "UNKNOWN")
            direction = current_signal.get("signal_type", "UNKNOWN")  # BUY or SELL
            current_strategy = (
                current_signal.get("metadata", {}).get("strategy_id", "unknown")
            )
            current_score = current_signal.get("confidence", 0.5)

            # Step 2: Find agreeing signals in time window
            agreeing_signals = self._find_agreeing_signals(
                symbol, direction, recent_signals, current_signal
            )

            if not agreeing_signals:
                return 0.0  # No consensus

            # Step 3: Calculate consensus strength
            participating_strategies = [
                sig.get("metadata", {}).get("strategy_id", "unknown")
                for sig in agreeing_signals
            ]
            participating_strategies.append(current_strategy)  # Include current
            participating_strategies = list(set(participating_strategies))  # Deduplicate

            consensus_strength = self._compute_consensus_strength(
                [current_score] + [sig.get("confidence", 0.5) for sig in agreeing_signals]
            )

            # Step 4: Determine bonus tier
            if consensus_strength >= self.STRONG_CONSENSUS_THRESHOLD:
                bonus = self.BONUS_STRONG_CONSENSUS
                consensus_type = "STRONG"
            elif consensus_strength >= self.WEAK_CONSENSUS_THRESHOLD:
                bonus = self.BONUS_WEAK_CONSENSUS
                consensus_type = "WEAK"
            else:
                bonus = 0.0
                consensus_type = "NONE"

            # Step 5: Log and persist
            trace_id = f"CONSENSUS-{datetime.now(timezone.utc).isoformat()}"
            self.logger.info(
                f"[CONSENSUS] {symbol} {direction}: "
                f"{consensus_type} ({consensus_strength:.2f}) "
                f"Strategies={participating_strategies} → Bonus={bonus:.2f} | {trace_id}"
            )

            # Persist event for learning
            await self._persist_consensus_event(
                symbol,
                direction,
                consensus_strength,
                len(participating_strategies),
                bonus,
                trace_id,
                participating_strategies,
            )

            return bonus

        except Exception as e:
            self.logger.error(f"Error computing consensus bonus: {e}")
            return 0.0  # Safe default on error

    def _find_agreeing_signals(
        self,
        symbol: str,
        direction: str,
        recent_signals: List[Dict[str, Any]],
        current_signal: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Find signals in recent_signals that agree with current signal.

        Agreement criteria:
          - Same symbol
          - Same direction (BUY or SELL)
          - Score >= threshold (0.55 minimum)
          - Different strategy (not the same strategy)
          - Within time window (last 5 minutes)
        """
        current_strategy = current_signal.get("metadata", {}).get("strategy_id", "")
        current_time = datetime.now(timezone.utc)
        window_start = current_time - timedelta(minutes=self.CONSENSUS_WINDOW_MINUTES)

        agreeing = []
        for sig in recent_signals:
            # Check symbol and direction match
            if sig.get("symbol") != symbol or sig.get("signal_type") != direction:
                continue

            # Check minimum score
            if sig.get("confidence", 0.0) < 0.55:
                continue

            # Check different strategy
            sig_strategy = sig.get("metadata", {}).get("strategy_id", "")
            if sig_strategy == current_strategy or not sig_strategy:
                continue

            # Check time window
            try:
                sig_time = datetime.fromisoformat(sig.get("created_at", ""))
                if sig_time < window_start:
                    continue
            except (ValueError, TypeError):
                # Invalid timestamp, skip
                continue

            agreeing.append(sig)

        return agreeing

    def _compute_consensus_strength(self, scores: List[float]) -> float:
        """
        Compute consensus strength as average of top N scores.

        Strength = average of all scores (treating each strategy equally)
        Range: 0.0-1.0 (will be used for threshold comparison)
        """
        if not scores:
            return 0.0

        # Average all agreeing scores
        avg_score = sum(scores) / len(scores)

        # Return as 0-1 range
        return min(avg_score, 1.0)

    async def _persist_consensus_event(
        self,
        symbol: str,
        direction: str,
        consensus_strength: float,
        num_strategies: int,
        bonus: float,
        trace_id: str,
        strategies: List[str],
    ) -> None:
        """
        Persist consensus event for audit and learning.

        Creates sys_consensus_events table record.
        """
        try:
            await self.storage.execute(
                """
                INSERT INTO sys_consensus_events 
                (symbol, direction, consensus_strength, num_strategies, bonus, 
                 strategies_json, trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    symbol,
                    direction,
                    consensus_strength,
                    num_strategies,
                    bonus,
                    ",".join(strategies),
                    trace_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception as e:
            self.logger.warning(f"Failed to persist consensus event: {e}")


async def analyze_consensus_effectiveness(
    scorer: ConsensusEngine, window_hours: int = 24
) -> Dict[str, Any]:
    """
    Analyze effectiveness of consensus signals vs single-strategy signals.

    Compares:
      - Win rate of STRONG consensus signals vs WEAK vs NONE
      - Average return per consensus type
      - False positive rate

    Used for learning and tuning consensus thresholds.
    """
    try:
        # Query consensus events from last N hours
        consensus_events = await scorer.storage.query(
            f"""
            SELECT symbol, direction, consensus_strength, bonus, num_strategies
            FROM sys_consensus_events
            WHERE created_at > datetime('now', '-{window_hours} hours')
            ORDER BY created_at DESC
            """
        )

        if not consensus_events:
            return {"error": "No consensus events found", "window_hours": window_hours}

        # Group by consensus type
        strong = [e for e in consensus_events if e[2] >= 0.75]
        weak = [e for e in consensus_events if 0.50 <= e[2] < 0.75]
        none_consensus = [e for e in consensus_events if e[2] < 0.50]

        return {
            "window_hours": window_hours,
            "total_events": len(consensus_events),
            "strong_consensus": {
                "count": len(strong),
                "avg_strength": (
                    sum(e[2] for e in strong) / len(strong) if strong else 0.0
                ),
                "avg_bonus": sum(e[3] for e in strong) / len(strong) if strong else 0.0,
                "avg_strategy_count": (
                    sum(e[4] for e in strong) / len(strong) if strong else 0.0
                ),
            },
            "weak_consensus": {
                "count": len(weak),
                "avg_strength": sum(e[2] for e in weak) / len(weak) if weak else 0.0,
                "avg_bonus": sum(e[3] for e in weak) / len(weak) if weak else 0.0,
                "avg_strategy_count": (
                    sum(e[4] for e in weak) / len(weak) if weak else 0.0
                ),
            },
        }
    except Exception as e:
        logger.error(f"Error analyzing consensus effectiveness: {e}")
        return {"error": str(e)}
