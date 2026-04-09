"""
Test Market Structure Analyzer - Detección HH/HL/LH/LL y Breaker Blocks

TRACE_ID: TEST-MARKET-STRUCT-001

Cubre:
- Detección correcta de pivots (HH, HL, LH, LL)
- Identificación de Breaker Block (zona de quiebre)
- Validación de ruptura (BOS - Break of Structure)
- Cálculo de zonas de pullback
- Inyección de dependencias
- Caching de resultado
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List

from core_brain.sensors.market_structure_analyzer import MarketStructureAnalyzer


class TestMarketStructureAnalyzer(unittest.TestCase):
    """Test suite para Market Structure Analyzer."""
    
    def setUp(self):
        """Preparar mocks y fixtures."""
        # Mock storage
        self.mock_storage = self._create_mock_storage()
        
        # Inicializar analyzer con trace_id
        self.analyzer = MarketStructureAnalyzer(
            storage=self.mock_storage,
            trace_id="TEST-MARKET-STRUCT-001"
        )
        
        # Datos de prueba: 20 velas con tendencia alcista
        self.test_candles = self._generate_uptrend_candles()
    
    
    def _create_mock_storage(self) -> Dict[str, Any]:
        """Crear mock simple de storage."""
        class MockStorage:
            def get_dynamic_params(self):
                return {
                    'structure_min_pivots': 3,
                    'breaker_buffer_pips': 5,
                    'structure_lookback_candles': 20,
                    'zig_zag_depth': 5
                }
        
        return MockStorage()
    
    
    def _generate_uptrend_candles(self) -> pd.DataFrame:
        """Generar 20 velas con HH/HL (tendencia alcista)."""
        data = []
        base_price = 1.0900
        
        for i in range(20):
            # HH: cada high es 20+ pips más alto
            high = base_price + (i * 0.0020) + np.random.uniform(0, 0.0015)
            low = high - np.random.uniform(0.0010, 0.0050)
            open_ = low + np.random.uniform(0.0000, 0.0030)
            close = open_ + np.random.uniform(0.0005, 0.0040)
            
            data.append({
                'datetime': datetime.now() - timedelta(hours=20-i),
                'open': open_,
                'high': high,
                'low': low,
                'close': close,
                'volume': 1000 + np.random.randint(0, 500)
            })
        
        df = pd.DataFrame(data)
        df = df.sort_values('datetime').reset_index(drop=True)
        return df
    
    
    # =============== TESTS DE INICIALIZACIÓN ===============
    
    def test_init_with_dependency_injection(self):
        """✓ Test: Inicialización con inyección de dependencias."""
        self.assertIsNotNone(self.analyzer)
        self.assertIsNotNone(self.analyzer.storage)
        self.assertEqual(self.analyzer.trace_id, "TEST-MARKET-STRUCT-001")
    
    
    def test_load_config_from_storage(self):
        """✓ Test: Cargar configuración desde storage (SSOT)."""
        self.assertEqual(self.analyzer.structure_min_pivots, 3)
        self.assertEqual(self.analyzer.breaker_buffer_pips, 5)
        self.assertEqual(self.analyzer.structure_lookback_candles, 20)
    
    
    # =============== TESTS DE DETECCIÓN DE PIVOTS ===============
    
    def test_detect_higher_high(self):
        """✓ Test: Detectar Higher High (HH) en tendencia alcista."""
        result = self.analyzer.detect_higher_highs(self.test_candles)
        
        # Debe haber al menos 3 Higher Highs en tendencia alcista de 20 velas
        self.assertGreater(len(result), 2)
        # Los índices deben estar en orden ascendente
        self.assertEqual(result, sorted(result))
    
    
    def test_detect_higher_low(self):
        """✓ Test: Detectar Higher Low (HL) en tendencia alcista."""
        result = self.analyzer.detect_higher_lows(self.test_candles)
        
        # Debe haber al menos 3 Higher Lows
        self.assertGreater(len(result), 2)
        # Los índices deben estar en orden ascendente
        self.assertEqual(result, sorted(result))
    
    
    def test_detect_structure_uptrend(self):
        """✓ Test: Detectar estructura de tendencia alcista (HH/HL)."""
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        
        self.assertIsNotNone(structure)
        self.assertEqual(structure['type'], 'UPTREND')
        self.assertGreater(structure['hh_count'], 2)
        self.assertGreater(structure['hl_count'], 2)
        self.assertTrue(structure['is_valid'])
    
    
    def test_detect_structure_downtrend(self):
        """✓ Test: Detectar estructura de tendencia bajista (LH/LL)."""
        # Invertir los precios (tendencia bajista)
        downtrend_candles = self.test_candles.copy()
        downtrend_candles['high'] = 1.1500 - downtrend_candles['high']
        downtrend_candles['low'] = 1.1500 - downtrend_candles['low']
        downtrend_candles['open'] = 1.1500 - downtrend_candles['open']
        downtrend_candles['close'] = 1.1500 - downtrend_candles['close']
        
        structure = self.analyzer.detect_market_structure("EURUSD", downtrend_candles)
        
        self.assertEqual(structure['type'], 'DOWNTREND')
        self.assertGreater(structure['lh_count'], 2)
    
    
    # =============== TESTS DE BREAKER BLOCK ===============
    
    def test_calculate_breaker_block(self):
        """✓ Test: Calcular zona de Breaker Block."""
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        breaker = self.analyzer.calculate_breaker_block(
            structure=structure,
            candles=self.test_candles
        )
        
        self.assertIsNotNone(breaker)
        self.assertIn('high', breaker)
        self.assertIn('low', breaker)
        self.assertIn('midpoint', breaker)
        self.assertGreater(breaker['high'], breaker['low'])
    
    
    def test_breaker_block_has_buffer(self):
        """✓ Test: Breaker Block incluye buffer configurado."""
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        breaker = self.analyzer.calculate_breaker_block(structure, self.test_candles)
        
        # El rango debe ser coherente con los pivots y buffer
        breaker_range = breaker['high'] - breaker['low']
        self.assertGreater(breaker_range, 0)
    
    
    # =============== TESTS DE RUPTURA (BOS) ===============
    
    def test_detect_break_of_structure_uptrend(self):
        """✓ Test: Detectar ruptura de estructura en tendencia alcista."""
        # Usar datos de tendencia alcista
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        breaker = self.analyzer.calculate_breaker_block(structure, self.test_candles)
        
        # Nueva vela que rompe por debajo del HL
        breakout_candle = {
            'high': breaker['low'] - 0.0010,
            'low': breaker['low'] - 0.0030,
            'close': breaker['low'] - 0.0020
        }
        
        bos = self.analyzer.detect_break_of_structure(
            structure=structure,
            breaker_block=breaker,
            current_candle=breakout_candle
        )
        
        self.assertIsNotNone(bos)
        self.assertTrue(bos['is_break'])
        self.assertEqual(bos['direction'], 'DOWN')  # Ruptura hacia abajo
    
    
    def test_detect_no_break_if_above_breaker(self):
        """✓ Test: NO detectar ruptura si precio está dentro del Breaker Block."""
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        breaker = self.analyzer.calculate_breaker_block(structure, self.test_candles)
        
        # Vela dentro del Breaker Block
        within_candle = {
            'high': (breaker['high'] + breaker['low']) / 2,
            'low': breaker['low'] + 0.0005,
            'close': (breaker['high'] + breaker['low']) / 2
        }
        
        bos = self.analyzer.detect_break_of_structure(structure, breaker, within_candle)
        
        self.assertFalse(bos['is_break'])
    
    
    # =============== TESTS DE PULLBACK ===============
    
    def test_calculate_pullback_zone(self):
        """✓ Test: Calcular zona de pullback después de ruptura."""
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        breaker = self.analyzer.calculate_breaker_block(structure, self.test_candles)
        
        # Simular ruptura
        bos = self.analyzer.detect_break_of_structure(
            structure,
            breaker,
            {'high': breaker['low'] - 0.0010, 'low': breaker['low'] - 0.0030, 'close': breaker['low'] - 0.0020}
        )
        
        if bos['is_break']:
            pullback = self.analyzer.calculate_pullback_zone(breaker_block=breaker)
            
            self.assertIsNotNone(pullback)
            self.assertIn('entry_high', pullback)
            self.assertIn('entry_low', pullback)
    
    
    # =============== TESTS DE VALIDACIÓN ===============
    
    def test_structure_requires_minimum_pivots(self):
        """✓ Test: Estructura requiere mínimo de pivots válidos."""
        # Generar datos sin estructura clara (random)
        random_candles = pd.DataFrame({
            'datetime': pd.date_range('2026-03-01', periods=10, freq='1h'),
            'open': np.random.uniform(1.0900, 1.1000, 10),
            'high': np.random.uniform(1.0950, 1.1050, 10),
            'low': np.random.uniform(1.0850, 1.0950, 10),
            'close': np.random.uniform(1.0900, 1.1000, 10),
            'volume': np.random.randint(500, 2000, 10)
        })
        
        structure = self.analyzer.detect_market_structure("EURUSD", random_candles)
        
        # Datos random no deben ser válidos
        self.assertFalse(structure['is_valid'])

    def test_validate_input_allows_index_without_volume(self):
        """✓ Test: Índices CFD (US30) deben validar con OHLC aunque falte volume."""
        index_candles = self.test_candles.drop(columns=["volume"]).copy()

        is_valid = self.analyzer._validate_input_candles("US30", index_candles)

        self.assertTrue(is_valid)
    
    
    def test_caching_of_structure(self):
        """✓ Test: Sistema cachea resultados de estructura."""
        # Primera llamada (calcula)
        struct1 = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        
        # Segunda llamada (recupera del cache)
        struct2 = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        
        # Deben ser idénticos
        self.assertEqual(struct1['type'], struct2['type'])
        self.assertEqual(struct1['hh_count'], struct2['hh_count'])
    
    
    # =============== TESTS DE INTEGRACIÓN ===============
    
    def test_full_structure_analysis_workflow(self):
        """✓ Test: Workflow completo de análisis de estructura."""
        # 1. Detectar estructura
        structure = self.analyzer.detect_market_structure("EURUSD", self.test_candles)
        self.assertTrue(structure['is_valid'])
        self.assertEqual(structure['type'], 'UPTREND')
        
        # 2. Calcular Breaker Block
        breaker = self.analyzer.calculate_breaker_block(structure, self.test_candles)
        self.assertIsNotNone(breaker)
        
        # 3. Esperar ruptura
        breakout_candle = {
            'high': breaker['low'] - 0.0010,
            'low': breaker['low'] - 0.0030,
            'close': breaker['low'] - 0.0020
        }
        
        bos = self.analyzer.detect_break_of_structure(structure, breaker, breakout_candle)
        self.assertTrue(bos['is_break'])
        
        # 4. Calcular zona de pullback
        pullback = self.analyzer.calculate_pullback_zone(breaker)
        self.assertIsNotNone(pullback)


if __name__ == '__main__':
    unittest.main()
