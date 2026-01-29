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
    factory = SignalFactory(storage_manager=mock_storage_manager)
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
    base_price=100, num_candles=250, atr_value=0.5,
    trend_slope=0.05, is_perfect_elephant=False, is_inconsistent=False
):
    """
    Crea un DataFrame sintético para simular datos de mercado.
    Permite crear escenarios específicos para las pruebas.
    """
    dates = pd.to_datetime(pd.date_range(end=datetime.now(), periods=num_candles, freq='5min'))
    prices = base_price + np.arange(num_candles, dtype=float) * trend_slope
    
    # Simulación de ruido y volatilidad
    noise = np.random.normal(0, atr_value * 0.5, num_candles)
    prices += noise
    
    df = pd.DataFrame(index=dates)
    df['open'] = prices - np.random.uniform(0, atr_value, num_candles)
    df['close'] = prices + np.random.uniform(0, atr_value, num_candles)
    df['high'] = df[['open', 'close']].max(axis=1) + np.random.uniform(0, atr_value * 0.5, num_candles)
    df['low'] = df[['open', 'close']].min(axis=1) - np.random.uniform(0, atr_value * 0.5, num_candles)
    
    # Indicadores
    df['atr'] = atr_value
    df['sma_20'] = df['close'].rolling(window=20).mean()
    df['sma_200'] = df['close'].rolling(window=200).mean()

    # --- Escenarios Específicos ---
    if is_perfect_elephant:
        # Forzamos una vela elefante alcista al final que rebota en la SMA20
        last_idx = df.index[-1]
        sma20 = df['sma_20'].iloc[-2]
        
        df.loc[last_idx, 'low'] = sma20 - 0.01  # Rebote justo en la SMA20
        df.loc[last_idx, 'open'] = sma20 + 0.05
        # Cuerpo > 2.5x ATR
        df.loc[last_idx, 'close'] = df.loc[last_idx, 'open'] + atr_value * 2.5
        df.loc[last_idx, 'high'] = df.loc[last_idx, 'close'] + 0.05
        df.loc[last_idx, 'sma_200'] = base_price * 0.9 # Asegurar que el precio está muy por encima
        df.loc[last_idx, 'atr'] = atr_value

    if is_inconsistent:
        # Creamos una vela alcista fuerte, PERO por debajo de la SMA200
        last_idx = df.index[-1]
        df.loc[last_idx, 'open'] = base_price * 0.9
        df.loc[last_idx, 'close'] = base_price * 0.9 + atr_value * 3 # Vela fuerte
        df.loc[last_idx, 'sma_200'] = base_price * 1.1 # SMA200 muy por encima
        df.loc[last_idx, 'atr'] = atr_value

    # Rellenar NaNs iniciales
    df.bfill(inplace=True)
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
    df = create_synthetic_dataframe(is_perfect_elephant=True, trend_slope=0.1)
    symbol = "EURUSD_PERFECT"
    
    # Act: Generar señales (ahora devuelve lista)
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
    # Obtener la estrategia OliverVelezStrategy de la lista
    ov_strategy = next(s for s in signal_factory.strategies if isinstance(s, OliverVelezStrategy))

    # Arrange: Crear una base de señal válida, pero con valores débiles.
    atr = 0.2
    df = create_synthetic_dataframe(is_perfect_elephant=True, atr_value=atr, trend_slope=0.01)

    # Degradamos la vela "perfecta" a una "apenas pasable".
    # El cuerpo será > 2.0x ATR, pero no por mucho.
    last_idx = df.index[-1]
    # Usamos el multiplicador configurado en la estrategia
    df.loc[last_idx, 'close'] = df.loc[last_idx, 'open'] + (atr * ov_strategy.elephant_atr_multiplier + 0.01)

    symbol = "EURUSD_WEAK"
    
    # Modificamos los umbrales en la **estrategia** para forzar un score bajo
    ov_strategy.base_score = 60.0 # Score base normal
    ov_strategy.regime_bonus = 5.0 # Bono bajo por estar en Trend
    ov_strategy.premium_threshold = 85.0 # Umbral premium normal

    # Act: Generar la señal
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
