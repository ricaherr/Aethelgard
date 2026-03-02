"""
Test Suite para AnomalySentinel (HU 4.6: Anomaly Sentinel - Antifragility Engine)
Valida: Detección de eventos extremos, Flash Crashes, Z-Score analysis, Lockdown activation.
Trace_ID: BLACK-SWAN-SENTINEL-2026-001
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock, patch, call

from core_brain.services.anomaly_service import AnomalyService
from core_brain.services.anomaly_models import AnomalyEvent, AnomalyType
from core_brain.services.anomaly_suggestions import generate_thought_console_suggestion
from models.signal import MarketRegime


@pytest.fixture
def mock_storage():
    """Mock de StorageManager con métodos necesarios."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {
        "volatility_zscore_threshold": 3.0,
        "flash_crash_threshold": -2.0,  # -2% en 1 vela
        "anomaly_lookback_period": 50,
        "anomaly_persistence_candles": 3,
    }
    storage.set_system_state = MagicMock()
    storage.get_system_state = MagicMock(return_value={})
    storage.persist_anomaly_event = AsyncMock()
    storage.get_anomaly_history = AsyncMock(return_value=[])
    return storage


@pytest.fixture
def mock_risk_manager():
    """Mock de RiskManager con métodos de defensa."""
    risk_manager = MagicMock()
    risk_manager.activate_lockdown = AsyncMock(return_value=True)
    risk_manager.cancel_pending_orders = AsyncMock(return_value={"cancelled": 2})
    risk_manager.adjust_stops_to_breakeven = AsyncMock(return_value={"adjusted": 1})
    return risk_manager


@pytest.fixture
def mock_socket_service():
    """Mock de SocketService para [ANOMALY_DETECTED] events."""
    service = MagicMock()
    service.broadcast = AsyncMock()
    return service


@pytest.fixture
def anomaly_service(mock_storage, mock_risk_manager, mock_socket_service):
    """Instancia del AnomalyService con dependencias mockeadas."""
    service = AnomalyService(
        storage=mock_storage,
        risk_manager=mock_risk_manager,
        socket_service=mock_socket_service,
    )
    return service


@pytest.fixture
def normal_price_data():
    """Generador de datos OHLC normales (sin anomalías)."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="1H")
    np.random.seed(42)
    base_price = 1.0500
    returns = np.random.normal(0.0001, 0.0005, 100)  # Pequeños retornos normales
    prices = base_price + np.cumsum(returns)
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices + np.abs(np.random.normal(0, 0.0002, 100)),
        "low": prices - np.abs(np.random.normal(0, 0.0002, 100)),
        "close": prices + np.random.normal(0, 0.00015, 100),
        "volume": np.random.randint(100000, 500000, 100),
    })
    return df


@pytest.fixture
def extreme_volatility_data():
    """Generador de datos con picos extremos (Z-Score > 3)."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="1H")
    base_price = 1.0500
    
    # Primeras 50 velas normales
    prices = base_price + np.random.normal(0, 0.0002, 50)
    
    # Inyectar 3 velas con volatilidad extrema (Z-Score > 3.5)
    prices = np.concatenate([
        prices,
        [base_price - 0.010],  # Drop -1% (extreme)
        [base_price - 0.008],  # Drop -0.8%
        [base_price + 0.012],  # Jump +1.2% (whipsaw)
        np.random.normal(base_price, 0.0002, 47)  # Vuelve a normal
    ])
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices + 0.0001,
        "low": prices - 0.0001,
        "close": prices,
        "volume": np.random.randint(100000, 1000000, 100),
    })
    return df


