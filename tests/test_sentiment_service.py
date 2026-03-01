from datetime import datetime, timezone

from core_brain.services.sentiment_service import SentimentService


class _StorageStub:
    def __init__(self, cfg: dict):
        self._cfg = cfg

    def get_dynamic_params(self) -> dict:
        return self._cfg


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def test_sentiment_veto_blocks_high_confidence_buy_on_bearish_fed_news() -> None:
    storage = _StorageStub(
        {
            "sentiment_stream": {
                "enabled": True,
                "high_probability_threshold": 0.75,
                "bearish_veto_threshold_pct": 80.0,
                "bullish_veto_threshold_pct": 80.0,
                "min_events_for_veto": 1,
            }
        }
    )
    service = SentimentService(storage=storage)  # type: ignore[arg-type]
    events = [
        {
            "source": "Bloomberg",
            "headline": "Fed signals higher for longer policy and quantitative tightening",
            "published_at": _now_iso(),
        }
    ]

    allowed, reason, snapshot = service.evaluate_trade_veto(
        symbol="EURUSD",
        side="BUY",
        confidence=0.92,
        events=events,
    )

    assert not allowed
    assert "veto" in reason.lower()
    assert snapshot["bearish_pct"] >= 80.0
    assert snapshot["high_impact_macro"] is True


def test_sentiment_does_not_veto_when_signal_is_not_high_probability() -> None:
    storage = _StorageStub({"sentiment_stream": {"enabled": True, "high_probability_threshold": 0.75}})
    service = SentimentService(storage=storage)  # type: ignore[arg-type]
    events = [
        {
            "source": "Reuters",
            "headline": "Fed remains hawkish and points to higher for longer",
            "published_at": _now_iso(),
        }
    ]

    allowed, reason, _ = service.evaluate_trade_veto(
        symbol="EURUSD",
        side="BUY",
        confidence=0.61,
        events=events,
    )

    assert allowed
    assert "below high-probability" in reason.lower()
