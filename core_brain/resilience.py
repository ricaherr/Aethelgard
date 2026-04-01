"""
resilience.py — Canonical contracts for Aethelgard's Granular Resilience System.

This module defines ONLY types, enums, and interfaces (no business logic).
Concrete services (IntegrityGuard, AnomalySentinel, CoherenceService) must
implement ResilienceInterface to participate in the L0–L3 evaluation protocol.

Containment hierarchy:
  L0 (ASSET)    → Health of a single instrument (e.g. "XAUUSD").
  L1 (STRATEGY) → Health of a specific strategy (e.g. "STRAT_01").
  L2 (SERVICE)  → Health of a core_brain service (e.g. "AnomalySentinel").
  L3 (GLOBAL)   → Systemic posture of the entire engine.

Source of truth for this spec: docs/10_INFRA_RESILIENCY.md §E14
Trace_ID: ARCH-RESILIENCE-ENGINE-V1-A
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import uuid


# ---------------------------------------------------------------------------
# Canonical Enums
# ---------------------------------------------------------------------------

class ResilienceLevel(Enum):
    """Containment layer of the failure — from lowest to highest impact."""
    ASSET    = "L0"   # A single instrument
    STRATEGY = "L1"   # A specific strategy
    SERVICE  = "L2"   # An internal component
    GLOBAL   = "L3"   # The entire ecosystem


class EdgeAction(Enum):
    """Autonomous action the ResilienceManager applies to the affected scope."""
    MUTE       = "MUTE"        # L0: Ignore signals from the affected asset
    QUARANTINE = "QUARANTINE"  # L1: Stop the affected strategy
    SELF_HEAL  = "SELF_HEAL"   # L2: Restart socket / flush cache
    LOCKDOWN   = "LOCKDOWN"    # L3: Full system suspension


class SystemPosture(Enum):
    """Global operational posture of the orchestrator."""
    NORMAL   = "NORMAL"    # 100% operational. L0/L1 clean.
    CAUTION  = "CAUTION"   # Local anomaly. Active quarantines. Reduced risk (0.5%).
    DEGRADED = "DEGRADED"  # L2 failure. Position management only. No new entries.
    STRESSED = "STRESSED"  # L3 activated. Orderly shutdown. Manual intervention required.


# ---------------------------------------------------------------------------
# Value Object
# ---------------------------------------------------------------------------

@dataclass
class EdgeEventReport:
    """
    Report emitted by any diagnostic component to the ResilienceManager.

    The component does NOT decide the final action — it only reports severity
    and scope. The ResilienceManager is the sole arbiter of system posture.

    Attributes:
        level     : Containment layer affected (L0–L3).
        scope     : Identifier of the subject (symbol, strategy_id,
                    service_name, or "GLOBAL").
        action    : Recommended corrective action.
        reason    : Human-readable message for audit trail.
        trace_id  : Auto-generated correlation token (EDGE-XXXXXXXX format).
        metadata  : Optional free-form context for the ResilienceManager.
    """
    level:    ResilienceLevel
    scope:    str
    action:   EdgeAction
    reason:   str
    trace_id: str  = field(default_factory=lambda: f"EDGE-{uuid.uuid4().hex[:8].upper()}")
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Abstract Interface
# ---------------------------------------------------------------------------

class ResilienceInterface(ABC):
    """
    Mandatory contract for all diagnostic components
    (IntegrityGuard, AnomalySentinel, CoherenceService, etc.).

    Guarantees that no component unilaterally decides actions — every
    component reports to the ResilienceManager, which holds sole authority
    over SystemPosture transitions and EdgeAction enforcement.
    """

    @abstractmethod
    def check_health(self) -> Optional[EdgeEventReport]:
        """
        Runs the component's self-diagnostic.

        Returns:
            EdgeEventReport describing the problem if one is detected,
            None if the component is fully healthy.
        """
