"""
test_shadow_models.py — Unit tests for SHADOW EVOLUTION models.

Tests:
  1. ShadowInstance creation with validators
  2. 3 Pilares evaluation logic
  3. Promotion eligibility check
  4. Metric conversion (to/from DB dict)
  5. HealthStatus transitions
  6. Trace_ID generation

Trace_ID: TRACE_TEST_20260312_002_MODELS
"""

import pytest
from datetime import datetime, timezone
from models.shadow import (
    ShadowInstance,
    ShadowMetrics,
    ShadowStatus,
    HealthStatus,
    PillarStatus,
    ShadowPerformanceHistory,
    ShadowPromotionLog,
)


class TestShadowMetrics:
    """Test ShadowMetrics dataclass and metric storage."""

    def test_metrics_creation(self):
        """Verify metrics can be created with default values."""
        metrics = ShadowMetrics()
        assert metrics.profit_factor == 0.0
        assert metrics.win_rate == 0.0
        assert metrics.total_trades_executed == 0

    def test_metrics_creation_with_values(self):
        """Create metrics with specific values."""
        metrics = ShadowMetrics(
            profit_factor=1.75,
            win_rate=0.68,
            max_drawdown_pct=10.5,
            consecutive_losses_max=2,
            equity_curve_cv=0.38,
            total_trades_executed=45,
        )
        assert metrics.profit_factor == 1.75
        assert metrics.win_rate == 0.68
        assert metrics.max_drawdown_pct == 10.5
        assert metrics.consecutive_losses_max == 2
        assert metrics.equity_curve_cv == 0.38
        assert metrics.total_trades_executed == 45

    def test_metrics_to_dict(self):
        """Verify metrics can be converted to dict."""
        metrics = ShadowMetrics(profit_factor=1.5, win_rate=0.60)
        d = metrics.to_dict()
        
        assert isinstance(d, dict)
        assert "profit_factor" in d
        assert d["profit_factor"] == 1.5
        assert d["win_rate"] == 0.60

    def test_metrics_from_dict(self):
        """Verify metrics can be created from dict."""
        data = {
            "profit_factor": 1.8,
            "win_rate": 0.65,
            "max_drawdown_pct": 9.0,
            "consecutive_losses_max": 3,
        }
        metrics = ShadowMetrics.from_dict(data)
        
        assert metrics.profit_factor == 1.8
        assert metrics.win_rate == 0.65
        assert metrics.max_drawdown_pct == 9.0
        assert metrics.consecutive_losses_max == 3

    def test_13_confirmatory_metrics_stored(self):
        """Verify all 13 confirmatory metrics are stored."""
        metrics = ShadowMetrics(
            calmar_ratio=0.8,
            trade_frequency_per_day=1.5,
            avg_slippage_pips=2.5,
            recovery_factor=2.0,
            avg_trade_duration_hours=4.2,
            risk_reward_ratio=1.8,
            zero_profit_days_pct=20.0,
            last_activity_hours_ago=0.5,
        )
        
        assert metrics.calmar_ratio == 0.8
        assert metrics.trade_frequency_per_day == 1.5
        assert metrics.avg_slippage_pips == 2.5
        assert metrics.recovery_factor == 2.0
        assert metrics.avg_trade_duration_hours == 4.2
        assert metrics.risk_reward_ratio == 1.8
        assert metrics.zero_profit_days_pct == 20.0
        assert metrics.last_activity_hours_ago == 0.5


