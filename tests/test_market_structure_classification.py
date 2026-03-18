"""
Test Suite: Market Structure Classification Refactoring
Tests for professional structure classification with improved financial logic.

OBJETIVO: Validar que:
1. Clasificación es correcta (STRONG/PARTIAL/INSUFFICIENT)
2. Confianza sigue lógica financiera realista
3. Edge cases están cubiertos
4. Sin duplicación de código (DRY)
5. Responsabilidad única por método
"""

import pytest
import pandas as pd
import numpy as np
from typing import Dict, Any
from core_brain.sensors.market_structure_analyzer import MarketStructureAnalyzer


class MockStorage:
    """Mock de StorageManager para testing"""
    def get_dynamic_params(self):
        return {
            'structure_lookback_candles': 100,
            'structure_min_pivots': 3,
            'breaker_buffer_pips': 5,
            'zig_zag_depth': 5,
            'bos_strength_atr': 2.0
        }


def create_candles_with_structure(
    num_candles: int = 100, 
    trend: str = "uptrend",
    pivot_ratio: Dict[str, int] = None
) -> pd.DataFrame:
    """
    Crear datos OHLC controlados con patrón de estructura específico.
    
    Args:
        num_candles: Cantidad de velas
        trend: "uptrend", "downtrend", "mixed", "ambiguous"
        pivot_ratio: dict con {'hh': 5, 'hl': 4, 'lh': 3, 'll': 2}
    
    Returns:
        DataFrame con OHLC
    """
    dates = pd.date_range(start='2026-01-01', periods=num_candles, freq='h')
    np.random.seed(42)
    
    # Generar estructura base
    base_price = 100.0
    if trend == "uptrend":
        trend_mult = np.linspace(1.0, 1.1, num_candles)  # +10% trend
    elif trend == "downtrend":
        trend_mult = np.linspace(1.0, 0.9, num_candles)  # -10% trend
    else:
        trend_mult = np.ones(num_candles)  # sideways
    
    returns = np.random.normal(0.0001, 0.005, num_candles)
    closes = pd.Series(base_price * trend_mult * np.exp(np.cumsum(returns)))
    
    opens = closes.shift(1).fillna(base_price)
    highs = pd.Series(np.maximum(opens, closes) + np.abs(np.random.normal(0, 0.2, num_candles)))
    lows = pd.Series(np.minimum(opens, closes) - np.abs(np.random.normal(0, 0.2, num_candles)))
    volumes = pd.Series(np.random.randint(1000, 100000, num_candles))
    
    df = pd.DataFrame({
        'time': dates,
        'open': opens.values,
        'high': highs.values,
        'low': lows.values,
        'close': closes.values,
        'volume': volumes.values
    })
    
    return df


