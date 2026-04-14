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
from datetime import datetime, timezone

from core_brain.services.market_session_service import MarketSessionService

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
    
    SESSION_PRIORITY = ["london", "ny", "tokyo", "sydney"]
    SESSION_LABELS = {
        "london": "LONDON",
        "ny": "NEW_YORK",
        "tokyo": "ASIA",
        "sydney": "SYDNEY",
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
        self.market_session_service = MarketSessionService(storage=storage)
        self.current_session = None
        self.session_start_time = None
        logger.info("[SENSOR-SESSION-STATE-001] SessionStateDetector initialized")

    def _resolve_utc_time(self, utc_time: Optional[datetime]) -> datetime:
        """Obtiene el instante UTC a evaluar, usando reloj real si no se inyecta."""
        if utc_time is None:
            return datetime.now(timezone.utc)
        if utc_time.tzinfo is None:
            return utc_time.replace(tzinfo=timezone.utc)
        return utc_time.astimezone(timezone.utc)

    def _get_active_sessions(self, utc_time: Optional[datetime] = None) -> Dict[str, bool]:
        """Retorna snapshot de sesiones activas usando la fuente canónica unificada."""
        resolved_utc_time = self._resolve_utc_time(utc_time)
        active_sessions = set(
            self.market_session_service.get_active_sessions_utc(resolved_utc_time)
        )

        return {
            session_name: session_name in active_sessions
            for session_name in self.SESSION_LABELS.keys()
        }
    
    def detect_current_session(self, utc_time: Optional[datetime] = None) -> str:
        """
        Detecta la sesión actual basada en horas UTC.
        
        Returns:
            Nombre de la sesión: "LONDON", "NEW_YORK", "ASIA", "SYDNEY"
        """
        active_sessions = self._get_active_sessions(utc_time)

        for session_name in self.SESSION_PRIORITY:
            if active_sessions.get(session_name):
                return self.SESSION_LABELS[session_name]

        return "CLOSED"
    
    def is_session_overlap(self, utc_time: Optional[datetime] = None) -> bool:
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
        active_sessions = self._get_active_sessions(utc_time)
        london_active = active_sessions.get("london", False)
        ny_active = active_sessions.get("ny", False)
        asia_active = active_sessions.get("tokyo", False)
        sydney_active = active_sessions.get("sydney", False)
        
        # Overlap #1: LONDON-NEW_YORK (máxima volatilidad)
        if london_active and ny_active:
            logger.debug(f"[SENSOR-SESSION-STATE-001] LONDON-NEW_YORK overlap detected")
            return True
        
        # Overlap #2: ASIA-SYDNEY (volatilidad moderada, menor volumen)
        if asia_active and sydney_active:
            logger.debug(f"[SENSOR-SESSION-STATE-001] ASIA-SYDNEY overlap detected")
            return True
        
        return False
    
    def get_session_volatility(
        self, session: Optional[str] = None, utc_time: Optional[datetime] = None
    ) -> int:
        """
        Retorna volatilidad esperada para sesión.
        
        Args:
            session: Nombre de sesión (auto-detecta si es None)
            
        Returns:
            Volatilidad en escala 0-100
        """
        if session is None:
            session = self.detect_current_session(utc_time=utc_time)
        
        return self.SESSION_VOLATILITY.get(session, 50)
    
    def get_session_stats(self, utc_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Retorna estadísticas de sesión actual.
        
        Returns:
            Dict con session, is_overlap, volatility
        """
        resolved_utc_time = self._resolve_utc_time(utc_time)
        session = self.detect_current_session(utc_time=resolved_utc_time)
        is_overlap = self.is_session_overlap(utc_time=resolved_utc_time)
        volatility = self.get_session_volatility(session, utc_time=resolved_utc_time)
        
        return {
            "session": session,
            "is_overlap": is_overlap,
            "volatility": volatility,
            "timestamp": resolved_utc_time.isoformat(),
        }
    
    def analyze(
        self, symbol: str, df: Any, utc_time: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Análisis completo de estado de sesión.
        
        Args:
            symbol: Par de trading
            df: DataFrame OHLCV
            
        Returns:
            Dict con análisis de sesión
        """
        resolved_utc_time = self._resolve_utc_time(utc_time)
        current_session = self.detect_current_session(utc_time=resolved_utc_time)
        is_overlap = self.is_session_overlap(utc_time=resolved_utc_time)
        volatility = self.get_session_volatility(
            current_session, utc_time=resolved_utc_time
        )
        
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
