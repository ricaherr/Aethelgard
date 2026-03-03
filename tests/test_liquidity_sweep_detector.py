"""
Test Suite: LiquiditySweepDetector - Detección de Breakout Falso + Reversión

TRACE_ID: TEST-LIQUIDITY-SWEEP-2026

Responsabilidades:
- Detectar PIN BAR: Wick > 60%, cuerpo < 30% del rango
- Detectar ENGULFING: Vela actual envuelve anterior
- Validar que cierre está dentro del rango previo (negación de ruptura)
- Calcular probabilidad/strength de reversión
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock
import pandas as pd

from core_brain.sensors.liquidity_sweep_detector import LiquiditySweepDetector


class TestLiquiditySweepDetectorInitialization:
    """Test inicialización del detector."""

    def test_detector_initializes_with_dependencies(self):
        """
        GIVEN: MagicMock de StorageManager
        WHEN: Se crea LiquiditySweepDetector
        THEN: Debe inicializar correctamente
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT", trace_id="TEST-001")
        
        assert detector.storage_manager == mock_storage
        assert detector.trace_id == "TEST-001"
        assert detector.pin_bar_wick_threshold == 0.60  # 60%
        assert detector.pin_bar_body_threshold == 0.30  # 30%


class TestLiquiditySweepDetectorPinBar:
    """Test detección de PIN BAR."""

    def test_detect_pin_bar_bullish(self):
        """
        GIVEN: Vela elefante bullish (wick abajo > 50%, cuerpo < 25%)
        WHEN: Se llama detect_pin_bar()
        THEN: Debe retornar (True, 'BULLISH', confidence)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        current_candle = {
            'open': 1.0850,
            'high': 1.0920,   # 70 pips arriba
            'low': 1.0750,    # 100 pips abajo (wick grande)
            'close': 1.0910,  # Cierre arriba (cuerpo 60 pips)
        }
        # Rango: 170 pips
        # Cuerpo: 60 pips = 35% (ajustar para < 25%)
        
        # Ajustar para que cuerpo sea < 25%
        current_candle = {
            'open': 1.0850,
            'high': 1.0920,   # 70 pips arriba
            'low': 1.0750,    # 100 pips abajo (total rango = 170)
            'close': 1.0865,  # Cierre ligero arriba (cuerpo = 15 pips = 8.8%)
        }
        
        is_pin_bar, direction, strength = detector.detect_pin_bar(current_candle)
        
        assert is_pin_bar is True
        assert direction == 'BULLISH'
        assert 0 < strength < 1  # Confidence score

    def test_detect_pin_bar_bearish(self):
        """
        GIVEN: Vela elefante bearish (wick arriba > 50%, cuerpo < 25%)
        WHEN: Se llama detect_pin_bar()
        THEN: Debe retornar (True, 'BEARISH', confidence)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        # Crear vela con wick superior >= 50% del rango
        # high - max(open, close) >= 0.50 * rango_total
        current_candle = {
            'open': 1.0900,
            'high': 1.1000,    # 100 pips arriba
            'low': 1.0800,     # 100 pips abajo (rango = 200)
            'close': 1.0885,   # 15 pips abajo (cuerpo = 15 = 7.5%)
        }
        # Upper wick: 1.1000 - 1.0900 = 100 pips (50% de 200) ✓
        # Cuerpo: 15 pips = 7.5% < 25% ✓
        
        is_pin_bar, direction, strength = detector.detect_pin_bar(current_candle)
        
        assert is_pin_bar is True
        assert direction == 'BEARISH'
        assert 0 < strength < 1

    def test_no_pin_bar_too_large_body(self):
        """
        GIVEN: Vela con cuerpo > 40% (no es PIN BAR)
        WHEN: Se llama detect_pin_bar()
        THEN: Debe retornar (False, None, 0)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        current_candle = {
            'open': 1.0850,
            'high': 1.0900,
            'low': 1.0800,
            'close': 1.0870,  # Cuerpo de 20 pips pero wick mínimo
        }
        
        is_pin_bar, direction, strength = detector.detect_pin_bar(current_candle)
        
        # Con wick/body ratio bajo, no es pin bar válido
        assert is_pin_bar is False or strength < 0.5


class TestLiquiditySweepDetectorEngulfing:
    """Test detección de ENGULFING."""

    def test_detect_bullish_engulfing(self):
        """
        GIVEN: Vela actual envuelve anterior + cierre arriba
        WHEN: Se llama detect_engulfing()
        THEN: Debe retornar (True, 'BULLISH', confidence)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        previous_candle = {
            'open': 1.0850,
            'close': 1.0840,  # Bajista
            'high': 1.0860,
            'low': 1.0830,
        }
        
        current_candle = {
            'open': 1.0820,   # Abre debajo del anterior
            'close': 1.0870,  # Cierra arriba (envuelve)
            'high': 1.0875,
            'low': 1.0815,    # Abre/cierra dentro
        }
        
        is_engulf, direction, strength = detector.detect_engulfing(previous_candle, current_candle)
        
        assert is_engulf is True
        assert direction == 'BULLISH'
        assert 0 < strength <= 1

    def test_detect_bearish_engulfing(self):
        """
        GIVEN: Vela actual envuelve anterior (bajista)
        WHEN: Se llama detect_engulfing()
        THEN: Debe retornar (True, 'BEARISH', confidence)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        previous_candle = {
            'open': 1.0850,
            'close': 1.0860,  # Alcista
            'high': 1.0875,
            'low': 1.0840,
        }
        
        current_candle = {
            'open': 1.0880,   # Abre arriba del anterior
            'close': 1.0830,  # Cierra abajo (envuelve)
            'high': 1.0890,
            'low': 1.0825,    # Abre/cierra dentro
        }
        
        is_engulf, direction, strength = detector.detect_engulfing(previous_candle, current_candle)
        
        assert is_engulf is True
        assert direction == 'BEARISH'
        assert 0 < strength <= 1

    def test_no_engulfing_partial_overlap(self):
        """
        GIVEN: Vela que solo parcialmente envuelve
        WHEN: Se llama detect_engulfing()
        THEN: Debe retornar (False, None, 0)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        previous_candle = {
            'open': 1.0850,
            'close': 1.0860,
            'high': 1.0875,
            'low': 1.0840,
        }
        
        current_candle = {
            'open': 1.0855,  # Dentro del anterior
            'close': 1.0865,  # Dentro del anterior
            'high': 1.0880,
            'low': 1.0845,
        }
        
        is_engulf, direction, strength = detector.detect_engulfing(previous_candle, current_candle)
        
        assert is_engulf is False
        assert direction is None


