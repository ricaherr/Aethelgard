"""
Tests para RegimeService (HU 2.1: Motor de Unificación Temporal).
Valida: alineación fractal, veto fractal, sincronización de ledger.
"""

import pytest
import pandas as pd
from datetime import datetime
from unittest.mock import MagicMock, patch

from core_brain.services.regime_service import RegimeService
from models.signal import MarketRegime, FractalContext, Signal, SignalType


@pytest.fixture
def mock_storage():
    """Mock de StorageManager con métodos necesarios."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {
        "adx_period": 14,
        "sma_period": 200,
        "adx_trend_threshold": 25.0,
        "adx_range_threshold": 20.0,
        "adx_range_exit_threshold": 18.0,
        "volatility_shock_multiplier": 5.0
    }
    storage.set_sys_config = MagicMock()
    storage.get_sys_config = MagicMock()
    return storage


@pytest.fixture
def regime_service(mock_storage):
    """Instancia del RegimeService con dependencias mockeadas."""
    return RegimeService(storage=mock_storage)


@pytest.fixture
def sample_ohlc_data():
    """Genera datos OHLCV de prueba (temporalidad neutral)."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="H")
    df = pd.DataFrame({
        "timestamp": dates,
        "open": [1.0500 + i * 0.0001 for i in range(100)],
        "high": [1.0510 + i * 0.0001 for i in range(100)],
        "low": [1.0490 + i * 0.0001 for i in range(100)],
        "close": [1.0505 + i * 0.0001 for i in range(100)],
    })
    return df


@pytest.fixture
def bullish_ohlc_data():
    """Genera datos con tendencia alcista (fuerte para M15, débil para H4)."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="H")
    prices = [1.0500 + i * 0.0005 for i in range(100)]  # Subida progresiva
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": [p + 0.0010 for p in prices],
        "low": [p - 0.0005 for p in prices],
        "close": [p + 0.0003 for p in prices],
    })
    return df


@pytest.fixture
def bearish_ohlc_data():
    """Genera datos con tendencia bajista."""
    dates = pd.date_range(start="2026-01-01", periods=100, freq="H")
    prices = [1.0500 - i * 0.0005 for i in range(100)]  # Bajada progresiva
    df = pd.DataFrame({
        "timestamp": dates,
        "open": prices,
        "high": [p + 0.0005 for p in prices],
        "low": [p - 0.0010 for p in prices],
        "close": [p - 0.0003 for p in prices],
    })
    return df


class TestRegimeServiceInitialization:
    """Tests de inicialización del servicio."""

    def test_regime_service_init(self, regime_service):
        """Verifica que el servicio se inicializa correctamente."""
        assert regime_service.storage is not None
        assert regime_service.trace_id is not None
        assert regime_service.trace_id.startswith("REGIME-")
        assert regime_service.m15_classifier is None
        assert regime_service.h1_classifier is None
        assert regime_service.h4_classifier is None

    def test_initialize_classifiers(self, regime_service, sample_ohlc_data):
        """Verifica que los clasificadores se inicializan correctamente."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        assert regime_service.m15_classifier is not None
        assert regime_service.h1_classifier is not None
        assert regime_service.h4_classifier is not None


class TestFractalContextGeneration:
    """Tests de generación de contexto fractal."""

    def test_get_fractal_context_aligned(self, regime_service, sample_ohlc_data):
        """Si todas las temporalidades tienen el mismo régimen, veto = 'ALIGNED'."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        context = regime_service.get_fractal_context()
        assert context is not None
        assert context.m15_regime == context.h1_regime == context.h4_regime
        assert context.is_fractally_aligned is True
        assert context.veto_signal in ["ALIGNED", "PARTIAL_CONFLICT"]

    def test_get_fractal_context_before_init(self, regime_service):
        """Si no se inicializa, retorna None."""
        context = regime_service.get_fractal_context()
        assert context is None


class TestFractalVeto:
    """Tests de la Regla de Veto Fractal (H4=Bearish, M15=Bullish → RETRACEMENT_RISK)."""

    @patch("core_brain.regime.RegimeClassifier.classify")
    def test_retracement_risk_veto(self, mock_classify, regime_service, sample_ohlc_data):
        """
        TESTE CRÍTICO: Si H4=Bearish Y M15=Bullish → RETRACEMENT_RISK.
        La confianza debe elevarse a 0.90.
        """
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        # Forzar regímenes específicos
        def classify_side_effect():
            if regime_service.m15_classifier.classify.call_args:
                return MarketRegime.BULL  # M15 Bullish
            elif regime_service.h1_classifier.classify.call_args:
                return MarketRegime.NORMAL
            elif regime_service.h4_classifier.classify.call_args:
                return MarketRegime.BEAR  # H4 Bearish
            return MarketRegime.NORMAL

        # Mockear los regímenes
        regime_service.m15_classifier.classify = MagicMock(return_value=MarketRegime.BULL)
        regime_service.h1_classifier.classify = MagicMock(return_value=MarketRegime.NORMAL)
        regime_service.h4_classifier.classify = MagicMock(return_value=MarketRegime.BEAR)

        context = regime_service.get_fractal_context()

        # Validaciones
        assert context.m15_regime == MarketRegime.BULL
        assert context.h4_regime == MarketRegime.BEAR
        assert context.veto_signal == "RETRACEMENT_RISK"
        assert context.confidence_threshold == 0.90

    @patch("core_brain.regime.RegimeClassifier.classify")
    def test_catastrophic_conflict_veto(self, mock_classify, regime_service, sample_ohlc_data):
        """Si H4=CRASH Y M15=BULL → CATASTROPHIC_CONFLICT."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        regime_service.m15_classifier.classify = MagicMock(return_value=MarketRegime.BULL)
        regime_service.h1_classifier.classify = MagicMock(return_value=MarketRegime.NORMAL)
        regime_service.h4_classifier.classify = MagicMock(return_value=MarketRegime.CRASH)

        context = regime_service.get_fractal_context()

        assert context.veto_signal == "CATASTROPHIC_CONFLICT"
        assert context.confidence_threshold == 0.90


