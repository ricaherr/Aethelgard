import pytest
from datetime import date, datetime, timezone, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from core_brain.orchestrators._cycle_trade import run_execute_phase
from core_brain.orchestrators._types import ScanBundle
from core_brain.signal_selector import SignalSelectorResult


def _build_orchestrator() -> SimpleNamespace:
    storage = MagicMock()
    storage.get_recent_sys_signals.return_value = []
    storage.update_module_heartbeat.return_value = None
    storage.get_sys_config.return_value = {}

    orch = SimpleNamespace()
    orch.storage = storage
    orch.stats = SimpleNamespace(
        date=date.today(),
        usr_signals_processed=0,
        usr_signals_executed=0,
        cycles_completed=0,
        errors_count=0,
        scans_total=0,
        usr_signals_generated=0,
        usr_signals_risk_passed=0,
        usr_signals_vetoed=0,
    )
    orch.volatility_zscore = 0.0
    orch.regime_classifier = None
    orch.signal_selector = SimpleNamespace(should_operate_signal=AsyncMock())
    orch.executor = SimpleNamespace(
        execute_signal=AsyncMock(return_value=False),
        persists_usr_signals=False,
        last_execution_response=None,
        last_rejection_reason="",
    )
    orch.thought_callback = None
    orch.signal_quality_scorer = None
    orch.signal_review_manager = None
    orch.execution_feedback_collector = SimpleNamespace(record_failure=AsyncMock())
    orch.cooldown_manager = SimpleNamespace(apply_cooldown=AsyncMock(return_value={"cooldown_minutes": 1, "retry_count": 1}))
    orch._check_closed_usr_positions = AsyncMock()
    orch._last_ranking_cycle = datetime.now(timezone.utc)
    orch._ranking_interval = 999999
    orch.strategy_ranker = SimpleNamespace(evaluate_all_usr_strategies=MagicMock(return_value={}))
    orch._active_usr_signals = []
    orch.coherence_monitor = SimpleNamespace(run_once=MagicMock(return_value=[]))
    orch.heartbeat_monitor = None
    return orch


def _bundle() -> ScanBundle:
    return ScanBundle(
        scan_results_with_data={},
        price_snapshots={},
        scan_results={},
        trace_id="TRACE-CYCLE-001",
    )


@pytest.mark.asyncio
async def test_funnel_counts_dedup_and_cooldown_rejections(monkeypatch) -> None:
    orch = _build_orchestrator()
    orch.signal_selector.should_operate_signal.side_effect = [
        (SignalSelectorResult.REJECT_DUPLICATE, {"reason": "dup"}),
        (SignalSelectorResult.REJECT_COOLDOWN, {"remaining_minutes": 2, "failure_reason": "timeout"}),
    ]

    monkeypatch.setattr(
        "core_brain.orchestrators._cycle_trade.is_strategy_authorized_for_execution",
        lambda _orch, _signal, with_reason=False: (True, "auth_live") if with_reason else True,
    )

    s1 = SimpleNamespace(symbol="EURUSD", signal_type="BUY", timeframe="M5", strategy="S1", connector="paper")
    s2 = SimpleNamespace(symbol="GBPUSD", signal_type="SELL", timeframe="M5", strategy="S2", connector="paper")

    await run_execute_phase(orch, [s1, s2], _bundle())

    funnel = getattr(orch, "_latest_signal_funnel", None)
    assert funnel is not None
    assert funnel["reasons"]["reject_duplicate"] == 1
    assert funnel["reasons"]["reject_cooldown"] == 1


@pytest.mark.asyncio
async def test_execution_failure_is_counted_in_funnel(monkeypatch) -> None:
    orch = _build_orchestrator()
    orch.signal_selector.should_operate_signal.return_value = (
        SignalSelectorResult.OPERATE,
        {"reason": "ok"},
    )

    monkeypatch.setattr(
        "core_brain.orchestrators._cycle_trade.is_strategy_authorized_for_execution",
        lambda _orch, _signal, with_reason=False: (True, "auth_live") if with_reason else True,
    )

    from core_brain.execution_feedback import ExecutionFailureReason

    orch.executor.last_execution_response = SimpleNamespace(
        failure_reason=ExecutionFailureReason.ORDER_REJECTED,
        failure_context={"message": "broker reject"},
    )
    orch.executor.last_rejection_reason = "broker rejected order"

    signal = SimpleNamespace(
        symbol="USDJPY",
        signal_type="BUY",
        timeframe="M5",
        strategy="S3",
        connector="paper",
        id="sig-001",
        signal_id="sig-001",
    )

    await run_execute_phase(orch, [signal], _bundle())

    funnel = getattr(orch, "_latest_signal_funnel", None)
    assert funnel is not None
    assert funnel["stages"]["STAGE_EXECUTION_OUTCOME"]["in"] == 1
    assert funnel["stages"]["STAGE_EXECUTION_OUTCOME"]["out"] == 0
    assert funnel["reasons"].get("executor_failed_broker", 0) == 1
