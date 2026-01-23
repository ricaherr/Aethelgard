"""
Script de Simulación para Calibrar el Clasificador de Régimen
Genera datos sintéticos que simulan RANGE -> TREND -> CRASH
y detecta los cambios de régimen en tiempo real
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from core_brain.regime import RegimeClassifier
from models.signal import MarketRegime


def generate_range_market(num_candles: int = 100, base_price: float = 100.0) -> pd.DataFrame:
    """
    Genera un mercado lateral (RANGE) con volatilidad baja y sin tendencia clara
    
    Args:
        num_candles: Número de velas a generar
        base_price: Precio base inicial
    
    Returns:
        DataFrame con columnas: timestamp, open, high, low, close
    """
    timestamps = [datetime.now() + timedelta(minutes=i) for i in range(num_candles)]
    
    # Generar precios que oscilan alrededor de base_price
    # Baja volatilidad (desviación estándar pequeña)
    returns = np.random.normal(0, 0.001, num_candles)  # 0.1% de volatilidad
    
    prices = [base_price]
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    # Generar OHLC realista para mercado lateral
    candles = []
    for i, close in enumerate(prices):
        # En rango, high y low están cerca del close
        volatility = np.random.uniform(0.002, 0.005)  # 0.2% - 0.5%
        high = close * (1 + volatility)
        low = close * (1 - volatility)
        open_price = prices[i-1] if i > 0 else close
        
        candles.append({
            'timestamp': timestamps[i],
            'open': open_price,
            'high': high,
            'low': low,
            'close': close
        })
    
    return pd.DataFrame(candles)


def generate_trend_market(num_candles: int = 100, start_price: float = 100.0, 
                         trend_strength: float = 0.003) -> pd.DataFrame:
    """
    Genera un mercado con tendencia alcista fuerte (TREND)
    
    Args:
        num_candles: Número de velas a generar
        start_price: Precio inicial
        trend_strength: Fuerza de la tendencia (retorno esperado por vela)
    
    Returns:
        DataFrame con columnas: timestamp, open, high, low, close
    """
    timestamps = [datetime.now() + timedelta(minutes=i) for i in range(num_candles)]
    
    # Generar precios con tendencia alcista clara
    # Tendencia + ruido pequeño
    returns = np.random.normal(trend_strength, 0.0015, num_candles)  # Tendencia + 0.15% ruido
    
    prices = [start_price]
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    # Generar OHLC realista para mercado con tendencia
    candles = []
    for i, close in enumerate(prices):
        # En tendencia, high está más arriba que low (sesgo alcista)
        volatility = np.random.uniform(0.003, 0.008)  # 0.3% - 0.8%
        high = close * (1 + volatility * 1.5)  # Más espacio arriba
        low = close * (1 - volatility * 0.5)   # Menos espacio abajo
        open_price = prices[i-1] if i > 0 else close
        
        candles.append({
            'timestamp': timestamps[i],
            'open': open_price,
            'high': high,
            'low': low,
            'close': close
        })
    
    return pd.DataFrame(candles)


def generate_crash_market(num_candles: int = 50, start_price: float = 130.0) -> pd.DataFrame:
    """
    Genera un mercado con caída violenta (CRASH/SHOCK)
    
    Args:
        num_candles: Número de velas a generar
        start_price: Precio inicial (después de la tendencia)
    
    Returns:
        DataFrame con columnas: timestamp, open, high, low, close
    """
    timestamps = [datetime.now() + timedelta(minutes=i) for i in range(num_candles)]
    
    # Primero algunas velas normales, luego crash
    crash_start = num_candles // 3
    
    returns = []
    for i in range(num_candles):
        if i < crash_start:
            # Velas normales con ligera tendencia bajista
            returns.append(np.random.normal(-0.001, 0.002))
        else:
            # CRASH: retornos negativos grandes y alta volatilidad
            returns.append(np.random.normal(-0.01, 0.015))  # -1% promedio, alta volatilidad
    
    prices = [start_price]
    for ret in returns[1:]:
        prices.append(prices[-1] * (1 + ret))
    
    # Generar OHLC realista para crash
    candles = []
    for i, close in enumerate(prices):
        # En crash, alta volatilidad y movimientos grandes
        volatility = np.random.uniform(0.01, 0.03)  # 1% - 3% de volatilidad
        high = close * (1 + volatility * 0.8)   # Movimientos grandes
        low = close * (1 - volatility * 1.5)    # Más espacio abajo (caída)
        open_price = prices[i-1] if i > 0 else close
        
        candles.append({
            'timestamp': timestamps[i],
            'open': open_price,
            'high': high,
            'low': low,
            'close': close
        })
    
    return pd.DataFrame(candles)


def simulate_regime_detection():
    """
    Simula los tres escenarios y detecta cambios de régimen
    """
    print("=" * 80)
    print("SIMULACIÓN DE DETECCIÓN DE RÉGIMEN DE MERCADO")
    print("=" * 80)
    print()
    
    # Clasificador con lógica optimizada:
    # - Histéresis ADX: entrar TREND >25, salir RANGE <18
    # - Shock: 5 velas, 5.0x, solo si vol > ATR base
    # - Persistencia: 2 velas consecutivas para confirmar cambio
    classifier = RegimeClassifier(
        adx_period=14,
        sma_period=200,
        adx_trend_threshold=25.0,
        adx_range_threshold=20.0,
        adx_range_exit_threshold=18.0,
        volatility_shock_multiplier=5.0,
        shock_lookback=5,
        persistence_candles=2,
    )
    
    # Generar los tres escenarios
    print("Generando datos sintéticos...")
    print("- Fase 1: Mercado RANGE (100 velas)")
    range_data = generate_range_market(num_candles=100, base_price=100.0)
    
    print("- Fase 2: Mercado TREND (100 velas)")
    trend_data = generate_trend_market(
        num_candles=100, 
        start_price=range_data['close'].iloc[-1],
        trend_strength=0.003
    )
    
    print("- Fase 3: Mercado CRASH (50 velas)")
    crash_data = generate_crash_market(
        num_candles=50,
        start_price=trend_data['close'].iloc[-1]
    )
    
    # Combinar todos los datos
    all_data = pd.concat([range_data, trend_data, crash_data], ignore_index=True)
    
    print(f"\nTotal de velas generadas: {len(all_data)}")
    print(f"Rango de precios: ${all_data['close'].min():.2f} - ${all_data['close'].max():.2f}")
    print()
    
    # Procesar cada vela y detectar cambios
    print("=" * 80)
    print("PROCESANDO VELAS Y DETECTANDO CAMBIOS DE RÉGIMEN")
    print("=" * 80)
    print()
    
    previous_regime = None
    regime_changes = []
    current_phase = "RANGE"
    phase_boundaries = {
        "RANGE": (0, 100),
        "TREND": (100, 200),
        "CRASH": (200, 250)
    }
    
    for idx, row in all_data.iterrows():
        # Determinar fase actual
        if idx < 100:
            expected_phase = "RANGE"
        elif idx < 200:
            expected_phase = "TREND"
        else:
            expected_phase = "CRASH"
        
        # Añadir vela al clasificador
        classifier.add_candle(
            close=row['close'],
            high=row['high'],
            low=row['low'],
            open_price=row['open'],
            timestamp=row['timestamp']
        )
        
        # Clasificar régimen (solo si hay suficientes datos)
        if len(classifier.df) >= max(classifier.adx_period * 2, 20):
            current_regime = classifier.classify()
            
            # Detectar cambio de régimen
            if previous_regime is None:
                previous_regime = current_regime
                print(f"Vela {idx:3d} | Fase: {expected_phase:6s} | Régimen inicial: {current_regime.value}")
            elif current_regime != previous_regime:
                # Obtener métricas para contexto
                metrics = classifier.get_metrics()
                adx = metrics['adx']
                volatility = metrics['volatility']
                bias = metrics['bias']
                
                print()
                print("!" * 80)
                print(f"CAMBIO DE RÉGIMEN DETECTADO en vela {idx}")
                print(f"  De: {previous_regime.value:6s} -> A: {current_regime.value:6s}")
                print(f"  Fase esperada: {expected_phase}")
                print(f"  ADX: {adx:.2f}")
                print(f"  Volatilidad: {volatility:.4f} ({volatility*100:.2f}%)")
                print(f"  Sesgo (SMA 200): {bias if bias else 'N/A'}")
                if metrics.get('volatility_shock_detected'):
                    print(f"  [SHOCK] SHOCK DE VOLATILIDAD DETECTADO")
                print("!" * 80)
                print()
                
                regime_changes.append({
                    'candle': idx,
                    'from': previous_regime.value,
                    'to': current_regime.value,
                    'expected_phase': expected_phase,
                    'adx': adx,
                    'volatility': volatility,
                    'bias': bias
                })
                
                previous_regime = current_regime
    
    # Resumen final
    print("=" * 80)
    print("RESUMEN DE CAMBIOS DETECTADOS")
    print("=" * 80)
    print()
    
    if not regime_changes:
        print("[ADVERTENCIA] No se detectaron cambios de régimen durante la simulación")
        print("   Esto puede indicar que los umbrales son demasiado conservadores")
    else:
        print(f"Total de cambios detectados: {len(regime_changes)}")
        print()
        
        for i, change in enumerate(regime_changes, 1):
            print(f"Cambio {i}:")
            print(f"  Vela: {change['candle']}")
            print(f"  Transición: {change['from']} -> {change['to']}")
            print(f"  Fase esperada: {change['expected_phase']}")
            print(f"  ADX en el momento: {change['adx']:.2f}")
            print(f"  Volatilidad: {change['volatility']*100:.2f}%")
            print(f"  Sesgo: {change['bias'] if change['bias'] else 'N/A'}")
            print()
    
    # Análisis de calibración
    print("=" * 80)
    print("ANÁLISIS DE CALIBRACIÓN")
    print("=" * 80)
    print()
    
    # Obtener métricas finales de cada fase
    classifier.reset()
    
    phases_analysis = {}
    for phase_name, (start, end) in phase_boundaries.items():
        phase_data = all_data.iloc[start:end]
        
        # Procesar fase
        for _, row in phase_data.iterrows():
            classifier.add_candle(
                close=row['close'],
                high=row['high'],
                low=row['low'],
                open_price=row['open']
            )
        
        if len(classifier.df) >= max(classifier.adx_period * 2, 20):
            final_regime = classifier.classify()
            metrics = classifier.get_metrics()
            
            phases_analysis[phase_name] = {
                'regime': final_regime.value,
                'adx': metrics['adx'],
                'volatility': metrics['volatility'],
                'bias': metrics['bias']
            }
        
        classifier.reset()
    
    print("Métricas al final de cada fase:")
    for phase_name, metrics in phases_analysis.items():
        print(f"\n{phase_name}:")
        print(f"  Régimen detectado: {metrics['regime']}")
        print(f"  ADX: {metrics['adx']:.2f}")
        print(f"  Volatilidad: {metrics['volatility']*100:.2f}%")
        print(f"  Sesgo: {metrics['bias'] if metrics['bias'] else 'N/A'}")
    
    print()
    print("=" * 80)
    print("RECOMENDACIONES DE CALIBRACIÓN")
    print("=" * 80)
    print()
    
    # Analizar si los umbrales son apropiados
    range_adx = phases_analysis.get('RANGE', {}).get('adx', 0)
    trend_adx = phases_analysis.get('TREND', {}).get('adx', 0)
    crash_vol = phases_analysis.get('CRASH', {}).get('volatility', 0)
    
    print("Análisis de umbrales (optimizados):")
    print(f"  ADX en RANGE: {range_adx:.2f} (entrar RANGE: < 20.0, salir TREND: < 18.0)")
    print(f"  ADX en TREND: {trend_adx:.2f} (entrar TREND: > 25.0)")
    print(f"  Volatilidad en CRASH: {crash_vol*100:.2f}%")
    print()
    
    if range_adx > 20:
        print("[ADVERTENCIA] ADX en RANGE es mayor que el umbral (20.0)")
        print("   Considera aumentar adx_range_threshold o revisar la generacion de datos")
    
    if trend_adx < 25:
        print("[ADVERTENCIA] ADX en TREND es menor que el umbral (25.0)")
        print("   Considera disminuir adx_trend_threshold o aumentar la fuerza de tendencia")
    
    if crash_vol > 0:
        range_vol = phases_analysis.get('RANGE', {}).get('volatility', 0)
        if range_vol > 0:
            vol_increase = (crash_vol / range_vol) if range_vol > 0 else 0
            print(f"  Aumento de volatilidad RANGE -> CRASH: {vol_increase:.1f}x (umbral shock: 5.0x)")
            if vol_increase < 5.0:
                print("[ADVERTENCIA] El aumento de volatilidad no alcanza el umbral de 5.0x")
                print("   Considera ajustar volatility_shock_multiplier o shock_lookback")
    
    print()
    print("=" * 80)


if __name__ == "__main__":
    simulate_regime_detection()