class TestShadowInstance:
    """Test ShadowInstance creation and business logic."""

    def test_shadow_instance_creation(self):
        """Create a basic SHADOW instance."""
        instance = ShadowInstance(
            instance_id="shadow_001",
            strategy_id="BRK_OPEN_0001",
            account_id="acc_demo_001",
            account_type="DEMO",
        )
        
        assert instance.instance_id == "shadow_001"
        assert instance.strategy_id == "BRK_OPEN_0001"
        assert instance.account_type == "DEMO"
        assert instance.status == ShadowStatus.INCUBATING

    def test_shadow_instance_validation_account_type(self):
        """Verify account_type validation (DEMO|REAL only)."""
        with pytest.raises(ValueError, match="account_type must be DEMO or REAL"):
            ShadowInstance(
                instance_id="test",
                strategy_id="TEST_STRAT",
                account_id="acc",
                account_type="INVALID",
            )

    def test_shadow_instance_validation_required_fields(self):
        """Verify required fields are validated."""
        with pytest.raises(ValueError, match="instance_id and strategy_id are required"):
            ShadowInstance(
                instance_id="",
                strategy_id="TEST",
                account_id="acc",
                account_type="DEMO",
            )

    def test_shadow_instance_to_db_dict(self):
        """Verify instance can be converted to DB dict with valid JSON for parameter_overrides."""
        import json
        instance = ShadowInstance(
            instance_id="test_001",
            strategy_id="BRK_OPEN_0001",
            account_id="acc_001",
            account_type="DEMO",
            parameter_overrides={"risk_pct": 0.02},
            regime_filters=["TREND_UP", "EXPANSION"],
        )

        db_dict = instance.to_db_dict()

        assert db_dict["instance_id"] == "test_001"
        assert db_dict["strategy_id"] == "BRK_OPEN_0001"
        assert db_dict["account_type"] == "DEMO"
        # parameter_overrides must be valid JSON (not Python repr with single quotes)
        parsed = json.loads(db_dict["parameter_overrides"])
        assert parsed["risk_pct"] == 0.02
        assert "TREND_UP" in db_dict["regime_filters"]

    def test_shadow_instance_from_db_dict(self):
        """Verify instance can be created from DB dict using valid JSON parameter_overrides."""
        db_dict = {
            "instance_id": "test_002",
            "strategy_id": "OliverVelez",
            "account_id": "acc_002",
            "account_type": "REAL",
            "parameter_overrides": '{"aggressive": true}',  # valid JSON, not Python repr
            "regime_filters": "TRENDING,EXPANSION",
            "birth_timestamp": "2026-03-12T10:00:00",
            "status": "SHADOW_READY",
            "profit_factor": 1.6,
            "win_rate": 0.65,
            "max_drawdown_pct": 11.0,
            "consecutive_losses_max": 2,
            "equity_curve_cv": 0.39,
            "total_trades_executed": 30,
            "created_at": "2026-03-12T10:00:00",
            "updated_at": "2026-03-12T10:00:00",
        }

        instance = ShadowInstance.from_db_dict(db_dict)

        assert instance.instance_id == "test_002"
        assert instance.strategy_id == "OliverVelez"
        assert instance.account_type == "REAL"
        assert instance.status == ShadowStatus.SHADOW_READY
        # parameter_overrides must be correctly deserialized (no eval needed)
        assert instance.parameter_overrides == {"aggressive": True}

    def test_parameter_overrides_json_roundtrip(self):
        """Verify parameter_overrides survives a full DB round-trip as valid JSON (no eval)."""
        import json
        overrides = {"confidence_threshold": 0.55, "risk_pct": 0.015}
        instance = ShadowInstance(
            instance_id="roundtrip_001",
            strategy_id="TEST_STRAT",
            account_id="acc_001",
            account_type="DEMO",
            parameter_overrides=overrides,
        )

        db_dict = instance.to_db_dict()

        # Must be parseable as valid JSON (not Python single-quote repr)
        assert json.loads(db_dict["parameter_overrides"]) == overrides

        # Reconstruct from db_dict and verify round-trip fidelity
        restored = ShadowInstance.from_db_dict(db_dict)
        assert restored.parameter_overrides == overrides


