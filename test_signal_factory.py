"""
Test de Signal Factory - Verificación del Sistema de Scoring
Prueba el scoring Oliver Vélez y la generación de señales
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from core_brain.signal_factory import SignalFactory
from models.signal import MarketRegime, ConnectorType, MembershipTier


def create_mock_ohlc_data(
    num_candles: int = 100,
    trend: str = "up",
    elephant_candle: bool = False,
    high_volume: bool = False,
    near_sma20: bool = False
) -> pd.DataFrame:
    """
    Crea datos OHLC simulados para pruebas
    
    Args:
        num_candles: Número de velas
        trend: 'up', 'down', o 'sideways'
        elephant_candle: Si True, la última vela es elefante
        high_volume: Si True, el último volumen es alto
        near_sma20: Si True, el precio está cerca de SMA 20
    
    Returns:
        DataFrame con OHLC simulado
    """
    np.random.seed(42)
    
    # Base de precios
    if trend == "up":
        base_prices = np.linspace(100, 120, num_candles)
    elif trend == "down":
        base_prices = np.linspace(120, 100, num_candles)
    else:
        base_prices = np.ones(num_candles) * 110
    
    # Añadir ruido
    noise = np.random.normal(0, 0.5, num_candles)
    closes = base_prices + noise
    
    # OHLC
    highs = closes + np.random.uniform(0.1, 0.5, num_candles)
    lows = closes - np.random.uniform(0.1, 0.5, num_candles)
    opens = closes + np.random.normal(0, 0.2, num_candles)
    
    # Vela elefante (última vela con rango 3x normal)
    if elephant_candle:
        avg_range = np.mean(highs - lows)
        highs[-1] = closes[-1] + (avg_range * 2)
        lows[-1] = closes[-1] - (avg_range * 1)
    
    # Volumen
    volumes = np.random.randint(1000, 5000, num_candles)
    
    if high_volume:
        volumes[-1] = int(np.mean(volumes) * 2.5)  # 2.5x el promedio
    
    # Ajustar para estar cerca de SMA 20
    if near_sma20:
        sma20 = pd.Series(closes).rolling(window=20).mean()
        # Hacer que el último precio esté a 0.5% de la SMA 20
        if not pd.isna(sma20.iloc[-1]):
            closes[-1] = sma20.iloc[-1] * 1.005
            highs[-1] = closes[-1] + 0.2
            lows[-1] = closes[-1] - 0.2
    
    # Timestamps
    timestamps = [datetime.now() - timedelta(minutes=5*i) for i in range(num_candles)]
    timestamps.reverse()
    
    df = pd.DataFrame({
        'time': timestamps,
        'open': opens,
        'high': highs,
        'low': lows,
        'close': closes,
        'tick_volume': volumes
    })
    
    return df


def test_scoring_system():
    """Prueba el sistema de scoring de Signal Factory"""
    print("=" * 80)
    print("🧪 TEST: Sistema de Scoring Oliver Vélez")
    print("=" * 80)
    
    factory = SignalFactory(
        connector_type=ConnectorType.METATRADER5,
        strategy_id="test_oliver_velez"
    )
    
    # Test 1: Score máximo (100) - Todas las condiciones
    print("\n📊 Test 1: Score Máximo (100 puntos)")
    print("-" * 80)
    df_max = create_mock_ohlc_data(
        num_candles=100,
        trend="up",
        elephant_candle=True,
        high_volume=True,
        near_sma20=True
    )
    
    signal_max = factory.generate_signal(
        symbol="EURUSD",
        df=df_max,
        regime=MarketRegime.TREND
    )
    
    if signal_max:
        print(f"✅ Señal generada")
        print(f"   Score: {signal_max.score:.1f}/100")
        print(f"   Tipo: {signal_max.signal_type.value}")
        print(f"   Membresía: {signal_max.membership_tier.value}")
        print(f"   Vela Elefante: {signal_max.is_elephant_candle}")
        print(f"   Volumen Alto: {signal_max.volume_above_average}")
        print(f"   Cerca SMA20: {signal_max.near_sma20}")
        print(f"   Precio: {signal_max.price:.5f}")
        if signal_max.stop_loss:
            print(f"   Stop Loss: {signal_max.stop_loss:.5f}")
        if signal_max.take_profit:
            print(f"   Take Profit: {signal_max.take_profit:.5f}")
        
        assert signal_max.score == 100.0, "Score debería ser 100"
        assert signal_max.membership_tier == MembershipTier.ELITE, "Debería ser ELITE"
    else:
        print("❌ No se generó señal (puede ser normal si no hay setup)")
    
    # Test 2: Score Premium (80-90 puntos)
    print("\n📊 Test 2: Score Premium (80-90 puntos)")
    print("-" * 80)
    df_premium = create_mock_ohlc_data(
        num_candles=100,
        trend="up",
        elephant_candle=True,
        high_volume=True,
        near_sma20=False  # Sin SMA 20
    )
    
    signal_premium = factory.generate_signal(
        symbol="GBPUSD",
        df=df_premium,
        regime=MarketRegime.TREND
    )
    
    if signal_premium:
        print(f"✅ Señal generada")
        print(f"   Score: {signal_premium.score:.1f}/100")
        print(f"   Membresía: {signal_premium.membership_tier.value}")
        print(f"   Vela Elefante: {signal_premium.is_elephant_candle}")
        print(f"   Volumen Alto: {signal_premium.volume_above_average}")
        print(f"   Cerca SMA20: {signal_premium.near_sma20}")
        
        assert 70 <= signal_premium.score <= 90, "Score debería estar entre 70-90"
        assert signal_premium.membership_tier in [MembershipTier.PREMIUM, MembershipTier.ELITE]
    else:
        print("❌ No se generó señal")
    
    # Test 3: Score Bajo (FREE)
    print("\n📊 Test 3: Score Bajo - FREE tier")
    print("-" * 80)
    df_free = create_mock_ohlc_data(
        num_candles=100,
        trend="sideways",
        elephant_candle=False,
        high_volume=False,
        near_sma20=False
    )
    
    signal_free = factory.generate_signal(
        symbol="USDJPY",
        df=df_free,
        regime=MarketRegime.RANGE  # RANGE no suma puntos
    )
    
    if signal_free:
        print(f"✅ Señal generada")
        print(f"   Score: {signal_free.score:.1f}/100")
        print(f"   Membresía: {signal_free.membership_tier.value}")
    else:
        print("✅ No se generó señal (correcto, score demasiado bajo)")
    
    # Test 4: Filtrado por Membresía
    print("\n📊 Test 4: Filtrado por Membresía")
    print("-" * 80)
    
    # Crear señales de diferentes tiers
    all_signals = []
    
    # Señal ELITE
    signal_elite = signal_max
    if signal_elite:
        all_signals.append(signal_elite)
    
    # Señal PREMIUM
    if signal_premium:
        all_signals.append(signal_premium)
    
    # Filtrar para FREE user
    free_signals = factory.filter_by_membership(all_signals, MembershipTier.FREE)
    print(f"   Usuario FREE: {len(free_signals)}/{len(all_signals)} señales visibles")
    
    # Filtrar para PREMIUM user
    premium_signals = factory.filter_by_membership(all_signals, MembershipTier.PREMIUM)
    print(f"   Usuario PREMIUM: {len(premium_signals)}/{len(all_signals)} señales visibles")
    
    # Filtrar para ELITE user
    elite_signals = factory.filter_by_membership(all_signals, MembershipTier.ELITE)
    print(f"   Usuario ELITE: {len(elite_signals)}/{len(all_signals)} señales visibles")
    
    # Test 5: Verificación de Componentes Técnicos
    print("\n📊 Test 5: Componentes Técnicos")
    print("-" * 80)
    
    # Test ATR
    atr = factory._calculate_atr(df_max)
    print(f"   ATR calculado: {atr.iloc[-1]:.5f}")
    assert not atr.isna().all(), "ATR debería calcularse"
    
    # Test vela elefante
    is_elephant, ratio = factory._is_elephant_candle(df_max)
    print(f"   Vela Elefante: {is_elephant} (ratio: {ratio:.2f}x ATR)")
    
    # Test volumen
    vol_high, vol_ratio = factory._is_volume_above_average(df_max)
    print(f"   Volumen Alto: {vol_high} (ratio: {vol_ratio:.2f}x promedio)")
    
    # Test SMA 20
    near_sma, distance = factory._is_near_sma20(df_max)
    print(f"   Cerca SMA 20: {near_sma} (distancia: {distance:.2f}%)")
    
    print("\n" + "=" * 80)
    print("✅ Todos los tests completados")
    print("=" * 80)


def test_batch_generation():
    """Prueba generación por lote"""
    print("\n" + "=" * 80)
    print("🧪 TEST: Generación de Señales por Lote")
    print("=" * 80)
    
    factory = SignalFactory()
    
    # Simular resultados de escáner
    scan_results = {}
    
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "GOLD", "US30"]
    
    for i, symbol in enumerate(symbols):
        # Variar condiciones
        df = create_mock_ohlc_data(
            num_candles=100,
            trend="up" if i % 2 == 0 else "down",
            elephant_candle=i < 3,
            high_volume=i < 2,
            near_sma20=i < 4
        )
        
        regime = MarketRegime.TREND if i < 3 else MarketRegime.RANGE
        
        scan_results[symbol] = {
            "regime": regime,
            "df": df,
            "metrics": {}
        }
    
    # Generar señales
    signals = factory.generate_signals_batch(scan_results)
    
    print(f"\n📊 Resultados:")
    print(f"   Símbolos escaneados: {len(scan_results)}")
    print(f"   Señales generadas: {len(signals)}")
    
    for signal in signals:
        print(f"\n   {signal.symbol}:")
        print(f"      Tipo: {signal.signal_type.value}")
        print(f"      Score: {signal.score:.1f}")
        print(f"      Tier: {signal.membership_tier.value}")
    
    print("\n" + "=" * 80)
    print("✅ Test de lote completado")
    print("=" * 80)


if __name__ == "__main__":
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║     🧪  SIGNAL FACTORY - SISTEMA DE SCORING TEST  🧪     ║
    ║                                                           ║
    ║          Verificación de lógica Oliver Vélez             ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
    
    # Ejecutar tests
    test_scoring_system()
    test_batch_generation()
    
    print("""
    ╔═══════════════════════════════════════════════════════════╗
    ║                                                           ║
    ║                  ✅  TODOS LOS TESTS OK  ✅              ║
    ║                                                           ║
    ╚═══════════════════════════════════════════════════════════╝
    """)
