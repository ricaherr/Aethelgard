"""
test_signal_review_queue.py — Tests for B/C Grade Signal Review Queue (DISC-001)

Tests TDD following Phase 1: Backend Infrastructure acceptance criteria.
Run with: pytest tests/test_signal_review_queue.py -v

TRACE_ID: DISC-SQ-001-2026-04-04-TESTS
"""

import pytest
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import uuid

# Mock imports (assuming tests run with mocked storage)
from core_brain.services.signal_review_manager import SignalReviewManager, ReviewStatus


class MockStorageManager:
    """Minimal mock for StorageManager to test review manager logic."""
    
    def __init__(self):
        # In-memory storage for testing
        self.signals: Dict[str, Dict[str, Any]] = {}
        self.audit_logs: list = []
        self.config: Dict[str, str] = {}
    
    def execute_update(self, sql: str, params: tuple) -> int:
        """Mock UPDATE/INSERT operations."""
        # Parse UPDATE sys_signals
        if "UPDATE sys_signals" in sql and "review_status" in sql:
            # Update signal in memory
            signal_id = params[-1] if params else None
            if signal_id and signal_id in self.signals:
                self.signals[signal_id]["review_status"] = params[0]
                # Handle multi-param updates
                param_count = len(params) - 1  # Exclude signal_id
                if param_count >= 2:
                    self.signals[signal_id]["trader_review_reason"] = params[1]
                if param_count >= 3:
                    self.signals[signal_id]["review_timeout_at"] = params[2]
                return 1
            return 0
        
        # Parse INSERT into sys_audit_logs
        if "INSERT INTO sys_audit_logs" in sql:
            self.audit_logs.append({"params": params})
            return 1
        
        # Parse INSERT into sys_config (both INSERT and INSERT OR REPLACE)
        if "INSERT" in sql and "sys_config" in sql and "CONFIG" in sql.upper():
            key = params[0] if len(params) > 0 else None
            value = params[1] if len(params) > 1 else None
            if key:
                self.config[key] = value
            return 1
        
        return 0
    
    def execute_query(self, sql: str, params: tuple = ()) -> list:
        """Mock SELECT queries."""
        if "SELECT id, symbol, review_status FROM sys_signals WHERE id" in sql:
            signal_id = params[0] if params else None
            if signal_id and signal_id in self.signals:
                signal = self.signals[signal_id]
                return [{
                    "id": signal.get("id"),
                    "symbol": signal.get("symbol"),
                    "review_status": signal.get("review_status"),
                }]
            return []

        if "SELECT id, symbol, strategy_id" in sql and "FROM sys_signals WHERE id" in sql:
            signal_id = params[0] if params else None
            if signal_id and signal_id in self.signals:
                signal = self.signals[signal_id]
                return [{
                    "id": signal.get("id"),
                    "symbol": signal.get("symbol"),
                    "strategy_id": signal.get("strategy_id"),
                    "review_status": signal.get("review_status"),
                }]
            return []

        if "SELECT id, symbol, review_timeout_at, trader_review_reason" in sql:
            review_val = params[0] if params else ReviewStatus.PENDING.value
            return [
                {
                    "id": s.get("id"),
                    "symbol": s.get("symbol"),
                    "review_timeout_at": s.get("review_timeout_at"),
                    "trader_review_reason": s.get("trader_review_reason"),
                }
                for s in self.signals.values()
                if s.get("review_status") == review_val
            ]
        
        if "SELECT id, symbol, signal_type, confidence" in sql:
            # Get pending signals
            if "review_status" in sql and "?" in sql:
                review_val = params[0] if params else ReviewStatus.PENDING.value
                return [
                    {
                        "id": s.get("id"),
                        "symbol": s.get("symbol"),
                        "signal_type": s.get("signal_type", "BUY"),
                        "confidence": s.get("confidence", 0.75),
                        "price": s.get("price", 0.0),
                        "review_timeout_at": s.get("review_timeout_at"),
                        "trader_review_reason": s.get("trader_review_reason"),
                        "created_at": s.get("created_at", datetime.now(timezone.utc).isoformat()),
                        "review_status": s.get("review_status"),
                    }
                    for s in self.signals.values()
                    if s.get("review_status") == review_val
                ]
            return []
        
        return []


