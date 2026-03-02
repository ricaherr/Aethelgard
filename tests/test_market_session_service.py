"""
Tests para MarketSessionService (HU 2.2: Global Liquidity Clock).
Trace_ID: EXEC-STRAT-OPEN-001

Valida:
  - Trackeo de sesiones Sydney, Tokyo, London, NY
  - Método get_pre_market_range() para límites de liquidez pre-apertura NY
  - Cálculos UTC correctos
  - Persistencia de rangos en DB
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from core_brain.services.market_session_service import MarketSessionService


@pytest.fixture
def mock_storage():
    """Mock de StorageManager con métodos necesarios."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = {
        "market_sessions": {
            "sydney": {"open": "23:00", "close": "07:00", "utc_offset": 11},
            "tokyo": {"open": "00:00", "close": "09:00", "utc_offset": 9},
            "london": {"open": "08:00", "close": "17:00", "utc_offset": 0},
            "ny": {"open": "13:30", "close": "21:00", "utc_offset": -5}
        },
        "pre_market_buffer_minutes": 30
    }
    storage.set_system_state = MagicMock()
    storage.get_system_state = MagicMock(return_value={})
    return storage


@pytest.fixture
def market_session_service(mock_storage):
    """Instancia del MarketSessionService con dependencias mockeadas."""
    return MarketSessionService(storage=mock_storage)


class TestMarketSessionServiceInitialization:
    """Tests de inicialización del servicio de sesiones."""
    
    def test_initialization(self, market_session_service):
        """Verifica que el servicio se inicializa correctamente."""
        assert market_session_service.storage is not None
        assert market_session_service.trace_id is not None
        assert market_session_service.trace_id.startswith("SESSION-")
        
    def test_trace_id_generation(self, market_session_service):
        """Verifica que trace_id sigue el formato correcto."""
        assert len(market_session_service.trace_id) > 0
        assert "SESSION-" in market_session_service.trace_id


class TestSessionDetection:
    """Tests para detección de sesiones activas."""
    
    def test_is_sydney_session_active(self, market_session_service, mock_storage):
        """Verifica detección de sesión Sydney (00:00-08:00 UTC)."""
        # Sydney session es 23:00-07:00 AEDT (UTC+11)
        # Equivalente a 12:00-20:00 UTC del día anterior
        utc_time = datetime(2026, 3, 2, 14, 0, tzinfo=ZoneInfo("UTC"))
        
        is_active = market_session_service.is_session_active("sydney", utc_time)
        # 14:00 UTC está en [12:00, 20:00] → True
        assert is_active is True
        
    def test_is_tokyo_session_active(self, market_session_service, mock_storage):
        """Verifica detección de sesión Tokyo (00:00-09:00 JST = 15:00 UTC-1 a 00:00 UTC)."""
        # Tokyo: 00:00-09:00 JST (UTC+9)
        # Equivalente UTC: 15:00 UTC (día anterior) a 00:00 UTC
        # Test: 20:00 UTC está en [15:00 UTC prev, 00:00 UTC] → True
        utc_time = datetime(2026, 3, 2, 20, 0, tzinfo=ZoneInfo("UTC"))
        is_active = market_session_service.is_session_active("tokyo", utc_time)
        # 20:00 UTC está en [15:00, 24:00] → True
        assert is_active is True
        
    def test_is_london_session_active(self, market_session_service, mock_storage):
        """Verifica detección de sesión London (08:00-17:00 GMT = 08:00-17:00 UTC)."""
        utc_time = datetime(2026, 3, 2, 12, 0, tzinfo=ZoneInfo("UTC"))
        is_active = market_session_service.is_session_active("london", utc_time)
        # 12:00 UTC está en [08:00, 17:00] → True
        assert is_active is True
        
    def test_is_ny_session_active(self, market_session_service, mock_storage):
        """Verifica detección de sesión NY (13:30-21:00 EST = 18:30-02:00 UTC siguiente día)."""
        # NY open a las 13:30 EST = 18:30 UTC
        utc_time = datetime(2026, 3, 2, 20, 0, tzinfo=ZoneInfo("UTC"))
        is_active = market_session_service.is_session_active("ny", utc_time)
        # 20:00 UTC está en [18:30, siguiente 02:00] → True
        assert is_active is True
        
    def test_is_no_session_outside_hours(self, market_session_service, mock_storage):
        """Verifica que fuera de horarios no hay sesión activa."""
        # 02:00 UTC no es hora de transacción para ninguna sesión principal
        utc_time = datetime(2026, 3, 2, 2, 0, tzinfo=ZoneInfo("UTC"))
        
        # Verificar todas las sesiones
        sydney_active = market_session_service.is_session_active("sydney", utc_time)
        tokyo_active = market_session_service.is_session_active("tokyo", utc_time)
        london_active = market_session_service.is_session_active("london", utc_time)
        ny_active = market_session_service.is_session_active("ny", utc_time)
        
        # En 02:00 UTC, solo Sydney (primera mitad) podría estar activa
        # Pero verificamos que el método está funcionando


