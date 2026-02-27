"""
TDD: DrawdownMonitor — HU 4.5
================================
Tests for the Exposure & Drawdown Monitor (multi-tenant equity supervisor).

Responsibilities (orthogonal to PositionSizeMonitor):
- Track peak equity per tenant
- Calculate drawdown as percentage from peak
- Emit SOFT_ALERT at soft_threshold (default 5%)
- Trigger HARD_BREACH and lockdown at hard_threshold (default 10%)
- Guarantee tenant isolation (tenant A's drawdown does not affect tenant B)
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch


# ─── Fixture ──────────────────────────────────────────────────────────────────

def _make_storage() -> MagicMock:
    """Mock StorageManager that returns no existing system state by default."""
    mock = MagicMock()
    mock.get_system_state.return_value = {}
    mock.update_system_state.return_value = None
    return mock


def _make_monitor(soft_pct: float = 5.0, hard_pct: float = 10.0) -> "DrawdownMonitor":
    """Instantiate DrawdownMonitor with configurable thresholds."""
    from core_brain.drawdown_monitor import DrawdownMonitor
    return DrawdownMonitor(soft_threshold_pct=soft_pct, hard_threshold_pct=hard_pct)


# ─── Status Level Tests ────────────────────────────────────────────────────────

class TestDrawdownStatusLevels:
    """Verify the three status levels: SAFE, SOFT_ALERT, HARD_BREACH."""

    def test_safe_when_within_limits(self):
        """Equity at peak — no drawdown — should return SAFE."""
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=10000.0)
        assert status.level == "SAFE", f"Expected SAFE, got {status.level}"
        assert not status.should_lockdown

    def test_safe_when_small_drawdown(self):
        """3% drawdown with 5% threshold should be SAFE."""
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9700.0)
        assert status.level == "SAFE", f"Expected SAFE for 3% DD, got {status.level}"
        assert not status.should_lockdown

    def test_soft_alert_at_threshold(self):
        """Exactly at soft threshold => SOFT_ALERT, no lockdown."""
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9500.0)
        assert status.level == "SOFT_ALERT", f"Expected SOFT_ALERT at 5%, got {status.level}"
        assert not status.should_lockdown, "SOFT_ALERT must NOT trigger lockdown"

    def test_soft_alert_between_thresholds(self):
        """7% drawdown (between 5% and 10%) => SOFT_ALERT."""
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9300.0)
        assert status.level == "SOFT_ALERT", f"Expected SOFT_ALERT at 7%, got {status.level}"

    def test_hard_breach_at_hard_threshold(self):
        """Exactly at hard threshold => HARD_BREACH with lockdown."""
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9000.0)
        assert status.level == "HARD_BREACH", f"Expected HARD_BREACH at 10%, got {status.level}"
        assert status.should_lockdown, "HARD_BREACH MUST trigger lockdown"

    def test_hard_breach_beyond_threshold(self):
        """15% drawdown (beyond hard limit) => HARD_BREACH."""
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=8500.0)
        assert status.level == "HARD_BREACH"
        assert status.should_lockdown


# ─── Drawdown Calculation ──────────────────────────────────────────────────────

class TestDrawdownCalculation:
    """Verify precision and correctness of drawdown percentage calculation."""

    def test_drawdown_pct_is_decimal(self):
        """drawdown_pct in DrawdownStatus must be Decimal (not float)."""
        monitor = _make_monitor()
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9500.0)
        assert isinstance(status.drawdown_pct, Decimal), (
            f"drawdown_pct must be Decimal, got {type(status.drawdown_pct).__name__}"
        )

    def test_drawdown_pct_formula(self):
        """
        DD% = (peak - current) / peak * 100
        (10000 - 9000) / 10000 * 100 = 10.0%
        """
        monitor = _make_monitor()
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9000.0)
        expected = Decimal("10.000")
        assert status.drawdown_pct == pytest.approx(expected, rel=Decimal("0.001")), (
            f"Expected drawdown_pct=10.0, got {status.drawdown_pct}"
        )

    def test_zero_drawdown(self):
        """Zero drawdown when current == peak."""
        monitor = _make_monitor()
        status = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=10000.0)
        assert status.drawdown_pct == Decimal("0"), f"Expected 0 DD, got {status.drawdown_pct}"

    def test_status_contains_peak_and_current_equity(self):
        """DrawdownStatus must expose peak_equity and current_equity for UI."""
        monitor = _make_monitor()
        status = monitor.update_equity("tenant_A", peak_equity=12000.0, current_equity=11000.0)
        assert hasattr(status, "peak_equity"), "DrawdownStatus must have peak_equity"
        assert hasattr(status, "current_equity"), "DrawdownStatus must have current_equity"


# ─── Tenant Isolation ─────────────────────────────────────────────────────────

class TestTenantIsolation:
    """Verify that drawdown tracking is fully isolated per tenant."""

    def test_tenant_a_breach_does_not_affect_tenant_b(self):
        """
        Tenant A in HARD_BREACH must not change Tenant B's status.
        """
        monitor = _make_monitor(soft_pct=5.0, hard_pct=10.0)
        status_a = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=8500.0)
        status_b = monitor.update_equity("tenant_B", peak_equity=10000.0, current_equity=9900.0)

        assert status_a.level == "HARD_BREACH"
        assert status_b.level == "SAFE", (
            f"Tenant B should be SAFE regardless of Tenant A's state. Got: {status_b.level}"
        )

    def test_different_tenants_have_independent_drawdown_pct(self):
        """Each tenant tracks its own drawdown independently."""
        monitor = _make_monitor()
        status_a = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=9000.0)
        status_b = monitor.update_equity("tenant_B", peak_equity=5000.0, current_equity=4750.0)

        assert status_a.drawdown_pct == pytest.approx(Decimal("10.0"), rel=Decimal("0.01"))
        assert status_b.drawdown_pct == pytest.approx(Decimal("5.0"), rel=Decimal("0.01"))

    def test_lockdown_flag_is_per_tenant(self):
        """should_lockdown=True for tenant A must not bleed into tenant B."""
        monitor = _make_monitor(hard_pct=10.0)
        status_a = monitor.update_equity("tenant_A", peak_equity=10000.0, current_equity=8000.0)
        status_b = monitor.update_equity("tenant_B", peak_equity=10000.0, current_equity=9980.0)

        assert status_a.should_lockdown is True
        assert status_b.should_lockdown is False
