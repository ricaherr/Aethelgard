"""
Symbol Coverage Policy - Per-symbol provider exclusion and retry management
HU 10.28: Provider Coverage Reliability
Trace_ID: HU10.28-PROVIDER-COVERAGE-RELIABILITY-2026-04-09

Encapsulates runtime state for provider coverage per symbol:
- Exponential backoff when all fallbacks are exhausted for a symbol
- Temporary exclusion during cooldown period
- Automatic retry on expiry
- Warning throttling to suppress operational noise

Design principles:
- Entirely in-memory: no DB writes to avoid SQLite lock pressure
- Params read from dynamic_params via StorageManager (with safe defaults)
- Single Responsibility: coverage policy lives here, NOT in DataProviderManager
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger: logging.Logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal state per symbol
# ---------------------------------------------------------------------------

@dataclass
class _SymbolState:
    consecutive_failures: int = 0
    exclusion_until_monotonic: float = 0.0
    last_success_utc: Optional[datetime] = None
    last_provider_used: Optional[str] = None
    last_failure_reason: Optional[str] = None
    last_warning_ts: float = 0.0


# ---------------------------------------------------------------------------
# Default policy parameters (overridable via dynamic_params in DB)
# ---------------------------------------------------------------------------

_DEFAULTS: Dict[str, Any] = {
    "provider_symbol_failure_threshold": 3,
    "provider_symbol_exclusion_base_sec": 60.0,
    "provider_symbol_exclusion_multiplier": 2.0,
    "provider_symbol_exclusion_max_sec": 900.0,
    "provider_symbol_warning_throttle_sec": 60.0,
}

_PARAMS_CACHE_TTL_SEC: float = 300.0  # Refresh dynamic_params from DB every 5 min


# ---------------------------------------------------------------------------
# SymbolCoveragePolicy
# ---------------------------------------------------------------------------

class SymbolCoveragePolicy:
    """
    Per-symbol coverage policy: tracks provider failure state and enforces
    temporary exclusion with exponential backoff when all fallbacks are exhausted.

    State is ephemeral (in-memory only). The system re-learns on restart within
    seconds of real traffic — acceptable for a runtime policy.
    """

    def __init__(self, storage: Any) -> None:
        self._storage = storage
        self._symbol_state: Dict[str, _SymbolState] = {}
        self._params_cache: Dict[str, Any] = {}
        self._params_cache_ts: float = 0.0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def is_temporarily_excluded(self, symbol: str) -> bool:
        """Return True if symbol is currently within an active exclusion window."""
        state = self._symbol_state.get(symbol)
        if not state:
            return False
        return time.monotonic() < state.exclusion_until_monotonic

    def register_success(self, symbol: str, provider_name: str) -> None:
        """Reset failure counter and clear exclusion after a successful fetch."""
        state = self._symbol_state.get(symbol)
        if state:
            state.consecutive_failures = 0
            state.exclusion_until_monotonic = 0.0
            state.last_provider_used = provider_name
            state.last_success_utc = datetime.now(tz=timezone.utc)

    def register_failure(self, symbol: str, reason_code: str) -> bool:
        """
        Increment failure count for symbol.

        Returns True if this failure triggered a new exclusion window.
        Exclusion is only activated when consecutive_failures reaches threshold.
        """
        state = self._symbol_state.setdefault(symbol, _SymbolState())
        state.consecutive_failures += 1
        state.last_failure_reason = reason_code

        threshold = int(self._param("provider_symbol_failure_threshold"))
        if state.consecutive_failures >= threshold:
            exclusion_secs = self._compute_exclusion_seconds(state.consecutive_failures)
            state.exclusion_until_monotonic = time.monotonic() + exclusion_secs
            logger.debug(
                "[COVERAGE-POLICY] %s excluded for %.0fs (failures=%d, reason=%s)",
                symbol, exclusion_secs, state.consecutive_failures, reason_code,
            )
            return True
        return False

    def should_emit_warning(self, symbol: str) -> bool:
        """
        Return True if a warning for this symbol is due (throttle check).
        Marks the timestamp on True to suppress subsequent calls within the window.
        """
        state = self._symbol_state.setdefault(symbol, _SymbolState())
        throttle = float(self._param("provider_symbol_warning_throttle_sec"))
        now = time.monotonic()
        if now - state.last_warning_ts >= throttle:
            state.last_warning_ts = now
            return True
        return False

    def get_snapshot(self) -> Dict[str, Any]:
        """Read-only snapshot of current coverage state for observability."""
        now_mono = time.monotonic()
        result: Dict[str, Any] = {}
        for symbol, state in self._symbol_state.items():
            excluded = now_mono < state.exclusion_until_monotonic
            ttl = max(0.0, state.exclusion_until_monotonic - now_mono) if excluded else 0.0
            result[symbol] = {
                "consecutive_failures": state.consecutive_failures,
                "is_excluded": excluded,
                "exclusion_ttl_sec": round(ttl, 1),
                "last_provider": state.last_provider_used,
                "last_failure_reason": state.last_failure_reason,
                "last_success_utc": (
                    state.last_success_utc.isoformat() if state.last_success_utc else None
                ),
            }
        return result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _compute_exclusion_seconds(self, failure_count: int) -> float:
        """Exponential backoff capped at provider_symbol_exclusion_max_sec."""
        base = float(self._param("provider_symbol_exclusion_base_sec"))
        multiplier = float(self._param("provider_symbol_exclusion_multiplier"))
        cap = float(self._param("provider_symbol_exclusion_max_sec"))
        threshold = int(self._param("provider_symbol_failure_threshold"))
        exponent = max(0, failure_count - threshold)
        secs = base * (multiplier ** exponent)
        return min(secs, cap)

    def _param(self, key: str) -> Any:
        """Read policy param from cached dynamic_params with safe default fallback."""
        return self._get_params().get(key, _DEFAULTS[key])

    def _get_params(self) -> Dict[str, Any]:
        """Lazily refresh dynamic_params cache (TTL = 5 min) to avoid DB pressure."""
        now = time.monotonic()
        if now - self._params_cache_ts > _PARAMS_CACHE_TTL_SEC:
            try:
                raw = self._storage.get_dynamic_params()
                self._params_cache = raw if isinstance(raw, dict) else {}
            except Exception as exc:
                logger.debug("[COVERAGE-POLICY] Could not refresh dynamic_params: %s", exc)
                self._params_cache = {}
            self._params_cache_ts = now
        return self._params_cache
