"""
N1-5: Test — StrategyGatekeeper DI wiring in MainOrchestrator.

TDD Red Phase: these tests MUST FAIL before implementation.

Validates:
  1. MainOrchestrator.__init__ accepts `strategy_gatekeeper` parameter
  2. `self.strategy_gatekeeper` is stored correctly
  3. run_single_cycle calls gatekeeper.can_execute_on_tick for each signal
  4. Signals vetoed by gatekeeper are counted in stats.usr_signals_vetoed
  5. A None gatekeeper is safe (no crash, all signals proceed)
  6. Gatekeeper veto does NOT call executor
"""
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone

from models.signal import Signal, SignalType, ConnectorType
from core_brain.main_orchestrator import MainOrchestrator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(symbol: str = "EURUSD", strategy_id: str = "strat-001") -> Signal:
    return Signal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        confidence=0.80,
        connector_type=ConnectorType.PAPER,
        strategy_id=strategy_id,
    )


def _make_orchestrator(gatekeeper=None):
    """Build a minimal MainOrchestrator with required DI, no real broker."""
    from core_brain.main_orchestrator import MainOrchestrator

    mock_scanner = MagicMock()
    mock_scanner.scan.return_value = []

    mock_storage = MagicMock()
    mock_storage.get_global_modules_enabled.return_value = {
        "executor": True, "position_manager": True
    }
    mock_storage.count_executed_usr_signals.return_value = 0
    mock_storage.get_session_state.return_value = None
    mock_storage.update_module_heartbeat.return_value = None
    mock_storage.get_dynamic_params.return_value = {}
    mock_storage.get_strategy_affinity_scores.return_value = {}
    mock_storage.get_sys_broker_accounts.return_value = []
    mock_storage.get_recent_signals.return_value = []

    mock_risk = MagicMock()
    mock_risk.validate_signal.return_value = True
    mock_risk.is_lockdown_active.return_value = False

    mock_executor = MagicMock()
    mock_executor.submit.return_value = None

    orchestrator = MainOrchestrator(
        scanner=mock_scanner,
        storage=mock_storage,
        risk_manager=mock_risk,
        executor=mock_executor,
        strategy_gatekeeper=gatekeeper,
    )
    return orchestrator, mock_storage, mock_risk, mock_executor


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