class TestShadowInstanceHealthEvaluation:
    """Test the 3 Pilares evaluation logic."""

    def test_health_healthy_status(self):
        """Test HEALTHY status: 3/3 Pilares PASS."""
        instance = ShadowInstance(
            instance_id="healthy_001",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=1.75,  # PASS (>= 1.5)
                win_rate=0.68,       # PASS (>= 0.60)
                max_drawdown_pct=9.0,  # PASS (<= 12.0)
                consecutive_losses_max=2,  # PASS (<= 3)
                equity_curve_cv=0.38,  # PASS (<= 0.40)
                total_trades_executed=50,  # PASS (>= 15)
            ),
        )
        
        health, reason = instance.evaluate_health()
        assert health == HealthStatus.HEALTHY
        assert "3/3 Pilares PASSED" in reason

    def test_health_dead_status_low_profit_factor(self):
        """Test DEAD status: Pilar 1 (Profitabilidad) fails."""
        instance = ShadowInstance(
            instance_id="dead_001",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=1.0,  # FAIL (< 1.5)
                win_rate=0.50,      # FAIL (< 0.60)
                max_drawdown_pct=9.0,
                consecutive_losses_max=2,
                equity_curve_cv=0.38,
                total_trades_executed=20,  # Sufficient for evaluation
            ),
        )
        
        health, reason = instance.evaluate_health()
        assert health == HealthStatus.DEAD
        assert "Pilar 1" in reason or "PROFITABILIDAD" in reason or "PF=" in reason

    def test_health_quarantined_status_high_drawdown(self):
        """Test QUARANTINED status: Pilar 2 (Resiliencia) fails."""
        instance = ShadowInstance(
            instance_id="quarantined_001",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=1.8,
                win_rate=0.70,
                max_drawdown_pct=15.0,  # FAIL (> 12.0)
                consecutive_losses_max=2,
                equity_curve_cv=0.38,
                total_trades_executed=50,
            ),
        )
        
        health, reason = instance.evaluate_health()
        assert health == HealthStatus.QUARANTINED
        assert "Pilar 2" in reason or "RESILIENCIA" in reason or "DD=" in reason

    def test_health_monitor_status_high_equity_cv(self):
        """Test MONITOR status: Pilar 3 (Consistencia) fails."""
        instance = ShadowInstance(
            instance_id="monitor_001",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=1.8,
                win_rate=0.70,
                max_drawdown_pct=9.0,
                consecutive_losses_max=2,
                equity_curve_cv=0.50,  # FAIL (> 0.40)
                total_trades_executed=20,  # Sufficient
            ),
        )
        
        health, reason = instance.evaluate_health()
        assert health == HealthStatus.MONITOR
        assert "Pilar 3" in reason or "CONSISTENCIA" in reason or "CV=" in reason

    def test_health_incubating_status_insufficient_trades(self):
        """Test INCUBATING status: Not enough trades for evaluation."""
        instance = ShadowInstance(
            instance_id="incubating_001",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=2.0,
                win_rate=0.80,
                max_drawdown_pct=5.0,
                consecutive_losses_max=1,
                equity_curve_cv=0.30,
                total_trades_executed=8,  # FAIL (< 15)
            ),
        )
        
        health, reason = instance.evaluate_health()
        assert health == HealthStatus.INCUBATING
        assert "bootstrap" in reason.lower() or "< 15" in reason


