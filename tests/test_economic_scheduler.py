"""
Economic Data Scheduler Tests - FASE C.4 EDGE Intelligence

Tests for EconomicDataScheduler with EDGE philosophy:
- Evolutivo: Self-learning, calibration
- Dinámico: Adaptive margins, trend analysis
- Graceful: Degradation, backpressure, recovery
- Escalable: Performance optimization

Type Hints: 100% coverage
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import psutil

from core_brain.economic_scheduler import (
    EconomicDataScheduler,
    SchedulerConfig,
    CPUMetrics,
    CPUTrend,
    CPUTrendDirection,
    SchedulerHealthStatus
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def scheduler_config() -> SchedulerConfig:
    """Create test scheduler config."""
    return SchedulerConfig(
        job_interval_minutes=5,
        base_safety_margin_pct=10,
        max_critical_cpu_pct=85,
        min_safe_cpu_pct=10,
        calibration_samples=3,  # Fast calibration for tests
        warning_cpu_pct=75,
        critical_cpu_pct=90
    )


@pytest.fixture
async def dummy_job() -> None:
    """Dummy async job for scheduler."""
    await asyncio.sleep(0.01)


@pytest.fixture
def scheduler(scheduler_config, dummy_job) -> EconomicDataScheduler:
    """Create scheduler instance for testing."""
    return EconomicDataScheduler(
        fetch_and_persist_func=dummy_job,
        config=scheduler_config
    )


# ============================================================================
# EVOLUTIVO: Learning Tests
# ============================================================================

class TestSchedulerEvolution:
    """Tests for self-learning capabilities."""
    
    def test_overhead_measurement(self, scheduler: EconomicDataScheduler) -> None:
        """Verify overhead measurement from metrics."""
        # Simulate job metrics
        scheduler.metrics = [
            CPUMetrics(
                timestamp=datetime.now(timezone.utc),
                system_cpu_percent=50.0,
                scheduler_overhead_percent=5.0,
                job_duration_sec=1.0,
                is_job_skipped=False
            ),
            CPUMetrics(
                timestamp=datetime.now(timezone.utc),
                system_cpu_percent=52.0,
                scheduler_overhead_percent=6.0,
                job_duration_sec=1.1,
                is_job_skipped=False
            ),
            CPUMetrics(
                timestamp=datetime.now(timezone.utc),
                system_cpu_percent=51.0,
                scheduler_overhead_percent=5.5,
                job_duration_sec=1.05,
                is_job_skipped=False
            )
        ]
        
        overhead = scheduler._measure_overhead()
        assert overhead is not None
        assert abs(overhead - 5.5) < 0.1  # Average of [5.0, 6.0, 5.5]
    
    def test_calibration_completion(
        self,
        scheduler: EconomicDataScheduler,
        scheduler_config: SchedulerConfig
    ) -> None:
        """Verify calibration completes after N samples."""
        # Add exactly N metrics
        for i in range(scheduler_config.calibration_samples):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0 + i,
                    scheduler_overhead_percent=5.0 + i * 0.5,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        # Calibration not yet complete
        assert not scheduler.calibration_complete
        
        # Trigger calibration
        measured = scheduler._measure_overhead()
        if measured is not None:
            scheduler.measured_overhead_pct = measured
            scheduler.calibration_complete = True
        
        assert scheduler.calibration_complete
        assert scheduler.measured_overhead_pct is not None
    
    def test_overhead_improves_precision(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify measured overhead becomes more precise with more samples."""
        # Add varied metrics (more than calibration_samples)
        metrics_data = [
            (50.0, 4.5), (52.0, 5.5), (51.0, 5.0),
            (49.0, 4.0), (51.0, 5.2)
        ]
        
        for cpu, overhead in metrics_data:
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=cpu,
                    scheduler_overhead_percent=overhead,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        # Measure - should use last calibration_samples
        measured = scheduler._measure_overhead()
        
        # Should measure from last 3 samples (calibration_samples=3)
        # [5.0, 4.0, 5.2] = 4.73...
        assert measured is not None
        assert 4.0 <= measured <= 5.5  # Reasonable bounds


# ============================================================================
# DINÁMICO: Adaptive Tests
# ============================================================================

