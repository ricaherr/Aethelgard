"""
close_only_guard.py — Close-Only Mode Guard

Controls whether the system is in "close-only" mode:
  - can_open_position() → False  (new entries are blocked)
  - can_close_position() → True  (existing positions can always be closed)

Activated by ResilienceManager on LOCKDOWN (L3/STRESSED) to protect open
positions while preventing new exposure during a crisis.

Extracted from PositionManager to comply with the 30KB file-size rule.

Trace_ID: ARCH-CLOSE-ONLY-GUARD-V1
Source of truth: docs/10_INFRA_RESILIENCY.md — ETI EDGE_Lockdown_Degradation
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class CloseOnlyGuard:
    """
    Thread-safe guard that enforces close-only mode.

    Usage::

        guard = CloseOnlyGuard(auto_revert_check_fn=my_market_is_normal)
        guard.activate()

        if not guard.can_open_position():
            reject_new_entry()

        # Later, if condition normalised:
        guard.check_auto_revert()   # deactivates if callback returns True

    Args:
        auto_revert_check_fn: Optional callable that returns True when the
            market/system condition that triggered close-only has normalised.
            Defaults to a no-op that always returns False.
        revert_poll_seconds: Minimum seconds between revert checks (informational,
            enforced by the caller via try_auto_revert loop cadence).
    """

    def __init__(
        self,
        auto_revert_check_fn: Optional[Callable[[], bool]] = None,
        revert_poll_seconds: float = 60.0,
    ) -> None:
        self._active: bool = False
        self._activated_at: float = 0.0
        self._lock = threading.Lock()
        self._auto_revert_check_fn: Callable[[], bool] = (
            auto_revert_check_fn or (lambda: False)
        )
        self.revert_poll_seconds: float = revert_poll_seconds

    # ── Public interface ──────────────────────────────────────────────────────

    @property
    def is_active(self) -> bool:
        """True while close-only mode is enforced."""
        return self._active

    def activate(self) -> None:
        """
        Enable close-only mode.

        Idempotent: calling when already active is a no-op (no duplicate log).
        Thread-safe.
        """
        with self._lock:
            if self._active:
                return
            self._active = True
            self._activated_at = time.monotonic()
        logger.warning(
            "[CloseOnlyGuard] CLOSE-ONLY MODE ACTIVADO — "
            "nuevas entradas bloqueadas, cierres permitidos."
        )

    def deactivate(self) -> None:
        """
        Disable close-only mode and restore normal operation.

        Idempotent: calling when already inactive is a no-op.
        Thread-safe.
        """
        with self._lock:
            if not self._active:
                return
            self._active = False
        logger.info(
            "[CloseOnlyGuard] Close-only mode desactivado — sistema normalizado."
        )

    def can_open_position(self) -> bool:
        """Return True only when close-only mode is NOT active."""
        return not self._active

    def can_close_position(self) -> bool:
        """Always True — closing positions is never blocked."""
        return True

    def check_auto_revert(self) -> bool:
        """
        Invoke the injected revert-check callback.

        If the callback returns True (condition normalised), close-only mode
        is deactivated automatically.

        Returns:
            True if reversion occurred, False otherwise.

        Note:
            Exceptions raised by the callback are caught and logged at WARNING
            level; the guard remains active in that case.
        """
        if not self._active:
            return False
        try:
            condition_normalised = bool(self._auto_revert_check_fn())
        except Exception as exc:
            logger.warning(
                "[CloseOnlyGuard] auto_revert_check raised an exception: %s — "
                "close-only mode remains active.",
                exc,
            )
            return False
        if condition_normalised:
            self.deactivate()
            return True
        return False