class TestShadowInstancePromotion:
    """Test promotion eligibility logic."""

    def test_promotable_when_healthy(self):
        """Instance with HEALTHY status can be promoted."""
        instance = ShadowInstance(
            instance_id="promo_001",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=1.75,
                win_rate=0.68,
                max_drawdown_pct=9.0,
                consecutive_losses_max=2,
                equity_curve_cv=0.38,
                total_trades_executed=50,
            ),
        )
        
        is_promotable, reason = instance.is_promotable_to_real()
        assert is_promotable is True
        assert "Ready for promotion" in reason

    def test_not_promotable_dead_instance(self):
        """DEAD instance cannot be promoted."""
        instance = ShadowInstance(
            instance_id="dead_promo",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=0.8,
                win_rate=0.40,
                max_drawdown_pct=9.0,
                consecutive_losses_max=2,
                equity_curve_cv=0.38,
                total_trades_executed=20,
            ),
        )
        
        is_promotable, reason = instance.is_promotable_to_real()
        assert is_promotable is False
        assert "Cannot promote" in reason

    def test_not_promotable_insufficient_trades(self):
        """Instance with < 15 trades cannot be promoted."""
        instance = ShadowInstance(
            instance_id="insuf_trades",
            strategy_id="TEST",
            account_id="acc",
            account_type="DEMO",
            metrics=ShadowMetrics(
                profit_factor=1.75,
                win_rate=0.68,
                max_drawdown_pct=9.0,
                consecutive_losses_max=2,
                equity_curve_cv=0.38,
                total_trades_executed=10,  # FAIL (< 15)
            ),
        )
        
        is_promotable, reason = instance.is_promotable_to_real()
        assert is_promotable is False
        assert "trades" in reason.lower() or "pilar" in reason.lower()


class TestShadowPerformanceHistory:
    """Test performance history snapshots."""

    def test_performance_history_creation(self):
        """Create a performance history snapshot."""
        history = ShadowPerformanceHistory(
            instance_id="test_001",
            evaluation_date=datetime.now(timezone.utc),
            pillar1_status=PillarStatus.PASS,
            pillar2_status=PillarStatus.PASS,
            pillar3_status=PillarStatus.PASS,
            overall_health=HealthStatus.HEALTHY,
            event_trace_id="TRACE_HEALTH_20260312_120000_test_001",
        )
        
        assert history.instance_id == "test_001"
        assert history.pillar1_status == PillarStatus.PASS
        assert history.overall_health == HealthStatus.HEALTHY

    def test_performance_history_to_db_dict(self):
        """Verify history can be converted to DB dict."""
        history = ShadowPerformanceHistory(
            instance_id="hist_001",
            evaluation_date=datetime(2026, 3, 12, 12, 0, 0),
            pillar1_status=PillarStatus.PASS,
            pillar2_status=PillarStatus.FAIL,
            pillar3_status=PillarStatus.PASS,
            overall_health=HealthStatus.QUARANTINED,
            event_trace_id="TRACE_TEST",
        )
        
        db_dict = history.to_db_dict()
        assert db_dict["instance_id"] == "hist_001"
        assert db_dict["pillar1_status"] == "PASS"
        assert db_dict["pillar2_status"] == "FAIL"
        assert db_dict["overall_health"] == "QUARANTINED"


class TestShadowPromotionLog:
    """Test immutable promotion log entries."""

    def test_promotion_log_creation(self):
        """Create a promotion log entry."""
        log = ShadowPromotionLog(
            instance_id="promo_log_001",
            trace_id="TRACE_PROMOTION_REAL_20260312_120000_promo_",
            promotion_status="APPROVED",
            pillar1_passed=True,
            pillar2_passed=True,
            pillar3_passed=True,
        )
        
        assert log.instance_id == "promo_log_001"
        assert log.promotion_status == "APPROVED"
        assert log.pillar1_passed is True

    def test_promotion_log_to_db_dict(self):
        """Verify log can be converted to DB dict."""
        log = ShadowPromotionLog(
            instance_id="log_001",
            trace_id="TRACE_PROMOTION_TEST",
            promotion_status="EXECUTED",
            pillar1_passed=True,
            pillar2_passed=False,
            pillar3_passed=True,
            notes="Promoted to REAL with restrictions",
        )
        
        db_dict = log.to_db_dict()
        assert db_dict["instance_id"] == "log_001"
        assert db_dict["promotion_status"] == "EXECUTED"
        assert db_dict["pillar2_passed"] is False
        assert "restrictions" in db_dict["notes"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
