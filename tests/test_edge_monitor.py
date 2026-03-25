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


class TestEdgeMonitorConnectorAgnostic:
    """HU 10.5: EdgeMonitor accepts a generic connectors dict (not MT5-hardcoded)."""

    @pytest.fixture
    def storage(self):
        s = MagicMock()
        s.save_edge_learning = MagicMock()
        return s

    def test_accepts_connectors_dict(self, storage):
        """EdgeMonitor can be constructed with connectors={connector_id: instance}."""
        mock_conn = MagicMock()
        monitor = EdgeMonitor(storage=storage, connectors={"mt5": mock_conn})
        assert monitor.connectors == {"mt5": mock_conn}

    def test_accepts_multiple_connectors(self, storage):
        """EdgeMonitor can hold multiple heterogeneous connectors."""
        mt5 = MagicMock()
        ctrader = MagicMock()
        monitor = EdgeMonitor(storage=storage, connectors={"mt5": mt5, "ctrader": ctrader})
        assert len(monitor.connectors) == 2

    def test_empty_connectors_does_not_raise(self, storage):
        """No connectors → no exception, just silent skip."""
        monitor = EdgeMonitor(storage=storage)
        # Should not raise
        monitor._check_mt5_external_operations()

    def test_mt5_connector_kwarg_backward_compat(self, storage):
        """Legacy mt5_connector= kwarg is wrapped into connectors dict automatically."""
        mock_mt5 = MagicMock()
        monitor = EdgeMonitor(storage=storage, mt5_connector=mock_mt5)
        assert "mt5" in monitor.connectors
        assert monitor.connectors["mt5"] is mock_mt5

    def test_get_active_connectors_returns_all(self, storage):
        """_get_active_connectors() returns the full connectors dict."""
        mt5 = MagicMock()
        paper = MagicMock()
        monitor = EdgeMonitor(storage=storage, connectors={"mt5": mt5, "paper": paper})
        active = monitor._get_active_connectors()
        assert "mt5" in active
        assert "paper" in active

    def test_no_warning_logged_when_no_connectors(self, storage):
        """When no connectors provided, no WARNING is emitted."""
        monitor = EdgeMonitor(storage=storage)
        with patch("core_brain.edge_monitor.logger") as mock_logger:
            monitor._get_active_connectors()
        mock_logger.warning.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
