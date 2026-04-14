"""Validaciones de overlap con ventanas dinámicas UTC/DST reales."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest
from zoneinfo import ZoneInfo

from core_brain.sensors.session_state_detector import SessionStateDetector


@pytest.fixture
def detector():
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
    return SessionStateDetector(storage)


class TestSessionOverlapBugFix:
    """Validación exhaustiva de Bug #3 fix."""

    def test_london_ny_overlap_during_window_dst_march(self, detector):
        """Verifica overlap LONDON-NEW_YORK en marzo con DST estadounidense activo."""
        utc_time = datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is True

    def test_london_ny_overlap_start_boundary_dst_march(self, detector):
        """Verifica límite inferior real del overlap en marzo (12:00 UTC)."""
        utc_time = datetime(2026, 3, 9, 12, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is True

    def test_london_ny_overlap_end_boundary_dst_march(self, detector):
        """Verifica fin real del overlap en marzo (17:00 UTC fuera del rango)."""
        utc_time = datetime(2026, 3, 9, 17, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is False

    def test_asia_sydney_overlap_during_window(self, detector):
        """Verifica overlap ASIA-SYDNEY en una fecha con Sydney en AEDT."""
        utc_time = datetime(2026, 3, 9, 3, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is True

    def test_asia_sydney_overlap_start_boundary(self, detector):
        """Verifica el inicio del overlap ASIA-SYDNEY a las 00:00 UTC."""
        utc_time = datetime(2026, 3, 9, 0, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is True

    def test_asia_sydney_overlap_end_boundary(self, detector):
        """Verifica el cierre real del overlap ASIA-SYDNEY a las 05:00 UTC en AEDT."""
        utc_time = datetime(2026, 3, 9, 5, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is False

    def test_asia_sydney_false_positive_fix_after_close(self, detector):
        """Verifica que tras el cierre real de Sydney no persista falso overlap."""
        utc_time = datetime(2026, 3, 9, 7, 30, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is False

    def test_no_overlap_sydney_only(self, detector):
        """Verifica NO overlap cuando solo Sydney está abierto."""
        utc_time = datetime(2026, 4, 14, 22, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is False

    def test_no_overlap_asia_only(self, detector):
        """Verifica NO overlap cuando ASIA está solo (08:00-09:00 UTC)."""
        utc_time = datetime(2026, 3, 9, 8, 30, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is False

    def test_no_overlap_closed_hours(self, detector):
        """Verifica NO overlap en horas de mercado cerrado (09:00-13:00 UTC)."""
        utc_time = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("UTC"))

        assert detector.is_session_overlap(utc_time=utc_time) is False


class TestSessionOverlapComprehensive:
    """Test exhaustivo hora por hora."""

    @pytest.mark.parametrize("hour,expected_overlap", [
        (0, True),   # ASIA-SYDNEY
        (1, True),   # ASIA-SYDNEY
        (4, True),   # ASIA-SYDNEY
        (5, False),  # SYDNEY close, ASIA still open (BUG FIX)
        (8, False),  # ASIA only
        (9, False),  # CLOSED
        (10, False), # CLOSED
        (12, True),  # LONDON-NY start
        (14, True),  # LONDON-NY
        (16, True),  # LONDON-NY
        (17, False), # LONDON close, NY still open
        (20, False), # NY only
        (21, False), # NY close
        (22, False), # SYDNEY open, ASIA not yet
        (23, False), # SYDNEY only
    ])
    def test_overlap_by_hour(self, detector, hour, expected_overlap):
        """Validación exhaustiva: cada hora del día."""
        utc_time = datetime(2026, 3, 9, hour, 0, tzinfo=ZoneInfo("UTC"))
        result = detector.is_session_overlap(utc_time=utc_time)

        assert result == expected_overlap, (
            f"Hour {hour:02d}:00 UTC: "
            f"Expected overlap={expected_overlap}, got {result}"
        )
