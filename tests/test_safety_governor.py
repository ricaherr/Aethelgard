"""
TDD: Safety Governor — HU 4.4
===============================
Tests for the R-Unit veto logic integrated into RiskManager.can_take_new_trade().
These tests MUST FAIL before implementation and PASS after.

Safety Governor rules:
- Every order must be validated against the tenant's max_r_per_trade limit
- R = |Entry - SL| * contract_size / account_balance * 100
- Decimal arithmetic is mandatory (no float for financial calculations)
- A RejectionAudit dict must be generated on veto with trace_id
"""
import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch
from models.signal import Signal, SignalType, ConnectorType


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def _make_signal(
    symbol="EURUSD",
    entry=1.0800,
    sl=1.0700,   # 100 pip SL
    tp=1.0950,
    connector_type=ConnectorType.PAPER,
) -> Signal:
    """Helper: creates a minimal valid Signal for testing."""
    return Signal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        confidence=0.75,
        entry_price=entry,
        stop_loss=sl,
        take_profit=tp,
        connector_type=connector_type,
        metadata={"signal_id": "TST-001"},
    )


def _make_storage(max_r: float = 1.0, risk_per_trade: float = 0.01) -> MagicMock:
    """Mock StorageManager with configurable risk settings."""
    mock = MagicMock()
    mock.get_risk_settings.return_value = {
        "max_consecutive_losses": 3,
        "max_account_risk_pct": 5.0,
        "max_r_per_trade": max_r,
    }
    mock.get_dynamic_params.return_value = {"risk_per_trade": risk_per_trade}
    mock.get_system_state.return_value = {"lockdown_mode": False}
    mock.get_asset_profile.return_value = {
        "contract_size": 100000,
        "lot_step": 0.01,
        "lot_min": 0.01,
    }
    return mock


def _make_connector(balance: float = 10000.0) -> MagicMock:
    """Mock broker connector with configurable account balance."""
    mock = MagicMock()
    mock.get_account_balance.return_value = balance
    mock.get_open_positions.return_value = []

    symbol_info = MagicMock()
    symbol_info.trade_contract_size = 100000
    symbol_info.volume_min = 0.01
    symbol_info.volume_max = 100.0
    symbol_info.volume_step = 0.01
    mock.get_symbol_info.return_value = symbol_info
    return mock


def _make_risk_manager(storage: MagicMock) -> "RiskManager":
    """Instantiate RiskManager with mocked storage (avoids DB calls)."""
    from core_brain.risk_manager import RiskManager
    from core_brain.position_size_monitor import PositionSizeMonitor
    monitor = PositionSizeMonitor()
    return RiskManager(storage=storage, initial_capital=10000.0, monitor=monitor)


# ─── HU 4.4: Veto by R-Unit ───────────────────────────────────────────────────

class TestSafetyGovernorVeto:
    """Verify that can_take_new_trade() rejects orders exceeding the R limit."""

    def test_veto_when_r_exceeds_limit(self):
        """
        EURUSD: Entry=1.0800, SL=1.0700, Balance=$10,000, contract_size=100,000
        R = |1.0800 - 1.0700| * 100,000 / 10,000 * 100 = 10R
        max_r_per_trade = 1.0R  => VETO
        """
        storage = _make_storage(max_r=1.0)
        rm = _make_risk_manager(storage)
        connector = _make_connector(balance=10000.0)
        signal = _make_signal(entry=1.0800, sl=1.0700)  # 100-pip SL = 10R

        can_trade, reason = rm.can_take_new_trade(signal, connector)

        assert can_trade is False, "Order with 10R should be vetoed (limit=1R)"
        assert "SAFETY_GOV" in reason or "R" in reason.upper(), (
            f"Rejection reason should mention Safety Governor or R-units: '{reason}'"
        )

    def test_approved_when_r_within_limit(self):
        """
        EURUSD: Entry=1.0800, SL=1.0799, Balance=$10,000
        R = |0.0001| * 100,000 / 10,000 * 100 = 0.1R
        max_r_per_trade = 1.0R  => APPROVED
        """
        storage = _make_storage(max_r=1.0)
        rm = _make_risk_manager(storage)
        connector = _make_connector(balance=10000.0)
        signal = _make_signal(entry=1.0800, sl=1.0799)  # 1-pip SL = 0.1R

        can_trade, reason = rm.can_take_new_trade(signal, connector)

        assert can_trade is True, f"Order with 0.1R should pass (limit=1R). Reason: {reason}"

    def test_exactly_at_limit_is_approved(self):
        """
        R == max_r_per_trade must be APPROVED (inclusive boundary).
        EURUSD: Entry=1.0800, SL=1.0790 => R = 0.01 * 100000 / 10000 * 100 = 1.0R
        """
        storage = _make_storage(max_r=1.0)
        rm = _make_risk_manager(storage)
        connector = _make_connector(balance=10000.0)
        signal = _make_signal(entry=1.0800, sl=1.0790)  # 10-pip SL = 1.0R exactly

        can_trade, reason = rm.can_take_new_trade(signal, connector)

        assert can_trade is True, (
            f"Order at exactly 1.0R should be approved (limit=1.0R). Reason: {reason}"
        )

    def test_no_veto_when_sl_is_missing(self):
        """
        If stop_loss is 0 or None, Safety Governor cannot calculate R.
        Defensive posture: do NOT block on R (other checks may still block).
        """
        storage = _make_storage(max_r=0.001)  # Extremely tight limit
        rm = _make_risk_manager(storage)
        connector = _make_connector(balance=10000.0)
        signal = _make_signal(sl=0.0)  # No SL provided

        # Should not raise, should not veto solely due to missing SL
        # (The R-unit check must be skipped gracefully)
        can_trade, reason = rm.can_take_new_trade(signal, connector)
        # Only assert it didn't raise an exception and reason is not R-related
        assert "SAFETY_GOV" not in reason, (
            "R-unit veto should not fire when SL is 0/missing"
        )


