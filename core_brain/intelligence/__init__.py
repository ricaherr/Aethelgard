"""
core_brain.intelligence — Signal Intelligence Module

Consolidates all signal quality and learning logic.

Components:
  - signal_quality_scorer: Unified signal quality authority (technical + contextual)
  - consensus_engine: Multi-strategy consensus detection and bonus calculation
  - failure_pattern_registry: Autonomous failure correlation learning
"""

from .signal_quality_scorer import SignalQualityScorer, SignalQualityGrade, SignalQualityResult
from .consensus_engine import ConsensusEngine, ConsensusAnalysis
from .failure_pattern_registry import FailurePatternRegistry, FailurePattern

__all__ = [
    "SignalQualityScorer",
    "SignalQualityGrade",
    "SignalQualityResult",
    "ConsensusEngine",
    "ConsensusAnalysis",
    "FailurePatternRegistry",
    "FailurePattern",
]
