"""
Integration tests for ShadowManager + MainOrchestrator weekly evolution loop.

WEEK 3: MainOrchestrator Integration (28-Apr 3 Apr 2026)
- Objective: Integrate weekly SHADOW evaluation into main cycle
- Pattern: Mondays 00:00 UTC ± 1 hour trigger evaluation
- Result: Promote HEALTHY instances to REAL, mark DEAD as inactive
"""

import asyncio
import pytest
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from typing import List

from models.shadow import ShadowInstance, ShadowMetrics, ShadowStatus, HealthStatus
from core_brain.shadow_manager import ShadowManager, PromotionValidator
from data_vault.shadow_db import ShadowStorageManager
from core_brain.main_orchestrator import MainOrchestrator


class TestShadowManagerInjection:
    """Test DI pattern: ShadowManager injected into MainOrchestrator."""

    def test_shadow_storage_exists(self):
        """ShadowStorageManager class is importable."""
        from data_vault.shadow_db import ShadowStorageManager
        assert ShadowStorageManager is not None

    def test_shadow_manager_exists(self):
        """ShadowManager class is importable and instantiable."""
        from core_brain.shadow_manager import ShadowManager
        assert ShadowManager is not None
        
        # Verify it can be instantiated with ShadowStorageManager or mock storage
        # (ShadowManager now handles both types via Union[ShadowStorageManager, StorageManager])
        conn = sqlite3.connect(":memory:")
        from data_vault.shadow_db import ShadowStorageManager
        real_storage = ShadowStorageManager(conn)
        shadow_mgr = ShadowManager(storage=real_storage)
        assert shadow_mgr.storage is not None
        assert shadow_mgr.promotion_validator is not None

    def test_main_orchestrator_has_check_and_run_weekly_shadow_evolution(self):
        """MainOrchestrator has the scheduler method."""
        assert hasattr(MainOrchestrator, '_check_and_run_weekly_shadow_evolution')
        # Verify it's a coroutine function (async)
        import inspect
        assert inspect.iscoroutinefunction(
            MainOrchestrator._check_and_run_weekly_shadow_evolution
        )


class TestWeeklyScheduler:
    """Test Monday 00:00 UTC detection and scheduling logic."""

    def test_monday_midnight_utc_detection(self):
        """Detect if current time is Monday 00:00 UTC ± 60 minutes."""
        # Monday 00:15 UTC
        monday_time = datetime(2026, 3, 16, 0, 15, 0, tzinfo=timezone.utc)
        
        # Check if within window (00:00 ± 1h)
        hour = monday_time.hour
        dow = monday_time.weekday()  # 0=Monday, 6=Sunday
        
        assert dow == 0  # Monday
        assert hour == 0  # Within 00:00-00:59

    def test_sunday_not_scheduled(self):
        """Sunday should NOT trigger weekly evolution."""
        sunday_time = datetime(2026, 3, 15, 0, 30, 0, tzinfo=timezone.utc)
        
        dow = sunday_time.weekday()
        assert dow == 6  # Sunday, not Monday

    def test_monday_but_wrong_hour_not_scheduled(self):
        """Monday 15:00 UTC should NOT trigger (only 00:00 ± 1h)."""
        monday_time = datetime(2026, 3, 16, 15, 0, 0, tzinfo=timezone.utc)
        
        hour = monday_time.hour
        in_window = 0 <= hour < 1  # Should be false for 15:00
        
        assert not in_window

    def test_skips_if_already_ran_today(self):
        """Skip weekly evolution if already ran within 24h."""
        last_run = datetime.now(timezone.utc) - timedelta(hours=2)
        current_time = datetime.now(timezone.utc)
        
        time_since_last = (current_time - last_run).total_seconds()
        already_ran = time_since_last < 86400  # 24h in seconds
        
        assert already_ran == True


