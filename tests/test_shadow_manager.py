"""
Tests for ShadowManager: Health evaluation and promotion logic for SHADOW instances.

Trace_ID: SHADOW-MANAGER-TESTS-2026-001
Coverage:
  - evaluate_all_instances() → returns {promotions, kills, quarantines}
  - evaluate_single_instance() → returns HealthStatus + reason
  - is_promotable_to_real() → returns (bool, reason)
  - Health status transitions (HEALTHY → MONITOR → QUARANTINED → DEAD)
"""

import pytest
import sqlite3
from datetime import datetime, timezone
from typing import Dict

from models.shadow import (
    ShadowInstance,
    ShadowMetrics,
    ShadowStatus,
    HealthStatus,
)
from data_vault.shadow_db import ShadowStorageManager
from core_brain.shadow_manager import ShadowManager, PromotionValidator


class TestShadowManagerInitialization:
    """Tests for ShadowManager dependency injection and setup."""

    def test_manager_requires_storage_injection(self):
        """ShadowManager must receive storage via DI (RULE: NO self.storage = ...)."""
        conn = sqlite3.connect(":memory:")
        storage = ShadowStorageManager(conn)
        
        manager = ShadowManager(storage=storage)
        
        assert manager.storage is storage
        assert manager.storage is not None

    def test_manager_initializes_promotion_validator(self):
        """ShadowManager initializes PromotionValidator internally."""
        conn = sqlite3.connect(":memory:")
        storage = ShadowStorageManager(conn)
        
        manager = ShadowManager(storage=storage)
        
        assert manager.promotion_validator is not None
        assert isinstance(manager.promotion_validator, PromotionValidator)


