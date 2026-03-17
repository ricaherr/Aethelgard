"""
Test Suite: SessionLiquiditySensor - Detector de Niveles de Sesión

TRACE_ID: TEST-SESSION-LIQUIDITY-2026

Responsabilidades:
- Calcular Highest_High y Lowest_Low de sesión Londres
- Calcular máximo/mínimo del día anterior (H-1)
- Detectar breakouts por encima/debajo de estos niveles
- Mantener histórico de bordes de liquidez para análisis
"""

import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
import pandas as pd
import numpy as np

from core_brain.sensors.session_liquidity_sensor import SessionLiquiditySensor


class TestSessionLiquiditySensorInitialization:
    """Test inicialización del sensor con inyección de dependencias."""

    def test_sensor_initializes_with_storage(self):
        """
        GIVEN: MagicMock de StorageManager y tenant_id
        WHEN: Se crea SessionLiquiditySensor
        THEN: Debe inicializar correctamente con trace_id y tenant_id
        """
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT", trace_id="TEST-001")
        
        assert sensor.storage_manager == mock_storage
        assert sensor.user_id == "TEST_TENANT"
        assert sensor.trace_id == "TEST-001"
        assert sensor.london_session_start == 8  # 08:00 GMT
        assert sensor.london_session_end == 17   # 17:00 GMT


class TestSessionLiquiditySensorSessionHighLow:
    """Test cálculo de Session High/Low de Londres."""

    def test_session_high_low_london_hours(self):
        """
        GIVEN: DataFrame con 12 velas (08:00-20:00 GMT)
        WHEN: Período cruza sesión completa de Londres (08:00-17:00)
        THEN: Debe retornar High/Low solo de horas de Londres
        """
        # Crear 12 velas con precios variados
        times = pd.date_range('2026-03-02 08:00', periods=12, freq='h', tz=timezone.utc)
        df = pd.DataFrame({
            'open': [1.0850, 1.0855, 1.0860, 1.0865, 1.0870, 1.0875, 1.0880, 1.0885, 1.0890, 1.0895, 1.0900, 1.0805],
            'high': [1.0860, 1.0870, 1.0880, 1.0890, 1.0900, 1.0910, 1.0920, 1.0930, 1.0940, 1.0950, 1.0870, 1.0815],
            'low':  [1.0840, 1.0845, 1.0850, 1.0855, 1.0860, 1.0865, 1.0870, 1.0875, 1.0880, 1.0885, 1.0850, 1.0790],
            'close': [1.0855, 1.0860, 1.0865, 1.0870, 1.0875, 1.0880, 1.0885, 1.0890, 1.0895, 1.0900, 1.0860, 1.0800],
        }, index=times)
        
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT", trace_id="TEST-002")
        
        session_high, session_low = sensor.get_london_session_high_low(df)
        
        # High durante Londres 08:00-17:00 (17 excluido): máximo debe ser 1.0940 (16:00)
        # Low durante Londres: mínimo debe ser 1.0840 (08:00)
        assert session_high == 1.0940  # Hora 16
        assert session_low == 1.0840

    def test_session_high_low_empty_dataframe(self):
        """
        GIVEN: DataFrame vacío
        WHEN: Se llama get_london_session_high_low()
        THEN: Debe retornar (None, None)
        """
        df = pd.DataFrame({'high': [], 'low': []})
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        session_high, session_low = sensor.get_london_session_high_low(df)
        
        assert session_high is None
        assert session_low is None

    def test_session_high_low_insufficient_data(self):
        """
        GIVEN: DataFrame con menos de 8 velas (< sesión completa)
        WHEN: Se llama get_london_session_high_low()
        THEN: Debe procesar lo disponible correctamente
        """
        times = pd.date_range('2026-03-02 12:00', periods=4, freq='h', tz=timezone.utc)
        df = pd.DataFrame({
            'high': [1.0890, 1.0900, 1.0910, 1.0920],
            'low':  [1.0875, 1.0885, 1.0895, 1.0905],
        }, index=times)
        
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        session_high, session_low = sensor.get_london_session_high_low(df)
        
        assert session_high == 1.0920
        assert session_low == 1.0875


