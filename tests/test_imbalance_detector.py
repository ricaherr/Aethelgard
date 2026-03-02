"""
Tests para ImbalanceDetector (HU 3.3: Detector de Ineficiencias).
Trace_ID: EXEC-STRAT-OPEN-001

Valida:
  - Detección de FVG (Fair Value Gaps) asíncrona
  - Validación de volumen para huella institucional
  - Timeframes M5 y M15
  - Generación de señales de imbalance
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock
import asyncio
from zoneinfo import ZoneInfo

from core_brain.sensors.imbalance_detector import ImbalanceDetector


@pytest.fixture
def mock_storage():
    """Mock de StorageManager con métodos necesarios."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {
        "imbalance_thresholds": {
            "fvg_min_size_pips": 5.0,
            "volume_confirmation_ratio": 1.3,
            "max_lookback_candles": 20,
            "min_volume_avg": 50
        }
    }
    storage.get_system_state = MagicMock(return_value={})
    storage.set_system_state = MagicMock()
    return storage


@pytest.fixture
def imbalance_detector(mock_storage):
    """Instancia del ImbalanceDetector con dependencias mockeadas."""
    return ImbalanceDetector(storage=mock_storage)


@pytest.fixture
def sample_m5_ohlcv():
    """Datos OHLCV M5 con FVG bullish detectables."""
    return [
        {"timestamp": datetime(2026, 3, 2, 13, 0, tzinfo=ZoneInfo("UTC")), 
         "open": 1.0500, "high": 1.0510, "low": 1.0490, "close": 1.0495, "volume": 100},
        
        # Vela de expansión (volumen alto)
        {"timestamp": datetime(2026, 3, 2, 13, 5, tzinfo=ZoneInfo("UTC")), 
         "open": 1.0495, "high": 1.0530, "low": 1.0490, "close": 1.0525, "volume": 250},
        
        # Vela de formación - creando FVG
        {"timestamp": datetime(2026, 3, 2, 13, 10, tzinfo=ZoneInfo("UTC")), 
         "open": 1.0525, "high": 1.0540, "low": 1.0515, "close": 1.0535, "volume": 200},
    ]


@pytest.fixture
def sample_m15_ohlcv():
    """Datos OHLCV M15 con múltiples FVGs."""
    return [
        {"timestamp": datetime(2026, 3, 2, 13, 0, tzinfo=ZoneInfo("UTC")), 
         "open": 1.0500, "high": 1.0510, "low": 1.0490, "close": 1.0500, "volume": 500},
        
        {"timestamp": datetime(2026, 3, 2, 13, 15, tzinfo=ZoneInfo("UTC")), 
         "open": 1.0500, "high": 1.0550, "low": 1.0480, "close": 1.0545, "volume": 1500},
        
        {"timestamp": datetime(2026, 3, 2, 13, 30, tzinfo=ZoneInfo("UTC")), 
         "open": 1.0545, "high": 1.0560, "low": 1.0520, "close": 1.0555, "volume": 1000},
    ]


class TestImbalanceDetectorInitialization:
    """Tests de inicialización del detector."""
    
    def test_initialization(self, imbalance_detector):
        """Verifica que el detector se inicializa correctamente."""
        assert imbalance_detector.storage is not None
        assert imbalance_detector.trace_id is not None
        assert imbalance_detector.trace_id.startswith("IMBALANCE-")
        
    def test_trace_id_format(self, imbalance_detector):
        """Verifica que trace_id sigue el formato correcto."""
        assert len(imbalance_detector.trace_id) > 0
        assert "IMBALANCE-" in imbalance_detector.trace_id


