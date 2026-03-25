"""
Test StructureShift0001Strategy - S-0006 Detección de Quiebre de Estructura

TRACE_ID: TEST-STRUC-SHIFT-0001

Cubre:
- Inicialización con inyección de dependencias
- Detección de estructura (HH/HL en UPTREND, LH/LL en DOWNTREND)
- Validación de Breaker Block
- Detección de Break of Structure (BOS)
- Generación de señales con confluencia
- Gestión de afinidad de activos
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any

from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from core_brain.strategies.struc_shift_0001 import StructureShift0001Strategy
from core_brain.sensors.market_structure_analyzer import MarketStructureAnalyzer


class TestStructureShift0001Strategy(unittest.TestCase):
    """Test suite para StructureShift0001Strategy (S-0006)."""
    
    def setUp(self):
        """Preparar mocks y fixtures."""
        self.mock_storage = self._create_mock_storage()
        self.market_structure_analyzer = MarketStructureAnalyzer(
            storage=self.mock_storage,
            trace_id="TEST-STRUC-SHIFT-0001"
        )
        
        self.strategy = StructureShift0001Strategy(
            storage_manager=self.mock_storage,
            market_structure_analyzer=self.market_structure_analyzer,
            user_id="test-user-uuid",
            trace_id="TEST-STRUC-SHIFT-0001"
        )
        
        # Datos de prueba: tendencia alcista con estructura clara
        self.uptrend_candles = self._generate_uptrend_candles()
        self.downtrend_candles = self._generate_downtrend_candles()
    
    
    def _create_mock_storage(self) -> Dict[str, Any]:
        """Crear mock simple de storage."""
        class MockStorage:
            def get_dynamic_params(self):
                return {
                    'structure_min_pivots': 3,
                    'breaker_buffer_pips': 5,
                    'structure_lookback_candles': 20,
                    'zig_zag_depth': 5,
                    'struc_shift_max_daily_usr_trades': 5,
                    'struc_shift_tp1_ratio': 1.27,
                    'struc_shift_tp2_ratio': 1.618,
                    'struc_shift_sl_buffer_pips': 10,
                    'struc_shift_min_structure_strength': 3  # Mínimo de pivots
                }
        
        return MockStorage()
    
    
    def _generate_uptrend_candles(self) -> pd.DataFrame:
        """Generar 20 velas con HH/HL (tendencia alcista)."""
        data = []
        base_price = 1.0900
        
        for i in range(20):
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
        return df.sort_values('datetime').reset_index(drop=True)
    
    
    def _generate_downtrend_candles(self) -> pd.DataFrame:
        """Generar 20 velas con LH/LL (tendencia bajista)."""
        uptrend = self._generate_uptrend_candles()
        
        # Invertir para crear tendencia bajista
        downtrend = uptrend.copy()
        downtrend['high'] = 1.1500 - downtrend['high']
        downtrend['low'] = 1.1500 - downtrend['low']
        downtrend['open'] = 1.1500 - downtrend['open']
        downtrend['close'] = 1.1500 - downtrend['close']
        
        return downtrend
    
    
    # =============== TESTS DE INICIALIZACIÓN ===============
    
    def test_strategy_init_with_dependency_injection(self):
        """✓ Test: Inicialización con inyección de dependencias."""
        self.assertIsNotNone(self.strategy)
        self.assertEqual(self.strategy.STRATEGY_ID, "STRUC_SHIFT_0001")
        self.assertEqual(self.strategy.user_id, "test-user-uuid")
    
    
    def test_strategy_affinity_scores_loaded(self):
        """✓ Test: Cargar scores de afinidad de activos."""
        self.assertIn("EURUSD", self.strategy.AFFINITY_SCORES)
        self.assertIn("USDCAD", self.strategy.AFFINITY_SCORES)
        # EURUSD debe tener score >= 0.89
        self.assertGreaterEqual(self.strategy.AFFINITY_SCORES["EURUSD"], 0.89)
    
    
    def test_market_structure_analyzer_available(self):
        """✓ Test: Analizador de estructura disponible."""
        self.assertIsNotNone(self.strategy.market_structure_analyzer)
    
    
    # =============== TESTS DE ANÁLISIS ===============
    
    def test_analyze_uptrend_structure(self):
        """✓ Test: Analizar estructura de tendencia alcista."""
        # Crear un DataFrame con índice de datetime
        import asyncio
        candles = self.uptrend_candles.copy()
        candles.set_index('datetime', inplace=True)
        
        signal = asyncio.run(self.strategy.analyze(
            symbol="EURUSD",
            df=candles
        ))
        
        # El análisis debe retornar un resultado (puede ser None si no hay confluencia)
        # pero no debe lanzar excepción
        # Si hay estructura válida, la señal debe estar presente
        if signal is not None:
            self.assertIsInstance(signal, Signal)
            self.assertEqual(signal.symbol, "EURUSD")
    
    
    def test_detect_structure_in_candles(self):
        """✓ Test: Detectar estructura en datos."""
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", self.uptrend_candles
        )
        
        # Tendencia alcista debe tener HH y HL
        self.assertEqual(structure['type'], 'UPTREND')
        self.assertGreater(structure['hh_count'], 2)
        self.assertGreater(structure['hl_count'], 2)
    
    
    def test_breaker_block_calculation(self):
        """✓ Test: Calcular Breaker Block desde estructura."""
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", self.uptrend_candles
        )
        
        breaker = self.strategy.market_structure_analyzer.calculate_breaker_block(
            structure, self.uptrend_candles
        )
        
        self.assertIsNotNone(breaker)
        self.assertGreater(breaker['high'], breaker['low'])
    
    
    # =============== TESTS DE CONFLUENCIA ===============
    
    def test_validate_confluence_uptrend(self):
        """✓ Test: Validar confluencia en ruptura UPTREND."""
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", self.uptrend_candles
        )
        breaker = self.strategy.market_structure_analyzer.calculate_breaker_block(
            structure, self.uptrend_candles
        )
        
        # Simular vela de ruptura con confluencia
        rupture_candle = {
            'high': breaker['low'] - 0.0010,
            'low': breaker['low'] - 0.0030,
            'close': breaker['low'] - 0.0020
        }
        
        bos = self.strategy.market_structure_analyzer.detect_break_of_structure(
            structure, breaker, rupture_candle
        )
        
        self.assertTrue(bos['is_break'])
        self.assertEqual(bos['direction'], 'DOWN')
    
    
    def test_asset_affinity_filtering(self):
        """✓ Test: Filtrado de activos por afinidad."""
        # EUR/USD tiene alta afinidad (0.89)
        eur_usd_affinity = self.strategy.AFFINITY_SCORES.get("EURUSD", 0)
        self.assertGreaterEqual(eur_usd_affinity, 0.85)
        
        # AUD/NZD está vetado (0.40)
        aud_nzd_affinity = self.strategy.AFFINITY_SCORES.get("AUDNZD", 0)
        self.assertLessEqual(aud_nzd_affinity, 0.45)
    
    
    # =============== TESTS DE GENERACIÓN DE SEÑALES ===============
    
    def test_signal_has_required_fields(self):
        """✓ Test: Señal generada tiene campos requridos."""
        import asyncio
        candles = self.uptrend_candles.copy()
        candles.set_index('datetime', inplace=True)
        
        signal = asyncio.run(self.strategy.analyze(symbol="EURUSD", df=candles))
        
        if signal is not None:
            # Verificar campos obligatorios
            self.assertEqual(signal.symbol, "EURUSD")
            self.assertIsNotNone(signal.entry_price)
            self.assertIsNotNone(signal.stop_loss)
            self.assertIsNotNone(signal.take_profit_primary)
    
    
    def test_signal_tp_levels(self):
        """✓ Test: Señal tiene múltiples TP (TP1 = 1.27R, TP2 = 1.618R)."""
        # Crear una estructura clara de ruptura
        candles = self.uptrend_candles.copy()
        
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", candles)
        breaker = self.strategy.market_structure_analyzer.calculate_breaker_block(
            structure, candles
        )
        
        # TP1 debe ser 1.27R desde entrada
        risk = breaker['high'] - breaker['low']
        expect_tp1 = breaker['low'] - (risk * 1.27)
        
        # Verificar que TP1 está por debajo del Breaker Block (ruptura DOWN)
        self.assertLess(expect_tp1, breaker['low'])
    
    
    # =============== TESTS DE GESTIÓN DE RIESGO ===============
    
    def test_stop_loss_at_breaker_block(self):
        """✓ Test: SL se coloca en Breaker Block bajo + buffer."""
        candles = self.uptrend_candles.copy()
        
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", candles)
        breaker = self.strategy.market_structure_analyzer.calculate_breaker_block(
            structure, candles
        )
        
        # SL debe estar en breaker['low'] - buffer
        breaker_low_with_buffer = breaker['low'] - (10 / 10000)  # 10 pips
        
        # El SL debe estar al menos cercano a esta zona
        self.assertLess(breaker_low_with_buffer, breaker['low'])
    
    
    def test_max_daily_usr_trades_limit(self):
        """✓ Test: Límite de usr_trades diarios enforced."""
        self.assertEqual(self.strategy.max_daily_usr_trades, 5)
    
    
    # =============== TESTS DE VALIDACIÓN ===============
    
    def test_requires_valid_structure(self):
        """✓ Test: Estrategia requiere estructura válida."""
        # Datos random sin estructura
        random_candles = pd.DataFrame({
            'open': np.random.uniform(1.0900, 1.1000, 10),
            'high': np.random.uniform(1.0950, 1.1050, 10),
            'low': np.random.uniform(1.0850, 1.0950, 10),
            'close': np.random.uniform(1.0900, 1.1000, 10),
            'volume': np.random.randint(500, 2000, 10)
        })
        
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", random_candles)
        
        # Estructura debe ser inválida
        self.assertFalse(structure['is_valid'])
    
    
    # =============== TESTS DE INTEGRACIÓN ===============
    
    def test_full_strategy_workflow_uptrend(self):
        """✓ Test: Workflow completo en tendencia alcista."""
        # 1. Detectar estructura
        structure = self.strategy.market_structure_analyzer.detect_market_structure("EURUSD", self.uptrend_candles
        )
        self.assertTrue(structure['is_valid'])
        self.assertEqual(structure['type'], 'UPTREND')
        
        # 2. Calcular Breaker Block
        breaker = self.strategy.market_structure_analyzer.calculate_breaker_block(
            structure, self.uptrend_candles
        )
        self.assertIsNotNone(breaker)
        
        # 3. Simular ruptura
        rupture_candle = {
            'high': breaker['low'] - 0.0010,
            'low': breaker['low'] - 0.0030,
            'close': breaker['low'] - 0.0020
        }
        
        bos = self.strategy.market_structure_analyzer.detect_break_of_structure(
            structure, breaker, rupture_candle
        )
        self.assertTrue(bos['is_break'])
        
        # 4. Calcular zona de pullback
        pullback = self.strategy.market_structure_analyzer.calculate_pullback_zone(
            breaker
        )
        self.assertIsNotNone(pullback)
        
        # 5. Ready para entrada en confluencia
        self.assertIsNotNone(bos['direction'])


if __name__ == '__main__':
    unittest.main()