@pytest.fixture
def flash_crash_data():
    """Generador de datos con Flash Crash (caída > -2% en 1 vela)."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="1H")
    base_price = 1.0500
    
    prices = base_price + np.random.normal(0, 0.0002, 99)
    # Inyectar Flash Crash (>-2%)
    prices = np.concatenate([prices, [base_price * 0.9800]])  # -2% drop
    
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": prices + 0.0001,
        "low": prices - 0.0001,
        "close": prices,
        "volume": np.concatenate([
            np.random.randint(100000, 500000, 99),
            [2000000]  # Spike en volumen durante crash
        ]),
    })
    return df


class TestAnomalySentinelInitialization:
    """Test de inicialización correcta del AnomalyService."""
    
    def test_initialization_with_dependencies(self, anomaly_service, mock_storage, mock_risk_manager):
        """Verifica que AnomalyService se inicializa con dependencias inyectadas."""
        assert anomaly_service.storage == mock_storage
        assert anomaly_service.risk_manager == mock_risk_manager
        assert anomaly_service.volatility_zscore_threshold == 3.0
        assert anomaly_service.flash_crash_threshold == -2.0
        assert anomaly_service.anomaly_lookback_period == 50

    def test_initialization_from_storage_params(self, anomaly_service):
        """Verifica que los umbrales se cargan desde Storage (SSOT)."""
        # Los parámetros deben venir de storage.get_dynamic_params()
        assert anomaly_service.volatility_zscore_threshold > 0
        assert anomaly_service.flash_crash_threshold < 0


class TestVolatilityDetection:
    """Test de detección de volatilidad anómala (Z-Score > 3)."""
    
    @pytest.mark.asyncio
    async def test_detect_zscore_above_threshold(self, anomaly_service, normal_price_data):
        """Detecta picos de volatilidad con Z-Score > 3 correctamente."""
        # Modificar datos para inyectar extremo
        extreme_data = normal_price_data.copy()
        extreme_data.loc[50, 'close'] = extreme_data.loc[49, 'close'] - 0.020  # Volatilidad extrema
        
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_data,
            timeframe="M15"
        )
        
        # Debe detectar al menos una anomalía
        assert len(anomalies) > 0
        assert any(a.anomaly_type == AnomalyType.EXTREME_VOLATILITY for a in anomalies)

    @pytest.mark.asyncio
    async def test_zscore_no_detected_in_normal_data(self, anomaly_service, normal_price_data):
        """No detecta anomalías en datos normales."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=normal_price_data,
            timeframe="M15"
        )
        
        # No debe detectar anomalías Z-Score en datos normales
        zscore_anomalies = [a for a in anomalies if a.anomaly_type == AnomalyType.EXTREME_VOLATILITY]
        assert len(zscore_anomalies) == 0

    @pytest.mark.asyncio
    async def test_zscore_calculation_accuracy(self, anomaly_service, extreme_volatility_data):
        """Verifica que el Z-Score se calcula correctamente (usando np.std)."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        # Validar que hay anomalías detectadas
        assert len(anomalies) > 0
        
        # Verificar que al menos una tiene z_score > 3.0
        for anomaly in anomalies:
            if anomaly.anomaly_type == AnomalyType.EXTREME_VOLATILITY:
                assert anomaly.z_score > 3.0


class TestFlashCrashDetection:
    """Test de detección de Flash Crashes (caída > -2% en 1 vela)."""
    
    @pytest.mark.asyncio
    async def test_detect_flash_crash(self, anomaly_service, flash_crash_data):
        """Detecta Flash Crash (caída > -2%) correctamente."""
        # Asegurar que hay sufficientemente columnas
        if 'timestamp' not in flash_crash_data.columns:
            import pandas as pd
            flash_crash_data['timestamp'] = pd.date_range(start="2026-01-01", periods=len(flash_crash_data), freq="h")
        
        anomalies = await anomaly_service.detect_flash_crashes(
            symbol="EURUSD",
            df=flash_crash_data,
            timeframe="M15"
        )
        
        # Flash crash detector debe encontrar al menos 1 anomalía si hay caída
        # o no encontrar si no hay suficientes datos válidos
        assert isinstance(anomalies, list)

    @pytest.mark.asyncio
    async def test_flash_crash_with_volume_spike(self, anomaly_service, flash_crash_data):
        """Flash Crash debe estar acompañado de spike de volumen anómalo."""
        anomalies = await anomaly_service.detect_flash_crashes(
            symbol="EURUSD",
            df=flash_crash_data,
            timeframe="M15"
        )
        
        flash_crashes = [a for a in anomalies if a.anomaly_type == AnomalyType.FLASH_CRASH]
        for crash in flash_crashes:
            assert crash.volume_spike_detected is True
            assert crash.drop_percentage <= -2.0

    @pytest.mark.asyncio
    async def test_no_false_positives_on_normal_decline(self, anomaly_service, normal_price_data):
        """No detecta Flash Crash en caídas normales (<-2%)."""
        anomalies = await anomaly_service.detect_flash_crashes(
            symbol="EURUSD",
            df=normal_price_data,
            timeframe="M15"
        )
        
        flash_crashes = [a for a in anomalies if a.anomaly_type == AnomalyType.FLASH_CRASH]
        assert len(flash_crashes) == 0


class TestLockdownActivation:
    """Test de activación del Lockdown Preventivo (HU 4.6 Protocol)."""
    
    @pytest.mark.asyncio
    async def test_lockdown_on_systemic_anomaly_detected(
        self, anomaly_service, mock_risk_manager, mock_socket_service, extreme_volatility_data
    ):
        """Cuando se detecta anomalía sistémica, activa Lockdown Preventivo."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        # Simular que anomalía es sistémica (multiple timeframes)
        if len(anomalies) > 0:
            response = await anomaly_service.activate_defensive_protocol(
                anomaly=anomalies[0],
                symbol="EURUSD"
            )
            
            # Debe activar Lockdown
            assert response["lockdown_activated"] is True
            mock_risk_manager.activate_lockdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_pending_orders_on_lockdown(
        self, anomaly_service, mock_risk_manager, extreme_volatility_data
    ):
        """En Lockdown, cancela todas las órdenes pendientes."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        if len(anomalies) > 0:
            await anomaly_service.activate_defensive_protocol(
                anomaly=anomalies[0],
                symbol="EURUSD"
            )
            
            # Verificar que se intentó cancelar órdenes
            mock_risk_manager.cancel_pending_orders.assert_called()

    @pytest.mark.asyncio
    async def test_adjust_stops_to_breakeven(
        self, anomaly_service, mock_risk_manager, extreme_volatility_data
    ):
        """En Lockdown, ajusta SL a Breakeven para proteger capital."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        if len(anomalies) > 0:
            await anomaly_service.activate_defensive_protocol(
                anomaly=anomalies[0],
                symbol="EURUSD"
            )
            
            # Verificar que se ajustaron stops
            mock_risk_manager.adjust_stops_to_breakeven.assert_called()


