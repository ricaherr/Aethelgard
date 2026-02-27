"""
DrawdownMonitor — HU 4.5: Exposure & Drawdown Monitor (Multi-Tenant)
=====================================================================
Monitors equity drawdown per tenant and enforces hard/soft thresholds.

Responsibility (orthogonal to PositionSizeMonitor):
  - PositionSizeMonitor  → circuit breaker for CALCULATION FAILURES (infra)
  - DrawdownMonitor      → circuit breaker for EQUITY DRAWDOWN (business)

Architecture:
  - Agnostic: no connector imports
  - Per-tenant state stored in memory dict (reset on restart)
    → persistent peak_equity can be added via StorageManager if needed
  - Uses Decimal for all financial calculations (project standard)
  - Emits dict-based alerts for WebSocket integration
"""
import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional

logger = logging.getLogger(__name__)


@dataclass
class DrawdownStatus:
    """
    Result of a drawdown check for a given tenant equity snapshot.

    Attributes:
        tenant_id:        Tenant identifier
        level:            "SAFE" | "SOFT_ALERT" | "HARD_BREACH"
        current_equity:   Current account equity (Decimal)
        peak_equity:      Highest recorded equity for this tenant (Decimal)
        drawdown_pct:     Drawdown as percentage of peak (Decimal, 2dp)
        soft_threshold:   Soft alert threshold in % (Decimal)
        hard_threshold:   Hard breach threshold in % (Decimal)
        should_lockdown:  True only when level == "HARD_BREACH"
    """
    tenant_id: str
    level: str
    current_equity: Decimal
    peak_equity: Decimal
    drawdown_pct: Decimal
    soft_threshold: Decimal
    hard_threshold: Decimal
    should_lockdown: bool


class DrawdownMonitor:
    """
    Equity drawdown supervisor with per-tenant isolation.

    Thresholds (configurable via constructor):
        soft_threshold_pct (default 5.0%): Alert-only, trading NOT blocked
        hard_threshold_pct (default 10.0%): Triggers lockdown

    Usage:
        monitor = DrawdownMonitor(soft_threshold_pct=5.0, hard_threshold_pct=10.0)
        status = monitor.update_equity("tenant_001", peak_equity=10000.0, current_equity=9400.0)
        if status.should_lockdown:
            risk_manager.activate_lockdown()
    """

    def __init__(
        self,
        soft_threshold_pct: float = 5.0,
        hard_threshold_pct: float = 10.0,
    ) -> None:
        """
        Initialize DrawdownMonitor with configurable thresholds.

        Args:
            soft_threshold_pct: % drawdown from peak that triggers SOFT_ALERT (no lockdown)
            hard_threshold_pct: % drawdown from peak that triggers HARD_BREACH (lockdown)
        """
        if soft_threshold_pct >= hard_threshold_pct:
            raise ValueError(
                f"soft_threshold ({soft_threshold_pct}) must be < hard_threshold ({hard_threshold_pct})"
            )

        self._soft = Decimal(str(soft_threshold_pct))
        self._hard = Decimal(str(hard_threshold_pct))

        # Per-tenant state: {tenant_id: {"peak": Decimal}}
        # Using in-memory dict for simplicity; peak survives within process lifetime
        self._tenant_state: Dict[str, Dict] = {}

        logger.info(
            f"[DrawdownMonitor] Initialized: soft={self._soft}%, hard={self._hard}%"
        )

    # ─── Public API ───────────────────────────────────────────────────────────

    def update_equity(
        self,
        tenant_id: str,
        peak_equity: float,
        current_equity: float,
    ) -> DrawdownStatus:
        """
        Evaluate current equity against peak and classify drawdown level.

        Args:
            tenant_id:      Tenant identifier (used for isolation and logging)
            peak_equity:    Highest recorded equity (caller provides; use get_peak() for stored value)
            current_equity: Current account equity snapshot

        Returns:
            DrawdownStatus with level, drawdown_pct, and should_lockdown flag
        """
        d_peak = Decimal(str(peak_equity))
        d_current = Decimal(str(current_equity))

        # Update stored peak for this tenant if current exceeds it
        self._update_peak(tenant_id, d_current)

        drawdown_pct = self._calculate_drawdown_pct(d_peak, d_current)
        level, should_lockdown = self._classify(drawdown_pct)

        status = DrawdownStatus(
            tenant_id=tenant_id,
            level=level,
            current_equity=d_current,
            peak_equity=d_peak,
            drawdown_pct=drawdown_pct,
            soft_threshold=self._soft,
            hard_threshold=self._hard,
            should_lockdown=should_lockdown,
        )

        self._log(status)
        return status

    def get_peak(self, tenant_id: str) -> Optional[Decimal]:
        """
        Returns the stored peak equity for a tenant (None if not seen yet).
        Useful for passing to update_equity() on subsequent calls.
        """
        state = self._tenant_state.get(tenant_id)
        return state["peak"] if state else None

    def reset_peak(self, tenant_id: str) -> None:
        """
        Reset the peak equity for a tenant (e.g., start of new trading session).
        """
        if tenant_id in self._tenant_state:
            del self._tenant_state[tenant_id]
            logger.info(f"[DrawdownMonitor] Peak reset for tenant: {tenant_id}")

    # ─── Private Methods ──────────────────────────────────────────────────────

    def _update_peak(self, tenant_id: str, current_equity: Decimal) -> None:
        """Update stored peak for tenant if current equity is higher."""
        state = self._tenant_state.setdefault(tenant_id, {"peak": current_equity})
        if current_equity > state["peak"]:
            state["peak"] = current_equity

    def _calculate_drawdown_pct(self, peak: Decimal, current: Decimal) -> Decimal:
        """
        Calculate drawdown as a percentage from peak.

        Formula: DD% = (peak - current) / peak * 100
        Returns Decimal rounded to 3 decimal places.
        """
        if peak <= 0:
            return Decimal("0")
        if current >= peak:
            return Decimal("0")
        raw = (peak - current) / peak * Decimal("100")
        return raw.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)

    def _classify(self, drawdown_pct: Decimal) -> tuple:
        """
        Classify drawdown level based on thresholds.

        Returns:
            (level: str, should_lockdown: bool)
        """
        if drawdown_pct >= self._hard:
            return "HARD_BREACH", True
        if drawdown_pct >= self._soft:
            return "SOFT_ALERT", False
        return "SAFE", False

    def _log(self, status: DrawdownStatus) -> None:
        """Emit appropriate log level based on status."""
        msg = (
            f"[DrawdownMonitor] [{status.tenant_id}] Level={status.level} | "
            f"DD={status.drawdown_pct:.2f}% | "
            f"Equity={status.current_equity} / Peak={status.peak_equity}"
        )
        if status.level == "HARD_BREACH":
            logger.critical(f"🔒 {msg} — LOCKDOWN TRIGGERED")
        elif status.level == "SOFT_ALERT":
            logger.warning(f"⚠️  {msg}")
        else:
            logger.debug(msg)
