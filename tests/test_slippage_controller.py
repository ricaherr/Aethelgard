"""
TDD Tests: HU 5.2 - Adaptive Slippage Controller
Verifies that slippage limits are derived from DB config (SSOT),
not hardcoded by symbol string patterns.
"""
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

_BASE_CFG = {
    "class_limits": {
        "FOREX_MAJOR": "1.5",
        "FOREX_CROSS": "2.5",
        "INDICES": "3.0",
        "CRYPTO": "5.0",
        "DEFAULT": "2.0",
    },
    "regime_multipliers": {
        "VOLATILE": "1.5",
        "RANGING": "0.85",
        "TRENDING": "1.2",
        "DEFAULT": "1.0",
    },
    "p90_min_records": 50,
    "p90_cap_multiplier": "3.0",
}


def _make_storage(
    slippage_config=None,
    p90_result=None,
    dynamic_params_override=None,
):
    storage = MagicMock()
    if dynamic_params_override is not None:
        storage.get_dynamic_params.return_value = dynamic_params_override
    else:
        cfg = slippage_config if slippage_config is not None else _BASE_CFG
        storage.get_dynamic_params.return_value = {"slippage_config": cfg}
    storage.get_slippage_p90.return_value = p90_result
    return storage


# ── Group 1: Asset class base limits come from DB config ─────────────────────

class TestAssetClassLimits:
    def test_forex_major_returns_1_5(self):
        ctrl = _make_ctrl()
        assert ctrl.get_limit("EURUSD", market_type="FOREX_MAJOR") == Decimal("1.5")

    def test_forex_cross_returns_2_5(self):
        ctrl = _make_ctrl()
        assert ctrl.get_limit("GBPJPY", market_type="FOREX_CROSS") == Decimal("2.5")

    def test_indices_returns_3_0(self):
        ctrl = _make_ctrl()
        assert ctrl.get_limit("US30", market_type="INDICES") == Decimal("3.0")

    def test_crypto_returns_5_0(self):
        ctrl = _make_ctrl()
        assert ctrl.get_limit("BTCUSD", market_type="CRYPTO") == Decimal("5.0")

    def test_unknown_market_type_uses_default(self):
        ctrl = _make_ctrl()
        assert ctrl.get_limit("XYZABC", market_type="EXOTIC") == Decimal("2.0")

    def test_none_market_type_uses_default(self):
        ctrl = _make_ctrl()
        assert ctrl.get_limit("EURUSD", market_type=None) == Decimal("2.0")


# ── Group 2: Regime multipliers come from DB config ──────────────────────────

class TestRegimeMultipliers:
    def test_volatile_multiplies_factor_1_5(self):
        ctrl = _make_ctrl()
        # FOREX_MAJOR(1.5) * VOLATILE(1.5) = 2.25
        result = ctrl.get_limit("EURUSD", regime="VOLATILE", market_type="FOREX_MAJOR")
        assert result == Decimal("2.25")

    def test_ranging_multiplies_factor_0_85(self):
        ctrl = _make_ctrl()
        # FOREX_MAJOR(1.5) * RANGING(0.85) = 1.275
        result = ctrl.get_limit("EURUSD", regime="RANGING", market_type="FOREX_MAJOR")
        assert result == Decimal("1.275")

    def test_trending_multiplies_factor_1_2(self):
        ctrl = _make_ctrl()
        # FOREX_MAJOR(1.5) * TRENDING(1.2) = 1.80
        result = ctrl.get_limit("EURUSD", regime="TRENDING", market_type="FOREX_MAJOR")
        assert result == Decimal("1.80")

    def test_none_regime_uses_default_multiplier(self):
        ctrl = _make_ctrl()
        # FOREX_MAJOR(1.5) * DEFAULT(1.0) = 1.5
        result = ctrl.get_limit("EURUSD", regime=None, market_type="FOREX_MAJOR")
        assert result == Decimal("1.5")


# ── Group 3: p90 auto-calibration from shadow logs ───────────────────────────

class TestP90AutoCalibration:
    def test_p90_above_calculated_is_used(self):
        """p90 > calculated → return p90."""
        storage = _make_storage(p90_result=Decimal("3.2"))
        from core_brain.services.slippage_controller import SlippageController
        ctrl = SlippageController(storage)
        # FOREX_MAJOR(1.5) * DEFAULT(1.0) = 1.5; p90=3.2 > 1.5 → use 3.2
        result = ctrl.get_limit("EURUSD", market_type="FOREX_MAJOR")
        assert result == Decimal("3.2")

    def test_p90_below_calculated_is_ignored(self):
        """p90 ≤ calculated → keep calculated."""
        storage = _make_storage(p90_result=Decimal("0.5"))
        from core_brain.services.slippage_controller import SlippageController
        ctrl = SlippageController(storage)
        result = ctrl.get_limit("EURUSD", market_type="FOREX_MAJOR")
        assert result == Decimal("1.5")

    def test_p90_capped_at_cap_multiplier(self):
        """Extreme p90 is capped at base_limit * p90_cap_multiplier."""
        storage = _make_storage(p90_result=Decimal("50.0"))
        from core_brain.services.slippage_controller import SlippageController
        ctrl = SlippageController(storage)
        # FOREX_MAJOR(1.5) * DEFAULT(1.0) = 1.5; cap = 1.5 * 3.0 = 4.5
        # p90=50 > cap=4.5 → use cap
        result = ctrl.get_limit("EURUSD", market_type="FOREX_MAJOR")
        assert result == Decimal("4.5")

    def test_no_p90_data_uses_calculated(self):
        """storage returns None (insufficient records) → uses calculated limit."""
        storage = _make_storage(p90_result=None)
        from core_brain.services.slippage_controller import SlippageController
        ctrl = SlippageController(storage)
        result = ctrl.get_limit("EURUSD", market_type="FOREX_MAJOR")
        assert result == Decimal("1.5")


# ── Group 4: ExecutionService integration ────────────────────────────────────

class TestExecutionServiceIntegration:
    def test_execution_service_has_no_hardcoded_default_slippage_limit(self):
        """ExecutionService must not have the old hardcoded attribute."""
        from core_brain.services.execution_service import ExecutionService
        storage = MagicMock()
        slippage_ctrl = MagicMock()
        svc = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        assert not hasattr(svc, "default_slippage_limit")

    def test_execution_service_holds_injected_controller(self):
        """ExecutionService exposes the injected controller for inspection."""
        from core_brain.services.execution_service import ExecutionService
        storage = MagicMock()
        slippage_ctrl = MagicMock()
        svc = ExecutionService(storage=storage, slippage_controller=slippage_ctrl)
        assert svc.slippage_controller is slippage_ctrl

    def test_fallback_defaults_when_db_has_no_slippage_config(self):
        """Falls back to _DEFAULT_CONFIG when dynamic_params has no slippage_config key."""
        storage = _make_storage(dynamic_params_override={})  # empty → no slippage_config
        from core_brain.services.slippage_controller import SlippageController
        ctrl = SlippageController(storage)
        # Fallback _DEFAULT_CONFIG: FOREX_MAJOR = 1.5
        result = ctrl.get_limit("EURUSD", market_type="FOREX_MAJOR")
        assert result == Decimal("1.5")


# ── Helper: build controller with standard base config ───────────────────────

def _make_ctrl():
    from core_brain.services.slippage_controller import SlippageController
    return SlippageController(_make_storage())