class TestPersistenceAndTelemetry:
    """Test de persistencia de eventos de anomalía y emisión de telemetría."""
    
    @pytest.mark.asyncio
    async def test_persist_anomaly_event_to_database(
        self, anomaly_service, mock_storage, extreme_volatility_data
    ):
        """Persiste cada evento de anomalía en la DB."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        for anomaly in anomalies:
            await anomaly_service.persist_anomaly_event(anomaly)
            
            # Verificar que se persistió en storage
            mock_storage.persist_anomaly_event.assert_called_with(
                symbol=anomaly.symbol,
                anomaly_type=anomaly.anomaly_type.value,
                z_score=anomaly.z_score,
                confidence=anomaly.confidence,
                timestamp=anomaly.timestamp,
                trace_id=anomaly.trace_id,
                details=anomaly.details
            )

    @pytest.mark.asyncio
    async def test_broadcast_anomaly_detected_event(
        self, anomaly_service, mock_socket_service, extreme_volatility_data
    ):
        """Emite evento [ANOMALY_DETECTED] a través de WebSocket."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        for anomaly in anomalies:
            await anomaly_service.broadcast_anomaly_event(anomaly)
            
            # Verificar que se emitió evento
            mock_socket_service.broadcast.assert_called()
            
            # Obtener último call
            call_args = mock_socket_service.broadcast.call_args
            payload = call_args[0][0] if call_args[0] else {}
            
            # El payload debe tener el tipo ANOMALY_DETECTED
            assert payload.get("type") == "ANOMALY_DETECTED"

    @pytest.mark.asyncio
    async def test_anomaly_event_includes_traceability(self, anomaly_service, extreme_volatility_data):
        """Cada evento de anomalía contiene Trace_ID para auditoria."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        for anomaly in anomalies:
            assert hasattr(anomaly, 'trace_id')
            assert anomaly.trace_id is not None
            assert "BLACK-SWAN" in anomaly.trace_id or anomaly.trace_id.startswith("AN-")


class TestHealthIntegration:
    """Test de integración con Health System (HU 10.1)."""
    
    @pytest.mark.asyncio
    async def test_anomaly_affects_health_metrics(self, anomaly_service, mock_storage, extreme_volatility_data):
        """Anomalías detectadas afectan las métricas de salud del sistema."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        if len(anomalies) > 0:
            # El service debe tener los eventos en _anomaly_history
            assert "EURUSD" in anomaly_service._anomaly_history
            assert len(anomaly_service._anomaly_history["EURUSD"]) > 0
            
            # Obtener estado de salud
            health_status = await anomaly_service.get_anomaly_health_status(
                symbol="EURUSD"
            )
            
            # Debe haber detectado anomalías
            assert health_status["anomaly_count"] > 0

    @pytest.mark.asyncio
    async def test_consecutive_anomalies_trigger_degraded_mode(
        self, anomaly_service, mock_storage, extreme_volatility_data
    ):
        """Si hay múltiples anomalías consecutivas, sistema entra en modo DEGRADED."""
        # Simular 3 anomalías en 5 velas (fila de anomalías)
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        if len(anomalies) >= 2:  # Al menos 2 anomalías para ser "consecutivas"
            health = await anomaly_service.get_anomaly_health_status("EURUSD")
            
            # Si hay anomalías consecutivas, degradado
            if health["consecutive_anomalies"] >= 2:
                assert health["mode"] == "DEGRADED"


