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
from datetime import datetime, timezone
from models.signal import Signal, SignalType, ConnectorType

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
    
    async def analyze(self, symbol: str, df: Any, regime: Optional[str] = None) -> Optional[Signal]:
        """
        Analiza para señales de extensión de sesión.
        
        Args:
            symbol: Par de trading
            df: DataFrame OHLCV
            regime: Régimen actual del mercado (TREND, RANGE, VOLATILE, SHOCK)
            
        Returns:
            Signal object si hay oportunidad, None en caso contrario
        """
        try:
            # Validación: DataFrame debe tener datos
            if df is None or df.empty:
                logger.warning(f"[{self.trace_id}] {symbol}: Empty DataFrame provided")
                return None
            
            # Obtener estado de sesión actual
            session_stats = self.session_state_detector.get_session_stats()
            current_session = session_stats.get("session", "CLOSED")
            is_overlap = session_stats.get("is_overlap", False)
            
            # Si no hay solapamiento, sin señal
            if not is_overlap:
                logger.debug(
                    f"[{self.trace_id}] {symbol}: No session overlap detected. Skipping."
                )
                return None
            
            # Obtener precios del DataFrame (SSOT)
            current_close = float(df['close'].iloc[-1])
            current_high = float(df['high'].iloc[-1])
            current_low = float(df['low'].iloc[-1])
            current_open = float(df['open'].iloc[-1])
            
            # Determinar dirección y parámetros
            direction = "BUY" if current_session != "ASIA" else "SELL"
            
            if direction == "BUY":
                entry_price = current_close
                stop_loss = current_low - 0.0005  # Bajo de la vela - buffer
                take_profit = current_close + (2 * (entry_price - stop_loss))  # 2:1 R:R
                signal_type = SignalType.BUY
            else:  # SELL
                entry_price = current_close
                stop_loss = current_high + 0.0005  # Alto de la vela + buffer
                take_profit = current_close - (2 * (stop_loss - entry_price))  # 2:1 R:R
                signal_type = SignalType.SELL
            
            signal = Signal(
                symbol=symbol,
                connector_type=ConnectorType.METATRADER5,
                signal_type=signal_type,
                entry_price=round(entry_price, 5),
                stop_loss=round(stop_loss, 5),
                take_profit=round(take_profit, 5),
                confidence=0.5,
                volume=0.01,
                timestamp=datetime.now(timezone.utc),
                strategy_id="SESS_EXT_0001",
                trace_id=self.trace_id,
                metadata={
                    "session": current_session,
                    "is_overlap": is_overlap,
                    "reason": "session_overlap_detected",
                    "direction": direction,
                    "regime": regime,
                }
            )
            
            logger.info(
                f"[{self.trace_id}] {symbol}: Session overlap detected. "
                f"Signal={direction} @ {entry_price:.5f} | SL={stop_loss:.5f} | TP={take_profit:.5f}"
            )
            
            return signal
            
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error analyzing {symbol}: {e}", exc_info=True)
            return None
    
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
