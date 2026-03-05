"""
Session Extension 0001 Strategy (SESS_EXT_0001)
===============================================

Detecta extensiones de sesión ofreciendo oportunidades de continuación.

Responsabilidades:
1. Detectar elongación de sesiones (especialmente NY late)
2. Identificar patrones de continuación después de cierre
3. Usar session_state_detector para timing
4. Señalizar oportunidades de follow-through

TRACE_ID: STRAT-SESS-EXT-0001
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SessionExtension0001Strategy:
    """
    Estrategia de extensión de sesión.
    
    Oportunidades que surgen cuando una sesión se extiende más allá de su cierre
    típico, especialmente útil para New York late o transiciones verso asiática.
    """
    
    def __init__(self, storage_manager: Any, session_state_detector: Any):
        """
        Inicializa SessionExtension0001Strategy.
        
        Args:
            storage_manager: StorageManager para persistencia
            session_state_detector: SessionStateDetector para máquina de estados
        """
        self.storage_manager = storage_manager
        self.session_state_detector = session_state_detector
        self.trace_id = "STRAT-SESS-EXT-0001"
        logger.info(f"[{self.trace_id}] SessionExtension0001Strategy initialized")
    
    def analyze(self, symbol: str, df: Any) -> Dict[str, Any]:
        """
        Analiza para señales de extensión de sesión.
        
        Args:
            symbol: Par de trading
            df: DataFrame OHLCV
            
        Returns:
            Dict con análisis: signal, direction, confidence, reason
        """
        try:
            # Obtener estado de sesión actual
            session_stats = self.session_state_detector.get_session_stats()
            current_session = session_stats.get("session", "CLOSED")
            is_overlap = session_stats.get("is_overlap", False)
            
            # Signal por defecto: sin señal
            signal = {
                "symbol": symbol,
                "direction": None,
                "confidence": 0.0,
                "reason": "session_extension_analyze",
                "session": current_session,
                "is_overlap": is_overlap,
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self.trace_id,
            }
            
            # Si hay solapamiento, hay más volatilidad (oportunidad)
            if is_overlap:
                signal.update({
                    "confidence": 0.5,
                    "reason": "session_overlap_detected",
                })
            
            logger.debug(
                f"[{self.trace_id}] {symbol}: Session={current_session}, "
                f"Overlap={is_overlap}, Signal confidence={signal['confidence']}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error analyzing {symbol}: {e}")
            return {
                "symbol": symbol,
                "direction": None,
                "confidence": 0.0,
                "reason": f"error: {str(e)}",
                "timestamp": datetime.utcnow().isoformat(),
            }
    
    def get_metadata(self) -> Dict[str, Any]:
        """Retorna metadatos de la estrategia."""
        return {
            "name": "Session Extension 0001",
            "description": "Detecta elongaciones de sesión para oportunidades de continuación",
            "type": "PYTHON_CLASS",
            "sensors_required": ["session_state_detector"],
            "timeframes": ["M5", "M15", "H1"],
            "trace_id": self.trace_id,
        }
