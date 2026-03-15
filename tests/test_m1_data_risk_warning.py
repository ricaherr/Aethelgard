"""
N1-4: Test — DATA_RISK warning when M1 is active with a non-local provider.

TDD Red Phase: these tests MUST FAIL before implementation.
"""
import unittest
from unittest.mock import MagicMock, patch
import pandas as pd
import numpy as np


def _make_ohlc_df(rows: int = 100) -> pd.DataFrame:
    """Minimal OHLC DataFrame with random-ish data to pass classifier."""
    rng = np.random.default_rng(42)
    close = 1.1 + rng.normal(0, 0.001, rows).cumsum()
    return pd.DataFrame({
        "open": close - 0.0001,
        "high": close + 0.0002,
        "low": close - 0.0002,
        "close": close,
        "volume": rng.integers(100, 500, rows).astype(float),
        "tick_volume": rng.integers(100, 500, rows).astype(float),
    })


def _build_scanner(is_local: bool, storage=None, timeframes=None):
    """Build a minimal ScannerEngine ready to call _scan_one.
    
    The classifier is mocked to isolate the DATA_RISK path from
    RegimeClassifier internals that need real storage/data.
    """
    from core_brain.scanner import ScannerEngine
    from models.signal import MarketRegime

    mock_provider = MagicMock()
    mock_provider.is_local.return_value = is_local
    mock_provider.fetch_ohlc.return_value = _make_ohlc_df()
    mock_provider.provider_name = "mock_provider"
    # make sure get_best_provider returns None so provider_id doesn't need it
    mock_provider.get_best_provider.return_value = None

    mock_storage = storage or MagicMock()

    scanner = ScannerEngine.__new__(ScannerEngine)
    scanner.provider = mock_provider
    scanner.storage = mock_storage
    scanner.is_local_provider = is_local
    scanner.assets = ["EURUSD"]
    scanner.active_timeframes = timeframes or ["M1"]
    scanner.mt5_bars_count = 100
    scanner.consecutive_failures = {}
    scanner.circuit_breaker_cooldowns = {}
    scanner._data_risk_last_notif = {}  # throttle dict (N1-4 fix)
    scanner.last_regime = {}
    scanner.last_scan_time = {}

    # Inject mock classifier to isolate from RegimeClassifier complexity
    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = MarketRegime.NORMAL
    mock_classifier.get_metrics.return_value = {}
    scanner.classifiers = {}
    for tf in scanner.active_timeframes:
        scanner.classifiers[f"EURUSD|{tf}"] = mock_classifier
        scanner.last_regime[f"EURUSD|{tf}"] = MarketRegime.NORMAL
        scanner.last_scan_time[f"EURUSD|{tf}"] = 0.0

    return scanner


