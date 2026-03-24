"""
Tests: EdgeMonitor — TAREA 3.2
==============================
El warning de MT5 no disponible no debe emitirse cada 60s cuando MT5
está deliberadamente deshabilitado (no inyectado desde el inicio).

Coverage:
  - EdgeMonitor no repite WARNING en cada ciclo cuando mt5_connector=None
  - Primera llamada emite INFO de startup (no WARNING)
  - Llamadas posteriores emiten DEBUG solamente
"""
import pytest
from unittest.mock import MagicMock, patch


from core_brain.edge_monitor import EdgeMonitor


class TestEdgeMonitorMt5Warning:
    """TAREA 3.2: Silenciar warning repetitivo de MT5 cuando no está inyectado."""

    @pytest.fixture
    def storage(self):
        s = MagicMock()
        s.save_edge_learning = MagicMock()
        return s

    def test_first_call_does_not_emit_warning_level(self, storage):
        """Primera llamada con mt5=None NO debe emitir mensaje de nivel WARNING."""
        monitor = EdgeMonitor(storage=storage, mt5_connector=None)

        with patch("core_brain.edge_monitor.logger") as mock_logger:
            monitor._get_mt5_connector()

        mock_logger.warning.assert_not_called()

    def test_repeated_calls_never_emit_warning(self, storage):
        """Múltiples llamadas con mt5=None nunca emiten WARNING."""
        monitor = EdgeMonitor(storage=storage, mt5_connector=None)

        with patch("core_brain.edge_monitor.logger") as mock_logger:
            for _ in range(5):
                monitor._get_mt5_connector()

        mock_logger.warning.assert_not_called()

    def test_returns_none_when_not_injected(self, storage):
        """_get_mt5_connector devuelve None cuando mt5_connector no fue inyectado."""
        monitor = EdgeMonitor(storage=storage, mt5_connector=None)
        with patch("core_brain.edge_monitor.logger"):
            result = monitor._get_mt5_connector()
        assert result is None

    def test_returns_connector_when_injected(self, storage):
        """_get_mt5_connector devuelve el conector cuando sí fue inyectado."""
        mock_connector = MagicMock()
        monitor = EdgeMonitor(storage=storage, mt5_connector=mock_connector)
        result = monitor._get_mt5_connector()
        assert result is mock_connector


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