class TestStrategyGatekeeperWiring(unittest.TestCase):

    def setUp(self):
        # Patch CPU so the CPU-veto gate in run_single_cycle() never fires
        # regardless of host load during the test run.
        self._cpu_patch = patch("psutil.cpu_percent", return_value=10.0)
        self._cpu_patch.start()
        # Patch _check_and_run_daily_backtest to avoid real HTTP requests via
        # BacktestOrchestrator.run_pending_strategies() → DataProviderManager.fetch_ohlc()
        self._daily_backtest_patch = patch.object(
            MainOrchestrator,
            "_check_and_run_daily_backtest",
            new_callable=AsyncMock,
        )
        self._daily_backtest_patch.start()
        # Patch _is_market_closed so MARKET-GUARD never skips cycles on weekends
        self._market_patch = patch.object(
            MainOrchestrator,
            "_is_market_closed",
            return_value=False,
        )
        self._market_patch.start()

    def tearDown(self):
        self._cpu_patch.stop()
        self._daily_backtest_patch.stop()
        self._market_patch.stop()

    # ------------------------------------------------------------------
    # 1. DI acceptance in __init__
    # ------------------------------------------------------------------

    def test_orchestrator_accepts_gatekeeper_parameter(self):
        """MainOrchestrator.__init__ must accept strategy_gatekeeper kwarg."""
        mock_gatekeeper = MagicMock()
        try:
            orchestrator, _, _, _ = _make_orchestrator(gatekeeper=mock_gatekeeper)
        except TypeError as exc:
            self.fail(f"MainOrchestrator.__init__ rejected strategy_gatekeeper: {exc}")

    def test_gatekeeper_stored_on_instance(self):
        """self.strategy_gatekeeper must hold the injected instance."""
        mock_gatekeeper = MagicMock()
        orchestrator, _, _, _ = _make_orchestrator(gatekeeper=mock_gatekeeper)
        self.assertIs(
            orchestrator.strategy_gatekeeper, mock_gatekeeper,
            "strategy_gatekeeper must be accessible via orchestrator.strategy_gatekeeper"
        )

    def test_gatekeeper_none_by_default(self):
        """If not provided, strategy_gatekeeper defaults to None."""
        orchestrator, _, _, _ = _make_orchestrator(gatekeeper=None)
        self.assertIsNone(
            orchestrator.strategy_gatekeeper,
            "strategy_gatekeeper must be None if not injected"
        )

    # ------------------------------------------------------------------
    # 2. run_single_cycle calls gatekeeper for approved signals
    # ------------------------------------------------------------------

    def test_run_single_cycle_calls_gatekeeper_for_each_signal(self):
        """Gatekeeper.can_execute_on_tick_with_reason must be called once per approved signal."""
        mock_gatekeeper = MagicMock()
        mock_gatekeeper.can_execute_on_tick_with_reason.return_value = (True, "gk_approved")  # permit all

        orchestrator, mock_storage, mock_risk, _ = _make_orchestrator(gatekeeper=mock_gatekeeper)

        signals = [_make_signal("EURUSD", "strat-001"), _make_signal("GBPUSD", "strat-002")]

        # Patch the signal factory and internal pipeline
        orchestrator._signal_factory = MagicMock()
        orchestrator._signal_factory.generate_usr_signals_batch = AsyncMock(return_value=signals)
        orchestrator._econ_veto_symbols = set()
        orchestrator._econ_caution_symbols = set()

        # Patch deduplication and other async operations to pass-through
        orchestrator.signal_selector = MagicMock()
        orchestrator.signal_selector.should_operate_signal.return_value = (
            MagicMock(value="APPROVE"), {"reason": "ok"}
        )
        orchestrator.cooldown_manager = MagicMock()
        orchestrator.cooldown_manager.is_in_cooldown.return_value = False

        # Patch scanner scan
        orchestrator.scanner.scan.return_value = [
            ("EURUSD", "M5", MagicMock(), {}, MagicMock(), "mock"),
            ("GBPUSD", "M5", MagicMock(), {}, MagicMock(), "mock"),
        ]

        # Patch economic integration to skip
        orchestrator.economic_integration = None

        asyncio.run(orchestrator.run_single_cycle())

        gatekeeper_calls = mock_gatekeeper.can_execute_on_tick_with_reason.call_count
        self.assertEqual(
            gatekeeper_calls, len(signals),
            f"Expected {len(signals)} gatekeeper calls, got {gatekeeper_calls}"
        )

    # ------------------------------------------------------------------
    # 3. Vetoed signals are NOT sent to executor
    # ------------------------------------------------------------------

    def test_vetoed_signal_does_not_reach_executor(self):
        """Signal vetoed by gatekeeper must NOT be sent to executor.submit."""
        mock_gatekeeper = MagicMock()
        mock_gatekeeper.can_execute_on_tick_with_reason.return_value = (False, "gk_whitelist_reject")  # veto ALL

        orchestrator, mock_storage, mock_risk, mock_executor = _make_orchestrator(gatekeeper=mock_gatekeeper)

        signals = [_make_signal("EURUSD")]

        orchestrator._signal_factory = MagicMock()
        orchestrator._signal_factory.generate_usr_signals_batch = AsyncMock(return_value=signals)
        orchestrator._econ_veto_symbols = set()
        orchestrator._econ_caution_symbols = set()
        orchestrator.signal_selector = MagicMock()
        orchestrator.signal_selector.should_operate_signal.return_value = (
            MagicMock(value="APPROVE"), {"reason": "ok"}
        )
        orchestrator.cooldown_manager = MagicMock()
        orchestrator.cooldown_manager.is_in_cooldown.return_value = False
        orchestrator.scanner.scan.return_value = [
            ("EURUSD", "M5", MagicMock(), {}, MagicMock(), "mock"),
        ]
        orchestrator.economic_integration = None

        asyncio.run(orchestrator.run_single_cycle())

        mock_executor.submit.assert_not_called()

    # ------------------------------------------------------------------
    # 4. Vetoed signal increments stats counter
    # ------------------------------------------------------------------

    def test_vetoed_signal_increments_vetoed_counter(self):
        """Signals vetoed by gatekeeper must increment stats.usr_signals_vetoed."""
        mock_gatekeeper = MagicMock()
        mock_gatekeeper.can_execute_on_tick_with_reason.return_value = (False, "gk_whitelist_reject")  # veto ALL

        orchestrator, mock_storage, mock_risk, mock_executor = _make_orchestrator(gatekeeper=mock_gatekeeper)

        signals = [_make_signal("EURUSD"), _make_signal("GBPUSD")]
        orchestrator._signal_factory = MagicMock()
        orchestrator._signal_factory.generate_usr_signals_batch = AsyncMock(return_value=signals)
        orchestrator._econ_veto_symbols = set()
        orchestrator._econ_caution_symbols = set()
        orchestrator.signal_selector = MagicMock()
        orchestrator.signal_selector.should_operate_signal.return_value = (
            MagicMock(value="APPROVE"), {"reason": "ok"}
        )
        orchestrator.cooldown_manager = MagicMock()
        orchestrator.cooldown_manager.is_in_cooldown.return_value = False
        orchestrator.scanner.scan.return_value = [
            ("EURUSD", "M5", MagicMock(), {}, MagicMock(), "mock"),
            ("GBPUSD", "M5", MagicMock(), {}, MagicMock(), "mock"),
        ]
        orchestrator.economic_integration = None

        initial_vetoed = orchestrator.stats.usr_signals_vetoed
        asyncio.run(orchestrator.run_single_cycle())

        self.assertGreater(
            orchestrator.stats.usr_signals_vetoed, initial_vetoed,
            "Vetoed signals must increment stats.usr_signals_vetoed"
        )

    # ------------------------------------------------------------------
    # 5. None gatekeeper: no crash, signals proceed to executor
    # ------------------------------------------------------------------

    def test_no_crash_when_gatekeeper_is_none(self):
        """run_single_cycle must not crash if strategy_gatekeeper is None."""
        orchestrator, mock_storage, mock_risk, _ = _make_orchestrator(gatekeeper=None)

        orchestrator._signal_factory = MagicMock()
        orchestrator._signal_factory.generate_usr_signals_batch = AsyncMock(
            return_value=[_make_signal("EURUSD")]
        )
        orchestrator._econ_veto_symbols = set()
        orchestrator._econ_caution_symbols = set()
        orchestrator.signal_selector = MagicMock()
        orchestrator.signal_selector.should_operate_signal.return_value = (
            MagicMock(value="APPROVE"), {"reason": "ok"}
        )
        orchestrator.cooldown_manager = MagicMock()
        orchestrator.cooldown_manager.is_in_cooldown.return_value = False
        orchestrator.scanner.scan.return_value = [
            ("EURUSD", "M5", MagicMock(), {}, MagicMock(), "mock"),
        ]
        orchestrator.economic_integration = None

        try:
            asyncio.run(orchestrator.run_single_cycle())
        except Exception as exc:
            self.fail(f"run_single_cycle crashed with gatekeeper=None: {exc}")


if __name__ == "__main__":
    unittest.main()