class TestHealthyInstance:
    """Tests for healthy SHADOW instance (3/3 Pilares PASS)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.storage = ShadowStorageManager(self.conn)
        self.manager = ShadowManager(storage=self.storage)
        
        # Create test instance
        self.instance = ShadowInstance(
            instance_id="shadow_healthy_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )

    def test_instance_with_all_3_pillars_pass_is_healthy(self):
        """Instance with 3/3 Pilares PASS → HealthStatus.HEALTHY."""
        # Metrics that PASS all 3 Pilares
        self.instance.metrics = ShadowMetrics(
            profit_factor=1.75,          # >= 1.5 ✅ PILAR 1
            win_rate=0.65,               # >= 0.60 ✅ PILAR 1
            max_drawdown_pct=0.10,       # <= 0.12 ✅ PILAR 2
            consecutive_losses_max=2,    # <= 3 ✅ PILAR 2
            total_trades_executed=20,    # >= 15 ✅ PILAR 3
            equity_curve_cv=0.35,        # <= 0.40 ✅ PILAR 3
        )
        
        health = self.manager.evaluate_single_instance(self.instance)
        
        assert health == HealthStatus.HEALTHY

    def test_healthy_instance_is_promotable(self):
        """HEALTHY instance → is_promotable_to_real() = True."""
        self.instance.metrics = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        self.instance.status = ShadowStatus.INCUBATING
        
        can_promote, reason = self.manager.is_promotable_to_real(self.instance)
        
        assert can_promote is True
        assert "3 Pilares" in reason or "HEALTHY" in reason


class TestDeadInstance:
    """Tests for dead SHADOW instance (Pilar 1 FAIL)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.storage = ShadowStorageManager(self.conn)
        self.manager = ShadowManager(storage=self.storage)
        
        self.instance = ShadowInstance(
            instance_id="shadow_dead_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )

    def test_instance_with_pilar1_fail_is_dead(self):
        """Instance with Pilar 1 FAIL (PF < 1.5 OR WR < 0.60) → HealthStatus.DEAD."""
        # Low profit factor
        self.instance.metrics = ShadowMetrics(
            profit_factor=0.85,          # < 1.5 ❌ PILAR 1
            win_rate=0.55,               # < 0.60 ❌ PILAR 1
            max_drawdown_pct=0.08,       # ✅ PILAR 2
            consecutive_losses_max=1,    # ✅ PILAR 2
            total_trades_executed=25,    # ✅ PILAR 3
            equity_curve_cv=0.30,        # ✅ PILAR 3
        )
        self.instance.status = ShadowStatus.INCUBATING
        
        health = self.manager.evaluate_single_instance(self.instance)
        
        assert health == HealthStatus.DEAD

    def test_dead_instance_not_promotable(self):
        """DEAD instance → is_promotable_to_real() = False."""
        self.instance.metrics = ShadowMetrics(
            profit_factor=0.85, win_rate=0.55,
            max_drawdown_pct=0.08, consecutive_losses_max=1,
            total_trades_executed=25, equity_curve_cv=0.30,
        )
        
        can_promote, reason = self.manager.is_promotable_to_real(self.instance)
        
        assert can_promote is False
        assert "Pilar 1" in reason or "Profitability" in reason


class TestQuarantinedInstance:
    """Tests for quarantined SHADOW instance (Pilar 2 FAIL)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.storage = ShadowStorageManager(self.conn)
        self.manager = ShadowManager(storage=self.storage)
        
        self.instance = ShadowInstance(
            instance_id="shadow_quarantine_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )

    def test_instance_with_pilar2_fail_is_quarantined(self):
        """Instance with Pilar 2 FAIL (DD > 0.12 OR CL > 3) → HealthStatus.QUARANTINED."""
        # High drawdown
        self.instance.metrics = ShadowMetrics(
            profit_factor=1.60,          # ✅ PILAR 1
            win_rate=0.65,               # ✅ PILAR 1
            max_drawdown_pct=0.18,       # > 0.12 ❌ PILAR 2
            consecutive_losses_max=2,    # ✅ PILAR 2
            total_trades_executed=20,    # ✅ PILAR 3
            equity_curve_cv=0.35,        # ✅ PILAR 3
        )
        self.instance.status = ShadowStatus.INCUBATING
        
        health = self.manager.evaluate_single_instance(self.instance)
        
        assert health == HealthStatus.QUARANTINED

    def test_consecutive_losses_fail_triggers_quarantine(self):
        """Consecutive Losses > 3 → QUARANTINED."""
        self.instance.metrics = ShadowMetrics(
            profit_factor=1.60, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=5,  # > 3 ❌
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        
        health = self.manager.evaluate_single_instance(self.instance)
        
        assert health == HealthStatus.QUARANTINED


class TestMonitorInstance:
    """Tests for monitor SHADOW instance (Pilar 3 weak)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.storage = ShadowStorageManager(self.conn)
        self.manager = ShadowManager(storage=self.storage)
        
        self.instance = ShadowInstance(
            instance_id="shadow_monitor_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )

    def test_instance_with_pilar3_weak_is_monitor(self):
        """Instance with Pilar 3 WEAK (CV > 0.40 OR trades < 15) → HealthStatus.MONITOR."""
        # Too few trades
        self.instance.metrics = ShadowMetrics(
            profit_factor=1.60, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=8,     # < 15 ⚠️ PILAR 3
            equity_curve_cv=0.35,        # ✅
        )
        self.instance.status = ShadowStatus.INCUBATING
        
        health = self.manager.evaluate_single_instance(self.instance)
        
        assert health == HealthStatus.MONITOR

    def test_high_equity_cv_triggers_monitor(self):
        """Equity Curve CV > 0.40 → MONITOR."""
        self.instance.metrics = ShadowMetrics(
            profit_factor=1.60, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.55,  # > 0.40 ⚠️
        )
        
        health = self.manager.evaluate_single_instance(self.instance)
        
        assert health == HealthStatus.MONITOR


class TestTraceIDGeneration:
    """Tests for Trace_ID generation (RULE ID-1)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.storage = ShadowStorageManager(self.conn)
        self.manager = ShadowManager(storage=self.storage)

    def test_evaluate_generates_trace_id(self):
        """evaluate_single_instance() returns (HealthStatus, trace_id)."""
        instance = ShadowInstance(
            instance_id="shadow_trace_001",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )
        instance.metrics = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        
        health, trace_id = self.manager.evaluate_single_instance(instance, return_trace=True)
        
        assert trace_id is not None
        assert trace_id.startswith("TRACE_HEALTH_")
        assert len(trace_id) > len("TRACE_HEALTH_")

    def test_trace_id_includes_instance_id(self):
        """Trace_ID includes first 8 chars of instance_id."""
        instance = ShadowInstance(
            instance_id="shadowtest_1234567",
            strategy_id="BRK_OPEN_0001",
            account_id="demo_mt5_001",
            account_type="DEMO",
        )
        instance.metrics = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        
        _, trace_id = self.manager.evaluate_single_instance(instance, return_trace=True)
        
        assert "shadowte" in trace_id  # First 8 chars


class TestPromotionValidator:
    """Tests for PromotionValidator (3 Pilares logic)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.validator = PromotionValidator()

    def test_validator_checks_pilar1_profitability(self):
        """Validator requires Pilar 1: PF >= 1.5 AND WR >= 0.60."""
        metrics = ShadowMetrics(
            profit_factor=0.9,   # < 1.5 ❌
            win_rate=0.70,       # >= 0.60 ✅
            max_drawdown_pct=0.10,
            consecutive_losses_max=2,
            total_trades_executed=20,
            equity_curve_cv=0.35,
        )
        
        p1_pass, reason = self.validator.validate_pilar1_profitability(metrics)
        
        assert p1_pass is False
        assert "Profit Factor" in reason or "Win Rate" in reason

    def test_validator_checks_pilar2_resiliencia(self):
        """Validator requires Pilar 2: DD <= 0.12 AND CL <= 3."""
        metrics = ShadowMetrics(
            profit_factor=1.75,
            win_rate=0.65,
            max_drawdown_pct=0.20,   # > 0.12 ❌
            consecutive_losses_max=2,
            total_trades_executed=20,
            equity_curve_cv=0.35,
        )
        
        p2_pass, reason = self.validator.validate_pilar2_resiliencia(metrics)
        
        assert p2_pass is False
        assert "Drawdown" in reason

    def test_validator_checks_pilar3_consistency(self):
        """Validator requires Pilar 3: trades >= 15 AND CV <= 0.40."""
        metrics = ShadowMetrics(
            profit_factor=1.75,
            win_rate=0.65,
            max_drawdown_pct=0.10,
            consecutive_losses_max=2,
            total_trades_executed=10,   # < 15 ❌
            equity_curve_cv=0.35,
        )
        
        p3_pass, reason = self.validator.validate_pilar3_consistency(metrics)
        
        assert p3_pass is False
        assert "Trades" in reason or "Executed" in reason

    def test_all_3_pilares_pass_returns_approved(self):
        """All 3 Pilares PASS → approved = True."""
        metrics = ShadowMetrics(
            profit_factor=1.75, win_rate=0.65,
            max_drawdown_pct=0.10, consecutive_losses_max=2,
            total_trades_executed=20, equity_curve_cv=0.35,
        )
        
        approved, reason = self.validator.validate_all_pillars(metrics)
        
        assert approved is True
        assert "3 Pilares" in reason or "HEALTHY" in reason.upper()


class TestEvaluateAllInstances:
    """Tests for batch evaluation (evaluate_all_instances)."""

    def setup_method(self):
        """Initialize test fixtures."""
        self.conn = sqlite3.connect(":memory:")
        self.storage = ShadowStorageManager(self.conn)
        self.manager = ShadowManager(storage=self.storage)

    def test_evaluate_all_returns_dict_structure(self):
        """evaluate_all_instances() returns Dict with keys: promotions, kills, quarantines."""
        # Assuming no instances exist yet
        result = self.manager.evaluate_all_instances()
        
        assert isinstance(result, dict)
        assert "promotions" in result
        assert "kills" in result
        assert "quarantines" in result
        assert "monitors" in result

    def test_result_lists_are_empty_when_no_instances(self):
        """Empty pool → all result lists are empty."""
        result = self.manager.evaluate_all_instances()
        
        assert len(result["promotions"]) == 0
        assert len(result["kills"]) == 0
        assert len(result["quarantines"]) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
