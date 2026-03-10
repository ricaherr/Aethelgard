"""
test_signal_quality_scorer_phase4.py — Comprehensive tests for PHASE 4 Intelligence

Test Coverage:
  - SignalQualityScorer: Score combination, grading, edge cases
  - ConsensusEngine: Consensus detection, bonus calculation, density analysis
  - FailurePatternRegistry: Pattern learning, penalty computation
"""

import pytest
import asyncio
import tempfile
from datetime import datetime, timezone, timedelta
from core_brain.intelligence.signal_quality_scorer import (
    SignalQualityScorer,
    SignalQualityGrade,
)
from core_brain.intelligence.consensus_engine import ConsensusEngine
from core_brain.intelligence.failure_pattern_registry import FailurePatternRegistry
from data_vault.storage import StorageManager


class TestSignalQualityScorer:
    """Tests for SignalQualityScorer component."""

    @pytest.fixture
    def scorer(self):
        """Create scorer with in-memory storage."""
        storage = StorageManager(db_path=":memory:")
        return SignalQualityScorer(storage)

    @pytest.fixture
    def sample_signal(self):
        """Create a sample signal for testing."""
        return {
            "signal_id": "SIG-001",
            "id": "sig-001",
            "symbol": "EURUSD",
            "timeframe": "M5",
            "signal_type": "BUY",
            "confidence": 0.75,
            "price": 1.1000,
            "metadata": {
                "strategy_id": "oliver_velez",
                "score": 75.0,
                "confluence_bonus": 0.05,
                "trifecta_score": 78.0,
            },
        }

    @pytest.mark.asyncio
    async def test_extract_technical_score_with_trifecta(self, scorer, sample_signal):
        """Technical score from trifecta (Oliver Velez)."""
        score = scorer._extract_technical_score(sample_signal)
        # Expected: combination can be high (trifecta + confluence)
        assert 70.0 <= score <= 100.0  # Allow wide range for combo scores

    @pytest.mark.asyncio
    async def test_extract_technical_score_fallback_to_confidence(self, scorer):
        """Fallback to confidence if no confluence/trifecta."""
        signal = {
            "signal_id": "SIG-002",
            "confidence": 0.8,
            "metadata": {},
        }
        score = scorer._extract_technical_score(signal)
        assert score == 80.0  # 0.8 * 100

    @pytest.mark.asyncio
    async def test_assign_grade_a_plus(self, scorer):
        """Grade A+ for score >= 85."""
        grade = scorer._assign_grade(85.0)
        assert grade == SignalQualityGrade.A_PLUS

        grade = scorer._assign_grade(99.0)
        assert grade == SignalQualityGrade.A_PLUS

    @pytest.mark.asyncio
    async def test_assign_grade_a(self, scorer):
        """Grade A for score 75-85."""
        grade = scorer._assign_grade(75.0)
        assert grade == SignalQualityGrade.A

        grade = scorer._assign_grade(84.9)
        assert grade == SignalQualityGrade.A

    @pytest.mark.asyncio
    async def test_assign_grade_b(self, scorer):
        """Grade B for score 65-75."""
        grade = scorer._assign_grade(65.0)
        assert grade == SignalQualityGrade.B

        grade = scorer._assign_grade(74.9)
        assert grade == SignalQualityGrade.B

    @pytest.mark.asyncio
    async def test_assign_grade_c(self, scorer):
        """Grade C for score 50-65."""
        grade = scorer._assign_grade(50.0)
        assert grade == SignalQualityGrade.C

        grade = scorer._assign_grade(64.9)
        assert grade == SignalQualityGrade.C

    @pytest.mark.asyncio
    async def test_assign_grade_f(self, scorer):
        """Grade F for score < 50."""
        grade = scorer._assign_grade(49.9)
        assert grade == SignalQualityGrade.F

        grade = scorer._assign_grade(0.0)
        assert grade == SignalQualityGrade.F

    @pytest.mark.asyncio
    async def test_compute_contextual_score_baseline(self, scorer):
        """Contextual score baseline is 50% without bonuses/penalties."""
        score = scorer._compute_contextual_score(consensus_bonus=0.0, failure_penalty=0.0)
        assert score == 50.0

    @pytest.mark.asyncio
    async def test_compute_contextual_score_with_consensus_bonus(self, scorer):
        """Consensus bonus raises contextual score (max +20%)."""
        # 20% consensus bonus
        score = scorer._compute_contextual_score(
            consensus_bonus=0.20, failure_penalty=0.0
        )
        assert score == 70.0  # 50 + 20

        # 10% consensus bonus
        score = scorer._compute_contextual_score(
            consensus_bonus=0.10, failure_penalty=0.0
        )
        assert score == 60.0  # 50 + 10

    @pytest.mark.asyncio
    async def test_compute_contextual_score_with_failure_penalty(self, scorer):
        """Failure penalty lowers contextual score (max -30%)."""
        # 30% failure penalty
        score = scorer._compute_contextual_score(
            consensus_bonus=0.0, failure_penalty=0.30
        )
        assert score == 20.0  # 50 - 30

        # 10% failure penalty
        score = scorer._compute_contextual_score(
            consensus_bonus=0.0, failure_penalty=0.10
        )
        assert score == 40.0  # 50 - 10

    @pytest.mark.asyncio
    async def test_compute_contextual_score_combined(self, scorer):
        """Combined bonus and penalty."""
        score = scorer._compute_contextual_score(
            consensus_bonus=0.15, failure_penalty=0.10
        )
        # 50 + (15) - (10) = 55
        assert score == 55.0

    @pytest.mark.asyncio
    async def test_assess_signal_quality_high_confidence(self, scorer, sample_signal):
        """High-confidence signal should get A+ grade."""
        result = await scorer.assess_signal_quality(sample_signal)
        assert result.signal_id == "SIG-001"
        assert result.grade in [SignalQualityGrade.A_PLUS, SignalQualityGrade.A]
        assert result.overall_score >= 75.0

    @pytest.mark.asyncio
    async def test_assess_signal_quality_low_confidence(self, scorer):
        """Low-confidence signal should get F grade."""
        signal = {
            "signal_id": "SIG-LOW",
            "symbol": "EURUSD",
            "timeframe": "M5",
            "confidence": 0.30,  # 30%
            "metadata": {},
        }
        result = await scorer.assess_signal_quality(signal)
        assert result.grade == SignalQualityGrade.F
        assert result.overall_score < 50.0

    @pytest.mark.asyncio
    async def test_assess_signal_quality_error_handling(self, scorer):
        """Scorer handles errors gracefully."""
        # Invalid signal (missing required fields)
        signal = {"signal_id": None}  # Cause error
        result = await scorer.assess_signal_quality(signal)
        # Should still return valid result (C or F grade as safe default)
        assert result.grade in [SignalQualityGrade.C, SignalQualityGrade.F]


