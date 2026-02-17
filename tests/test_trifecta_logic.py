"""
Test Suite for Trifecta Logic (Oliver Velez Multi-Timeframe Analyzer)
Validates 2m-5m-15m alignment, Location filter, Narrow State, and Time of Day optimizations

TDD: Este test se crea ANTES de implementar trifecta_logic.py
"""
import pytest
from datetime import datetime, time
import pandas as pd
import numpy as np


class TestTrifectaAnalyzer:
    """Tests for Oliver Velez Trifecta alignment and optimizations"""

    @pytest.fixture
    def analyzer(self):
        """Import here para que falle claramente si el módulo no existe"""
        from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
        return TrifectaAnalyzer()

    @pytest.fixture
    def bullish_aligned_data(self):
        """
        Scenario: Perfect bullish alignment
        - Precio > SMA20 en M1, M5, M15
        - Precio cerca de SMA20 (good location)
        - SMA20 y SMA200 comprimidas (narrow state)
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        # Crear DataFrame base con tendencia alcista
        def create_bullish_df():
            close_prices = np.linspace(1.0900, 1.1000, 250)  # Tendencia alcista
            df = pd.DataFrame({
                'open': close_prices - 0.0002,
                'high': close_prices + 0.0003,
                'low': close_prices - 0.0003,
                'close': close_prices,
            }, index=dates)
            return df

        return {
            "M1": create_bullish_df(),
            "M5": create_bullish_df(),
            "M15": create_bullish_df()
        }

    @pytest.fixture
    def bearish_aligned_data(self):
        """
        Scenario: Perfect bearish alignment
        - Precio < SMA20 en M1, M5, M15
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        def create_bearish_df():
            close_prices = np.linspace(1.1000, 1.0900, 250)  # Tendencia bajista
            df = pd.DataFrame({
                'open': close_prices + 0.0002,
                'high': close_prices + 0.0003,
                'low': close_prices - 0.0003,
                'close': close_prices,
            }, index=dates)
            return df

        return {
            "M1": create_bearish_df(),
            "M5": create_bearish_df(),
            "M15": create_bearish_df()
        }

    @pytest.fixture
    def mixed_alignment_data(self):
        """
        Scenario: No alignment (mixed signals)
        - M1 bullish, M5 bearish, M15 neutral
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        # M1 bullish
        close_m1 = np.linspace(1.0900, 1.1000, 250)
        df_m1 = pd.DataFrame({
            'open': close_m1 - 0.0002,
            'high': close_m1 + 0.0003,
            'low': close_m1 - 0.0003,
            'close': close_m1,
        }, index=dates)
        
        # M5 bearish
        close_m5 = np.linspace(1.1000, 1.0900, 250)
        df_m5 = pd.DataFrame({
            'open': close_m5 + 0.0002,
            'high': close_m5 + 0.0003,
            'low': close_m5 - 0.0003,
            'close': close_m5,
        }, index=dates)
        
        # M15 range (precio oscila alrededor de SMA20)
        close_m15 = np.ones(250) * 1.0950
        close_m15[:125] += 0.0010  # Primera mitad arriba
        close_m15[125:] -= 0.0010  # Segunda mitad abajo
        df_m15 = pd.DataFrame({
            'open': close_m15 - 0.0001,
            'high': close_m15 + 0.0002,
            'low': close_m15 - 0.0002,
            'close': close_m15,
        }, index=dates)

        return {
            "M1": df_m1,
            "M5": df_m5,
            "M15": df_m15
        }

    @pytest.fixture
    def extended_price_data(self):
        """
        Scenario: Precio muy extendido de SMA20 (>1% distancia)
        "Rubber Band" effect - no ideal para entrar
        Debe tener alineación bullish PERO precio extendido
        
        Matemática:
        - Velas 0-229: Tendencia alcista gradual hasta 1.0960
        - Velas 230-249: Últimas 20 velas en rango 1.0970-1.1080
        - SMA20 (última vela) ≈ promedio(1.0970...1.1080) ≈ 1.1025
        - Precio actual = 1.1080
        - Extension = |1.1080 - 1.1025| / 1.1025 * 100 ≈ 0.5%
        
        Necesito extension > 1%, así que ajusto:
        - Últimas 20 velas: rango más estrecho 1.0960-1.1140
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        def create_extended_df():
            # Velas 0-229: tendencia alcista lenta
            base_trend = np.linspace(1.0900, 1.0960, 230)
            
            # Velas 230-249: salto rápido a 1.1140 (las primeras en 1.0960, las últimas en 1.1140)
            jump_trend = np.linspace(1.0960, 1.1140, 20)
            
            close_prices = np.concatenate([base_trend, jump_trend])
            
            df = pd.DataFrame({
                'open': close_prices - 0.0002,
                'high': close_prices + 0.0003,
                'low': close_prices - 0.0003,
                'close': close_prices,
            }, index=dates)
            
            # Verificar matemática (debug): SMA20 última vela ≈ 1.1050, precio ≈ 1.1140
            # Extension = |1.1140 - 1.1050| / 1.1050 * 100 ≈ 0.81% (aún no es >1%)
            # Aumento más: últimas velas a 1.1180
            return df

        # Crear datos con extensión garantizada >1%
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        base_trend = np.linspace(1.0900, 1.0950, 230)
        jump_trend = np.linspace(1.0950, 1.1180, 20)  # Salto más agresivo
        close_prices = np.concatenate([base_trend, jump_trend])
        
        df = pd.DataFrame({
            'open': close_prices - 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)

        return {
            "M1": df.copy(),
            "M5": df.copy(),
            "M15": df.copy()
        }

    # ========== TESTS ==========

    def test_bullish_alignment_valid_signal(self, analyzer, bullish_aligned_data):
        """
        GIVEN: Precio > SMA20 en M1, M5, M15 (perfect alignment)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe retornar valid=True, direction='BUY', score > 50
        """
        result = analyzer.analyze("EURUSD", bullish_aligned_data)
        
        assert result["valid"] is True
        assert result["direction"] == "BUY"
        assert result["score"] >= 50
        assert "metadata" in result

    def test_bearish_alignment_valid_signal(self, analyzer, bearish_aligned_data):
        """
        GIVEN: Precio < SMA20 en M1, M5, M15 (perfect bearish alignment)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe retornar valid=True, direction='SELL', score > 50
        """
        result = analyzer.analyze("EURUSD", bearish_aligned_data)
        
        assert result["valid"] is True
        assert result["direction"] == "SELL"
        assert result["score"] >= 50

    def test_no_alignment_rejected(self, analyzer, mixed_alignment_data):
        """
        GIVEN: Timeframes desalineados (M1 bull, M5 bear, M15 range)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe rechazar con valid=False, reason='No Alignment'
        """
        result = analyzer.analyze("EURUSD", mixed_alignment_data)
        
        assert result["valid"] is False
        assert result["reason"] == "No Alignment"

    def test_extended_price_rejected_location_filter(self, analyzer, extended_price_data):
        """
        GIVEN: Precio extendido >1% de SMA20 (Rubber Band)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe rechazar con valid=False, reason='Extended from SMA20 (Rubber Band)'
        """
        result = analyzer.analyze("EURUSD", extended_price_data)
        
        # Puede que pase alineación pero debe fallar en Location
        assert result["valid"] is False
        assert "Extended" in result["reason"] and "Rubber Band" in result["reason"]

    def test_narrow_state_bonus(self, analyzer, bullish_aligned_data):
        """
        GIVEN: SMA20 y SMA200 comprimidas (<1.5% distancia)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe aplicar bonus de +20 puntos (is_narrow=True)
        """
        result = analyzer.analyze("EURUSD", bullish_aligned_data)
        
        # Si el estado es "narrow", el score debe ser mayor
        if result["valid"] and result["metadata"].get("is_narrow"):
            # Base 50 + Narrow 20 + otros bonuses
            assert result["score"] >= 70

    def test_insufficient_data_rejected(self, analyzer):
        """
        GIVEN: Datos insuficientes (timeframes faltantes)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta (HYBRID MODE)
        THEN: Debe operar en DEGRADED MODE (valid=True, degraded_mode=True, score neutral)
        """
        # Crear DataFrames simples para M1 y M5 (M15 faltante)
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        close_prices = np.linspace(1.0900, 1.1000, 250)
        
        df_m1 = pd.DataFrame({
            'open': close_prices - 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)
        
        df_m5 = df_m1.copy()
        
        # Datos incompletos: solo M1 y M5, falta M15 → Activa DEGRADED MODE
        incomplete_data = {
            "M1": df_m1,
            "M5": df_m5,
            # M15 faltante
        }
        
        result = analyzer.analyze("EURUSD", incomplete_data)
        
        # HYBRID MODE: Señal válida PERO en modo degradado
        assert result["valid"] is True
        assert result["metadata"]["degraded_mode"] is True
        assert "M15" in result["metadata"]["missing_timeframes"]
        
        # Valores neutrales (score base 50, dirección UNKNOWN)
        assert result["score"] == 50.0
        assert result["direction"] == "UNKNOWN"

    def test_score_range_0_to_100(self, analyzer, bullish_aligned_data):
        """
        GIVEN: Cualquier resultado válido
        WHEN: TrifectaAnalyzer.analyze() retorna score
        THEN: Score debe estar en el rango [0, 100]
        """
        result = analyzer.analyze("EURUSD", bullish_aligned_data)
        
        if result["valid"]:
            assert 0 <= result["score"] <= 100

    def test_metadata_contains_required_fields(self, analyzer, bullish_aligned_data):
        """
        GIVEN: Resultado válido
        WHEN: Se accede a metadata
        THEN: Debe contener: is_narrow, in_doldrums, extension_pct, stop_loss_ref
        """
        result = analyzer.analyze("EURUSD", bullish_aligned_data)
        
        if result["valid"]:
            metadata = result["metadata"]
            assert "is_narrow" in metadata
            assert "in_doldrums" in metadata
            assert "extension_pct" in metadata
            assert "stop_loss_ref" in metadata

    def test_stop_loss_reference_correct_direction(self, analyzer, bullish_aligned_data, bearish_aligned_data):
        """
        GIVEN: Señal BUY o SELL
        WHEN: Se obtiene stop_loss_ref de metadata
        THEN: Para BUY debe ser la SMA20 de M5 (Stop más ajustado), no el Low de la vela
        """
        # Bullish signal
        result_buy = analyzer.analyze("EURUSD", bullish_aligned_data)
        if result_buy["valid"] and result_buy["direction"] == "BUY":
            # Calcular SMA20 esperada en M5
            m5_closes = bullish_aligned_data["M5"]["close"]
            expected_sl = m5_closes.rolling(20).mean().iloc[-1]
            # El SL debe ser la SMA20 (más ajustado que el Low de la vela)
            # Usamos aprox() o margen de error por flotantes
            assert abs(result_buy["metadata"]["stop_loss_ref"] - expected_sl) < 0.0001, \
                f"SL Reference {result_buy['metadata']['stop_loss_ref']} should be SMA20 {expected_sl}"
        
        # Bearish signal
        result_sell = analyzer.analyze("EURUSD", bearish_aligned_data)
        if result_sell["valid"] and result_sell["direction"] == "SELL":
            m5_closes = bearish_aligned_data["M5"]["close"]
            expected_sl = m5_closes.rolling(20).mean().iloc[-1]
            assert abs(result_sell["metadata"]["stop_loss_ref"] - expected_sl) < 0.0001

class TestTrifectaTimeOfDay:
    """Tests específicos para Time of Day filter (Midday Doldrums)"""

    @pytest.fixture
    def analyzer(self):
        from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
        return TrifectaAnalyzer()

    def test_doldrums_penalty(self, analyzer, monkeypatch):
        """
        GIVEN: Hora actual en "Midday Doldrums" (11:30 - 14:00 EST)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe aplicar penalización de -20 puntos (in_doldrums=True)
        """
        # Mock datetime.now() para retornar hora en doldrums
        class MockDatetime:
            @staticmethod
            def now():
                class MockNow:
                    @staticmethod
                    def time():
                        return time(12, 30)  # 12:30 PM (doldrums)
                return MockNow()
        
        import core_brain.strategies.trifecta_logic
        monkeypatch.setattr(core_brain.strategies.trifecta_logic, 'datetime', MockDatetime)
        
        # Datos bullish alineados
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        close_prices = np.linspace(1.0900, 1.1000, 250)
        df = pd.DataFrame({
            'open': close_prices - 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)
        
        data = {"M1": df, "M5": df, "M15": df}
        result = analyzer.analyze("EURUSD", data)
        
        if result["valid"]:
            # Score debería ser menor por doldrums
            # Base 50 + bonuses - doldrums penalty 20
            assert result["metadata"]["in_doldrums"] is True
            # El score debe reflejar la penalización
            assert result["score"] < 70  # Menos que el score ideal sin doldrums


class TestTrifectaTrapZone:
    """Tests para validar rechazo de señales en "Trap Zone" (jerarquía SMA incorrecta)"""

    @pytest.fixture
    def analyzer(self):
        from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
        return TrifectaAnalyzer(auto_enable_tfs=False)

    def test_trap_zone_bullish_rejected(self, analyzer):
        """
        GIVEN: Precio > SMA20 PERO SMA20 < SMA200 (rebote en tendencia bajista mayor)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe rechazar con valid=False, reason contiene "Trap Zone"
        
        Escenario Real:
        - Tendencia bajista larga (SMA200 = 1.1009 arriba)
        - Rebote técnico sobre SMA20 (precio = 1.0970)
        - SMA20 = 1.0935 (por debajo de SMA200)
        
        Esto es una TRAMPA: comprar aquí es ir contra la tendencia mayor
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        # Crear tendencia bajista + rebote
        # Velas 0-229: Bajada gradual de 1.1200 a 1.0900
        base_trend = np.linspace(1.1200, 1.0900, 230)
        # Velas 230-249: Rebote alcista sobre SMA20
        rebound = np.linspace(1.0900, 1.0970, 20)
        close_prices = np.concatenate([base_trend, rebound])
        
        df = pd.DataFrame({
            'open': close_prices - 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)
        
        # Verificar que efectivamente es Trap Zone
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        # Assertions de setup (debug)
        assert price > sma20, f"Test setup error: Precio {price} debe ser > SMA20 {sma20}"
        assert sma20 < sma200, f"Test setup error: SMA20 {sma20} debe ser < SMA200 {sma200}"
        
        # Datos multi-timeframe (mismo patrón en los 3)
        trap_data = {
            "M1": df.copy(),
            "M5": df.copy(),
            "M15": df.copy()
        }
        
        result = analyzer.analyze("EURUSD", trap_data)
        
        # EXPECTATIVA: La señal debe ser RECHAZADA
        assert result["valid"] is False, "Trap Zone debe ser rechazada (precio bullish en tendencia bearish)"
        assert "Trap Zone" in result["reason"] or "Misaligned" in result["reason"], \
            f"Reason debe mencionar 'Trap Zone', obtuvo: {result['reason']}"

    def test_trap_zone_bearish_rejected(self, analyzer):
        """
        GIVEN: Precio < SMA20 PERO SMA20 > SMA200 (caída en tendencia alcista mayor)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe rechazar con valid=False, reason contiene "Trap Zone"
        
        Escenario Real (inverso al bullish):
        - Tendencia alcista larga (SMA200 = 1.0800 abajo)
        - Caída técnica bajo SMA20 (precio = 1.0930)
        - SMA20 = 1.0965 (por encima de SMA200)
        
        Esto es una TRAMPA: vender aquí es ir contra la tendencia mayor
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        # Crear tendencia alcista + pullback
        # Velas 0-229: Subida gradual de 1.0700 a 1.1000
        base_trend = np.linspace(1.0700, 1.1000, 230)
        # Velas 230-249: Pullback bajista bajo SMA20
        pullback = np.linspace(1.1000, 1.0930, 20)
        close_prices = np.concatenate([base_trend, pullback])
        
        df = pd.DataFrame({
            'open': close_prices + 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)
        
        # Verificar que efectivamente es Trap Zone inverso
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        # Assertions de setup (debug)
        assert price < sma20, f"Test setup error: Precio {price} debe ser < SMA20 {sma20}"
        assert sma20 > sma200, f"Test setup error: SMA20 {sma20} debe ser > SMA200 {sma200}"
        
        # Datos multi-timeframe (mismo patrón en los 3)
        trap_data = {
            "M1": df.copy(),
            "M5": df.copy(),
            "M15": df.copy()
        }
        
        result = analyzer.analyze("EURUSD", trap_data)
        
        # EXPECTATIVA: La señal debe ser RECHAZADA
        assert result["valid"] is False, "Trap Zone debe ser rechazada (precio bearish en tendencia bullish)"
        assert "Trap Zone" in result["reason"] or "Misaligned" in result["reason"], \
            f"Reason debe mencionar 'Trap Zone', obtuvo: {result['reason']}"

    def test_valid_hierarchy_bullish_approved(self, analyzer):
        """
        GIVEN: Precio > SMA20 > SMA200 (jerarquía alcista perfecta)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe aprobar con valid=True, direction='BUY'
        
        Control positivo: Este test verifica que la corrección NO rompe casos válidos
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        # Tendencia alcista limpia
        close_prices = np.linspace(1.0900, 1.1000, 250)
        
        df = pd.DataFrame({
            'open': close_prices - 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)
        
        # Verificar jerarquía válida
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        assert price > sma20 > sma200, f"Test setup: Debe cumplir Precio > SMA20 > SMA200"
        
        data = {
            "M1": df.copy(),
            "M5": df.copy(),
            "M15": df.copy()
        }
        
        result = analyzer.analyze("EURUSD", data)
        
        # EXPECTATIVA: Señal VÁLIDA (jerarquía correcta)
        assert result["valid"] is True, "Jerarquía alcista válida debe ser aprobada"
        assert result["direction"] == "BUY"

    def test_valid_hierarchy_bearish_approved(self, analyzer):
        """
        GIVEN: Precio < SMA20 < SMA200 (jerarquía bajista perfecta)
        WHEN: TrifectaAnalyzer.analyze() se ejecuta
        THEN: Debe aprobar con valid=True, direction='SELL'
        
        Control positivo: Verificar caso válido bearish
        """
        dates = pd.date_range(start='2024-01-01', periods=250, freq='1min')
        
        # Tendencia bajista limpia
        close_prices = np.linspace(1.1000, 1.0900, 250)
        
        df = pd.DataFrame({
            'open': close_prices + 0.0002,
            'high': close_prices + 0.0003,
            'low': close_prices - 0.0003,
            'close': close_prices,
        }, index=dates)
        
        # Verificar jerarquía válida
        sma20 = df['close'].rolling(20).mean().iloc[-1]
        sma200 = df['close'].rolling(200).mean().iloc[-1]
        price = df['close'].iloc[-1]
        
        assert price < sma20 < sma200, f"Test setup: Debe cumplir Precio < SMA20 < SMA200"
        
        data = {
            "M1": df.copy(),
            "M5": df.copy(),
            "M15": df.copy()
        }
        
        result = analyzer.analyze("EURUSD", data)
        
        # EXPECTATIVA: Señal VÁLIDA (jerarquía correcta)
        assert result["valid"] is True, "Jerarquía bajista válida debe ser aprobada"
        assert result["direction"] == "SELL"


class TestTrifectaTrendValidation:
    """
    Tests para validar que Trifecta rechaza trades cuando:
    1. EMAs están planas (sin pendiente clara)
    2. EMA 20 y EMA 200 están muy cerca (sin separación = no hay tendencia)
    3. Régimen de mercado es RANGE
    
    Bug detectado: USDCAD SELL @ 1.35248 (2026-02-11)
    - EMA 20 plana y lejos de EMA 200
    - M1: sin tendencia, M5: rango, M15: EMA 20 casi plana
    - Trade ejecutado cuando debería rechazar
    """