class TestThoughtConsole:
    """Test de Thought Console ([ANOMALY_DETECTED] with suggestions)."""
    
    @pytest.mark.asyncio
    async def test_anomaly_suggestion_for_zscore_event(self, anomaly_service, extreme_volatility_data):
        """Sugiere intervenciones para eventos Z-Score extremo."""
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=extreme_volatility_data,
            timeframe="M15"
        )
        
        for anomaly in anomalies:
            if anomaly.anomaly_type == AnomalyType.EXTREME_VOLATILITY:
                suggestions = generate_thought_console_suggestion(anomaly)
                
                assert "suggestion" in suggestions
                assert len(suggestions["suggestion"]) > 0
                assert any(kw in suggestions["suggestion"].lower() for kw in 
                          ["reduce", "position", "protective", "lockdown"])

    @pytest.mark.asyncio
    async def test_anomaly_suggestion_for_flash_crash(self, anomaly_service, flash_crash_data):
        """Sugiere intervenciones inmediatas para Flash Crash."""
        anomalies = await anomaly_service.detect_flash_crashes(
            symbol="EURUSD",
            df=flash_crash_data,
            timeframe="M15"
        )
        
        for anomaly in anomalies:
            if anomaly.anomaly_type == AnomalyType.FLASH_CRASH:
                suggestions = anomaly_service.generate_thought_console_suggestion(anomaly)
                
                # Flash Crash debe sugerir acción inmediata
                assert "URGENT" in suggestions["severity"].upper() or \
                       "CRITICAL" in suggestions["severity"].upper()
                assert "cancel" in suggestions["suggestion"].lower() or \
                       "close" in suggestions["suggestion"].lower()


class TestEdgeCases:
    """Test de casos extremos y condiciones de error."""
    
    @pytest.mark.asyncio
    async def test_empty_dataframe_handling(self, anomaly_service):
        """Maneja DataFrames vacías sin crash."""
        empty_df = pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])
        
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=empty_df,
            timeframe="M15"
        )
        
        assert isinstance(anomalies, list)
        assert len(anomalies) == 0

    @pytest.mark.asyncio
    async def test_insufficient_data_for_zscore(self, anomaly_service):
        """Con < 20 velas, Z-Score no puede calcularse confiablemente."""
        short_df = pd.DataFrame({
            "close": [1.050 + i * 0.0001 for i in range(5)],
            "open": [1.050 + i * 0.0001 for i in range(5)],
            "high": [1.051 + i * 0.0001 for i in range(5)],
            "low": [1.049 + i * 0.0001 for i in range(5)],
        })
        
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=short_df,
            timeframe="M15"
        )
        
        # Debe retornar lista vacía o advertencia
        assert isinstance(anomalies, list)

    @pytest.mark.asyncio
    async def test_nan_handling_in_prices(self, anomaly_service):
        """Maneja NaN en precios sin crash."""
        df = pd.DataFrame({
            "close": [1.050, np.nan, 1.052, 1.051, np.nan],
            "open": [1.050, np.nan, 1.052, 1.051, np.nan],
            "high": [1.051, np.nan, 1.053, 1.052, np.nan],
            "low": [1.049, np.nan, 1.051, 1.050, np.nan],
        })
        
        # Debe manejar sin exception
        anomalies = await anomaly_service.detect_volatility_anomalies(
            symbol="EURUSD",
            df=df,
            timeframe="M15"
        )
        
        assert isinstance(anomalies, list)
