import pytest
from fastapi import HTTPException

from models.auth import TokenPayload
from core_brain.api.routers import trading


class _MockReviewManager:
    async def get_pending_reviews_for_trader(self, trader_id: str):
        return [
            {
                "id": "sig-1",
                "symbol": "EURUSD",
                "signal_type": "BUY",
                "confidence": 0.72,
                "price": 1.105,
                "review_timeout_at": "2026-01-01T00:00:00+00:00",
                "trader_review_reason": "B_GRADE_MODERATE_CONFIDENCE",
                "created_at": "2026-01-01T00:00:00+00:00",
                "remaining_seconds": 299,
                "timeout_at": "2026-01-01T00:05:00+00:00",
                "review_status": "PENDING",
            }
        ]

    async def process_trader_approval(self, signal_id: str, trader_id: str, approval_reason=None):
        if signal_id == "bad":
            return False, "Signal not pending"
        return True, "Approved"

    async def process_trader_rejection(self, signal_id: str, trader_id: str, rejection_reason: str):
        if signal_id == "bad":
            return False, "Signal not pending"
        return True, "Rejected"


@pytest.fixture
def token() -> TokenPayload:
    return TokenPayload(sub="user-1", exp=9999999999, role="trader")


@pytest.mark.asyncio
async def test_get_pending_signal_reviews_ok(monkeypatch, token):
    monkeypatch.setattr(trading, "_get_signal_review_manager", lambda _token: _MockReviewManager())

    result = await trading.get_pending_signal_reviews(token=token)

    assert result["count"] == 1
    assert result["pending_reviews"][0]["id"] == "sig-1"


@pytest.mark.asyncio
async def test_approve_signal_review_ok(monkeypatch, token):
    monkeypatch.setattr(trading, "_get_signal_review_manager", lambda _token: _MockReviewManager())

    async def _mock_exec(_data, _token):
        return {"success": True, "message": "executed"}

    monkeypatch.setattr(trading, "execute_signal_manual", _mock_exec)

    result = await trading.approve_signal_review(signal_id="sig-1", data={"reason": "ok"}, token=token)

    assert result["success"] is True
    assert result["review"]["status"] == "APPROVED"


@pytest.mark.asyncio
async def test_approve_signal_review_bad_request(monkeypatch, token):
    monkeypatch.setattr(trading, "_get_signal_review_manager", lambda _token: _MockReviewManager())

    async def _mock_exec(_data, _token):
        return {"success": False, "message": "no-exec"}

    monkeypatch.setattr(trading, "execute_signal_manual", _mock_exec)

    with pytest.raises(HTTPException) as exc:
        await trading.approve_signal_review(signal_id="bad", data={"reason": "ok"}, token=token)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_reject_signal_review_ok(monkeypatch, token):
    monkeypatch.setattr(trading, "_get_signal_review_manager", lambda _token: _MockReviewManager())

    result = await trading.reject_signal_review(signal_id="sig-2", data={"reason": "risk"}, token=token)

    assert result["success"] is True
    assert result["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_reject_signal_review_bad_request(monkeypatch, token):
    monkeypatch.setattr(trading, "_get_signal_review_manager", lambda _token: _MockReviewManager())

    with pytest.raises(HTTPException) as exc:
        await trading.reject_signal_review(signal_id="bad", data={"reason": "risk"}, token=token)

    assert exc.value.status_code == 400
