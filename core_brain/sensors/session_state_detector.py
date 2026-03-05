"""
Session State Detector - Market Session Identification
=====================================================

Responsabilidades:
1. Detectar sesión activa (London, New York, Asia, Sydney)
2. Detectar transiciones de sesión
3. Analizar volatilidad de sesión
4. Registrar estadísticas de sesión

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage

TRACE_ID: SENSOR-SESSION-STATE-001
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime, time
import pytz

logger = logging.getLogger(__name__)


class SessionStateDetector:
    """
    Detector de estado de sesión de mercado.
    
    Responsabilidades:
    - Identificar sesión actual (London, New York, Asia, Sydney)
    - Detectar solapamiento de sesiones
    - Registrar cambios de sesión
    - Analizar volatilidad esperada por sesión
    """
    
    # Horarios de sesiones (UTC)
    SESSIONS = {
        "LONDON": {"open": time(8, 0), "close": time(16, 0)},
        "NEW_YORK": {"open": time(13, 0), "close": time(21, 0)},
        "ASIA": {"open": time(0, 0), "close": time(9, 0)},
        "SYDNEY": {"open": time(22, 0), "close": time(7, 0)},  # Cruza medianoche
    }
    
    # Volatilidad relativa por sesión (escala 0-100)
    SESSION_VOLATILITY = {
        "LONDON": 75,
        "NEW_YORK": 80,
        "ASIA": 40,
        "SYDNEY": 45,
    }
    
    def __init__(self, storage: Any):
        """
        Inicializa SessionStateDetector con almacenamiento.
        
        Args:
            storage: StorageManager para persistencia
        """
        self.storage = storage
        self.current_session = None
        self.session_start_time = None
        logger.info("[SENSOR-SESSION-STATE-001] SessionStateDetector initialized")
    
    def detect_current_session(self) -> str:
        """
        Detecta la sesión actual basada en horas UTC.
        
        Returns:
            Nombre de la sesión: "LONDON", "NEW_YORK", "ASIA", "SYDNEY"
        """
        now_utc = datetime.now(pytz.UTC).time()
        
        # Verificar LONDON
        london_open = time(8, 0)
        london_close = time(16, 0)
        if london_open <= now_utc < london_close:
            return "LONDON"
        
        # Verificar NEW_YORK
        ny_open = time(13, 0)
        ny_close = time(21, 0)
        if ny_open <= now_utc < ny_close:
            return "NEW_YORK"
        
        # Verificar ASIA (0:00 - 9:00 UTC)
        asia_open = time(0, 0)
        asia_close = time(9, 0)
        if asia_open <= now_utc < asia_close:
            return "ASIA"
        
        # SYDNEY (22:00 - 7:00 cruza medianoche)
        sydney_open = time(22, 0)
        if now_utc >= sydney_open or now_utc < time(7, 0):
            return "SYDNEY"
        
        # Default: ASIA (mercados cerrados)
        return "CLOSED"
    
    def is_session_overlap(self) -> bool:
        """
        Detecta si hay solapamiento entre sesiones.
        
        Returns:
            True si hay solapamiento significativo
        """
        now_utc = datetime.now(pytz.UTC).time()
        
        # Solapamientos principales:
        # LONDON-NEWYORK: 13:00-16:00 UTC
        if time(13, 0) <= now_utc < time(16, 0):
            return True
        
        # ASIA-SYDNEY: 22:00-9:00 (cruza medianoche)
        if now_utc >= time(22, 0) or now_utc < time(9, 0):
            # Solo si no es LONDON
            if now_utc < time(8, 0):
                return True
        
        return False
    
    def get_session_volatility(self, session: Optional[str] = None) -> int:
        """
        Retorna volatilidad esperada para sesión.
        
        Args:
            session: Nombre de sesión (auto-detecta si es None)
            
        Returns:
            Volatilidad en escala 0-100
        """
        if session is None:
            session = self.detect_current_session()
        
        return self.SESSION_VOLATILITY.get(session, 50)
    
    def get_session_stats(self) -> Dict[str, Any]:
        """
        Retorna estadísticas de sesión actual.
        
        Returns:
            Dict con session, is_overlap, volatility
        """
        session = self.detect_current_session()
        is_overlap = self.is_session_overlap()
        volatility = self.get_session_volatility(session)
        
        return {
            "session": session,
            "is_overlap": is_overlap,
            "volatility": volatility,
            "timestamp": datetime.now(pytz.UTC).isoformat(),
        }
    
    def analyze(self, symbol: str, df: Any) -> Dict[str, Any]:
        """
        Análisis completo de estado de sesión.
        
        Args:
            symbol: Par de trading
            df: DataFrame OHLCV
            
        Returns:
            Dict con análisis de sesión
        """
        current_session = self.detect_current_session()
        is_overlap = self.is_session_overlap()
        volatility = self.get_session_volatility(current_session)
        
        result = {
            "symbol": symbol,
            "session": current_session,
            "is_overlap": is_overlap,
            "volatility": volatility,
            "signal": None,  # No genera dirección de trade directo
            "confidence": 0.5,
        }
        
        logger.info(
            f"[SENSOR-SESSION-STATE-001] {symbol}: "
            f"Session={current_session}, Overlap={is_overlap}, Vol={volatility}"
        )
        
        return result