class TestVetoApplicationToSignal:
    """Tests de aplicación del veto a señales de trading."""

    @patch("core_brain.regime.RegimeClassifier.classify")
    def test_apply_veto_to_signal_retracement_risk(
        self, mock_classify, regime_service, sample_ohlc_data
    ):
        """Cuando RETRACEMENT_RISK está activo, debe marcar la señal y elevar confianza."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        # Setup veto
        regime_service.m15_classifier.classify = MagicMock(return_value=MarketRegime.BULL)
        regime_service.h1_classifier.classify = MagicMock(return_value=MarketRegime.NORMAL)
        regime_service.h4_classifier.classify = MagicMock(return_value=MarketRegime.BEAR)

        # Crear señal de BUY
        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type="GENERIC",
            entry_price=1.0500,
            metadata={}
        )

        # Aplicar veto
        vetoed_signal = regime_service.apply_veto_to_signal(signal)

        # Validaciones
        assert vetoed_signal.confidence == 0.90  # Elevada
        assert "[RETRACEMENT_RISK]" in vetoed_signal.metadata.get("tags", [])

    def test_apply_veto_no_veto_active(self, regime_service, sample_ohlc_data):
        """Si no hay veto activo, la señal no es modificada."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        signal = Signal(
            symbol="EURUSD",
            signal_type=SignalType.BUY,
            confidence=0.75,
            connector_type="GENERIC",
            entry_price=1.0500,
            metadata={}
        )

        original_confidence = signal.confidence
        vetoed_signal = regime_service.apply_veto_to_signal(signal)

        # Sin veto, confianza no debe cambiar
        assert vetoed_signal.confidence == original_confidence


class TestLedgerSynchronization:
    """Tests de sincronización de ledger con almacenamiento."""

    def test_sync_ledger_persists_context(self, regime_service, mock_storage, sample_ohlc_data):
        """_sync_ledger debe persistir el contexto fractal en storage."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        regime_service._sync_ledger()

        # Verificar que set_sys_config fue llamado
        mock_storage.set_sys_config.assert_called()
        call_args = mock_storage.set_sys_config.call_args
        assert call_args[1]["key"] == "regime_fractal_ledger"
        assert "m15_regime" in call_args[1]["value"]
        assert "h4_regime" in call_args[1]["value"]
        assert "veto_signal" in call_args[1]["value"]

    def test_sync_ledger_on_update_regime_data(
        self, regime_service, mock_storage, sample_ohlc_data
    ):
        """update_regime_data debe sincronizar ledger (HANDSHAKE compliance)."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        mock_storage.reset_mock()

        # Actualizar datos
        regime_service.update_regime_data(
            m15_close=1.0505,
            h1_close=1.0505,
            h4_close=1.0505
        )

        # Verificar que ledger fue sincronizado
        mock_storage.set_sys_config.assert_called_with(
            key="regime_fractal_ledger",
            value=mock_storage.set_sys_config.call_args[1]["value"]
        )


class TestAlignmentMetrics:
    """Tests de métricas de alineación para UI."""

    def test_get_alignment_metrics(self, regime_service, sample_ohlc_data):
        """Retorna métricas de alineación correctamente."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        metrics = regime_service.get_alignment_metrics()

        assert "m15_regime" in metrics
        assert "h1_regime" in metrics
        assert "h4_regime" in metrics
        assert "is_aligned" in metrics
        assert "alignment_score" in metrics
        assert "veto_signal" in metrics
        assert "confidence_threshold" in metrics
        assert "timestamp" in metrics

    def test_get_alignment_metrics_uninitialized(self, regime_service):
        """Retorna status UNINITIALIZED si no está inicializado."""
        metrics = regime_service.get_alignment_metrics()
        assert metrics["status"] == "UNINITIALIZED"


class TestGetVetoStatus:
    """Tests de estado de veto para control de flujo."""

    @patch("core_brain.regime.RegimeClassifier.classify")
    def test_get_veto_status_active(self, mock_classify, regime_service, sample_ohlc_data):
        """Retorna (True, veto_reason) cuando veto está activo."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        regime_service.m15_classifier.classify = MagicMock(return_value=MarketRegime.BULL)
        regime_service.h1_classifier.classify = MagicMock(return_value=MarketRegime.NORMAL)
        regime_service.h4_classifier.classify = MagicMock(return_value=MarketRegime.BEAR)

        is_vetoed, reason = regime_service.get_veto_status()

        assert is_vetoed is True
        assert reason == "RETRACEMENT_RISK"

    def test_get_veto_status_inactive(self, regime_service, sample_ohlc_data):
        """Retorna (False, None) cuando no hay veto."""
        regime_service.initialize_classifiers(
            m15_df=sample_ohlc_data,
            h1_df=sample_ohlc_data,
            h4_df=sample_ohlc_data
        )

        is_vetoed, reason = regime_service.get_veto_status()

        assert is_vetoed is False
        assert reason is None

    def test_get_veto_status_uninitialized(self, regime_service):
        """Retorna (False, None) si no está inicializado."""
        is_vetoed, reason = regime_service.get_veto_status()
        assert is_vetoed is False
        assert reason is None
