"""Contract tests for known audit bugs (HU 10.13).

Audit reference date: 2026-03-27.
These tests protect behavior contracts so regressions are detected early.
"""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_brain.shadow_manager import ShadowManager
from core_brain.strategy_ranker import StrategyRanker
from core_brain.orchestrators import _background_tasks
from models.shadow import ShadowInstance, ShadowMetrics


class _DummyOrchestrator:
    """Minimal orchestrator stub for background task contract tests."""

    def __init__(self, shadow_manager: MagicMock):
        self.shadow_manager = shadow_manager
        self.last_shadow_evolution = None
        self.user_id = "SYSTEM"
        self.thought_callback = None


class TestContractsKnownBugs:
    def test_contract_pilar3_min_trades_uses_dynamic_threshold(self) -> None:
        """Given pilar3_min_trades=5, 8 trades must not fail Pilar 3 by legacy 15 threshold."""
        storage = MagicMock()

        instance = ShadowInstance(
            instance_id="inst-001",
            strategy_id="STRAT_A",
            account_id="DEMO-1",
            account_type="DEMO",
        )
        storage.list_active_instances.return_value = [instance]
        storage.calculate_instance_metrics_from_sys_trades.return_value = ShadowMetrics(
            profit_factor=1.8,
            win_rate=0.65,
            max_drawdown_pct=0.08,
            consecutive_losses_max=2,
            equity_curve_cv=0.25,
            total_trades_executed=8,
        )
        storage.record_performance_snapshot.return_value = None
        storage.update_shadow_instance.return_value = None
        storage.log_promotion_decision.return_value = None
        storage.update_strategy_score_shadow.return_value = None

        manager = ShadowManager(storage=MagicMock(), pilar3_min_trades=5)
        manager.storage = storage
        result = manager.evaluate_all_instances()

        assert len(result["promotions"]) == 1
        assert len(result["monitors"]) == 0

    def test_contract_strategy_ranker_live_rehabilitation_transition(self) -> None:
        """LIVE degradation contract: transition is rehabilitation LIVE->SHADOW."""
        storage = MagicMock()
        storage.get_signal_ranking.return_value = {
            "strategy_id": "STRAT_LIVE",
            "execution_mode": "LIVE",
            "drawdown_max": 4.0,
            "consecutive_losses": 1,
            "total_usr_trades": 120,
        }
        storage.update_strategy_execution_mode.return_value = "TRACE-RANK-001"
        storage.log_strategy_state_change.return_value = None
        storage.get_regime_weights.return_value = {
            "win_rate": Decimal("0.25"),
            "sharpe_ratio": Decimal("0.35"),
            "profit_factor": Decimal("0.30"),
            "drawdown_max": Decimal("0.10"),
        }

        ranker = StrategyRanker(storage=storage)

        with patch.object(ranker, "_degrade_strategy", wraps=ranker._degrade_strategy) as degrade_spy:
            result = ranker.evaluate_and_rank("STRAT_LIVE")

        assert result["action"] == "rehabilitated"
        assert result["from_mode"] == "LIVE"
        assert result["to_mode"] == "SHADOW"
        degrade_spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_contract_shadow_ws_emits_real_metrics_not_zero(self) -> None:
        """SHADOW_STATUS_UPDATE must publish real metrics, not hardcoded zeros."""
        shadow_manager = MagicMock()
        shadow_manager.evaluate_all_instances.return_value = {
            "promotions": [
                {
                    "instance_id": "inst-01",
                    "strategy_id": "STRAT_WS",
                    "trace_id": "TRACE_WS_001",
                    "metrics": {
                        "profit_factor": 1.9,
                        "win_rate": 0.61,
                        "max_drawdown_pct": 0.07,
                        "consecutive_losses_max": 2,
                        "trade_count": 18,
                    },
                }
            ],
            "kills": [],
            "quarantines": [],
            "monitors": [],
        }

        orch = _DummyOrchestrator(shadow_manager=shadow_manager)

        with patch.object(
            _background_tasks,
            "emit_shadow_status_update",
            new_callable=AsyncMock,
        ) as emit_mock:
            await _background_tasks.check_and_run_weekly_shadow_evolution(orch)

        emit_mock.assert_awaited_once()
        call_args = emit_mock.await_args.args
        emitted_metrics = call_args[6]
        assert emitted_metrics["profit_factor"] > 0
        assert emitted_metrics["win_rate"] > 0

    def test_contract_evaluate_and_rank_exposes_weighted_score(self) -> None:
        """evaluate_and_rank must expose weighted_score from calculate_weighted_score()."""
        storage = MagicMock()
        storage.get_signal_ranking.return_value = {
            "strategy_id": "STRAT_SCORE",
            "execution_mode": "SHADOW",
            "profit_factor": 1.2,
            "win_rate": 0.51,
            "completed_last_50": 10,
        }
        storage.get_regime_weights.return_value = {
            "win_rate": Decimal("0.25"),
            "sharpe_ratio": Decimal("0.35"),
            "profit_factor": Decimal("0.30"),
            "drawdown_max": Decimal("0.10"),
        }

        ranker = StrategyRanker(storage=storage)

        with patch.object(
            ranker,
            "calculate_weighted_score",
            return_value=Decimal("0.7777"),
        ) as weighted_spy:
            result = ranker.evaluate_and_rank("STRAT_SCORE")

        weighted_spy.assert_called_once()
        assert result["weighted_score"] == 0.7777