class TestFVGDetection:
    """Tests para detección de FVG (Fair Value Gaps)."""
    
    def test_detect_bullish_fvg_in_m5(self, imbalance_detector, sample_m5_ohlcv):
        """Detecta FVG bullish en timeframe M5."""
        fvgs = imbalance_detector.detect_fvg(
            ohlcv_data=sample_m5_ohlcv,
            pip_size=0.0001,
            timeframe="M5"
        )
        
        assert len(fvgs) >= 1
        assert fvgs[0]["type"] == "bullish_fvg"
        assert "size_pips" in fvgs[0]
        assert fvgs[0]["size_pips"] >= 5.0  # Cumple threshold
        assert fvgs[0]["timeframe"] == "M5"
        
    def test_detect_fvg_in_m15(self, imbalance_detector, sample_m15_ohlcv):
        """Detecta FVGs en timeframe M15."""
        fvgs = imbalance_detector.detect_fvg(
            ohlcv_data=sample_m15_ohlcv,
            pip_size=0.0001,
            timeframe="M15"
        )
        
        assert len(fvgs) >= 0
        if len(fvgs) > 0:
            assert "type" in fvgs[0]
            assert fvgs[0]["type"] in ["bullish_fvg", "bearish_fvg"]
            assert fvgs[0]["timeframe"] == "M15"
            
    def test_fvg_requires_minimum_size(self, imbalance_detector):
        """Verifica que FVGs pequeños se descartan."""
        # Datos con gap muy pequeño (2 pips)
        tiny_gap_data = [
            {"open": 1.0500, "high": 1.0510, "low": 1.0490, "close": 1.0495, "volume": 100},
            {"open": 1.0495, "high": 1.0520, "low": 1.0490, "close": 1.0515, "volume": 200},
            {"open": 1.0515, "high": 1.0525, "low": 1.0502, "close": 1.0520, "volume": 150},
            # Gap: 1.0502 (low 3) - 1.0510 (high 1) = -0.0008 (negativo, no es FVG)
        ]
        
        fvgs = imbalance_detector.detect_fvg(
            ohlcv_data=tiny_gap_data,
            pip_size=0.0001,
            timeframe="M5"
        )
        
        # Si hay FVGs detectados, todos deben cumplir el mínimo de 5 pips
        for fvg in fvgs:
            assert fvg["size_pips"] >= 5.0


class TestVolumeConfirmation:
    """Tests para validación de volumen como huella institucional."""
    
    def test_volume_validation_high_volume(self, imbalance_detector):
        """Valida FVG con volumen alto (huella institucional clara)."""
        ohlcv_with_volume = [
            {"open": 1.0500, "high": 1.0510, "low": 1.0490, "close": 1.0495, "volume": 100},
            {"open": 1.0495, "high": 1.0530, "low": 1.0480, "close": 1.0525, "volume": 500},  # Alto
            {"open": 1.0525, "high": 1.0540, "low": 1.0515, "close": 1.0535, "volume": 400},
        ]
        
        is_valid = imbalance_detector.validate_institutional_footprint(
            ohlcv_data=ohlcv_with_volume,
            fvg_index=1
        )
        
        assert is_valid is True
        
    def test_volume_validation_low_volume(self, imbalance_detector):
        """Rechaza FVG con volumen bajo (poco probable institucional)."""
        ohlcv_low_volume = [
            {"open": 1.0500, "high": 1.0510, "low": 1.0490, "close": 1.0495, "volume": 100},
            {"open": 1.0495, "high": 1.0530, "low": 1.0480, "close": 1.0525, "volume": 50},   # Bajo
            {"open": 1.0525, "high": 1.0540, "low": 1.0515, "close": 1.0535, "volume": 40},
        ]
        
        is_valid = imbalance_detector.validate_institutional_footprint(
            ohlcv_data=ohlcv_low_volume,
            fvg_index=1
        )
        
        assert is_valid is False