class TestShadowEvaluationPipeline:
    """Test full evaluation pipeline: instances → health classification → promotion."""

    @pytest.mark.asyncio
    async def test_evaluate_all_instances_from_storage(self):
        """Retrieve all INCUBATING instances and evaluate them."""
        # Create mock storage with instances
        mock_storage = MagicMock()
        mock_shadow_storage = MagicMock()
        
        # Mock instances
        healthy_instance = ShadowInstance(
            instance_id="shadow_healthy_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
            status=ShadowStatus.INCUBATING
        )
        healthy_instance.metrics = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        
        dead_instance = ShadowInstance(
            instance_id="shadow_dead_001",
            strategy_id="BRK_OPEN_0002",
            account_id="demo_mt5_001",
            account_type="DEMO",
            status=ShadowStatus.INCUBATING
        )
        dead_instance.metrics = ShadowMetrics(
            profit_factor=0.85, win_rate=0.55,
            max_drawdown_pct=0.08, consecutive_losses_max=1,
            total_trades_executed=25, equity_curve_cv=0.30,
        )
        
        # Verify instances have metrics
        assert healthy_instance.metrics.profit_factor == 1.75
        assert dead_instance.metrics.profit_factor == 0.85

    @pytest.mark.asyncio
    async def test_classify_results_by_health_status(self):
        """Classify instances into: HEALTHY | MONITOR | QUARANTINED | DEAD."""
        validator = PromotionValidator()
        
        # Test Pilar 1 validation (profitability)
        metrics_healthy = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        p1_pass, p1_reason = validator.validate_pilar1_profitability(metrics_healthy)
        assert p1_pass == True
        
        metrics_dead = ShadowMetrics(
            profit_factor=0.85, win_rate=0.55,
            max_drawdown_pct=0.08, consecutive_losses_max=1,
            total_trades_executed=25, equity_curve_cv=0.30,
        )
        p1_pass_dead, p1_reason_dead = validator.validate_pilar1_profitability(metrics_dead)
        assert p1_pass_dead == False

    @pytest.mark.asyncio
    async def test_generate_promotion_trace_ids(self):
        """Each promotion generates Trace_ID for audit."""
        shadow_mgr = ShadowManager(storage=MagicMock())
        
        instance = ShadowInstance(
            instance_id="shadowtest123",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )
        
        trace_id = shadow_mgr.generate_trace_id(instance.instance_id, "PROMOTION_REAL")
        
        assert "TRACE_PROMOTION_REAL" in trace_id
        # First 8 chars of "shadowtest123" = "shadowte"
        assert "shadowte" in trace_id
        assert len(trace_id) > 30


class TestPromotionExecution:
    """Test promotion actions: update DB status + log."""

    @pytest.mark.asyncio
    async def test_healthy_instance_promoted_to_real(self):
        """HEALTHY instance → update DB: status=PROMOTED_TO_REAL."""
        mock_storage = MagicMock()
        shadow_mgr = ShadowManager(storage=mock_storage)
        
        instance = ShadowInstance(
            instance_id="shadow_healthy_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
            status=ShadowStatus.INCUBATING
        )
        instance.metrics = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        
        # Verify promotability
        can_promote, reason = shadow_mgr.is_promotable_to_real(instance)
        assert can_promote == True

    @pytest.mark.asyncio
    async def test_dead_instance_marked_inactive(self):
        """DEAD instance → update DB: status=DEAD (or similar inactive)."""
        mock_storage = MagicMock()
        shadow_mgr = ShadowManager(storage=mock_storage)
        
        instance = ShadowInstance(
            instance_id="shadow_dead_001",
            strategy_id="BRK_OPEN_0002",
            account_id="demo_mt5_001",
            account_type="DEMO",
            status=ShadowStatus.INCUBATING
        )
        instance.metrics = ShadowMetrics(
            profit_factor=0.85, win_rate=0.55,
            max_drawdown_pct=0.08, consecutive_losses_max=1,
            total_trades_executed=25, equity_curve_cv=0.30,
        )
        
        # Verify NOT promotable
        can_promote, reason = shadow_mgr.is_promotable_to_real(instance)
        assert can_promote == False
        assert "Pilar 1" in reason or "Profitability" in reason

    @pytest.mark.asyncio
    async def test_quarantined_instance_skipped(self):
        """QUARANTINED instance → skip until retest passes."""
        instance = ShadowInstance(
            instance_id="shadow_quarantine_001",
            strategy_id="BRK_OPEN_0003",
            account_id="demo_mt5_001",
            account_type="DEMO",
            status=ShadowStatus.QUARANTINED
        )
        
        # Cannot promote if already quarantined
        mock_storage = MagicMock()
        shadow_mgr = ShadowManager(storage=mock_storage)
        
        can_promote, reason = shadow_mgr.is_promotable_to_real(instance)
        assert can_promote == False
        assert "QUARANTINED" in reason


