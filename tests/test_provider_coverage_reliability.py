"""
TDD Suite - HU 10.28: Provider Coverage Reliability
Trace_ID: HU10.28-PROVIDER-COVERAGE-RELIABILITY-2026-04-09

Tests for SymbolCoveragePolicy: cooldown/exclusion/recovery logic.
Red phase first — these tests MUST fail before implementation exists.
"""
from __future__ import annotations

import time
from unittest.mock import MagicMock, patch, call
from typing import Any

import pytest

from core_brain.symbol_coverage_policy import SymbolCoveragePolicy
from core_brain.data_provider_manager import DataProviderManager


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def mock_storage() -> MagicMock:
    """StorageManager stub returning empty dynamic_params (triggers defaults)."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {}
    storage.get_sys_data_providers.return_value = []
    return storage


@pytest.fixture()
def policy(mock_storage: MagicMock) -> SymbolCoveragePolicy:
    """Fresh SymbolCoveragePolicy with default params."""
    return SymbolCoveragePolicy(storage=mock_storage)


@pytest.fixture()
def manager(mock_storage: MagicMock) -> DataProviderManager:
    """DataProviderManager with isolated in-memory storage."""
    return DataProviderManager(storage=mock_storage)


# ---------------------------------------------------------------------------
# AC-1 / Test 1: Failures below threshold do NOT activate exclusion
# ---------------------------------------------------------------------------

class TestSymbolNotExcludedBeforeThreshold:
    """AC-1: Below threshold → no exclusion."""

    def test_symbol_not_excluded_before_threshold(self, policy: SymbolCoveragePolicy) -> None:
        """Fewer consecutive failures than threshold must NOT trigger exclusion."""
        symbol = "BTCUSDT"
        threshold = 3  # default

        # Register (threshold - 1) failures
        for _ in range(threshold - 1):
            policy.register_failure(symbol, reason_code="no_data")

        assert not policy.is_temporarily_excluded(symbol), (
            "Symbol should NOT be excluded when failures < threshold"
        )


# ---------------------------------------------------------------------------
# AC-2 / Test 2: Reaching threshold activates exclusion
# ---------------------------------------------------------------------------

class TestSymbolExcludedAfterThreshold:
    """AC-2: Hitting threshold → exclusion activated."""

    def test_symbol_excluded_after_threshold(self, policy: SymbolCoveragePolicy) -> None:
        """Exactly threshold consecutive failures must activate temporal exclusion."""
        symbol = "NAS100"
        threshold = 3  # default

        for _ in range(threshold):
            policy.register_failure(symbol, reason_code="all_fallbacks_exhausted")

        assert policy.is_temporarily_excluded(symbol), (
            "Symbol MUST be excluded after reaching failure threshold"
        )


# ---------------------------------------------------------------------------
# AC-3 / Test 3: Excluded symbol skips provider iteration in fetch_ohlc
# ---------------------------------------------------------------------------

class TestExcludedSymbolSkipsProviderIteration:
    """AC-3: Excluded symbol → fetch_ohlc returns None without iterating providers."""

    def test_excluded_symbol_skips_provider_iteration(self, manager: DataProviderManager) -> None:
        """An actively excluded symbol must NOT iterate providers on fetch_ohlc."""
        symbol = "ETHUSD"

        # Pre-load exclusion into manager's coverage policy
        manager._coverage_policy.register_failure(symbol, reason_code="no_data")
        manager._coverage_policy.register_failure(symbol, reason_code="no_data")
        manager._coverage_policy.register_failure(symbol, reason_code="no_data")

        # Confirm exclusion is active
        assert manager._coverage_policy.is_temporarily_excluded(symbol)

        # fetch_ohlc should NOT call any provider instance
        mock_provider = MagicMock()
        mock_provider.fetch_ohlc.return_value = [1, 2, 3]

        with patch.object(manager, "_get_provider_instance", return_value=mock_provider) as mock_get:
            result = manager.fetch_ohlc(symbol, timeframe="M5", count=100)

        mock_get.assert_not_called()
        mock_provider.fetch_ohlc.assert_not_called()
        assert result is None


# ---------------------------------------------------------------------------
# AC-4 / Test 4: Excluded symbol retries after exclusion expiry
# ---------------------------------------------------------------------------

class TestSymbolRetriesAfterExclusionExpiry:
    """AC-4: After exclusion_until expires → provider iteration resumes."""

    def test_symbol_retries_after_exclusion_expiry(self, manager: DataProviderManager) -> None:
        """Once exclusion expires, fetch_ohlc must attempt provider again."""
        symbol = "XRPUSDT"

        # Force very short exclusion by manipulating state directly
        policy = manager._coverage_policy
        policy.register_failure(symbol, reason_code="no_data")
        policy.register_failure(symbol, reason_code="no_data")
        policy.register_failure(symbol, reason_code="no_data")
        assert policy.is_temporarily_excluded(symbol)

        # Manually expire exclusion
        policy._symbol_state[symbol].exclusion_until_monotonic = time.monotonic() - 1.0

        # Now exclusion should be gone
        assert not policy.is_temporarily_excluded(symbol)

        # fetch_ohlc should attempt providers
        mock_provider = MagicMock()
        mock_provider.is_symbol_supported.return_value = True
        mock_provider.fetch_ohlc.return_value = [{"close": 0.5}]

        with patch.object(manager, "get_active_providers", return_value=[
            {"name": "yahoo", "supports": ["crypto"]}
        ]), patch.object(manager, "_get_provider_instance", return_value=mock_provider):
            result = manager.fetch_ohlc(symbol, timeframe="M5", count=100)

        mock_provider.fetch_ohlc.assert_called_once()
        assert result is not None


# ---------------------------------------------------------------------------
# AC-5 / Test 5: Success resets failure state
# ---------------------------------------------------------------------------

class TestSuccessResetsSymbolFailureState:
    """AC-5: Successful fetch → failures and exclusion are cleared."""

    def test_success_resets_symbol_failure_state(self, manager: DataProviderManager) -> None:
        """A successful fetch must reset consecutive_failures and cancel exclusion."""
        symbol = "EURUSD"
        policy = manager._coverage_policy

        # Build up failures to threshold
        for _ in range(3):
            policy.register_failure(symbol, reason_code="no_data")
        assert policy.is_temporarily_excluded(symbol)

        # Expire exclusion so the retry fires
        policy._symbol_state[symbol].exclusion_until_monotonic = time.monotonic() - 1.0

        mock_provider = MagicMock()
        mock_provider.is_symbol_supported.return_value = True
        mock_provider.fetch_ohlc.return_value = [{"close": 1.08}]

        with patch.object(manager, "get_active_providers", return_value=[
            {"name": "yahoo", "supports": ["forex"]}
        ]), patch.object(manager, "_get_provider_instance", return_value=mock_provider):
            result = manager.fetch_ohlc(symbol, timeframe="M5", count=100)

        assert result is not None
        state = policy._symbol_state[symbol]
        assert state.consecutive_failures == 0, "Failures must be reset after success"
        assert not policy.is_temporarily_excluded(symbol), "Exclusion must be cleared after success"


# ---------------------------------------------------------------------------
# AC-6 (partial) / Test 6: Exponential backoff is capped
# ---------------------------------------------------------------------------

class TestExponentialBackoffCapped:
    """Backoff duration must not exceed provider_symbol_exclusion_max_sec."""

    def test_exponential_backoff_capped(self, policy: SymbolCoveragePolicy) -> None:
        """Exclusion duration must plateau at max_sec regardless of failure count."""
        max_sec = 900.0  # default cap

        # Register many failures to trigger deep backoff
        for _ in range(20):
            policy.register_failure("SOLBTC", reason_code="no_data")

        state = policy._symbol_state["SOLBTC"]
        remaining_ttl = state.exclusion_until_monotonic - time.monotonic()

        assert remaining_ttl <= max_sec + 1.0, (
            f"Backoff exceeded cap: {remaining_ttl:.1f}s > {max_sec}s"
        )


# ---------------------------------------------------------------------------
# AC-6 / Test 7: Warning throttle per symbol
# ---------------------------------------------------------------------------

class TestWarningThrottlePerSymbol:
    """AC-6: Warning must not be emitted more frequently than throttle_sec."""

    def test_warning_throttle_per_symbol(self, policy: SymbolCoveragePolicy) -> None:
        """Second should_emit_warning call within throttle window must return False."""
        symbol = "ADAUSDT"

        # First call: no state yet → warning allowed
        first = policy.should_emit_warning(symbol)
        assert first is True, "First warning should always be allowed"

        # Immediate second call within throttle window → suppressed
        second = policy.should_emit_warning(symbol)
        assert second is False, "Warning within throttle window must be suppressed"


# ---------------------------------------------------------------------------
# AC-8 / Test 8: Existing fallback behavior unchanged (no-regression)
# ---------------------------------------------------------------------------

class TestExistingFallbackBehaviorUnchanged:
    """AC-8: New coverage policy must not break existing fallback iteration."""

    def test_existing_fallback_behavior_unchanged(self, manager: DataProviderManager) -> None:
        """Non-excluded symbols must still pass through normal provider iteration."""
        symbol = "GBPUSD"

        # Ensure symbol is NOT excluded
        assert not manager._coverage_policy.is_temporarily_excluded(symbol)

        provider_a = MagicMock()
        provider_a.is_symbol_supported.return_value = True
        provider_a.fetch_ohlc.return_value = None  # Primary fails

        provider_b = MagicMock()
        provider_b.is_symbol_supported.return_value = True
        provider_b.fetch_ohlc.return_value = [{"close": 1.25}]  # Fallback succeeds

        providers_config = [
            {"name": "provider_a", "supports": ["forex"]},
            {"name": "provider_b", "supports": ["forex"]},
        ]

        with patch.object(manager, "get_active_providers", return_value=providers_config), \
             patch.object(manager, "_get_provider_instance", side_effect=[provider_a, provider_b]):
            result = manager.fetch_ohlc(symbol, timeframe="M5", count=100)

        provider_a.fetch_ohlc.assert_called_once()
        provider_b.fetch_ohlc.assert_called_once()
        assert result == [{"close": 1.25}], "Fallback to second provider must still work"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