# ─── HU 4.4: R-Unit Calculation ───────────────────────────────────────────────

class TestRUnitCalculation:
    """Verify the _calculate_r_unit() method uses Decimal and correct formula."""

    def test_r_calculation_uses_decimal_type(self):
        """
        The internal R calculation must return Decimal, not float.
        This enforces financial precision per project standards.
        """
        storage = _make_storage(max_r=1.0)
        rm = _make_risk_manager(storage)
        signal = _make_signal(entry=1.0800, sl=1.0750)

        r = rm._calculate_r_unit(signal, account_balance=10000.0)

        assert isinstance(r, Decimal), (
            f"_calculate_r_unit() must return Decimal, got {type(r).__name__}"
        )

    def test_r_formula_correctness_eurusd(self):
        """
        EURUSD: Entry=1.0800, SL=1.0750, Balance=10000, contract=100000
        R = |1.0800-1.0750| * 100000 / 10000 * 100 = 0.0050 * 100000/10000 * 100 = 5.0R
        """
        storage = _make_storage(max_r=10.0)
        rm = _make_risk_manager(storage)
        signal = _make_signal(entry=1.0800, sl=1.0750)

        r = rm._calculate_r_unit(signal, account_balance=10000.0)

        assert r == pytest.approx(Decimal("5.0"), rel=Decimal("0.01")), (
            f"Expected R=5.0 for 50-pip EURUSD SL on $10k, got {r}"
        )

    def test_r_formula_scales_with_balance(self):
        """Doubling the balance should halve the R-units for the same trade."""
        storage = _make_storage(max_r=10.0)
        rm_small = _make_risk_manager(storage)
        rm_large = _make_risk_manager(storage)
        signal = _make_signal(entry=1.0800, sl=1.0750)

        r_small = rm_small._calculate_r_unit(signal, account_balance=5000.0)
        r_large = rm_large._calculate_r_unit(signal, account_balance=10000.0)

        assert r_small == pytest.approx(r_large * 2, rel=Decimal("0.01")), (
            f"R should double when balance halves. Got small={r_small}, large={r_large}"
        )


# ─── HU 4.4: Rejection Audit ──────────────────────────────────────────────────

class TestRejectionAudit:
    """Verify that a veto always produces a complete RejectionAudit."""

    def test_rejection_reason_contains_audit_reference(self):
        """
        When vetoed, the reason string must be traceable (contain trace_id or audit marker).
        """
        storage = _make_storage(max_r=0.01)  # Extremely tight, will always veto on normal SL
        rm = _make_risk_manager(storage)
        connector = _make_connector(balance=10000.0)
        signal = _make_signal(entry=1.0800, sl=1.0700)  # 100-pip SL

        can_trade, reason = rm.can_take_new_trade(signal, connector)

        assert not can_trade
        # Reason must be meaningful (not empty)
        assert len(reason) > 10, f"Rejection reason too short: '{reason}'"
        # Must mention R somewhere for operator clarity
        assert any(keyword in reason.upper() for keyword in ["SAFETY", "GOV", "R-UNIT", "R_UNIT", " R="]), (
            f"Rejection must mention Safety Governor. Got: '{reason}'"
        )

    def test_build_rejection_audit_has_required_fields(self):
        """
        _build_rejection_audit() must return a dict with mandatory fields
        for full auditability.
        """
        storage = _make_storage(max_r=1.0)
        rm = _make_risk_manager(storage)
        signal = _make_signal()

        audit = rm._build_rejection_audit(
            signal=signal,
            r_calculated=Decimal("5.0"),
            r_limit=Decimal("1.0"),
            tenant_id="tenant_test_001",
        )

        required_fields = {"trace_id", "timestamp", "symbol", "r_calculated", "r_limit", "reason"}
        missing = required_fields - set(audit.keys())
        assert not missing, f"RejectionAudit missing required fields: {missing}"
        assert audit["trace_id"].startswith("GOV-"), (
            f"trace_id must start with 'GOV-', got: {audit['trace_id']}"
        )
        assert audit["r_calculated"] == Decimal("5.0")
        assert audit["r_limit"] == Decimal("1.0")