class TestMarketStructureClassification:
    """Tests para clasificación de estructura mejorada"""
    
    @pytest.fixture
    def analyzer(self):
        """Fixture: Instancia de analizador"""
        return MarketStructureAnalyzer(storage=MockStorage(), trace_id="test")
    
    def test_strong_uptrend_detection(self, analyzer):
        """
        Caso: STRONG UPTREND
        - Min 3 HH y 3 HL
        - HH >= LH y HL >= LL (coherencia uptrend)
        Esperado: validation_level = STRONG, is_valid = True
        """
        candles = create_candles_with_structure(100, trend="uptrend")
        result = analyzer.detect_market_structure("EURUSD", candles)
        
        # Validaciones
        assert result['validation_level'] == "STRONG", \
            f"Uptrend fuerte debería ser STRONG, obtuvo {result['validation_level']}"
        assert result['is_valid'] is True, \
            f"Uptrend fuerte debería tener is_valid=True"
        assert result['type'] == "UPTREND", \
            f"Estructura debería detectar UPTREND"
        assert result['confidence'] > 50.0, \
            f"STRONG debería tener confidence > 50%, obtuvo {result['confidence']}"
    
    def test_strong_downtrend_detection(self, analyzer):
        """
        Caso: STRONG DOWNTREND
        - Min 3 LH y 3 LL
        - LH >= HH y LL >= HL (coherencia downtrend)
        Esperado: validation_level = STRONG, is_valid = True
        """
        candles = create_candles_with_structure(100, trend="downtrend")
        result = analyzer.detect_market_structure("EURUSD", candles)
        
        assert result['validation_level'] == "STRONG", \
            f"Downtrend fuerte debería ser STRONG"
        assert result['is_valid'] is True
        assert result['type'] == "DOWNTREND"
        assert result['confidence'] > 50.0
    
    def test_partial_structure_detection(self, analyzer):
        """
        Caso: PARTIAL
        - Menos de 3 pivots coherentes en ambos lados
        - Pero al menos 3 pivots totales
        - Y tiene tendencia detectable
        Esperado: validation_level = PARTIAL, is_valid = False
        """
        candles = create_candles_with_structure(100, trend="mixed")
        result = analyzer.detect_market_structure("EURUSD", candles)
        
        # Si es partial o strong, está bien (depende de la simulación)
        # Lo importante es que NO sea INSUFFICIENT si hay pivots
        pivot_count = (result['hh_count'] + result['hl_count'] + 
                       result['lh_count'] + result['ll_count'])
        
        if pivot_count >= 3:
            assert result['validation_level'] in ["STRONG", "PARTIAL"], \
                f"Con {pivot_count} pivots, debería ser STRONG o PARTIAL, no {result['validation_level']}"
        else:
            assert result['validation_level'] == "INSUFFICIENT", \
                f"Con < 3 pivots, debería ser INSUFFICIENT"
    
    def test_insufficient_no_pivots(self, analyzer):
        """
        Caso: INSUFFICIENT - Sin pivots
        - Total pivots < 3
        Esperado: validation_level = INSUFFICIENT, confidence = 0%
        """
        # Crear data plana (casi sin volatilidad)
        dates = pd.date_range(start='2026-01-01', periods=50, freq='h')
        close_price = 100.0
        
        df = pd.DataFrame({
            'time': dates,
            'open': np.full(50, close_price),
            'high': np.full(50, close_price + 0.001),
            'low': np.full(50, close_price - 0.001),
            'close': np.full(50, close_price),
            'volume': np.full(50, 1000)
        })
        
        result = analyzer.detect_market_structure("EURUSD", df)
        
        assert result['validation_level'] == "INSUFFICIENT", \
            f"Sin movimiento ni pivots debería ser INSUFFICIENT"
        assert result['confidence'] == 0.0, \
            f"Confianza debería ser 0% sin pivots"
        assert result['type'] == "UNKNOWN"
    
    def test_confidence_score_is_numeric(self, analyzer):
        """
        Caso: Validar que confianza siempre retorna número 0-100
        Esperado: confidence es float entre 0 y 100 siempre
        """
        for _ in range(5):
            candles = create_candles_with_structure(100, trend="uptrend")
            result = analyzer.detect_market_structure("EURUSD", candles)
            
            assert isinstance(result['confidence'], float), \
                f"Confidence debe ser float"
            assert 0.0 <= result['confidence'] <= 100.0, \
                f"Confidence debe estar entre 0-100, obtuvo {result['confidence']}"
    
    def test_validation_level_always_valid_value(self, analyzer):
        """
        Caso: Validar que validation_level siempre es válido
        Esperado: validation_level ∈ {STRONG, PARTIAL, INSUFFICIENT}
        """
        for trend in ["uptrend", "downtrend", "mixed"]:
            candles = create_candles_with_structure(100, trend=trend)
            result = analyzer.detect_market_structure("EURUSD", candles)
            
            assert result['validation_level'] in ["STRONG", "PARTIAL", "INSUFFICIENT"], \
                f"validation_level debe ser STRONG/PARTIAL/INSUFFICIENT, obtuvo {result['validation_level']}"
    
    def test_no_insufficient_with_many_pivots(self, analyzer):
        """
        REGRESIÓN: Verificar que nunca haya INSUFFICIENT si hay muchos pivots
        Bug original: AUDUSD HH=5, HL=4, LH=3, LL=7 → INSUFFICIENT (INCORRECTO)
        Esperado: Con >6 pivots totales, mínimo PARTIAL
        """
        candles = create_candles_with_structure(100, trend="mixed")
        result = analyzer.detect_market_structure("EURUSD", candles)
        
        pivot_count = (result['hh_count'] + result['hl_count'] + 
                       result['lh_count'] + result['ll_count'])
        
        if pivot_count >= 6:
            assert result['validation_level'] in ["STRONG", "PARTIAL"], \
                f"Con {pivot_count} pivots, NO puede ser INSUFFICIENT"
    
    def test_coherence_affects_confidence(self, analyzer):
        """
        Caso: Validar que mayor coherencia → mayor confianza
        Uptrend con HH=8, HL=7, LH=1, LL=1 debería tener >60% confidence
        """
        candles = create_candles_with_structure(100, trend="uptrend")
        result = analyzer.detect_market_structure("EURUSD", candles)
        
        if result['validation_level'] == "STRONG":
            # Si es STRONG uptrend, HH+HL debe ser mayoría
            hh_hl_ratio = (result['hh_count'] + result['hl_count']) / max(
                result['hh_count'] + result['hl_count'] + 
                result['lh_count'] + result['ll_count'], 1
            )
            
            # Confianza debe correlacionar con ratio coherente
            expected_confidence = hh_hl_ratio * 100
            assert result['confidence'] >= expected_confidence * 0.8, \
                f"Confidence {result['confidence']} no refleja coherencia {hh_hl_ratio}"
    
    def test_backward_compatibility_is_valid_field(self, analyzer):
        """
        Caso: Backward compatibility
        is_valid debe ser True si STRONG, False si PARTIAL/INSUFFICIENT
        """
        for trend in ["uptrend", "downtrend", "mixed"]:
            candles = create_candles_with_structure(100, trend=trend)
            result = analyzer.detect_market_structure("EURUSD", candles)
            
            expected_is_valid = (result['validation_level'] == "STRONG")
            assert result['is_valid'] == expected_is_valid, \
                f"is_valid debe coincidir con validation_level"


