"""
Test para validar la corrección de Bug #3: is_session_overlap() lógica incorrecta.

Validaciones:
1. LONDON-NY overlap: 13:00-16:00 UTC ✅
2. ASIA-SYDNEY overlap: 00:00-07:00 UTC ✅ (FIXED: antes falso positivo en 07:00-08:00)
3. No otros overlaps
4. Edge cases (límites exactos)
"""

import pytest
from datetime import datetime, time
from zoneinfo import ZoneInfo
from unittest.mock import patch

from core_brain.sensors.session_state_detector import SessionStateDetector


class TestSessionOverlapBugFix:
    """Validación exhaustiva de Bug #3 fix."""

    def test_london_ny_overlap_during_window(self):
        """Verifica overlap LONDON-NEW_YORK en 13:00-16:00 UTC."""
        detector = SessionStateDetector(None)
        
        # 14:00 UTC está en [13:00, 16:00) - Overlap
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 14, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is True, "LONDON-NY overlap should be detected at 14:00 UTC"

    def test_london_ny_overlap_start_boundary(self):
        """Verifica overlap LONDON-NEW_YORK en límite inferior (13:00 UTC)."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 13, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is True, "NY opens at 13:00, overlap should be True"

    def test_london_ny_overlap_end_boundary(self):
        """Verifica NO overlap LONDON-NEW_YORK en límite superior (16:00)."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 16, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "London closes at 16:00, no overlap"

    def test_asia_sydney_overlap_during_window(self):
        """Verifica overlap ASIA-SYDNEY en 00:00-07:00 UTC."""
        detector = SessionStateDetector(None)
        
        # 03:00 UTC está en [00:00, 07:00) - Overlap
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 3, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is True, "ASIA-SYDNEY overlap should be detected at 03:00 UTC"

    def test_asia_sydney_overlap_start_boundary(self):
        """Verifica overlap ASIA-SYDNEY en límite inferior (00:00 UTC)."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 0, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is True, "ASIA opens at 00:00, overlap should be True"

    def test_asia_sydney_overlap_end_boundary(self):
        """
        CRITICAL: Verifica NO overlap en 07:00 UTC.
        SYDNEY cierra exactamente a 07:00, ASIA aún abierto (cierra 09:00).
        Este es el BUG FIX: antes retornaba True incorrectamente.
        """
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 7, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "SYDNEY closes at 07:00, no overlap"

    def test_asia_sydney_false_positive_fix_07_30(self):
        """
        CRITICAL BUG FIX: 07:30 UTC.
        SYDNEY ya está CERRADO (cierre 07:00).
        ASIA aún ABIERTO (cierre 09:00).
        Debería retornar False (este era el falso positivo).
        """
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 7, 30, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "BUG FIX: 07:30 UTC - SYDNEY closed, ASIA still open"

    def test_asia_sydney_false_positive_fix_07_59(self):
        """
        CRITICAL BUG FIX: 07:59 UTC (justo antes 08:00).
        SYDNEY está CERRADO, ASIA aún ABIERTO.
        Debería retornar False.
        """
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 7, 59, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "BUG FIX: 07:59 UTC - SYDNEY closed, ASIA still open"

    def test_no_overlap_sydney_only(self):
        """Verifica NO overlap cuando SYDNEY está solo (22:00-23:59 UTC)."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 23, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "23:00 UTC: SYDNEY open, ASIA not yet open"

    def test_no_overlap_asia_only(self):
        """Verifica NO overlap cuando ASIA está solo (08:00-09:00 UTC)."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 8, 30, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "ASIA open, SYDNEY closed (since 07:00)"

    def test_no_overlap_closed_hours(self):
        """Verifica NO overlap en horas de mercado cerrado (09:00-13:00 UTC)."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, 10, 0, tzinfo=ZoneInfo("UTC"))
            assert detector.is_session_overlap() is False, "10:00 UTC: All markets closed"


class TestSessionOverlapComprehensive:
    """Test exhaustivo hora por hora."""

    @pytest.mark.parametrize("hour,expected_overlap", [
        (0, True),   # ASIA-SYDNEY
        (1, True),   # ASIA-SYDNEY
        (6, True),   # ASIA-SYDNEY
        (7, False),  # SYDNEY close, ASIA still open (BUG FIX)
        (8, False),  # ASIA only
        (9, False),  # CLOSED
        (10, False), # CLOSED
        (13, True),  # LONDON-NY start
        (14, True),  # LONDON-NY
        (15, True),  # LONDON-NY
        (16, False), # LONDON close, NY still open
        (20, False), # NY only
        (21, False), # NY close
        (22, False), # SYDNEY open, ASIA not yet
        (23, False), # SYDNEY only
    ])
    def test_overlap_by_hour(self, hour, expected_overlap):
        """Validación exhaustiva: cada hora del día."""
        detector = SessionStateDetector(None)
        
        with patch('core_brain.sensors.session_state_detector.datetime') as mock_datetime:
            mock_datetime.now.return_value = datetime(2026, 3, 9, hour, 0, tzinfo=ZoneInfo("UTC"))
            result = detector.is_session_overlap()
            assert result == expected_overlap, (
                f"Hour {hour:02d}:00 UTC: "
                f"Expected overlap={expected_overlap}, got {result}"
            )