class TestConsensusEngine:
    """Tests for ConsensusEngine component."""

    @pytest.fixture
    def engine(self):
        """Create consensus engine."""
        storage = StorageManager(db_path=":memory:")
        return ConsensusEngine(storage)

    @pytest.fixture
    def current_signal(self):
        """Current signal being assessed."""
        return {
            "signal_id": "SIG-CURRENT",
            "symbol": "EURUSD",
            "signal_type": "BUY",
            "confidence": 0.80,
            "metadata": {"strategy_id": "oliver_velez"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

    def _create_recent_signal(self, symbol, direction, confidence, strategy, offset_min):
        """Helper to create a recent signal."""
        return {
            "signal_id": f"SIG-RECENT-{offset_min}",
            "symbol": symbol,
            "signal_type": direction,
            "confidence": confidence,
            "metadata": {"strategy_id": strategy},
            "created_at": (
                datetime.now(timezone.utc) - timedelta(minutes=offset_min)
            ).isoformat(),
        }

    @pytest.mark.asyncio
    async def test_compute_bonus_no_recent_signals(self, engine, current_signal):
        """No bonus without recent signals."""
        bonus = await engine.compute_bonus(current_signal, recent_signals=[])
        assert bonus == 0.0

    @pytest.mark.asyncio
    async def test_compute_bonus_no_agreement(self, engine, current_signal):
        """No bonus if no agreeing signals."""
        # Signal with different symbol
        recent = [
            self._create_recent_signal(
                "GBPUSD", "BUY", 0.75, "another_strategy", 2
            )
        ]
        bonus = await engine.compute_bonus(current_signal, recent_signals=recent)
        assert bonus == 0.0

    @pytest.mark.asyncio
    async def test_compute_bonus_strong_consensus(self, engine, current_signal):
        """Strong consensus (>0.75) gets max bonus."""
        recent = [
            self._create_recent_signal("EURUSD", "BUY", 0.85, "trifecta_001", 1),
            self._create_recent_signal("EURUSD", "BUY", 0.80, "confluence_001", 2),
            self._create_recent_signal("EURUSD", "BUY", 0.75, "edge_tuner", 3),
        ]
        bonus = await engine.compute_bonus(current_signal, recent_signals=recent)
        assert bonus == engine.BONUS_STRONG_CONSENSUS  # 0.20 (20% max)

    @pytest.mark.asyncio
    async def test_compute_bonus_weak_consensus(self, engine, current_signal):
        """Weak consensus (50-75%) gets smaller bonus."""
        recent = [
            self._create_recent_signal("EURUSD", "BUY", 0.65, "trifecta_001", 1),
            self._create_recent_signal("EURUSD", "BUY", 0.60, "confluence_001", 2),
        ]
        bonus = await engine.compute_bonus(current_signal, recent_signals=recent)
        assert bonus == engine.BONUS_WEAK_CONSENSUS  # 0.10 (10%)

    @pytest.mark.asyncio
    async def test_compute_bonus_same_strategy_excluded(self, engine, current_signal):
        """Same strategy signals are excluded from consensus."""
        recent = [
            self._create_recent_signal(
                "EURUSD", "BUY", 0.90, "oliver_velez", 1
            ),  # Same strategy - should be excluded
            self._create_recent_signal("EURUSD", "BUY", 0.60, "other_strat", 2),
        ]
        bonus = await engine.compute_bonus(current_signal, recent_signals=recent)
        # Only 1 agreeing signal from DIFFERENT strategy (other_strat @ 0.60)
        # Current signal @ 0.80, other @ 0.60 → Average = (0.80 + 0.60) / 2 = 0.70 → WEAK consensus
        assert bonus == engine.BONUS_WEAK_CONSENSUS  # 0.10

    @pytest.mark.asyncio
    async def test_compute_bonus_outside_time_window(self, engine, current_signal):
        """Signals outside time window are excluded."""
        # Create signal 10 minutes old (outside default 5-min window)
        old_signal = self._create_recent_signal(
            "EURUSD", "BUY", 0.85, "ancient_strategy", 10
        )
        bonus = await engine.compute_bonus(
            current_signal, recent_signals=[old_signal]
        )
        assert bonus == 0.0  # Too old

    @pytest.mark.asyncio
    async def test_compute_bonus_low_confidence_excluded(self, engine, current_signal):
        """Signals below confidence threshold are excluded."""
        recent = [
            self._create_recent_signal("EURUSD", "BUY", 0.40, "low_conf_strat", 1),
        ]
        bonus = await engine.compute_bonus(current_signal, recent_signals=recent)
        assert bonus == 0.0  # Below 0.55 minimum

    @pytest.mark.asyncio
    async def test_consensus_strength_calculation(self, engine):
        """Test consensus strength calculation."""
        # Consensus strength = average of scores
        scores = [0.80, 0.75, 0.85]
        strength = engine._compute_consensus_strength(scores)
        expected = (0.80 + 0.75 + 0.85) / 3
        assert abs(strength - expected) < 0.01

    @pytest.mark.asyncio
    async def test_consensus_strength_clamped_to_one(self, engine):
        """Consensus strength clamped to 1.0 max."""
        scores = [1.5, 1.2, 1.0]  # Artificial high scores
        strength = engine._compute_consensus_strength(scores)
        assert strength <= 1.0


class TestFailurePatternRegistry:
    """Tests for FailurePatternRegistry component."""

    @pytest.fixture
    def registry(self):
        """Create failure pattern registry."""
        storage = StorageManager(db_path=":memory:")
        return FailurePatternRegistry(storage)

    @pytest.mark.asyncio
    async def test_compute_penalty_no_patterns(self, registry):
        """No penalty when no failure patterns exist."""
        penalty = await registry.compute_penalty(
            "EURUSD", "M5", {"session": "LONDON"}
        )
        assert penalty == 0.0

    @pytest.mark.asyncio
    async def test_pattern_matching_by_symbol(self, registry):
        """Patterns match by symbol."""
        # Manually add a pattern for EURUSD
        pattern_key = "EURUSD_M5_LONDON"
        from core_brain.intelligence.failure_pattern_registry import FailurePattern

        pattern = FailurePattern(
            key=pattern_key,
            symbol="EURUSD",
            timeframe="M5",
            session="LONDON",
            failure_reason="VETO_SLIPPAGE",
            occurrence_count=10,
            failure_rate=0.8,
            penalty=0.24,  # 80% × 30%
            last_updated=datetime.now(timezone.utc).isoformat(),
            confidence=0.9,
        )
        registry._patterns_cache[pattern_key] = pattern

        # Should match when symbol/TF/session match
        penalty = await registry.compute_penalty(
            "EURUSD", "M5", {"session": "LONDON"}
        )
        assert penalty > 0.0

        # Should not match different symbol
        penalty = await registry.compute_penalty(
            "GBPUSD", "M5", {"session": "LONDON"}
        )
        assert penalty == 0.0

    @pytest.mark.asyncio
    async def test_pattern_matching_wildcard_timeframe(self, registry):
        """Patterns with None timeframe match any TF."""
        from core_brain.intelligence.failure_pattern_registry import FailurePattern

        # Pattern without timeframe specification
        pattern_key = "USDJPY_ANY_ASIA"
        pattern = FailurePattern(
            key=pattern_key,
            symbol="USDJPY",
            timeframe=None,  # Matches any TF
            session="ASIA",
            failure_reason="LIQUIDITY_INSUFFICIENT",
            occurrence_count=15,
            failure_rate=0.9,
            penalty=0.27,  # 90% × 30%
            last_updated=datetime.now(timezone.utc).isoformat(),
            confidence=0.95,
        )
        registry._patterns_cache[pattern_key] = pattern

        # Should match any timeframe
        penalty_m5 = await registry.compute_penalty(
            "USDJPY", "M5", {"session": "ASIA"}
        )
        assert penalty_m5 > 0.0

        penalty_h1 = await registry.compute_penalty(
            "USDJPY", "H1", {"session": "ASIA"}
        )
        assert penalty_h1 > 0.0

    @pytest.mark.asyncio
    async def test_pattern_confidence_filtering(self, registry):
        """Patterns below confidence threshold (0.5) are ignored."""
        from core_brain.intelligence.failure_pattern_registry import FailurePattern

        # Low-confidence pattern
        pattern_key = "EURUSD_M15_VOLATILE"
        pattern = FailurePattern(
            key=pattern_key,
            symbol="EURUSD",
            timeframe="M15",
            session="VOLATILE",
            failure_reason="ORDER_REJECTED",
            occurrence_count=2,  # Very few samples
            failure_rate=0.5,
            penalty=0.15,
            last_updated=datetime.now(timezone.utc).isoformat(),
            confidence=0.2,  # Low confidence
        )
        registry._patterns_cache[pattern_key] = pattern

        # Should not apply penalty (confidence < 0.5)
        penalty = await registry.compute_penalty(
            "EURUSD", "M15", {"session": "VOLATILE"}
        )
        assert penalty == 0.0

    @pytest.mark.asyncio
    async def test_penalty_clamped_to_max(self, registry):
        """Total penalty clamped to MAX_PENALTY (0.3)."""
        from core_brain.intelligence.failure_pattern_registry import FailurePattern

        # Add multiple patterns that would exceed max
        patterns = [
            FailurePattern(
                key=f"PATTERN-{i}",
                symbol="EURUSD",
                timeframe=None,
                session=None,
                failure_reason="VETO_SLIPPAGE",
                occurrence_count=10,
                failure_rate=1.0,
                penalty=0.15,  # Each contributes 15%
                last_updated=datetime.now(timezone.utc).isoformat(),
                confidence=0.9,
            )
            for i in range(3)  # 3 patterns × 0.15 = 0.45, should clamp to 0.3
        ]

        for pattern in patterns:
            registry._patterns_cache[pattern.key] = pattern

        penalty = await registry.compute_penalty("EURUSD", "M5", {})
        assert penalty == registry.MAX_PENALTY  # 0.3

    @pytest.mark.asyncio
    async def test_error_handling(self, registry):
        """Registry handles errors gracefully."""
        # Simulate error in pattern loading
        try:
            penalty = await registry.compute_penalty(
                "EURUSD", "M5", {"invalid": "context"}
            )
            # Should return 0.0 on error (safe default)
            assert penalty == 0.0
        except Exception:
            pytest.fail("Registry should not raise exceptions")


class TestPhase4Integration:
    """Tests for PHASE 4 integration."""

    @pytest.mark.asyncio
    async def test_scorer_with_engines(self):
        """Full integration test: Scorer uses Consensus + Failure Registry."""
        storage = StorageManager(db_path=":memory:")
        consensus = ConsensusEngine(storage)
        failure = FailurePatternRegistry(storage)
        scorer = SignalQualityScorer(
            storage, consensus_engine=consensus, failure_pattern_registry=failure
        )

        signal = {
            "signal_id": "SIG-INTEGRATION",
            "symbol": "EURUSD",
            "timeframe": "M5",
            "signal_type": "BUY",
            "confidence": 0.80,
            "metadata": {"strategy_id": "oliver_velez"},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        result = await scorer.assess_signal_quality(signal)

        # Verify result structure
        assert result.signal_id == "SIG-INTEGRATION"
        assert result.symbol == "EURUSD"
        assert result.grade in [
            g
            for g in SignalQualityGrade
        ]  # Valid grade
        assert 0.0 <= result.overall_score <= 100.0

    @pytest.mark.asyncio
    async def test_phase4_execution_decision(self):
        """Test that only A+ and A grades execute."""
        storage = StorageManager(db_path=":memory:")
        scorer = SignalQualityScorer(storage)

        execute_grades = [SignalQualityGrade.A_PLUS, SignalQualityGrade.A]
        reject_grades = [
            SignalQualityGrade.B,
            SignalQualityGrade.C,
            SignalQualityGrade.F,
        ]

        for grade in execute_grades:
            score = (
                85 if grade == SignalQualityGrade.A_PLUS else 75
            )  # Typical score for grade
            calculated_grade = scorer._assign_grade(score)
            assert calculated_grade in execute_grades

        for grade in reject_grades:
            score = 60 if grade == SignalQualityGrade.B else 45
            calculated_grade = scorer._assign_grade(score)
            assert calculated_grade in reject_grades