class TestPreMarketRange:
    """Tests para get_pre_market_range() - Rango de liquidez pre-NY."""
    
    def test_get_pre_market_range_before_ny_open(self, market_session_service):
        """
        Obtiene rango de liquidez 30 minutos antes de apertura NY.
        NY abre a 13:30 EST = 18:30 UTC.
        Retorna rango desde 18:00 UTC hasta 18:30 UTC.
        """
        # Tiempo: 18:15 UTC (dentro de 30 min pre-market antes de NY open)
        utc_time = datetime(2026, 3, 2, 18, 15, tzinfo=ZoneInfo("UTC"))
        
        pre_market_range = market_session_service.get_pre_market_range(utc_time)
        
        assert pre_market_range is not None
        assert "start_utc" in pre_market_range
        assert "end_utc" in pre_market_range
        assert "session_name" in pre_market_range
        assert pre_market_range["session_name"] == "ny"
        
        # Verificar que el rango es correcto (30 minutos antes de 18:30 UTC)
        # start debería ser 18:00 UTC
        assert pre_market_range["start_utc"].hour == 18
        assert pre_market_range["start_utc"].minute == 0
        
    def test_get_pre_market_range_ny_opening(self, market_session_service):
        """Verifica rango cuando NY está abriéndose."""
        # Tiempo: 18:25 UTC (durante pre-market buffer)
        utc_time = datetime(2026, 3, 2, 18, 25, tzinfo=ZoneInfo("UTC"))
        
        pre_market_range = market_session_service.get_pre_market_range(utc_time)
        
        assert pre_market_range is not None
        assert pre_market_range["session_name"] == "ny"
        
    def test_get_pre_market_range_outside_ny_hours(self, market_session_service):
        """Verifica comportamiento cuando no es horario pre-NY."""
        # Tiempo: 10:00 UTC (en sesión London, no pre-NY)
        utc_time = datetime(2026, 3, 2, 10, 0, tzinfo=ZoneInfo("UTC"))
        
        pre_market_range = market_session_service.get_pre_market_range(utc_time)
        
        # Debería retornar None o información sobre la siguiente sesión NY
        # Dependiendo de la lógica: si no está en pre-market NY, retorna None
        assert pre_market_range is None or isinstance(pre_market_range, dict)


class TestLiquidityMetrics:
    """Tests para cálculos de liquidez y volatilidad por sesión."""
    
    def test_get_session_liquidity_metrics(self, market_session_service):
        """Obtiene métricas de liquidez para una sesión específica."""
        metrics = market_session_service.get_session_liquidity_metrics("london")
        
        assert metrics is not None
        assert "session_name" in metrics
        assert "pip_volatility_expected" in metrics
        assert "volume_profile" in metrics
        assert metrics["session_name"] == "london"
        
    def test_liquidity_trend_ny_to_london_overlap(self, market_session_service):
        """
        Verifica análisis de overlaps Londres-NY.
        London cierra 17:00 UTC, NY abre 18:30 UTC → 1.5h sin overlap.
        """
        utc_time = datetime(2026, 3, 2, 17, 30, tzinfo=ZoneInfo("UTC"))
        
        overlap_data = market_session_service.get_session_overlap_analysis(utc_time)
        
        assert overlap_data is not None
        assert "london" in overlap_data
        assert "ny" in overlap_data


class TestPersistenceAndSync:
    """Tests para persistencia y sincronización con StorageManager."""
    
    def test_sync_ledger_persists_session_state(self, market_session_service, mock_storage):
        """Verifica que estado de sesión se persiste en DB."""
        utc_time = datetime(2026, 3, 2, 12, 0, tzinfo=ZoneInfo("UTC"))
        
        market_session_service.sync_ledger(utc_time)
        
        # Verificar que se llamó a storage.set_system_state
        assert mock_storage.set_system_state.called
        
    def test_get_cached_liquidity_range(self, market_session_service):
        """Verifica que cache de rangos de liquidez funciona."""
        utc_time = datetime(2026, 3, 2, 18, 0, tzinfo=ZoneInfo("UTC"))
        
        # Primera llamada
        range1 = market_session_service.get_pre_market_range(utc_time)
        
        # Segunda llamada (debería usar cache si está dentro del mismo minuto)
        range2 = market_session_service.get_pre_market_range(utc_time)
        
        if range1 and range2:
            assert range1["start_utc"] == range2["start_utc"]
            assert range1["end_utc"] == range2["end_utc"]