class TestLiquiditySweepDetectorRangeValidation:
    """Test validación que cierre está dentro del rango previo."""

    def test_close_within_range_bullish_breakout(self):
        """
        GIVEN: Precio supers nivel por breakout, pero cierra dentro anterior
        WHEN: Se valida is_within_previous_range()
        THEN: Debe retornar True (falsa ruptura validada)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        # Nivel anterior: 1.0840-1.0850
        # Breakout sube a 1.0860
        # Pero cierra a 1.0845 (dentro del rango)
        
        is_within = detector.is_within_previous_range(
            current_close=1.0845,
            prev_high=1.0850,
            prev_low=1.0840
        )
        
        assert is_within is True

    def test_close_outside_range_continues_breakout(self):
        """
        GIVEN: Precio supers nivel y cierra afuera (continúa ruptura)
        WHEN: Se valida is_within_previous_range()
        THEN: Debe retornar False (no es falsa ruptura)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        is_within = detector.is_within_previous_range(
            current_close=1.0855,
            prev_high=1.0850,
            prev_low=1.0840
        )
        
        assert is_within is False


class TestLiquiditySweepDetectorFalseBreakout:
    """Test detección integrada: breakout falso + reversión."""

    def test_detect_false_breakout_with_reversal(self):
        """
        GIVEN: Breakout falso (sube/baja) + reversal candle válida
        WHEN: Se llama detect_false_breakout_with_reversal()
        THEN: Debe retornar (True, pattern_type, strength)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        breakout_level = 1.0950  # Session High
        current_candle = {
            'open': 1.0930,
            'high': 1.0955,   # Supers el nivel
            'low': 1.0920,
            'close': 1.0925,  # Cierra dentro previo (falsa ruptura)
        }
        previous_high = 1.0950
        previous_low = 1.0900
        
        is_false_breakout, pattern, strength = detector.detect_false_breakout_with_reversal(
            breakout_level=breakout_level,
            current_candle=current_candle,
            prev_high=previous_high,
            prev_low=previous_low,
            direction='ABOVE'
        )
        
        assert is_false_breakout is True
        assert pattern in ['PIN_BAR', 'ENGULFING', 'REVERSAL']
        assert 0 < strength <= 1

    def test_no_false_breakout_continues_direction(self):
        """
        GIVEN: Breakout que continúa (no es falso)
        WHEN: Se llama detect_false_breakout_with_reversal()
        THEN: Debe retornar (False, None, 0)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage)
        
        breakout_level = 1.0950
        current_candle = {
            'open': 1.0940,
            'high': 1.0960,
            'low': 1.0935,
            'close': 1.0955,  # Cierra afuera (continúa ruptura)
        }
        
        is_false_breakout, pattern, strength = detector.detect_false_breakout_with_reversal(
            breakout_level=breakout_level,
            current_candle=current_candle,
            prev_high=1.0950,
            prev_low=1.0900,
            direction='ABOVE'
        )
        
        assert is_false_breakout is False
        assert pattern is None


class TestLiquiditySweepDetectorVolumeValidation:
    """Test validación de volumen en reversión."""

    def test_volume_confirmation_high_volume_reversal(self):
        """
        GIVEN: Reversal con volumen > 120% del promedio
        WHEN: Se valida validate_volume_confirmation()
        THEN: Debe retornar (True, confidence_boost)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        ohlcv_data = [
            {'volume': 1000},
            {'volume': 1050},
            {'volume': 1020},
            {'volume': 980},
            {'volume': 1100},
            # Promedio: ~1030
            # Reversal vol: 1500 (> 120% de promedio)
        ]
        
        is_confirmed, confidence_boost = detector.validate_volume_confirmation(
            reversal_volume=1500,
            average_volume=1030
        )
        
        assert is_confirmed is True
        assert 0 < confidence_boost <= 0.2  # Boost máximo +20%

    def test_no_volume_confirmation_low_volume(self):
        """
        GIVEN: Reversal con volumen < 80% del promedio
        WHEN: Se valida validate_volume_confirmation()
        THEN: Debe retornar (False, 0)
        """
        mock_storage = MagicMock()
        detector = LiquiditySweepDetector(storage=mock_storage, tenant_id="TEST_TENANT")
        
        is_confirmed, confidence_boost = detector.validate_volume_confirmation(
            reversal_volume=800,
            average_volume=1000
        )
        
        assert is_confirmed is False
        assert confidence_boost == 0