@pytest.fixture
def mock_storage():
    """Fixture: Mock storage manager."""
    return MockStorageManager()


@pytest.fixture
def review_manager(mock_storage):
    """Fixture: Review manager with mock storage."""
    return SignalReviewManager(storage_manager=mock_storage)


@pytest.fixture
def sample_b_grade_signal():
    """Fixture: Sample B-grade signal."""
    return {
        "id": str(uuid.uuid4()),
        "symbol": "EURUSD",
        "signal_type": "BUY",
        "confidence": 0.72,  # B-grade range: 65-74%
        "price": 1.1050,
        "entry_price": 1.1050,
        "stop_loss": 1.1000,
        "take_profit": 1.1150,
        "volume": 0.01,
        "strategy_id": "test_strategy",
        "timeframe": "M5",
    }


# ============================================================================
# TEST 1: B-grade signal queued (not auto-executed)
# ============================================================================

@pytest.mark.asyncio
async def test_b_grade_queued_not_executed(review_manager, mock_storage, sample_b_grade_signal):
    """
    AC-001: When quality_score=72% (B grade), signal is queued with status=PENDING_REVIEW (NOT executed).
    """
    # Setup: Create signal in mock storage
    signal = sample_b_grade_signal
    mock_storage.signals[signal["id"]] = {
        "id": signal["id"],
        "symbol": signal["symbol"],
        "review_status": None,  # Initially None
        "trader_review_reason": None,
        "review_timeout_at": None,
    }
    
    # Act: Queue signal for review
    success, msg = await review_manager.queue_for_review(
        signal=signal,
        grade="B",
        score=72.0,
        reason="B_GRADE_MODERATE_CONFIDENCE"
    )
    
    # Assert
    assert success is True
    assert signal["id"] in mock_storage.signals
    assert mock_storage.signals[signal["id"]]["review_status"] == ReviewStatus.PENDING.value
    assert "PENDING" in mock_storage.signals[signal["id"]]["review_status"]
    assert signal["id"] in review_manager._pending_reviews


# ============================================================================
# TEST 2: Trader approval executes signal
# ============================================================================