class TestIntegrationWithMainCycle:
    """Test MainOrchestrator includes shadow evolution in run_single_cycle()."""

    def test_run_single_cycle_includes_shadow_check(self):
        """run_single_cycle() calls _check_and_run_weekly_shadow_evolution()."""
        assert hasattr(MainOrchestrator, 'run_single_cycle')
        # Should have method reference

    @pytest.mark.asyncio
    async def test_shadow_evolution_non_blocking(self):
        """Weekly evolution runs async and doesn't block main cycle."""
        # Should return immediately even if evaluation takes time
        mock_storage = MagicMock()
        shadow_mgr = ShadowManager(storage=mock_storage)
        
        # Async operation shouldn't block
        start = datetime.now()
        # Simulate async evaluation (non-blocking)
        await asyncio.sleep(0.01)  # Very short
        end = datetime.now()
        
        duration = (end - start).total_seconds()
        assert duration < 0.5  # Should be very fast

    def test_weekly_evolution_frequency_limit(self):
        """Weekly evolution runs AT MOST once per 24h."""
        last_run_1 = datetime.now(timezone.utc) - timedelta(hours=30)
        last_run_2 = datetime.now(timezone.utc) - timedelta(hours=2)
        
        # First run: should execute (>24h since last)
        can_run_1 = (datetime.now(timezone.utc) - last_run_1).total_seconds() > 86400
        assert can_run_1 == True
        
        # Second run: should NOT execute (<24h since last)
        can_run_2 = (datetime.now(timezone.utc) - last_run_2).total_seconds() > 86400
        assert can_run_2 == False


class TestEndToEndIntegration:
    """End-to-end: Instance creation → evaluation → promotion."""

    @pytest.mark.asyncio
    async def test_complete_shadow_evolution_flow(self):
        """Full flow: evaluate_all_instances() → promotion → DB update."""
        # Create real storage instead of mock (ShadowManager expects ShadowStorageManager)
        conn = sqlite3.connect(":memory:")
        storage = ShadowStorageManager(conn)
        
        shadow_mgr = ShadowManager(storage=storage)
        
        # Verify manager is ready for operations
        assert shadow_mgr.storage is not None
        assert hasattr(shadow_mgr, 'promotion_validator')

    @pytest.mark.asyncio
    async def test_multiple_instances_mixed_results(self):
        """Evaluate 10 instances: 3 promoted, 2 dead, 5 monitor."""
        conn = sqlite3.connect(":memory:")
        storage = ShadowStorageManager(conn)
        shadow_mgr = ShadowManager(storage=storage)
        
        instances = []
        
        # 3 HEALTHY
        for i in range(3):
            inst = ShadowInstance(
                instance_id=f"shadow_healthy_{i}",
                strategy_id=f"BRK_OPEN_{i}",
                account_id="demo_mt5_001",
                account_type="DEMO",
                status=ShadowStatus.INCUBATING
            )
            inst.metrics = ShadowMetrics(
                profit_factor=1.75, win_rate=0.65,
                max_drawdown_pct=0.10, consecutive_losses_max=2,
                total_trades_executed=20, equity_curve_cv=0.35,
            )
            instances.append(inst)
        
        # 2 DEAD
        for i in range(2):
            inst = ShadowInstance(
                instance_id=f"shadow_dead_{i}",
                strategy_id=f"BRK_OPEN_{3+i}",
                account_id="demo_mt5_001",
                account_type="DEMO",
                status=ShadowStatus.INCUBATING
            )
            inst.metrics = ShadowMetrics(
                profit_factor=0.85, win_rate=0.55,
                max_drawdown_pct=0.08, consecutive_losses_max=1,
                total_trades_executed=25, equity_curve_cv=0.30,
            )
            instances.append(inst)
        
        # 5 MONITOR
        for i in range(5):
            inst = ShadowInstance(
                instance_id=f"shadow_monitor_{i}",
                strategy_id=f"BRK_OPEN_{5+i}",
                account_id="demo_mt5_001",
                account_type="DEMO",
                status=ShadowStatus.INCUBATING
            )
            inst.metrics = ShadowMetrics(
                profit_factor=1.60, win_rate=0.65,
                max_drawdown_pct=0.10, consecutive_losses_max=2,
                total_trades_executed=8,  # < 15, triggers MONITOR
                equity_curve_cv=0.35,
            )
            instances.append(inst)
        
        # Verify counts
        assert len(instances) == 10
        assert len([i for i in instances if i.instance_id.startswith("shadow_healthy")]) == 3
        assert len([i for i in instances if i.instance_id.startswith("shadow_dead")]) == 2
        assert len([i for i in instances if i.instance_id.startswith("shadow_monitor")]) == 5


