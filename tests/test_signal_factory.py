"""
Test Suite para el Signal Factory de Aethelgard (Refactorizado)
=================================================

Objetivo: Validar la lógica de negocio del SignalFactory bajo los principios de TDD.
- Mockea dependencias externas (Storage, Notifier).
- Simula datos de mercado para probar escenarios específicos.
- Verifica la correcta asignación de scores y el disparo de notificaciones.
- Adaptado al Patrón Strategy (Fase 2.2).
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime

# Componentes a probar y mockear
from core_brain.signal_factory import SignalFactory
from core_brain.strategies.oliver_velez import OliverVelezStrategy
from models.signal import Signal, MarketRegime, MembershipTier, SignalType, ConnectorType
from data_vault.storage import StorageManager

# --- Fixtures de Pytest y Funciones de Ayuda ---

@pytest.fixture
def mock_storage_manager():
    """Mock del StorageManager para evitar accesos a la base de datos."""
    manager = MagicMock(spec=StorageManager)
    manager.save_signal.return_value = "signal_123"
    # Deduplication queries should return False (no existing signals/positions)
    manager.has_recent_signal.return_value = False
    manager.has_open_position.return_value = False
    return manager

@pytest.fixture
def mock_notifier():
    """
    Mock del Notificador de Telegram. Se usa patch para interceptar la llamada
    a `get_notifier` dentro del módulo `signal_factory`.
    """
    with patch('core_brain.signal_factory.get_notifier') as mock_get_notifier:
        notifier_instance = MagicMock()
        # Mockeamos el método asíncrono `notify_oliver_velez_signal`
        notifier_instance.notify_oliver_velez_signal = AsyncMock()
        mock_get_notifier.return_value = notifier_instance
        yield notifier_instance

@pytest.fixture
def signal_factory(mock_storage_manager, mock_notifier, monkeypatch):
    """Fixture que inicializa el SignalFactory con dependencias mockeadas."""
    # Preparar dependencias inyectadas para SignalFactory
    ov_strategy = OliverVelezStrategy(config={})
    confluence_analyzer = MagicMock()
    confluence_analyzer.enabled = True
    trifecta_analyzer = MagicMock()
    
    factory = SignalFactory(
        storage_manager=mock_storage_manager,
        strategies=[ov_strategy],
        confluence_analyzer=confluence_analyzer,
        trifecta_analyzer=trifecta_analyzer
    )
    # Re-asignamos el notifier por si la inicialización original falló
    factory.notifier = mock_notifier
    
    # Patch InstrumentManager to accept test symbols
    from core_brain.instrument_manager import InstrumentManager, InstrumentConfig
    
    test_config = InstrumentConfig(
        category="forex",
        subcategory="majors",
        enabled=True,
        min_score=50.0,
        risk_multiplier=1.0,
        max_spread=2.0,
        priority=3,
        instruments=["EURUSD_PERFECT", "EURUSD_WEAK"]
    )
    
    original_get_config = InstrumentManager.get_config
    original_is_enabled = InstrumentManager.is_enabled
    
    def patched_get_config(self, symbol: str):
        if symbol in ["EURUSD_PERFECT", "EURUSD_WEAK"]:
            return test_config
        return original_get_config(self, symbol)
    
    def patched_is_enabled(self, symbol: str):
        if symbol in ["EURUSD_PERFECT", "EURUSD_WEAK"]:
            return True
        return original_is_enabled(self, symbol)
    
    monkeypatch.setattr(InstrumentManager, "get_config", patched_get_config)
    monkeypatch.setattr(InstrumentManager, "is_enabled", patched_is_enabled)
    
    return factory

def create_synthetic_dataframe(
    base_price=1.1, num_candles=500, atr_value=0.002, 
    trend_slope=0.0001, is_perfect_elephant=False, is_inconsistent=False
):
    """
    Crea un DataFrame sintético para simular datos de mercado.
    """
    dates = pd.to_datetime(pd.date_range(end=datetime.now(), periods=num_candles, freq='5min'))
    prices = base_price + np.arange(num_candles, dtype=float) * trend_slope
    
    df = pd.DataFrame(index=dates)
    df['open'] = prices - np.random.uniform(0, atr_value, num_candles)
    df['close'] = prices + np.random.uniform(0, atr_value, num_candles)
    df['high'] = df[['open', 'close']].max(axis=1) + np.random.uniform(0, atr_value * 0.5, num_candles)
    df['low'] = df[['open', 'close']].min(axis=1) - np.random.uniform(0, atr_value * 0.5, num_candles)
    
    # Inicializar columnas para métricas EDGE STRICT (evitar NaNs)
    df['zscore_body'] = 0.0
    df['solidness'] = 0.8
    df['atr'] = float(atr_value)
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_200'] = df['close'].rolling(window=200).mean()

    # --- Escenarios Específicos ---
    if is_perfect_elephant:
        # Tendencia alcista fuerte para slope_slow > 0.05
        # Usar un slope que genere una tendencia clara en 200 velas
        steeper_slope = 0.001 
        trend_prices = base_price + np.arange(num_candles, dtype=float) * steeper_slope
        df['close'] = trend_prices + np.random.normal(0, 0.0001, num_candles)
        df['sma_20'] = df['close'].rolling(window=20).mean()
        df['sma_200'] = df['close'].rolling(window=200).mean()
        df['atr'] = float(atr_value)
        
        last_idx = df.index[-1]
        sma20_prev = df['sma_20'].iloc[-2]
        
        # Inyectar métricas EDGE STRICT de forma atómica
        df.at[last_idx, 'zscore_body'] = 3.5
        df.at[last_idx, 'solidness'] = 0.95
        df.at[last_idx, 'zscore_body'] = 3.5
        df.at[last_idx, 'solidness'] = 0.95
        
        # Ajuste de Location: Low exacto en SMA20 (o muy cerca)
        # Rango permitido: [SMA20 - 0.2*ATR, SMA20 + 0.5*ATR]
        # Ponemos Low = SMA20_prev (aprox)
        safe_low = float(sma20_prev) 
        df.at[last_idx, 'low'] = safe_low
        # FORZAMOS que la SMA20 actual sea igual al Low para alineación perfecta
        df.at[last_idx, 'sma_20'] = safe_low 
        
        df.at[last_idx, 'open'] = safe_low + 0.0001
        df.at[last_idx, 'close'] = safe_low + atr_value * 4.0
        df.at[last_idx, 'high'] = safe_low + atr_value * 4.0 + 0.0002

    if is_inconsistent:
        # Vela fuerte pero por debajo de SMA200
        last_idx = df.index[-1]
        df.at[last_idx, 'close'] = base_price * 0.5
        df.at[last_idx, 'sma_200'] = base_price * 1.5
        df.at[last_idx, 'zscore_body'] = 3.5
        df.at[last_idx, 'solidness'] = 0.95

    # Limpieza final robusta
    df.sort_index(inplace=True)
    df.bfill(inplace=True)
    df.ffill(inplace=True)
    return df

# --- Casos de Prueba ---

@pytest.mark.asyncio
async def test_perfect_elephant_candle_generates_high_score_signal(signal_factory, mock_notifier):
    """
    Prueba de Escenario Ideal (Validación de Score):
    Un DataFrame con una 'Vela Elefante' perfecta en tendencia alcista
    y rebotando en la SMA20 debe generar una señal con un score > 80.
    """
    # Arrange: Crear datos sintéticos para una señal de libro
    df = create_synthetic_dataframe(is_perfect_elephant=True)
    symbol = "EURUSD_PERFECT"
    
    # Act: Generar señal
    print(f"\n[DEBUG] {symbol} Tail before generate_signal:")
    cols = ['close', 'low', 'sma_20', 'sma_200', 'zscore_body', 'solidness']
    print(df[cols].tail(1))
    
    results = await signal_factory.generate_signal(symbol, df, MarketRegime.TREND)
    
    # Assert: Validar que la señal es de alta calidad
    assert len(results) > 0, "No se generó ninguna señal para un escenario perfecto."
    result_signal = results[0]
    
    assert isinstance(result_signal, Signal)
    assert result_signal.metadata.get("score", 0) > 80, f"El score fue {result_signal.metadata.get('score', 0)}, se esperaba > 80."
    assert result_signal.signal_type == SignalType.BUY
    membership_tier_value = result_signal.metadata.get("membership_tier", "")
    assert membership_tier_value in [MembershipTier.PREMIUM.value, MembershipTier.ELITE.value]
    
    # Validar que la notificación SÍ se disparó para una señal de alto score
    mock_notifier.notify_oliver_velez_signal.assert_called_once()


@pytest.mark.asyncio
async def test_inconsistent_data_is_rejected(signal_factory, mock_notifier):
    """
    Prueba de Error (Rechazo de Señal):
    Datos con una contradicción fundamental (ej. vela alcista por debajo de SMA200)
    deben ser rechazados y no generar una señal.
    """
    # Arrange: Datos con vela alcista pero en clara tendencia bajista (precio < SMA200)
    df = create_synthetic_dataframe(is_inconsistent=True)
    symbol = "EURUSD_INCONSISTENT"
    
    # Act: Intentar generar la señal
    results = await signal_factory.generate_signal(symbol, df, MarketRegime.TREND)
    
    # Assert: El sistema debe rechazar la señal
    assert len(results) == 0, "Se generó una señal para datos inconsistentes."
    
    # Asegurarse de que el notificador no fue llamado
    mock_notifier.notify_oliver_velez_signal.assert_not_called()


@pytest.mark.asyncio
async def test_low_score_signal_does_not_trigger_notification(signal_factory, mock_notifier):
    """
    Prueba de Membresía / Score Bajo:
    Una señal que cumple los requisitos mínimos pero con valores límite debe generar
    un score bajo y no disparar una notificación 'Premium'.
    """
    # Preparar la estrategia para el test
    ov_strategy = next(s for s in signal_factory.strategies if isinstance(s, OliverVelezStrategy))

    # Arrange: Crear una base de señal válida, pero con valores débiles.
    atr = 0.002
    df = create_synthetic_dataframe(is_perfect_elephant=True, atr_value=atr)

    # Degradamos la vela "perfecta" a una "apenas pasable".
    last_idx = df.index[-1]
    # Forzamos un cierre que genere un score bajo (Z-score 2.0 apenas)
    df.at[last_idx, 'zscore_body'] = 2.0
    df.at[last_idx, 'solidness'] = 0.55
    df.at[last_idx, 'close'] = float(df.at[last_idx, 'open'] + atr * 2.1)

    symbol = "EURUSD_WEAK"
    
    # Modificamos los umbrales en la **estrategia** para forzar un score bajo
    # Permitir solidez baja para este test
    ov_strategy.elephant_solidness_min = 0.5 
    ov_strategy.premium_threshold = 80.0

    # Act: Generar la señal
    print(f"\n[DEBUG] {symbol} Tail before generate_signal:")
    cols = ['close', 'open', 'zscore_body', 'solidness']
    print(df[cols].tail(1))

    results = await signal_factory.generate_signal(symbol, df, MarketRegime.TREND)
    
    # Assert
    assert len(results) > 0, "No se generó señal para datos débiles pero válidos."
    result_signal = results[0]
    
    score = result_signal.metadata.get("score", 0)
    assert score < 80, f"El score fue {score}, se esperaba < 80."
    membership_tier_value = result_signal.metadata.get("membership_tier", "")
    assert membership_tier_value == MembershipTier.FREE.value
    
    # La aserción CRÍTICA: el notificador no debe ser llamado para señales 'FREE'
    mock_notifier.notify_oliver_velez_signal.assert_not_called()
