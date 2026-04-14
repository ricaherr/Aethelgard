"""Tests TDD para la fuente canónica de sesiones Forex UTC/DST."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from zoneinfo import ZoneInfo

from core_brain.orchestrators._init_methods import is_market_closed_impl
from core_brain.services.market_session_service import MarketSessionService


@pytest.fixture
def mock_storage():
    """Mock de StorageManager con configuración canónica de sesiones."""
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
        },
        "pre_market_buffer_minutes": 30,
    }
    storage.set_sys_config = MagicMock()
    storage.get_sys_config = MagicMock(return_value={})
    return storage


@pytest.fixture
def market_session_service(mock_storage):
    return MarketSessionService(storage=mock_storage)


def test_market_session_active_no_gap_at_03utc(market_session_service):
    utc_time = datetime(2026, 4, 14, 3, 0, tzinfo=ZoneInfo("UTC"))

    active_sessions = market_session_service.get_active_sessions_utc(utc_time)

    assert active_sessions
    assert {"sydney", "tokyo"}.issubset(set(active_sessions))


def test_market_session_london_ny_overlap_dst(market_session_service):
    utc_time = datetime(2026, 4, 14, 14, 0, tzinfo=ZoneInfo("UTC"))

    active_sessions = set(market_session_service.get_active_sessions_utc(utc_time))

    assert {"london", "ny"}.issubset(active_sessions)


def test_market_session_london_ny_overlap_standard(market_session_service):
    utc_time = datetime(2026, 11, 17, 14, 0, tzinfo=ZoneInfo("UTC"))

    active_sessions = set(market_session_service.get_active_sessions_utc(utc_time))

    assert {"london", "ny"}.issubset(active_sessions)


def test_market_guard_uses_unified_session_source(mock_storage):
    orch = SimpleNamespace(storage=mock_storage)
    utc_time = datetime(2026, 4, 14, 3, 0, tzinfo=ZoneInfo("UTC"))

    with patch("core_brain.orchestrators._init_methods.datetime") as mock_datetime:
        mock_datetime.now.return_value = utc_time
        assert is_market_closed_impl(orch) is False


def test_get_pre_market_range_uses_dst_date(market_session_service):
    utc_time = datetime(2026, 4, 14, 11, 45, tzinfo=ZoneInfo("UTC"))

    pre_market_range = market_session_service.get_pre_market_range(utc_time)

    assert pre_market_range is not None
    assert pre_market_range["session_name"] == "ny"
    assert pre_market_range["start_utc"].hour == 11
    assert pre_market_range["start_utc"].minute == 30
    assert pre_market_range["end_utc"].hour == 12
    assert pre_market_range["end_utc"].minute == 0


def test_sync_ledger_persists_canonical_active_sessions(market_session_service, mock_storage):
    utc_time = datetime(2026, 4, 14, 14, 0, tzinfo=ZoneInfo("UTC"))

    state = market_session_service.sync_ledger(utc_time)

    assert state["active_sessions"]
    assert {"london", "ny"}.issubset(set(state["active_sessions"]))
    mock_storage.set_sys_config.assert_called_once()