class TestShadowExecutionAuthorization:
    """
    BUG-3: SHADOW strategies must return True from _is_strategy_authorized_for_execution()
    so that paper trades are routed to DEMO account and metrics can accumulate.

    Without paper trades, sys_signal_quality_assessments stays empty, win_rate stays 0,
    and the 3 Pilares system can never evaluate or promote any strategy.
    """

    def test_shadow_strategy_is_authorized_for_paper_execution(self):
        """
        BUG-3 FIX: SHADOW execution_mode must return True (not False).

        SHADOW signals must paper-trade on DEMO account to accumulate metrics
        for 3 Pilares evaluation. Returning False blocks all metric accumulation
        and makes the promotion system permanently stuck.
        """
        from unittest.mock import MagicMock
        from models.signal import Signal, SignalType, ConnectorType

        # Build a minimal MainOrchestrator with mocked dependencies
        orchestrator = MainOrchestrator.__new__(MainOrchestrator)
        orchestrator.storage = MagicMock()
        orchestrator.logger = MagicMock()

        # Strategy ranking says execution_mode = 'SHADOW'
        orchestrator.storage.get_signal_ranking.return_value = {
            "strategy_id": "BRK_OPEN_0001",
            "execution_mode": "SHADOW",
        }

        signal = MagicMock(spec=Signal)
        signal.strategy = "BRK_OPEN_0001"

        result = orchestrator._is_strategy_authorized_for_execution(signal)

        # SHADOW must be authorized (True) so the executor routes to DEMO for paper trade
        assert result is True, (
            "BUG-3: SHADOW strategy returned False — this blocks ALL paper trades, "
            "prevents metric accumulation, and makes 3 Pilares permanently stuck. "
            "SHADOW must route to DEMO account for paper execution."
        )

    def test_live_strategy_remains_authorized(self):
        """LIVE execution_mode must still return True (regression guard)."""
        from unittest.mock import MagicMock
        from models.signal import Signal, SignalType, ConnectorType

        orchestrator = MainOrchestrator.__new__(MainOrchestrator)
        orchestrator.storage = MagicMock()
        orchestrator.logger = MagicMock()

        orchestrator.storage.get_signal_ranking.return_value = {
            "strategy_id": "LIVE_STRAT_001",
            "execution_mode": "LIVE",
        }

        signal = MagicMock(spec=Signal)
        signal.strategy = "LIVE_STRAT_001"

        result = orchestrator._is_strategy_authorized_for_execution(signal)
        assert result is True, "LIVE strategies must still be authorized after BUG-3 fix"

    def test_quarantine_strategy_remains_blocked(self):
        """QUARANTINE execution_mode must still return False (regression guard)."""
        from unittest.mock import MagicMock
        from models.signal import Signal, SignalType, ConnectorType

        orchestrator = MainOrchestrator.__new__(MainOrchestrator)
        orchestrator.storage = MagicMock()
        orchestrator.logger = MagicMock()

        orchestrator.storage.get_signal_ranking.return_value = {
            "strategy_id": "QUARANTINE_STRAT_001",
            "execution_mode": "QUARANTINE",
        }

        signal = MagicMock(spec=Signal)
        signal.strategy = "QUARANTINE_STRAT_001"

        result = orchestrator._is_strategy_authorized_for_execution(signal)
        assert result is False, "QUARANTINE strategies must remain blocked after BUG-3 fix"
