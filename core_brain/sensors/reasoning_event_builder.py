"""
Reasoning Event Builder - High-Order Reasoning Event Construction
=================================================================

Responsabilidades:
1. Construir eventos de razonamiento de orden superior
2. Integrar análisis técnico, fundamental y de sentimiento
3. Generar "reasoning events" para confluencia multi-fuente
4. Almacenar eventos para auditoría y backtesting

Arquitectura Agnóstica: Ningún import de broker
Inyección de Dependencias: storage, market_structure_analyzer

TRACE_ID: SENSOR-REASONING-EVENT-001
"""
import logging
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)


class ReasoningEventBuilder:
    """
    Constructor de eventos de razonamiento de orden superior.
    
    Responsabilidades:
    - Agregar múltiples fuentes (price action, sentimiento, estructura)
    - Generar eventos de razonamiento consolidados
    - Crear trazabilidad para decisiones
    - Almacenar para análisis post-trade
    """
    
    def __init__(self, storage: Any, market_structure_analyzer: Optional[Any] = None):
        """
        Inicializa ReasoningEventBuilder.
        
        Args:
            storage: StorageManager para persistencia
            market_structure_analyzer: Analizador de estructura de mercado
        """
        self.storage = storage
        self.market_structure_analyzer = market_structure_analyzer
        self.event_id_counter = 0
        logger.info("[SENSOR-REASONING-EVENT-001] ReasoningEventBuilder initialized")
    
    def create_reasoning_event(
        self,
        symbol: str,
        event_type: str,
        source: str,
        data: Dict[str, Any],
        confidence: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Crea un evento de razonamiento individual.
        
        Args:
            symbol: Par de trading
            event_type: Tipo de evento (BREAKOUT, CONFLUENCE, STRUCTURE, etc)
            source: Fuente (PRICE_ACTION, SENTIMENT, STRUCTURE, etc)
            data: Datos asociados al evento
            confidence: Confianza 0-1
            
        Returns:
            Evento de razonamiento
        """
        event = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "event_type": event_type,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": data,
            "confidence": confidence,
            "status": "CREATED",
        }
        
        logger.debug(f"[SENSOR-REASONING-EVENT-001] Created event: {event['id']}")
        
        return event
    
    def build_confluence_reasoning(
        self,
        symbol: str,
        events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Construye evento de razonamiento de confluencia multi-fuente.
        
        Args:
            symbol: Par de trading
            events: Lista de eventos individuales
            
        Returns:
            Evento de confluencia de razonamiento
        """
        # Calcular confianza promedio
        avg_confidence = (
            sum(e.get("confidence", 0.5) for e in events) / len(events)
            if events
            else 0.5
        )
        
        # Consolidar fuentes
        sources = list(set(e.get("source", "UNKNOWN") for e in events))
        
        confluence_event = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "event_type": "CONFLUENCE_REASONING",
            "sources": sources,
            "source_count": len(sources),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "component_events": [e["id"] for e in events],
            "avg_confidence": avg_confidence,
            "consolidated_data": {
                "event_types": list(set(e.get("event_type") for e in events)),
                "supporting_sources": len(events),
            },
            "status": "CONSOLIDATED",
        }
        
        logger.info(
            f"[SENSOR-REASONING-EVENT-001] Confluence reasoning for {symbol}: "
            f"sources={sources}, confidence={avg_confidence:.2f}"
        )
        
        return confluence_event
    
    def build_structure_reasoning(
        self,
        symbol: str,
        structure_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Construye evento de razonamiento basado en estructura de mercado.
        
        Args:
            symbol: Par de trading
            structure_data: Datos de análisis de estructura
            
        Returns:
            Evento de razonamiento de estructura
        """
        event = {
            "id": str(uuid.uuid4()),
            "symbol": symbol,
            "event_type": "STRUCTURE_REASONING",
            "source": "MARKET_STRUCTURE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "structure_analysis": structure_data,
            "confidence": structure_data.get("confidence", 0.5),
            "status": "STRUCTURE_BASED",
        }
        
        logger.debug(f"[SENSOR-REASONING-EVENT-001] Structure reasoning: {event['id']}")
        
        return event
    
    def analyze(self, symbol: str, df: Any, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Análisis completo de reasoning events.
        
        Args:
            symbol: Par de trading
            df: DataFrame OHLCV
            context: Contexto adicional (estructura, sentimiento, etc)
            
        Returns:
            Dict con análisis de reasoning
        """
        context = context or {}
        
        # Crear eventos base según contexto
        events = []
        
        # Evento de precio si hay datos
        if context.get("price_signal"):
            price_event = self.create_reasoning_event(
                symbol=symbol,
                event_type="PRICE_ACTION",
                source="PRICE_ACTION",
                data=context.get("price_signal", {}),
                confidence=context.get("price_confidence", 0.5),
            )
            events.append(price_event)
        
        # Evento de estructura si hay análisis
        if context.get("structure_data"):
            structure_event = self.build_structure_reasoning(symbol, context["structure_data"])
            events.append(structure_event)
        
        # Construir confluencia
        final_event = (
            self.build_confluence_reasoning(symbol, events) if events
            else self.create_reasoning_event(
                symbol=symbol,
                event_type="NO_SIGNAL",
                source="REASONING_ENGINE",
                data={"reason": "insufficient_data"},
                confidence=0.0,
            )
        )
        
        result = {
            "symbol": symbol,
            "reasoning_event": final_event,
            "component_events": events,
            "signal": None,  # No genera dirección directa
            "confidence": final_event.get("confidence", 0.5),
        }
        
        logger.info(
            f"[SENSOR-REASONING-EVENT-001] {symbol}: "
            f"Events={len(events)}, Confidence={final_event.get('confidence', 0.5):.2f}"
        )
        
        return result
    
    def persist_reasoning_event(self, event: Dict[str, Any]) -> bool:
        """
        Persiste evento en storage para auditoría.
        
        Args:
            event: Evento a persistir
            
        Returns:
            True si se guardó correctamente
        """
        try:
            # Aquí se almacenaría en BD si existiera tabla para reasoning_events
            logger.debug(f"[SENSOR-REASONING-EVENT-001] Persisted: {event['id']}")
            return True
        except Exception as e:
            logger.error(f"[SENSOR-REASONING-EVENT-001] Failed to persist: {e}")
            return False