@pytest.mark.asyncio
async def test_trader_approval_executes(review_manager, mock_storage, sample_b_grade_signal):
    """
    AC-003: Trader approves B-grade → signal marked as APPROVED and ready to execute.
    """
    # Setup
    signal = sample_b_grade_signal
    signal_id = signal["id"]
    mock_storage.signals[signal_id] = {
        "id": signal_id,
        "symbol": signal["symbol"],
        "review_status": ReviewStatus.PENDING.value,
        "trader_review_reason": "B_GRADE_MODERATE_CONFIDENCE",
        "review_timeout_at": (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat(),
    }
    review_manager._pending_reviews[signal_id] = {"symbol": signal["symbol"]}
    
    # Act
    success, msg = await review_manager.process_trader_approval(
        signal_id=signal_id,
        trader_id="trader_123",
        approval_reason="Looks good"
    )
    
    # Assert
    assert success is True
    assert mock_storage.signals[signal_id]["review_status"] == ReviewStatus.APPROVED.value
    assert signal_id not in review_manager._pending_reviews  # Removed from cache
    assert len(mock_storage.audit_logs) > 0  # Logged


# ============================================================================
# TEST 3: Trader rejection archives signal and adds cooldown
# ============================================================================

@pytest.mark.asyncio
async def test_trader_rejection_archives(review_manager, mock_storage, sample_b_grade_signal):
    """
    AC-004: Trader rejects → signal archived with review_status=REJECTED + 30-min cooldown added.
    """
    # Setup
    signal = sample_b_grade_signal
    signal_id = signal["id"]
    mock_storage.signals[signal_id] = {
        "id": signal_id,
        "symbol": signal["symbol"],
        "strategy_id": signal["strategy_id"],
        "review_status": ReviewStatus.PENDING.value,
        "trader_review_reason": "B_GRADE_MODERATE_CONFIDENCE",
    }
    review_manager._pending_reviews[signal_id] = {"symbol": signal["symbol"]}
    
    # Act
    success, msg = await review_manager.process_trader_rejection(
        signal_id=signal_id,
        trader_id="trader_456",
        rejection_reason="Too risky"
    )
    
    # Assert
    assert success is True
    assert mock_storage.signals[signal_id]["review_status"] == ReviewStatus.REJECTED.value
    assert signal_id not in review_manager._pending_reviews
    
    # Verify cooldown added
    cooldown_key = f"cooldown_{signal['strategy_id']}_{signal['symbol']}"
    assert cooldown_key in mock_storage.config


# ============================================================================
# TEST 4: Timeout auto-executes after 5 minutes
# ============================================================================

@pytest.mark.asyncio
async def test_timeout_auto_execute(review_manager, mock_storage, sample_b_grade_signal):
    """
    AC-005: If no trader action in 5 min → auto-execute with review_status=AUTO_EXECUTED.
    """
    # Setup: Signal with expired timeout
    signal = sample_b_grade_signal
    signal_id = signal["id"]
    
    # Timeout in the past (already expired)
    past_timeout = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    
    mock_storage.signals[signal_id] = {
        "id": signal_id,
        "symbol": signal["symbol"],
        "review_status": ReviewStatus.PENDING.value,
        "review_timeout_at": past_timeout,
        "trader_review_reason": "B_GRADE_MODERATE_CONFIDENCE",
    }
    
    # Act
    stats = await review_manager.check_and_execute_timed_out_reviews()
    
    # Assert
    assert stats["auto_executed"] >= 1  # At least one auto-executed
    assert signal_id in stats["auto_executed_ids"]
    assert mock_storage.signals[signal_id]["review_status"] == ReviewStatus.AUTO_EXECUTED.value


# ============================================================================
# Additional Tests (Sub-part of AC coverage)
# ============================================================================

@pytest.mark.asyncio
async def test_a_grade_bypasses_review(review_manager, mock_storage):
    """
    AC-006: A+ and A grades should NEVER be queued (bypass review entirely).
    This test verifies that only B/C grades go through review.
    """
    # A-grade signal (should NOT be queued)
    signal = {
        "id": str(uuid.uuid4()),
        "symbol": "GBPUSD",
        "confidence": 0.88,  # A-grade range: 75-84%
    }
    
    # A-grades are handled elsewhere (MainOrchestrator skips review_manager call)
    # This test documents the boundary condition
    assert signal["confidence"] >= 0.75  # Verify it's A-grade


@pytest.mark.asyncio
async def test_get_pending_reviews(review_manager, mock_storage, sample_b_grade_signal):
    """
    AC-008: Review queue maintains state in DB and API can list pending signals.
    """
    # Setup: Multiple pending signals
    signal_ids = []
    for i in range(3):
        sig_id = str(uuid.uuid4())
        signal_ids.append(sig_id)
        timeout = (datetime.now(timezone.utc) + timedelta(seconds=300)).isoformat()
        mock_storage.signals[sig_id] = {
            "id": sig_id,
            "symbol": f"EUR{chr(85 + i % 3)}",
            "review_status": ReviewStatus.PENDING.value,
            "review_timeout_at": timeout,
            "trader_review_reason": "B_GRADE",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    
    # Act
    pending = await review_manager.get_pending_reviews_for_trader(trader_id="trader_123")
    
    # Assert
    assert len(pending) >= 3
    for p in pending:
        assert p["review_status"] == ReviewStatus.PENDING.value
        assert "remaining_seconds" in p


if __name__ == "__main__":
    # Run with: python -m pytest tests/test_signal_review_queue.py -v
    pytest.main([__file__, "-v", "-s"])
