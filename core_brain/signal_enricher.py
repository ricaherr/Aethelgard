"""
Signal Enricher - Enriquecimiento de Señales con Metadata
==========================================================

Responsabilidad única: Agregar metadata contextual a señales para UI y auditoría.

Enriquece con:
1. Affinity Scores (histórico de performance)
2. Fundamental Guard Veto (noticias macro)
3. Reasoning detallado (por qué fue aprobada/rechazada)
4. WebSocket Payload (para UI real-time)
"""
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from models.signal import Signal
from data_vault.storage import StorageManager
from core_brain.services.fundamental_guard import FundamentalGuardService

logger = logging.getLogger(__name__)


class SignalEnricher:
    """
    Enriquece señales con metadata contextual para UI y auditoría.
    
    Responsabilidades:
    1. Extraer affinity scores de StorageManager
    2. Consultar FundamentalGuardService para veto por noticias
    3. Construir reasoning detallado
    4. Crear WebSocket payload para UI real-time feed
    """
    
    def __init__(
        self,
        storage_manager: StorageManager,
        fundamental_guard: Optional[FundamentalGuardService] = None
    ):
        """
        Inicializa el enriquecedor con dependencias.
        
        Args:
            storage_manager: Para extraer affinity scores
            fundamental_guard: Para consultar veto por noticias (opcional)
        """
        self.storage_manager = storage_manager
        self.fundamental_guard = fundamental_guard
    
    async def enrich(self, signal: Signal, symbol: str, strategy_id: str) -> None:
        """
        Enriquece la señal con metadata completa.
        
        Args:
            signal: Señal a enriquecer (modifica in-place)
            symbol: Símbolo del activo
            strategy_id: ID de la estrategia (stateless design)
        
        Returns:
            None (modifica signal.metadata in-place)
        """
        try:
            # ── 1. Extraer Affinity Score ────────────────────────────────────
            affinity_score = self._get_affinity_score(strategy_id, symbol)
            signal.metadata["affinity_score"] = affinity_score
            signal.metadata["strategy_id"] = strategy_id  # Explicit traceability

            # ── 2. Consultar FundamentalGuardService ─────────────────────────
            fundamental_safe, fundamental_reason = self._check_fundamental_guard(symbol)
            signal.metadata["fundamental_safe"] = fundamental_safe
            signal.metadata["fundamental_reason"] = fundamental_reason

            # ── 3. Construir Reasoning ───────────────────────────────────────
            reasoning = self._build_reasoning(
                strategy_id, 
                affinity_score, 
                signal.confidence,
                fundamental_safe,
                fundamental_reason
            )
            signal.metadata["reasoning"] = reasoning

            # ── 4. Crear WebSocket Payload ───────────────────────────────────
            websocket_payload = self._build_websocket_payload(
                signal, symbol, strategy_id, affinity_score, 
                fundamental_safe, fundamental_reason, reasoning
            )
            signal.metadata["websocket_payload"] = websocket_payload

            logger.debug(
                f"[{symbol}] Signal enriched: "
                f"affinity={affinity_score:.2f}, fundamental_safe={fundamental_safe}"
            )

        except Exception as e:
            logger.error(f"[{symbol}] Error enriching signal metadata: {e}", exc_info=True)
            # Fallback: ensure minimal metadata
            self._set_fallback_metadata(signal)
    
    def _get_affinity_score(self, strategy_id: str, symbol: str) -> float:
        """
        Extrae affinity score para (strategy_id, symbol).
        
        Fallback: 0.5 si no disponible.
        
        Args:
            strategy_id: ID de la estrategia
            symbol: Símbolo del activo
        
        Returns:
            float entre 0 y 1
        """
        try:
            strategy_scores = self.storage_manager.get_strategy_affinity_scores()
            if strategy_scores and strategy_id in strategy_scores:
                affinity_by_symbol = strategy_scores[strategy_id]
                if isinstance(affinity_by_symbol, dict) and symbol in affinity_by_symbol:
                    return float(affinity_by_symbol[symbol])
        except Exception as e:
            logger.debug(f"[{symbol}] Failed to get affinity score: {e}")
        
        return 0.5  # Default
    
    def _check_fundamental_guard(self, symbol: str) -> tuple[bool, str]:
        """
        Verifica FundamentalGuardService para veto por noticias.
        
        Args:
            symbol: Símbolo del activo
        
        Returns:
            Tuple (is_safe: bool, reason: str)
        """
        if not self.fundamental_guard:
            return True, ""
        
        try:
            is_safe, reason = self.fundamental_guard.is_market_safe(symbol)
            if not is_safe:
                logger.warning(
                    f"[{symbol}] Signal vetoed by FundamentalGuard: {reason}"
                )
            return is_safe, reason
        except Exception as e:
            logger.warning(f"[{symbol}] FundamentalGuard check failed: {e}")
            return True, ""  # Fallback: assume safe
    
    @staticmethod
    def _build_reasoning(
        strategy_id: str,
        affinity_score: float,
        confidence: float,
        fundamental_safe: bool,
        fundamental_reason: str
    ) -> str:
        """
        Construye reasoning string para UI.
        
        Ejemplo: "Strategy: BRK_OPEN_0001 | Affinity: 0.92 | Confidence: 0.85 | ✅ No fundamental restrictions"
        """
        parts = [
            f"Strategy: {strategy_id}",
            f"Affinity: {affinity_score:.2f}",
            f"Confidence: {confidence:.2f}",
        ]
        
        if not fundamental_safe:
            parts.append(f"❌ Fundamental Veto: {fundamental_reason}")
        else:
            if fundamental_reason:
                parts.append(f"⚠️ {fundamental_reason}")
            else:
                parts.append("✅ No fundamental restrictions")
        
        return " | ".join(parts)
    
    @staticmethod
    def _build_websocket_payload(
        signal: Signal,
        symbol: str,
        strategy_id: str,
        affinity_score: float,
        fundamental_safe: bool,
        fundamental_reason: str,
        reasoning: str
    ) -> Dict[str, Any]:
        """
        Crea payload estructurado para envío a UI via WebSocket.
        """
        signal_type_value = (
            signal.signal_type.value 
            if hasattr(signal.signal_type, 'value') 
            else str(signal.signal_type)
        )
        
        return {
            "symbol": symbol,
            "signal_type": signal_type_value,
            "timeframe": signal.timeframe or "M5",
            "confidence": signal.confidence,
            "affinity_score": affinity_score,
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "fundamental_safe": fundamental_safe,
            "fundamental_reason": fundamental_reason,
            "reasoning": reasoning,
            "strategy_id": strategy_id,
            "timestamp": signal.timestamp.isoformat() if signal.timestamp else datetime.utcnow().isoformat(),
            "status": "APPROVED" if fundamental_safe else "VETOED",
        }
    
    @staticmethod
    def _set_fallback_metadata(signal: Signal) -> None:
        """
        Asegura que signal.metadata tenga valores mínimos válidos.
        """
        signal.metadata.setdefault("affinity_score", 0.5)
        signal.metadata.setdefault("fundamental_safe", True)
        signal.metadata.setdefault("fundamental_reason", "")
        signal.metadata.setdefault("reasoning", "Enriquecimiento fallido (fallback mode)")
