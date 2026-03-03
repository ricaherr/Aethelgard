"""
Reasoning Event Builder - Construye events de razonamiento estratégico

Responsabilidad: Formatear y enriquecer eventos de razonamiento que se envían
a la UI para explicar decisiones del sistema (qué estrategias están activas,
por qué están bloqueadas, etc).

Usado por:
- TradingService cuando procesa señales de estrategias
- StrategyGatekeeper cuando bloquea/permite estrategias  
- FibonacciExtender cuando proyecta niveles

Formato estándar para UI:
{
  "type": "STRATEGY_REASONING",
  "payload": {
    "strategy_id": "SESS_EXT_0001",
    "strategy_name": "SESSION EXTENSION",
    "asset": "GBP/JPY",
    "action": "seeking_extension",  // o "blocked", "active", "scouting"
    "message": "S-0005 activa: Buscando extensión 1.272 en GBP/JPY",
    "parameters": {
      "london_high": 186.50,
      "london_low": 185.00,
      "fib_127_target": 188.41,
      "fib_161_target": 188.93,
      "current_price": 186.25
    },
    "confidence": 0.85,
    "mode": "INSTITUTIONAL"  // Level override si aplica
  },
  "timestamp": "ISO_timestamp"
}
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class ReasoningEventBuilder:
    """Builder para construir eventos de razonamiento estratégico."""
    
    # Acciones posibles
    ACTION_SEEKING_EXTENSION = "seeking_extension"
    ACTION_BLOCKED = "blocked" 
    ACTION_ACTIVE = "active"
    ACTION_SCOUTING = "scouting"
    ACTION_ENTRY_SPOTTED = "entry_spotted"
    ACTION_STRUCTURE_DETECTED = "structure_detected"
    ACTION_BOS_CONFIRMED = "bos_confirmed"
    
    @staticmethod
    def build_sess_ext_reasoning(
        asset: str,
        action: str,
        london_high: Optional[float] = None,
        london_low: Optional[float] = None,
        fib_127_target: Optional[float] = None,
        fib_161_target: Optional[float] = None,
        current_price: Optional[float] = None,
        confidence: float = 0.85,
        mode: str = "INSTITUTIONAL"
    ) -> Dict[str, Any]:
        """
        Construye un evento de razonamiento para S-0005 (SESS_EXT_0001).
        
        Args:
            asset: Par de divisas (e.g., "GBP/JPY")
            action: Acción actual (seeking_extension, blocked, active, etc)
            london_high: Session high de Londres
            london_low: Session low de Londres
            fib_127_target: Nivel FIB_127 proyectado
            fib_161_target: Nivel FIB_161 proyectado
            current_price: Precio actual de mercado
            confidence: Nivel de confianza (0-1)
            mode: Modo operativo (INSTITUTIONAL, TEST, DEMO)
            
        Returns:
            Dict con estructura de evento listo para WebSocket
        """
        
        # Mapear acción a mensaje amigable
        action_messages = {
            ReasoningEventBuilder.ACTION_SEEKING_EXTENSION: 
                f"S-0005 activa: Buscando extensión {fib_127_target:.3f if fib_127_target else '?'} en {asset}",
            ReasoningEventBuilder.ACTION_BLOCKED:
                f"S-0005 en pausa: Condiciones no confluentes para {asset}",
            ReasoningEventBuilder.ACTION_ACTIVE:
                f"S-0005 operativa: Monitoreando {asset} hacia {fib_127_target:.3f if fib_127_target else '?'}",
            ReasoningEventBuilder.ACTION_SCOUTING:
                f"S-0005 reconocimiento: Analizando sesión de Londres para {asset}",
            ReasoningEventBuilder.ACTION_ENTRY_SPOTTED:
                f"S-0005 señal: Confluencia detectada en {asset} @ {current_price:.5f if current_price else '?'}"
        }
        
        message = action_messages.get(action, f"S-0005: Acción {action} en {asset}")
        
        # Construir payload
        parameters = {}
        if london_high is not None:
            parameters['london_high'] = london_high
        if london_low is not None:
            parameters['london_low'] = london_low
        if fib_127_target is not None:
            parameters['fib_127_target'] = fib_127_target
        if fib_161_target is not None:
            parameters['fib_161_target'] = fib_161_target
        if current_price is not None:
            parameters['current_price'] = current_price
        
        payload = {
            "strategy_id": "SESS_EXT_0001",
            "strategy_name": "SESSION EXTENSION",
            "asset": asset,
            "action": action,
            "message": message,
            "parameters": parameters,
            "confidence": min(max(confidence, 0.0), 1.0),  # Clamp 0-1
            "mode": mode
        }
        
        logger.debug(
            f"[SESS_EXT_0001] Reasoning event built for {asset}: "
            f"action={action}, message={message}"
        )
        
        return {
            "type": "STRATEGY_REASONING",
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def build_struc_shift_reasoning(
        asset: str,
        action: str,
        structure_type: Optional[str] = None,
        breaker_high: Optional[float] = None,
        breaker_low: Optional[float] = None,
        bos_direction: Optional[str] = None,
        bos_strength: Optional[float] = None,
        current_price: Optional[float] = None,
        confidence: float = 0.85,
        mode: str = "INSTITUTIONAL"
    ) -> Dict[str, Any]:
        """
        Construye evento de razonamiento para S-0006 (STRUC_SHIFT_0001).
        
        Args:
            asset: Par de divisas (e.g., "EUR/USD")
            action: Acción (structure_detected, bos_confirmed, blocked, etc)
            structure_type: Tipo de estructura (UPTREND, DOWNTREND)
            breaker_high: Nivel alto del Breaker Block
            breaker_low: Nivel bajo del Breaker Block
            bos_direction: Dirección de ruptura (UP, DOWN)
            bos_strength: Fuerza de ruptura (0-100%)
            current_price: Precio actual
            confidence: Confianza (0-1)
            mode: Modo operativo
            
        Returns:
            Dict con evento de razonamiento para WebSocket
        """
        
        # Mapear acción a mensaje amigable
        action_messages = {
            ReasoningEventBuilder.ACTION_STRUCTURE_DETECTED:
                f"S-0006: Estructura {structure_type} detectada en {asset}. "
                f"Breaker Block: {breaker_low:.5f} - {breaker_high:.5f}",
            ReasoningEventBuilder.ACTION_BOS_CONFIRMED:
                f"S-0006: Ruptura de estructura confirmada en {asset}. "
                f"Dirección: {bos_direction} | Fuerza: {bos_strength:.0f}% "
                f"| Esperando pullback a zona {breaker_low:.5f} - {breaker_high:.5f}",
            ReasoningEventBuilder.ACTION_BLOCKED:
                f"S-0006 bloqueada en {asset}: Affinity insuficiente o estructura no válida",
            ReasoningEventBuilder.ACTION_SCOUTING:
                f"S-0006: Analizando estructura en {asset}. "
                f"Precio: {current_price:.5f}",
            ReasoningEventBuilder.ACTION_ENTRY_SPOTTED:
                f"S-0006: Señal confluencia detectada en {asset} @ {current_price:.5f}. "
                f"Entrada en zona Breaker Block"
        }
        
        message = action_messages.get(action, f"S-0006: Acción {action} en {asset}")
        
        # Construir parámetros
        parameters = {}
        if structure_type:
            parameters['structure_type'] = structure_type
        if breaker_high is not None:
            parameters['breaker_high'] = breaker_high
        if breaker_low is not None:
            parameters['breaker_low'] = breaker_low
        if bos_direction:
            parameters['bos_direction'] = bos_direction
        if bos_strength is not None:
            parameters['bos_strength'] = bos_strength
        if current_price is not None:
            parameters['current_price'] = current_price
        
        payload = {
            "strategy_id": "STRUC_SHIFT_0001",
            "strategy_name": "STRUCTURE BREAK SHIFT",
            "asset": asset,
            "action": action,
            "message": message,
            "parameters": parameters,
            "confidence": min(max(confidence, 0.0), 1.0),
            "mode": mode
        }
        
        logger.debug(
            f"[STRUC_SHIFT_0001] Reasoning event built for {asset}: "
            f"action={action}, structure={structure_type}, bos_direction={bos_direction}"
        )
        
        return {
            "type": "STRATEGY_REASONING",
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def build_strategy_blocked_reasoning(
        strategy_id: str,
        strategy_name: str,
        asset: str,
        reason: str,
        confidence: float = 0.0
    ) -> Dict[str, Any]:
        """
        Construye evento de razonamiento cuando una estrategia está bloqueada.
        
        Args:
            strategy_id: ID de la estrategia (e.g., "SESS_EXT_0001")
            strategy_name: Nombre amigable (e.g., "SESSION EXTENSION")
            asset: Par de divisas
            reason: Razón del bloqueo (e.g., "low affinity 0.65", "membership required")
            confidence: Confianza (generalmente 0)
            
        Returns:
            Dict con evento de razonamiento
        """
        payload = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "asset": asset,
            "action": "blocked",
            "message": f"{strategy_name} bloqueada en {asset} ({reason})",
            "parameters": {"block_reason": reason},
            "confidence": confidence,
            "mode": "INSTITUTIONAL"
        }
        
        logger.debug(
            f"[{strategy_id}] Strategy blocked for {asset}: {reason}"
        )
        
        return {
            "type": "STRATEGY_REASONING",
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
    
    @staticmethod
    def build_generic_strategy_reasoning(
        strategy_id: str,
        strategy_name: str,
        message: str,
        parameters: Optional[Dict[str, Any]] = None,
        confidence: float = 0.85
    ) -> Dict[str, Any]:
        """
        Constructor genérico para cualquier estrategia.
        
        Args:
            strategy_id: ID de estrategia
            strategy_name: Nombre amigable
            message: Mensaje a mostrar en UI
            parameters: Dict opcional de parámetros relevantes
            confidence: Nivel de confianza (0-1)
            
        Returns:
            Dict con evento preparado para WebSocket
        """
        payload = {
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "action": "reasoning",
            "message": message,
            "parameters": parameters or {},
            "confidence": min(max(confidence, 0.0), 1.0),
            "mode": "INSTITUTIONAL"
        }
        
        return {
            "type": "STRATEGY_REASONING",
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        }
