"""Tests de compatibilidad para SessionStateDetector usando la fuente canónica."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from zoneinfo import ZoneInfo

from core_brain.sensors.session_state_detector import SessionStateDetector
from core_brain.services.market_session_service import MarketSessionService


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {
        "market_sessions": {
            "sydney": {
                "timezone": "Australia/Sydney",
                "local_open": "07:00",
                "local_close": "16:00",
            },
            "tokyo": {
                "timezone": "Asia/Tokyo",
                "local_open": "09:00",
                "local_close": "18:00",
            },
            "london": {
                "timezone": "Europe/London",
                "local_open": "08:00",
                "local_close": "17:00",
            },
            "ny": {
                "timezone": "America/New_York",
                "local_open": "08:00",
                "local_close": "17:00",
            },
        }
    }
    return storage


@pytest.fixture
def detector(mock_storage):
    return SessionStateDetector(storage=mock_storage)


def test_session_state_detector_matches_market_session_service(mock_storage, detector):
    service = MarketSessionService(storage=mock_storage)
    test_cases = [
        (datetime(2026, 4, 14, 3, 0, tzinfo=ZoneInfo("UTC")), "ASIA", True),
        (datetime(2026, 4, 14, 14, 0, tzinfo=ZoneInfo("UTC")), "LONDON", True),
        (datetime(2026, 4, 14, 20, 0, tzinfo=ZoneInfo("UTC")), "NEW_YORK", False),
        (datetime(2026, 4, 14, 22, 0, tzinfo=ZoneInfo("UTC")), "SYDNEY", False),
    ]

    for utc_time, expected_session, expected_overlap in test_cases:
        active_sessions = set(service.get_active_sessions_utc(utc_time))

        assert detector.detect_current_session(utc_time=utc_time) == expected_session
        assert detector.is_session_overlap(utc_time=utc_time) is expected_overlap

        if expected_session == "ASIA":
            assert "tokyo" in active_sessions
        elif expected_session == "LONDON":
            assert "london" in active_sessions
        elif expected_session == "NEW_YORK":
            assert "ny" in active_sessions
        elif expected_session == "SYDNEY":
            assert "sydney" in active_sessions


def test_session_state_detector_does_not_return_asia_during_new_york_window(detector):
    utc_time = datetime(2026, 4, 14, 20, 0, tzinfo=ZoneInfo("UTC"))

    assert detector.detect_current_session(utc_time=utc_time) == "NEW_YORK"


def test_get_session_stats_uses_injected_utc_time(detector):
    utc_time = datetime(2026, 11, 17, 14, 0, tzinfo=ZoneInfo("UTC"))

    stats = detector.get_session_stats(utc_time=utc_time)

    assert stats["session"] == "LONDON"
    assert stats["is_overlap"] is True
    assert stats["volatility"] == detector.SESSION_VOLATILITY["LONDON"]
    assert stats["timestamp"] == utc_time.isoformat()