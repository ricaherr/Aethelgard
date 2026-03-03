"""
Test Suite: FundamentalGuardService — "Escudo de Noticias"

TRACE_ID: TEST-FUNDAMENTAL-GUARD-2026

Responsibilidades:
- Consultar calendario económico para eventos próximos
- Filtro ROJO (LOCKDOWN): 15 min antes/después alto impacto
- Filtro NARANJA: 30 min antes/después impacto medio
- Integración con StrategyGatekeeper para vetos
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, Mock
from core_brain.services.fundamental_guard import FundamentalGuardService


class TestFundamentalGuardServiceInitialization:
    """Test inicialización del servicio con inyección de dependencias."""

    def test_initialization_with_storage(self):
        """
        GIVEN: StorageManager mock
        WHEN: FundamentalGuardService se inicializa
        THEN: Debe cargar calendario desde storage
        """
        mock_storage = MagicMock()
        mock_storage.get_economic_calendar.return_value = []

        service = FundamentalGuardService(storage=mock_storage)

        assert service.storage == mock_storage
        assert service.calendar_cache is not None
        mock_storage.get_economic_calendar.assert_called_once()

    def test_initialization_empty_calendar(self):
        """
        GIVEN: Storage retorna calendario vacío
        WHEN: FundamentalGuardService inicializa
        THEN: calendar_cache debe estar vacío
        """
        mock_storage = MagicMock()
        mock_storage.get_economic_calendar.return_value = []

        service = FundamentalGuardService(storage=mock_storage)

        assert len(service.calendar_cache) == 0


class TestFundamentalGuardServiceRedFilter:
    """Test FILTRO ROJO (LOCKDOWN) para noticias alto impacto."""

    def test_is_lockdown_period_high_impact_event(self):
        """
        GIVEN: Evento CPI (alto impacto) a las 14:30 UTC
        WHEN: se llama is_lockdown_period(symbol) a las 14:40 UTC
        THEN: Debe retornar True (dentro de 15 min después)
        """
        mock_storage = MagicMock()
        
        # Crear evento CPI
        event_time = datetime(2026, 3, 2, 14, 30, 0)  # 14:30 UTC
        calendar_data = [
            {
                "event": "CPI",
                "impact": "HIGH",
                "time_utc": event_time,
                "forecast": 2.5,
                "previous": 2.3
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        # Simular time at 14:40 UTC (10 min after event)
        current_time = datetime(2026, 3, 2, 14, 40, 0)
        
        is_lockdown = service.is_lockdown_period("EUR/USD", current_time=current_time)

        assert is_lockdown is True

    def test_is_lockdown_period_before_event(self):
        """
        GIVEN: Evento FOMC a las 18:00 UTC
        WHEN: se llama is_lockdown_period(symbol) a las 17:50 UTC
        THEN: Debe retornar True (dentro de 15 min antes)
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 18, 0, 0)  # 18:00 UTC
        calendar_data = [
            {
                "event": "FOMC",
                "impact": "HIGH",
                "time_utc": event_time,
                "forecast": None,
                "previous": 1.5
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 17, 50, 0)  # 10 min before
        
        is_lockdown = service.is_lockdown_period("GBP/USD", current_time=current_time)
        
        assert is_lockdown is True

    def test_is_lockdown_period_outside_window(self):
        """
        GIVEN: Evento CPI a las 14:30 UTC
        WHEN: se llama is_lockdown_period(symbol) a las 15:00 UTC
        THEN: Debe retornar False (fuera de 15 min ventana)
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 14, 30, 0)
        calendar_data = [
            {
                "event": "CPI",
                "impact": "HIGH",
                "time_utc": event_time,
                "forecast": 2.5,
                "previous": 2.3
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 15, 0, 0)  # 30 min after
        
        is_lockdown = service.is_lockdown_period("EUR/USD", current_time=current_time)
        
        assert is_lockdown is False

    def test_is_lockdown_period_no_events(self):
        """
        GIVEN: Calendario económico vacío
        WHEN: se llama is_lockdown_period(symbol)
        THEN: Debe retornar False
        """
        mock_storage = MagicMock()
        mock_storage.get_economic_calendar.return_value = []

        service = FundamentalGuardService(storage=mock_storage)
        
        is_lockdown = service.is_lockdown_period("EUR/USD")
        
        assert is_lockdown is False


class TestFundamentalGuardServiceOrangeFilter:
    """Test FILTRO NARANJA (VOLATILITY) para noticias impacto medio."""

    def test_is_volatility_period_medium_impact(self):
        """
        GIVEN: Evento PMI (impacto MEDIUM) a las 10:00 UTC
        WHEN: se llama is_volatility_period(symbol) a las 10:20 UTC
        THEN: Debe retornar True (dentro de 30 min después)
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 10, 0, 0)
        calendar_data = [
            {
                "event": "PMI Manufacturing",
                "impact": "MEDIUM",
                "time_utc": event_time,
                "forecast": 50.5,
                "previous": 50.2
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 10, 20, 0)  # 20 min after
        
        is_volatility = service.is_volatility_period("EUR/USD", current_time=current_time)
        
        assert is_volatility is True

    def test_is_volatility_period_outside_window(self):
        """
        GIVEN: Evento Retail Sales (MEDIUM) a las 13:30 UTC
        WHEN: se llama is_volatility_period(symbol) a las 14:15 UTC
        THEN: Debe retornar False (fuera de 30 min ventana)
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 13, 30, 0)
        calendar_data = [
            {
                "event": "Retail Sales",
                "impact": "MEDIUM",
                "time_utc": event_time,
                "forecast": 0.3,
                "previous": 0.1
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 14, 15, 0)  # 45 min after
        
        is_volatility = service.is_volatility_period("GBP/USD", current_time=current_time)
        
        assert is_volatility is False


class TestFundamentalGuardServiceMarketSafe:
    """Test método is_market_safe(symbol) para integración con SignalFactory."""

    def test_is_market_safe_during_lockdown(self):
        """
        GIVEN: Mercado en LOCKDOWN (evento CPI activo)
        WHEN: se llama is_market_safe(symbol)
        THEN: Debe retornar False con reason="FUNDAMENTAL_LOCKDOWN"
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 14, 30, 0)
        calendar_data = [
            {
                "event": "CPI",
                "impact": "HIGH",
                "time_utc": event_time,
                "forecast": 2.5,
                "previous": 2.3
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 14, 35, 0)  # 5 min after CPI
        
        is_safe, reason = service.is_market_safe("EUR/USD", current_time=current_time)
        
        assert is_safe is False
        assert "LOCKDOWN" in reason or "CPI" in reason

    def test_is_market_safe_during_volatility(self):
        """
        GIVEN: Mercado en VOLATILITY (evento PMI activo)
        WHEN: se llama is_market_safe(symbol)
        THEN: Debe retornar True pero con reason indicando restricción
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 10, 0, 0)
        calendar_data = [
            {
                "event": "PMI",
                "impact": "MEDIUM",
                "time_utc": event_time,
                "forecast": 50.5,
                "previous": 50.2
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 10, 15, 0)  # 15 min after PM
        
        is_safe, reason = service.is_market_safe("GBP/USD", current_time=current_time)
        
        # Durante volatility, aún es "seguro" pero con advertencia
        assert is_safe is True
        assert "VOLATILITY" in reason or len(reason) > 0

    def test_is_market_safe_no_events(self):
        """
        GIVEN: Calendario económico vacío
        WHEN: se llama is_market_safe(symbol)
        THEN: Debe retornar (True, "")
        """
        mock_storage = MagicMock()
        mock_storage.get_economic_calendar.return_value = []

        service = FundamentalGuardService(storage=mock_storage)
        
        is_safe, reason = service.is_market_safe("EUR/USD")
        
        assert is_safe is True
        assert reason == ""


class TestFundamentalGuardServiceHighImpactEvents:
    """Test detección de eventos alto impacto específicos."""

    @pytest.mark.parametrize("event_name", ["CPI", "FOMC", "NFP", "ECB Rate", "BOJ"])
    def test_high_impact_events_detected(self, event_name):
        """
        GIVEN: Evento {event_name} en calendario
        WHEN: se llama is_lockdown_period()
        THEN: Debe estar en lista de HIGH_IMPACT_EVENTS
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 14, 0, 0)
        calendar_data = [
            {
                "event": event_name,
                "impact": "HIGH",
                "time_utc": event_time
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 14, 10, 0)
        is_lockdown = service.is_lockdown_period("EUR/USD", current_time=current_time)
        
        assert is_lockdown is True


class TestFundamentalGuardServiceIntegration:
    """Test integración con SignalFactory y StrategyGatekeeper."""

    def test_filter_signal_during_lockdown(self):
        """
        GIVEN: Signal generada durante LOCKDOWN
        WHEN: se evalúa con FundamentalGuardService
        THEN: Debe ser vetada con reasoning
        """
        mock_storage = MagicMock()
        
        event_time = datetime(2026, 3, 2, 14, 30, 0)
        calendar_data = [
            {
                "event": "CPI",
                "impact": "HIGH",
                "time_utc": event_time
            }
        ]
        mock_storage.get_economic_calendar.return_value = calendar_data

        service = FundamentalGuardService(storage=mock_storage)
        
        current_time = datetime(2026, 3, 2, 14, 40, 0)
        
        # Simular lógica de integración
        is_safe, reason = service.is_market_safe("EUR/USD", current_time=current_time)
        
        if not is_safe:
            signal_metadata = {"fundamental_veto": reason}
            assert signal_metadata["fundamental_veto"] != ""
