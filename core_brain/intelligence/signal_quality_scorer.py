"""
signal_quality_scorer.py — Unified Signal Quality Scoring (PHASE 4)

Responsibility:
  - Final authority on signal quality before execution
  - Consolidates technical score (60%: Confluence + Trifecta) + contextual score (40%: Consensus + Historial)
  - Emits SignalQualityGrade (A+, A, B, C, F)
  - Only A+ and A proceed to automatic execution

Architecture:
  - Consumes: OutputSignal from SignalFactory (already with Confluence/Trifecta scores)
  - Enriches: ConsensusEngine (density of signals in time window)
  - Consults: FailurePatternRegistry (learned failure correlations)
  - Returns: SignalQualityGrade + metadata

Rule:
  - NO broker/connector imports (agnostic rule #4)
  - ALL persistence via StorageManager (SSOT rule #15)
  - Dependency injection: storage, consensus_engine, failure_registry from MainOrchestrator
  - <30KB file limit (mass rule #4)
  - 100% type hints (quality rule #5)
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from enum import Enum

logger = logging.getLogger(__name__)


class SignalQualityGrade(Enum):
    """Signal quality grades. Only A+ and A execute automatically."""
    A_PLUS = "A+"    # Score >= 85: Exceptional confidence
    A = "A"          # Score >= 75: High confidence
    B = "B"          # Score >= 65: Moderate confidence (manual review)
    C = "C"          # Score >= 50: Low confidence (reject)
    F = "F"          # Score < 50: Fail (reject)


@dataclass
class SignalQualityResult:
    """Result of quality assessment."""
    signal_id: str
    symbol: str
    timeframe: str
    grade: SignalQualityGrade
    overall_score: float  # 0-100
    technical_score: float  # 60% weight
    contextual_score: float  # 40% weight
    consensus_bonus: float  # Added if multiple strategies align
    failure_penalty: float  # Subtracted if failure pattern detected
    trace_id: str
    metadata: Dict[str, Any]  # Rich context for debugging


class SignalQualityScorer:
    """
    Unified signal quality authority.
    
    Phase 4 Implementation:
      - Consolidates Confluence (multi-timeframe) + Trifecta (Oliver Velez) scores
      - Adds Consensus bonus if dense signal cluster detected
      - Subtracts Failure penalty if historical pattern correlation found
      - Emits final grade (A+/A/B/C/F) before execution
    """

    def __init__(
        self,
        storage_manager: Any,
        consensus_engine: Optional[Any] = None,
        failure_pattern_registry: Optional[Any] = None,
    ):
        """
        Args:
            storage_manager: StorageManager for persistence
            consensus_engine: ConsensusEngine for signal density analysis (optional)
            failure_pattern_registry: FailurePatternRegistry for learned patterns (optional)
        """
        self.storage = storage_manager
        self.consensus_engine = consensus_engine
        self.failure_pattern_registry = failure_pattern_registry
        self.logger = logging.getLogger(self.__class__.__name__)

    async def assess_signal_quality(
        self,
        signal: Dict[str, Any],
        recent_signals: Optional[List[Dict[str, Any]]] = None,
        market_context: Optional[Dict[str, Any]] = None,
    ) -> SignalQualityResult:
        """
        Main entry point: assess and grade signal quality.

        Args:
            signal: Output signal from SignalFactory (already has Confluence/Trifecta scores)
            recent_signals: Recent signals in time window (for consensus density analysis)
            market_context: Market context (volatility, regime, session, etc.)

        Returns:
            SignalQualityResult with grade and metadata
        """
        trace_id = f"QUALITY-{datetime.now(timezone.utc).isoformat()}"
        signal_id = signal.get("signal_id", "UNKNOWN")
        symbol = signal.get("symbol", "UNKNOWN")
        timeframe = signal.get("timeframe", "M5")

        try:
            # Step 1: Extract technical score (60% of final score)
            # Already computed by Confluence + Trifecta in SignalFactory
            technical_score = self._extract_technical_score(signal)

            # Step 2: Compute consensus bonus (part of contextual score)
            consensus_bonus = 0.0
            if self.consensus_engine and recent_signals:
                consensus_bonus = await self.consensus_engine.compute_bonus(
                    signal, recent_signals
                )

            # Step 3: Compute failure penalty (part of contextual score)
            failure_penalty = 0.0
            if self.failure_pattern_registry:
                failure_penalty = await self.failure_pattern_registry.compute_penalty(
                    symbol, timeframe, market_context or {}
                )

            # Step 4: Compute contextual score (40% of final score)
            # Contextual = (consensus_bonus - failure_penalty) normalized to 0-100
            contextual_score = self._compute_contextual_score(
                consensus_bonus, failure_penalty
            )

            # Step 5: Compute overall score (60% technical + 40% contextual)
            overall_score = (technical_score * 0.60) + (contextual_score * 0.40)

            # Step 6: Assign grade
            grade = self._assign_grade(overall_score)

            # Step 7: Log assessment
            self.logger.info(
                f"[QUALITY] {symbol} {timeframe}: "
                f"Technical={technical_score:.1f}% "
                f"Contextual={contextual_score:.1f}% "
                f"→ Overall={overall_score:.1f}% Grade={grade.value} | {trace_id}"
            )

            # Step 8: Construct result
            result = SignalQualityResult(
                signal_id=signal_id,
                symbol=symbol,
                timeframe=timeframe,
                grade=grade,
                overall_score=overall_score,
                technical_score=technical_score,
                contextual_score=contextual_score,
                consensus_bonus=consensus_bonus,
                failure_penalty=failure_penalty,
                trace_id=trace_id,
                metadata={
                    "source_signal_id": signal.get("id"),
                    "strategy": signal.get("metadata", {}).get("strategy_id"),
                    "confidence_original": signal.get("confidence"),
                    "score_confluence": signal.get("metadata", {}).get("confluence_bonus"),
                    "score_trifecta": signal.get("metadata", {}).get("trifecta_score"),
                },
            )

            # Step 9: Persist assessment if critical
            if grade in [SignalQualityGrade.A_PLUS, SignalQualityGrade.A]:
                await self._persist_assessment(result)

            return result

        except Exception as e:
            self.logger.error(f"Error assessing signal quality {signal_id}: {e}")
            # Return safe default (F grade, do not execute)
            return SignalQualityResult(
                signal_id=signal_id,
                symbol=symbol,
                timeframe=timeframe,
                grade=SignalQualityGrade.F,
                overall_score=0.0,
                technical_score=0.0,
                contextual_score=0.0,
                consensus_bonus=0.0,
                failure_penalty=100.0,  # Max penalty on error
                trace_id=trace_id,
                metadata={"error": str(e)},
            )

    def _extract_technical_score(self, signal: Dict[str, Any]) -> float:
        """
        Extract technical score from signal.

        Technical score comes from:
          - Confluence analyzer (multi-timeframe alignment)
          - Trifecta optimizer (Oliver Velez M2-M5-M15 alignment)
          - Original signal confidence

        Returns:
            Score 0-100
        """
        metadata = signal.get("metadata", {})

        # Trifecta score (if strategy is oliver, weight 60%)
        trifecta_score = metadata.get("trifecta_score", 0.0) * 100 if "trifecta_score" in metadata else 0.0

        # Confluence bonus (if multi-timeframe analysis applied, weight 40%)
        confluence_bonus = metadata.get("confluence_bonus", 0.0)
        confluence_score = (signal.get("confidence", 0.5) * 100) * (1 + confluence_bonus)

        # Original signal confidence (fallback, weight 50%)
        original_confidence = signal.get("confidence", 0.5) * 100

        # Weighted combination
        if trifecta_score > 0 and confluence_score > 0:
            # Both present: 60% trifecta + 40% confluence
            technical_score = (trifecta_score * 0.60) + (confluence_score * 0.40)
        elif trifecta_score > 0:
            # Only trifecta: use it
            technical_score = trifecta_score
        elif confluence_score > 0:
            # Only confluence: use it
            technical_score = confluence_score
        else:
            # Fall back to original confidence
            technical_score = original_confidence

        # Clamp to 0-100
        return min(max(technical_score, 0.0), 100.0)

    def _compute_contextual_score(
        self, consensus_bonus: float, failure_penalty: float
    ) -> float:
        """
        Compute contextual score (40% of final score).

        Contextual factors:
          - Consensus bonus: +0-20% if multiple strategies align
          - Failure penalty: -0-30% if historical failure pattern detected

        Returns:
            Score 0-100
        """
        # Start from baseline (neutral context = 50%)
        contextual = 50.0

        # Add consensus bonus (max +20%)
        contextual += min(consensus_bonus * 100, 20.0)

        # Subtract failure penalty (max -30%)
        contextual -= min(failure_penalty * 100, 30.0)

        # Clamp to 0-100
        return min(max(contextual, 0.0), 100.0)

    def _assign_grade(self, overall_score: float) -> SignalQualityGrade:
        """Assign letter grade based on overall score."""
        if overall_score >= 85:
            return SignalQualityGrade.A_PLUS
        elif overall_score >= 75:
            return SignalQualityGrade.A
        elif overall_score >= 65:
            return SignalQualityGrade.B
        elif overall_score >= 50:
            return SignalQualityGrade.C
        else:
            return SignalQualityGrade.F

    async def _persist_assessment(self, result: SignalQualityResult) -> None:
        """
        Persist high-quality assessments for audit and learning.

        Only persists A+ and A grades (execution-ready signals).
        """
        try:
            await self.storage.execute(
                """
                INSERT OR REPLACE INTO sys_signal_quality_assessments 
                (signal_id, symbol, timeframe, grade, overall_score, technical_score, 
                 contextual_score, consensus_bonus, failure_penalty, trace_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.signal_id,
                    result.symbol,
                    result.timeframe,
                    result.grade.value,
                    result.overall_score,
                    result.technical_score,
                    result.contextual_score,
                    result.consensus_bonus,
                    result.failure_penalty,
                    result.trace_id,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except Exception as e:
            self.logger.warning(f"Failed to persist quality assessment: {e}")


# Entry point for scheduler (if needed)
async def assess_signal_quality_batch(
    scorer: SignalQualityScorer, signals: List[Dict[str, Any]]
) -> Dict[str, SignalQualityResult]:
    """
    Batch assess multiple signals.

    Returns:
        Dict mapping signal_id → SignalQualityResult
    """
    results = {}
    for signal in signals:
        result = await scorer.assess_signal_quality(signal)
        results[signal.get("signal_id", "UNKNOWN")] = result
    return results