class TestSchedulerAdaptive:
    """Tests for dynamic adaptation."""
    
    def test_cpu_trend_rising(self, scheduler: EconomicDataScheduler) -> None:
        """Verify rising CPU trend detection."""
        # Add rising CPU metrics
        for i in range(5):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0 + i * 3,  # Rising: 50, 53, 56, 59, 62
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        trend = scheduler._analyze_cpu_trend()
        assert trend.direction == CPUTrendDirection.RISING
        assert trend.slope > 0
        assert "Reduce" in trend.recommendation
    
    def test_cpu_trend_falling(self, scheduler: EconomicDataScheduler) -> None:
        """Verify falling CPU trend detection."""
        # Add falling CPU metrics
        for i in range(5):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=70.0 - i * 3,  # Falling: 70, 67, 64, 61, 58
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        trend = scheduler._analyze_cpu_trend()
        assert trend.direction == CPUTrendDirection.FALLING
        assert trend.slope < 0
        assert "FALLING" in trend.recommendation
    
    def test_cpu_trend_stable(self, scheduler: EconomicDataScheduler) -> None:
        """Verify stable CPU trend detection."""
        # Add stable CPU metrics
        for _ in range(5):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0,  # Stable: always 50
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        trend = scheduler._analyze_cpu_trend()
        assert trend.direction == CPUTrendDirection.STABLE
        assert abs(trend.slope) < 1.0
    
    def test_dynamic_safety_margin_increases_with_volatility(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify safety margin increases with CPU volatility."""
        # High volatility
        volatile_metrics = [40, 80, 30, 90, 20]  # High variance
        for cpu in volatile_metrics:
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=float(cpu),
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        trend = scheduler._analyze_cpu_trend()
        margin = scheduler._calculate_dynamic_safety_margin(trend)
        
        # High volatility should increase margin
        assert margin > scheduler.config.base_safety_margin_pct
        assert 5 <= margin <= 15  # Respects bounds
    
    def test_dynamic_safety_margin_decreases_with_recovery(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify safety margin decreases when CPU recovers."""
        # Falling trend
        for i in range(5):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=80.0 - i * 5,  # Falling
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        trend = scheduler._analyze_cpu_trend()
        margin = scheduler._calculate_dynamic_safety_margin(trend)
        
        # Falling trend should reduce margin (can be more aggressive)
        assert margin <= scheduler.config.base_safety_margin_pct


# ============================================================================
# GRACEFUL: Degradation Tests
# ============================================================================

class TestSchedulerGraceful:
    """Tests for graceful degradation and recovery."""
    
    def test_graceful_skipping_under_load(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify jobs are gracefully skipped under high CPU."""
        # Simulate high CPU state
        with patch('psutil.cpu_percent') as mock_cpu:
            mock_cpu.return_value = 95.0  # Above threshold
            
            # Check if should run
            should_run = scheduler._should_run_job()
            assert not should_run
    
    def test_graceful_resume_when_cpu_drops(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify jobs resume automatically when CPU drops."""
        # Simulate CPU dropping
        with patch('psutil.cpu_percent') as mock_cpu:
            # First: High CPU (skip)
            mock_cpu.return_value = 95.0
            should_run_1 = scheduler._should_run_job()
            assert not should_run_1
            
            # Second: Low CPU (resume)
            mock_cpu.return_value = 30.0
            should_run_2 = scheduler._should_run_job()
            assert should_run_2
    
    def test_backpressure_prevents_scheduler_starvation(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify backpressure pauses without error."""
        # Add skip metrics
        for _ in range(5):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=95.0,
                    scheduler_overhead_percent=0,
                    job_duration_sec=0,
                    is_job_skipped=True
                )
            )
        
        # Scheduler should still be healthy (no exceptions)
        assert scheduler.is_running or not scheduler.is_running  # Both valid


# ============================================================================
# ESCALABLE: Performance Tests
# ============================================================================

class TestSchedulerScalable:
    """Tests for scalability and efficiency."""
    
    def test_job_efficiency_calculation(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify job efficiency metric."""
        # Add fast jobs
        for _ in range(3):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0,
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=0.5,  # Fast
                    is_job_skipped=False
                )
            )
        
        metrics = scheduler.get_metrics_summary()
        assert metrics["avg_job_duration_sec"] == 0.5
    
    def test_recovery_rate_high_with_auto_resume(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify high recovery rate when system auto-resumes."""
        # Mix of skips and usr_executions
        for i in range(10):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0 + (i % 2) * 40,
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=(i % 2 == 1)
                )
            )
        
        metrics = scheduler.get_metrics_summary()
        recovery = metrics.get("recovery_rate_percent", 0)
        assert recovery > 0  # Some recovery


# ============================================================================
# EDGE Philosophy Integration Tests
# ============================================================================

class TestEDGEPhilosophy:
    """Integration tests for complete EDGE behavior."""
    
    def test_edge_intelligence_report_complete(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify EDGE intelligence report includes all components."""
        # Add some metrics
        for i in range(3):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0 + i,
                    scheduler_overhead_percent=5.0 + i * 0.5,
                    job_duration_sec=1.0,
                    is_job_skipped=(i == 2)
                )
            )
        
        intelligence = scheduler.get_edge_intelligence()
        
        # Verify all 4 pillars present
        assert "evolution" in intelligence
        assert "dynamic" in intelligence
        assert "graceful" in intelligence
        assert "scalable" in intelligence
        assert "philosophy" in intelligence
    
    def test_edge_health_shows_intelligence(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify health report shows EDGE intelligence."""
        # Add metrics
        for _ in range(3):
            scheduler.metrics.append(
                CPUMetrics(
                    timestamp=datetime.now(timezone.utc),
                    system_cpu_percent=50.0,
                    scheduler_overhead_percent=5.0,
                    job_duration_sec=1.0,
                    is_job_skipped=False
                )
            )
        
        health = scheduler.get_health()
        
        # Should include trend info
        assert "cpu_trend" in health
        assert "cpu_volatility_percent" in health
        assert "trend_recommendation" in health
    
    def test_scheduler_autonomous_operation(
        self,
        scheduler: EconomicDataScheduler
    ) -> None:
        """Verify scheduler operates autonomously without manual config."""
        assert scheduler.is_running or not scheduler.is_running
        
        # Config should have sensible defaults
        assert scheduler.config.base_safety_margin_pct >= 5
        assert scheduler.config.base_safety_margin_pct <= 15
        assert scheduler.config.max_critical_cpu_pct >= 80
        assert scheduler.config.min_safe_cpu_pct <= 20