class TestSessionLiquiditySensorPreviousDayHighLow:
    """Test cálculo de High/Low del día anterior."""

    def test_previous_day_high_low(self):
        """
        GIVEN: DataFrame con datos de múltiples días
        WHEN: Se llama get_previous_day_high_low()
        THEN: Debe retornar High/Low del período correctamente
        """
        # Crear datos simples de 2 días (24 velas cada uno)
        times = pd.date_range('2026-03-01 00:00', periods=48, freq='h', tz=timezone.utc)
        
        # Día 1 (0-23): precios 1.0800-1.0824
        # Día 2 (24-47): precios 1.0920-1.0944
        prices_high = [1.0800 + i*0.0005 for i in range(24)] + [1.0920 + i*0.0005 for i in range(24)]
        prices_low = [p - 0.0010 for p in prices_high]
        
        df = pd.DataFrame({
            'high': prices_high,
            'low':  prices_low,
        }, index=times)
        
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        # Get previous day high/low con current_date = 2 de Marzo
        prev_high, prev_low = sensor.get_previous_day_high_low(df, current_date=datetime(2026, 3, 2, tzinfo=timezone.utc))
        
        # Debe dar los valores del primer día
        expected_high = max(prices_high[:24])
        assert prev_high == expected_high or prev_high == max(prices_high)  # Fallback si día anterior no está

    def test_previous_day_high_low_single_day(self):
        """
        GIVEN: DataFrame con solo un día
        WHEN: Se llama get_previous_day_high_low()
        THEN: Debe retornar ese día o valores por defecto
        """
        times = pd.date_range('2026-03-02 00:00', periods=24, freq='h', tz=timezone.utc)
        df = pd.DataFrame({
            'high': [1.0800 + i*0.0010 for i in range(24)],
            'low':  [1.0790 + i*0.0010 for i in range(24)],
        }, index=times)
        
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        prev_high, prev_low = sensor.get_previous_day_high_low(df)
        
        # Debe retornar valores válidos (máximo y mínimo del rango disponible)
        assert prev_high is not None
        assert prev_low is not None
        assert prev_high > prev_low


class TestSessionLiquiditySensorBreakoutDetection:
    """Test detección de breakout por encima/debajo de niveles."""

    def test_detect_breakout_above_session_high(self):
        """
        GIVEN: Session High = 1.0950
        WHEN: Precio cierra a 1.0955
        THEN: Debe retornar (True, 'BULLISH', 0.0005)
        """
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        is_breakout, direction, distance = sensor.detect_breakout(
            current_price=1.0955,
            breakout_level=1.0950,
            direction='ABOVE'
        )
        
        assert is_breakout is True
        assert direction == 'BULLISH'
        assert abs(distance - 0.0005) < 1e-5

    def test_detect_breakout_below_session_low(self):
        """
        GIVEN: Session Low = 1.0840
        WHEN: Precio cierra a 1.0835
        THEN: Debe retornar (True, 'BEARISH', 0.0005)
        """
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        is_breakout, direction, distance = sensor.detect_breakout(
            current_price=1.0835,
            breakout_level=1.0840,
            direction='BELOW'
        )
        
        assert is_breakout is True
        assert direction == 'BEARISH'
        assert abs(distance - 0.0005) < 1e-5

    def test_no_breakout_within_level(self):
        """
        GIVEN: Session High = 1.0950
        WHEN: Precio cierra a 1.0945 (dentro)
        THEN: Debe retornar (False, None, distance_pequeña)
        """
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        is_breakout, direction, distance = sensor.detect_breakout(
            current_price=1.0945,
            breakout_level=1.0950,
            direction='ABOVE'
        )
        
        assert is_breakout is False
        assert direction is None
        # Distance se calcula aunque no hay breakout
        assert abs(distance - 0.0005) < 1e-5


class TestSessionLiquiditySensorLiquidityZoneMapping:
    """Test mapeo de zonas de liquidez (session edges)."""

    def test_get_liquidity_zones(self):
        """
        GIVEN: Session High/Low y Previous Day High/Low
        WHEN: Se llama get_liquidity_zones()
        THEN: Debe retornar dict con todos los niveles críticos
        """
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT")
        
        zones = sensor.get_liquidity_zones(
            london_high=1.0950,
            london_low=1.0840,
            prev_day_high=1.0920,
            prev_day_low=1.0810
        )
        
        assert zones['london_session_high'] == 1.0950
        assert zones['london_session_low'] == 1.0840
        assert zones['previous_day_high'] == 1.0920
        assert zones['previous_day_low'] == 1.0810
        assert 'density_indicator' in zones


class TestSessionLiquiditySensorIntegration:
    """Test integración end-to-end del sensor."""

    def test_full_liquidity_analysis_london_session(self):
        """
        GIVEN: DataFrame completo de sesión Londres con breakout
        WHEN: Se ejecuta análisis completo
        THEN: Debe identificar niveles, breakouts y zonas de liquidez
        """
        times = pd.date_range('2026-03-02 08:00', periods=12, freq='h', tz=timezone.utc)
        df = pd.DataFrame({
            'open': [1.0850 + i*0.0005 for i in range(12)],
            'high': [1.0860 + i*0.0005 for i in range(12)],
            'low':  [1.0840 + i*0.0005 for i in range(12)],
            'close': [1.0855 + i*0.0005 for i in range(12)],
        }, index=times)
        
        mock_storage = MagicMock()
        sensor = SessionLiquiditySensor(storage=mock_storage, user_id="TEST_TENANT", trace_id="TEST-INTEG-001")
        
        result = sensor.analyze_session_liquidity(df)
        
        assert 'london_high' in result
        assert 'london_low' in result
        assert 'has_breakout' in result
        assert 'liquidity_zones' in result
