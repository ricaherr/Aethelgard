"""
order_gate.py — Order Execution Gate

Single responsibility: decide whether a signal is permitted to proceed to
execution based on the current close-only mode state.

Rules:
  - Close-only INACTIVE → all signal types pass (other guards may still reject).
  - Close-only ACTIVE   → only SignalType.CLOSE passes; BUY/SELL are rejected.

Extracted from OrderExecutor to comply with the 30KB file-size rule.

Trace_ID: ARCH-ORDER-GATE-V1
Source of truth: docs/10_INFRA_RESILIENCY.md — ETI EDGE_Lockdown_Degradation
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from models.signal import SignalType

if TYPE_CHECKING:
    from core_brain.close_only_guard import CloseOnlyGuard

logger = logging.getLogger(__name__)

# Signal types that represent closing an existing position.
_CLOSE_SIGNAL_TYPES: frozenset[SignalType] = frozenset({SignalType.CLOSE})


class OrderGate:
    """
    Gates signal execution against close-only mode.

    Usage::

        gate = OrderGate(close_only_guard=guard)
        allowed, reason = gate.is_allowed(signal)
        if not allowed:
            reject(signal, reason)

    Args:
        close_only_guard: Injected CloseOnlyGuard instance (DI).
    """

    def __init__(self, close_only_guard: "CloseOnlyGuard") -> None:
        self._guard = close_only_guard

    def is_allowed(self, signal: object) -> tuple[bool, str]:
        """
        Determine if the signal is allowed through the gate.

        Args:
            signal: Any object with a `signal_type` attribute of type SignalType
                    and a `symbol` attribute (str).

        Returns:
            (allowed, reason) — reason is empty string when allowed.
        """
        if not self._guard.is_active:
            return True, ""

        signal_type: SignalType = getattr(signal, "signal_type", None)
        if signal_type in _CLOSE_SIGNAL_TYPES:
            logger.debug(
                "[OrderGate] CLOSE signal permitida en close-only mode: %s",
                getattr(signal, "symbol", "?"),
            )
            return True, ""

        type_label = signal_type.value if signal_type else "UNKNOWN"
        symbol = getattr(signal, "symbol", "?")
        reason = (
            f"Close-only mode activo — señal {type_label} bloqueada para {symbol}. "
            "Solo se permiten cierres de posición."
        )
        logger.warning("[OrderGate] %s", reason)
        return False, reason