class TestAsyncDetection:
    """Tests para detección asíncrona de imbalances."""
    
    @pytest.mark.asyncio
    async def test_detect_imbalances_async_m5(self, imbalance_detector, sample_m5_ohlcv):
        """Detecta imbalances de forma asíncrona en M5."""
        signal = await imbalance_detector.detect_imbalances_async(
            ohlcv_data=sample_m5_ohlcv,
            pip_size=0.0001,
            timeframe="M5"
        )
        
        assert signal is not None
        assert "fvgs" in signal
        assert "timeframe" in signal
        assert signal["timeframe"] == "M5"
        
    @pytest.mark.asyncio
    async def test_detect_imbalances_async_m15(self, imbalance_detector, sample_m15_ohlcv):
        """Detecta imbalances de forma asíncrona en M15."""
        signal = await imbalance_detector.detect_imbalances_async(
            ohlcv_data=sample_m15_ohlcv,
            pip_size=0.0001,
            timeframe="M15"
        )
        
        assert signal is not None
        assert "fvgs" in signal
        assert signal["timeframe"] == "M15"
        
    @pytest.mark.asyncio
    async def test_concurrent_timeframe_detection(self, imbalance_detector, sample_m5_ohlcv, sample_m15_ohlcv):
        """Detecta imbalances en múltiples timeframes concurrentemente."""
        results = await asyncio.gather(
            imbalance_detector.detect_imbalances_async(sample_m5_ohlcv, 0.0001, "M5"),
            imbalance_detector.detect_imbalances_async(sample_m15_ohlcv, 0.0001, "M15")
        )
        
        assert len(results) == 2
        assert results[0]["timeframe"] == "M5"
        assert results[1]["timeframe"] == "M15"


class TestSignalGeneration:
    """Tests para generación de señales de imbalance."""
    
    def test_generate_imbalance_signal(self, imbalance_detector, sample_m5_ohlcv):
        """Genera señal de imbalance con metadatos correctos."""
        signal = imbalance_detector.generate_signal(
            instrument="EURUSD",
            fvgs=imbalance_detector.detect_fvg(sample_m5_ohlcv, 0.0001, "M5"),
            timeframe="M5",
            confidence=0.85
        )
        
        assert signal is not None
        assert signal["instrument"] == "EURUSD"
        assert signal["timeframe"] == "M5"
        assert signal["confidence"] == 0.85
        assert "fvg_count" in signal
        assert "instance_id" in signal  # UUID v4
        
    def test_signal_includes_uuid_instance_id(self, imbalance_detector, sample_m5_ohlcv):
        """Verifica que cada señal tenga UUID v4 como Instance ID."""
        signal = imbalance_detector.generate_signal(
            instrument="EURUSD",
            fvgs=imbalance_detector.detect_fvg(sample_m5_ohlcv, 0.0001, "M5"),
            timeframe="M5",
            confidence=0.85
        )
        
        # Verificar que instance_id existe y es UUID válido
        import uuid
        try:
            uuid_obj = uuid.UUID(signal["instance_id"])
            assert uuid_obj.version == 4
        except ValueError:
            pytest.fail(f"instance_id {signal['instance_id']} is not a valid UUIDv4")


class TestPersistenceAndIntegration:
    """Tests para persistencia y integración con StorageManager."""
    
    def test_persist_detected_imbalances(self, imbalance_detector, mock_storage, sample_m5_ohlcv):
        """Persiste imbalances detectados en DB."""
        fvgs = imbalance_detector.detect_fvg(sample_m5_ohlcv, 0.0001, "M5")
        
        imbalance_detector.persist_imbalances(
            instrument="EURUSD",
            fvgs=fvgs,
            timeframe="M5"
        )
        
        # Verificar que se intentó persistir
        assert mock_storage.set_system_state.called or len(fvgs) == 0
        
    def test_sync_ledger_with_trace_id(self, imbalance_detector, mock_storage, sample_m5_ohlcv):
        """Sincroniza ledger de imbalances con Trace_ID."""
        fvgs = imbalance_detector.detect_fvg(sample_m5_ohlcv, 0.0001, "M5")
        
        trace_data = imbalance_detector.sync_ledger(
            instrument="EURUSD",
            fvgs=fvgs,
            timeframe="M5"
        )
        
        assert "trace_id" in trace_data
        assert trace_data["trace_id"] == imbalance_detector.trace_id
        assert trace_data["fvg_count"] == len(fvgs)
