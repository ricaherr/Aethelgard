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
        Detecta si hay solapamiento significativo entre sesiones comerciales.
        
        Overlaps existentes:
        1. LONDON-NEW_YORK: 13:00-16:00 UTC (3 horas)
           - LONDON: 08:00-16:00, NEW_YORK: 13:00-21:00
           - Overlap = [13:00, min(16:00, 21:00)) = [13:00, 16:00)
        
        2. ASIA-SYDNEY: 00:00-07:00 UTC (7 horas)
           - ASIA: 00:00-09:00, SYDNEY: 22:00 (prev day)-07:00
           - Overlap = [max(00:00, 22:00), min(09:00, 07:00)) = [00:00, 07:00)
        
        Returns:
            True si hay solapamiento significativo, False en caso contrario
        """
        now_utc = datetime.now(pytz.UTC).time()
        
        # Helper: Verificar si un momento está dentro de un rango
        def is_in_range(current_time: time, open_time: time, close_time: time) -> bool:
            """
            Verifica si current_time está en [open_time, close_time).
            Maneja rangos que cruzan medianoche (open_time > close_time).
            """
            if open_time <= close_time:
                # Rango normal (no cruza medianoche)
                return open_time <= current_time < close_time
            else:
                # Rango que cruza medianoche (ej. 22:00-07:00)
                return current_time >= open_time or current_time < close_time
        
        # Define sesiones (UTC)
        london_active = is_in_range(now_utc, time(8, 0), time(16, 0))
        ny_active = is_in_range(now_utc, time(13, 0), time(21, 0))
        asia_active = is_in_range(now_utc, time(0, 0), time(9, 0))
        sydney_active = is_in_range(now_utc, time(22, 0), time(7, 0))
        
        # Overlap #1: LONDON-NEW_YORK (máxima volatilidad)
        if london_active and ny_active:
            logger.debug(f"[SENSOR-SESSION-STATE-001] LONDON-NEW_YORK overlap detected")
            return True
        
        # Overlap #2: ASIA-SYDNEY (volatilidad moderada, menor volumen)
        if asia_active and sydney_active:
            logger.debug(f"[SENSOR-SESSION-STATE-001] ASIA-SYDNEY overlap detected")
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