class TestM1DataRiskWarning(unittest.TestCase):

    # ------------------------------------------------------------------
    # Case 1: M1 + non-local provider → warning logged + notification saved
    # ------------------------------------------------------------------

    @patch("core_brain.scanner.logger")
    def test_logs_warning_when_m1_and_non_local(self, mock_logger):
        """M1 + non-local provider must emit a logger.warning with [DATA_RISK]."""
        scanner = _build_scanner(is_local=False)
        scanner._scan_one("EURUSD", "M1")

        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "DATA_RISK" in str(call)
        ]
        self.assertTrue(
            len(warning_calls) >= 1,
            "Expected at least one logger.warning containing '[DATA_RISK]'"
        )

    def test_saves_notification_when_m1_and_non_local(self):
        """M1 + non-local provider must persist a DATA_RISK notification."""
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=False, storage=mock_storage)
        scanner._scan_one("EURUSD", "M1")

        mock_storage.save_notification.assert_called_once()
        call_kwargs = mock_storage.save_notification.call_args[0][0]
        self.assertEqual(call_kwargs.get("category"), "DATA_RISK")

    def test_notification_contains_symbol(self):
        """DATA_RISK notification message must mention the scanned symbol."""
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=False, storage=mock_storage)
        scanner._scan_one("EURUSD", "M1")

        call_kwargs = mock_storage.save_notification.call_args[0][0]
        self.assertIn(
            "EURUSD",
            str(call_kwargs.get("message", "")) + str(call_kwargs.get("title", "")),
            "Notification must mention the symbol EURUSD"
        )

    def test_notification_priority_is_high(self):
        """DATA_RISK notification priority must be 'high' or 'warning'."""
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=False, storage=mock_storage)
        scanner._scan_one("EURUSD", "M1")

        call_kwargs = mock_storage.save_notification.call_args[0][0]
        self.assertIn(
            call_kwargs.get("priority", "").lower(),
            ("high", "warning"),
            "DATA_RISK priority must be 'high' or 'warning'"
        )

    # ------------------------------------------------------------------
    # Case 2: M1 + LOCAL provider → no warning, no notification
    # ------------------------------------------------------------------

    @patch("core_brain.scanner.logger")
    def test_no_warning_when_m1_and_local(self, mock_logger):
        """M1 + LOCAL provider must NOT emit a DATA_RISK warning."""
        scanner = _build_scanner(is_local=True)
        scanner._scan_one("EURUSD", "M1")

        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "DATA_RISK" in str(call)
        ]
        self.assertEqual(
            len(warning_calls), 0,
            "Local provider must NOT emit DATA_RISK warning"
        )

    def test_no_notification_when_m1_and_local(self):
        """M1 + LOCAL provider must NOT call save_notification with DATA_RISK."""
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=True, storage=mock_storage)
        scanner._scan_one("EURUSD", "M1")

        for call in mock_storage.save_notification.call_args_list:
            kwargs = call[0][0] if call[0] else call[1]
            self.assertNotEqual(
                kwargs.get("category"), "DATA_RISK",
                "Local provider must NOT produce DATA_RISK notification"
            )

    # ------------------------------------------------------------------
    # Case 3: M5 + non-local provider → no warning (only M1 is restricted)
    # ------------------------------------------------------------------

    @patch("core_brain.scanner.logger")
    def test_no_warning_when_m5_and_non_local(self, mock_logger):
        """M5 + non-local provider must NOT emit a DATA_RISK warning."""
        scanner = _build_scanner(is_local=False, timeframes=["M5"])

        scanner._scan_one("EURUSD", "M5")

        warning_calls = [
            call for call in mock_logger.warning.call_args_list
            if "DATA_RISK" in str(call)
        ]
        self.assertEqual(
            len(warning_calls), 0,
            "M5 with non-local provider must NOT emit DATA_RISK warning"
        )

    def test_no_notification_when_m5_and_non_local(self):
        """M5 + non-local provider must NOT call save_notification with DATA_RISK."""
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=False, storage=mock_storage, timeframes=["M5"])

        scanner._scan_one("EURUSD", "M5")

        for call in mock_storage.save_notification.call_args_list:
            kwargs = call[0][0] if call[0] else call[1]
            self.assertNotEqual(
                kwargs.get("category"), "DATA_RISK",
                "M5 non-local must NOT produce DATA_RISK notification"
            )

    # ------------------------------------------------------------------
    # Case 4: M1 + non-local + storage=None → no crash
    # ------------------------------------------------------------------

    def test_no_crash_when_storage_is_none(self):
        """DATA_RISK path must not raise even if storage is None."""
        scanner = _build_scanner(is_local=False, storage=None)
        scanner.storage = None  # explicitly None
        try:
            scanner._scan_one("EURUSD", "M1")
        except Exception as exc:
            self.fail(f"_scan_one raised unexpectedly with storage=None: {exc}")

    # ------------------------------------------------------------------
    # Case 5: M1 + non-local + save_notification raises → scan still returns
    # ------------------------------------------------------------------

    def test_scan_returns_result_even_if_save_notification_fails(self):
        """Storage failure in DATA_RISK path must not abort the scan."""
        mock_storage = MagicMock()
        mock_storage.save_notification.side_effect = Exception("DB offline")

        scanner = _build_scanner(is_local=False, storage=mock_storage)
        result = scanner._scan_one("EURUSD", "M1")

        # Must still return a valid tuple (scan completed successfully)
        self.assertIsNotNone(result, "Scan must complete and return result even if notification fails")

    # ------------------------------------------------------------------
    # Case 6: Throttle — second immediate call must NOT re-notify
    # ------------------------------------------------------------------

    def test_notification_not_repeated_within_60s(self):
        """Second call within 60s must NOT call save_notification again (throttle)."""
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=False, storage=mock_storage)

        # First call — should notify
        scanner._scan_one("EURUSD", "M1")
        first_count = mock_storage.save_notification.call_count
        self.assertEqual(first_count, 1, "First scan must trigger one DATA_RISK notification")

        # Immediately second call — throttled, must NOT notify again
        scanner._scan_one("EURUSD", "M1")
        second_count = mock_storage.save_notification.call_count
        self.assertEqual(
            second_count, 1,
            "Second scan within 60s must NOT re-trigger DATA_RISK notification (throttle)"
        )

    def test_notification_fires_after_throttle_window(self):
        """After 60s throttle window, notification must fire again."""
        import time as _time
        mock_storage = MagicMock()
        scanner = _build_scanner(is_local=False, storage=mock_storage)

        # First call — should notify
        scanner._scan_one("EURUSD", "M1")
        self.assertEqual(mock_storage.save_notification.call_count, 1)

        # Simulate 61s elapsed by manually resetting the throttle dict
        scanner._data_risk_last_notif.clear()  # expires throttle

        # Should notify again
        scanner._scan_one("EURUSD", "M1")
        self.assertEqual(
            mock_storage.save_notification.call_count, 2,
            "After throttle window expires, DATA_RISK notification must fire again"
        )


if __name__ == "__main__":
    unittest.main()