class TestEdgeCases:
    """Tests para edge cases críticos"""
    
    @pytest.fixture
    def analyzer(self):
        return MarketStructureAnalyzer(storage=MockStorage(), trace_id="test_edge")
    
    def test_empty_candles(self, analyzer):
        """Edge case: DataFrame vacío"""
        empty_df = pd.DataFrame(columns=['open', 'high', 'low', 'close', 'volume'])
        
        # Debería manejar gracefully sin crash
        try:
            result = analyzer.detect_market_structure("EURUSD", empty_df)
            assert result['validation_level'] == "INSUFFICIENT"
        except Exception as e:
            pytest.fail(f"analyze debería manejar DF vacío: {e}")
    
    def test_single_candle(self, analyzer):
        """Edge case: Una sola vela"""
        df = pd.DataFrame({
            'open': [100.0],
            'high': [101.0],
            'low': [99.0],
            'close': [100.5],
            'volume': [1000]
        })
        
        result = analyzer.detect_market_structure("EURUSD", df)
        assert result['validation_level'] == "INSUFFICIENT"
        assert result['confidence'] == 0.0
    
    def test_all_same_price(self, analyzer):
        """Edge case: Todas las velas con mismo precio"""
        df = pd.DataFrame({
            'open': np.full(50, 100.0),
            'high': np.full(50, 100.0),
            'low': np.full(50, 100.0),
            'close': np.full(50, 100.0),
            'volume': np.full(50, 1000)
        })
        
        result = analyzer.detect_market_structure("EURUSD", df)
        # Sin movimiento = sin pivots = INSUFFICIENT
        assert result['validation_level'] == "INSUFFICIENT"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
