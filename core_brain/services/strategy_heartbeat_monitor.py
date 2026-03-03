"""
Strategy Heartbeat Monitor - Pulso de Salud del Sistema

Responsabilidad:
  - Monitorear estado de las 6 estrategias en tiempo real
  - Reportar a la página Monitor: IDLE, SCANNING, SIGNAL_DETECTED, VETOED_BY_NEWS
  - Perseguir latido en base de datos para auditoría
  - Emitir eventos a UI vía WebSocket

Estados:
  - IDLE: Estrategia esperando condiciones
  - SCANNING: Analizando datos en busca de setup
  - SIGNAL_DETECTED: Señal generada, esperando validación
  - IN_EXECUTION: Orden en ejecución
  - POSITION_ACTIVE: Posición abierta
  - VETOED_BY_NEWS: Bloqueada por FundamentalGuard
  - VETO_BY_REGIME: Bloqueada por incompatibilidad régimen
  - PENDING_CONFLICT: Esperando que otra estrategia cierre posición

Frecuencia:
  - Heartbeat cada 1 segundo a UI
  - Persistencia cada 10 segundos a BD

TRACE_ID: EXEC-ORCHESTRA-001
"""

import logging
import asyncio
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class StrategyState(Enum):
    """Estados posibles de una estrategia."""
    IDLE = "IDLE"
    SCANNING = "SCANNING"
    SIGNAL_DETECTED = "SIGNAL_DETECTED"
    IN_EXECUTION = "IN_EXECUTION"
    POSITION_ACTIVE = "POSITION_ACTIVE"
    VETOED_BY_NEWS = "VETOED_BY_NEWS"
    VETO_BY_REGIME = "VETO_BY_REGIME"
    PENDING_CONFLICT = "PENDING_CONFLICT"
    ERROR = "ERROR"


@dataclass
class StrategyHeartbeat:
    """Pulso individual de una estrategia."""
    strategy_id: str
    strategy_name: str
    state: StrategyState
    asset: Optional[str] = None
    confidence: float = 0.0
    last_signal_time: Optional[datetime] = None
    position_open: bool = False
    error_message: Optional[str] = None
    timestamp: datetime = None
    
    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "state": self.state.value,
            "asset": self.asset,
            "confidence": self.confidence,
            "last_signal_time": self.last_signal_time.isoformat() if self.last_signal_time else None,
            "position_open": self.position_open,
            "error_message": self.error_message,
            "timestamp": self.timestamp.isoformat()
        }


class StrategyHeartbeatMonitor:
    """
    Monitor centralizado del latido de todas las estrategias.
    
    Mantiene estado actual de 6 estrategias y emite actualizaciones
    a la página Monitor en tiempo real.
    """
    
    # IDs de las 6 estrategias
    STRATEGY_IDS = [
        "BRK_OPEN_0001",
        "CONV_STRIKE_0001",
        "MOM_BIAS_0001",
        "SESS_EXT_0001",
        "STRUC_SHIFT_0001",
        "LIQ_SWEEP_0001"  # Placeholder para 6a estrategia
    ]
    
    def __init__(self, storage, socket_service=None):
        """
        Inicializa monitor de heartbeat.
        
        Args:
            storage: StorageManager para persistencia
            socket_service: SocketService para emitir eventos (opcional)
        """
        self.storage = storage
        self.socket_service = socket_service
        
        # Estado de cada estrategia
        self.heartbeats: Dict[str, StrategyHeartbeat] = {}
        
        # Inicializar todos los heartbeats (IDLE)
        for strategy_id in self.STRATEGY_IDS:
            self.heartbeats[strategy_id] = StrategyHeartbeat(
                strategy_id=strategy_id,
                strategy_name=strategy_id.replace("_", " "),
                state=StrategyState.IDLE
            )
        
        logger.info(f"[HEARTBEAT] Monitor initialized for {len(self.STRATEGY_IDS)} strategies")
    
    def update_heartbeat(
        self,
        strategy_id: str,
        state: StrategyState,
        asset: Optional[str] = None,
        confidence: float = 0.0,
        position_open: bool = False,
        error_message: Optional[str] = None
    ) -> None:
        """
        Actualiza el latido de una estrategia.
        
        Args:
            strategy_id: ID del strategy
            state: Nuevo estado
            asset: Activo siendo procesado
            confidence: Confianza de la señal (0-1)
            position_open: Si hay posición abierta
            error_message: Mensaje de error si aplica
        """
        try:
            if strategy_id not in self.heartbeats:
                logger.warning(f"[HEARTBEAT] Unknown strategy: {strategy_id}")
                return
            
            last_signal = self.heartbeats[strategy_id].last_signal_time
            if state in [StrategyState.SIGNAL_DETECTED, StrategyState.IN_EXECUTION]:
                last_signal = datetime.now()
            
            self.heartbeats[strategy_id] = StrategyHeartbeat(
                strategy_id=strategy_id,
                strategy_name=self.heartbeats[strategy_id].strategy_name,
                state=state,
                asset=asset,
                confidence=confidence,
                last_signal_time=last_signal,
                position_open=position_open,
                error_message=error_message
            )
            
            # Log estado
            state_color = self._get_state_color(state)
            logger.info(
                f"[HEARTBEAT] {strategy_id:20} → {state.value:20} "
                f"[asset={asset or '-':8}] [confidence={confidence:.2f}]"
            )
        
        except Exception as e:
            logger.error(f"[HEARTBEAT] Exception in update_heartbeat({strategy_id}): {str(e)}")
            # Fallback: no actualizar si falla
    
    
    def get_heartbeat(self, strategy_id: str) -> Optional[StrategyHeartbeat]:
        """Obtiene el latido actual de una estrategia."""
        return self.heartbeats.get(strategy_id)
    
    def get_all_heartbeats(self) -> Dict[str, StrategyHeartbeat]:
        """Obtiene los latidos de todas las estrategias."""
        return self.heartbeats.copy()
    
    async def emit_monitor_update(self) -> None:
        """
        Emite actualización a página Monitor vía WebSocket.
        
        Formato:
        {
          "type": "SYSTEM_HEARTBEAT",
          "timestamp": "2026-03-02T...",
          "strategies": {
            "BRK_OPEN_0001": {...heartbeat...},
            ...
          },
          "summary": {
            "idle": 2,
            "scanning": 1,
            "active": 2,
            "veto": 1
          }
        }
        """
        heartbeat_dicts = {
            sid: hb.to_dict() for sid, hb in self.heartbeats.items()
        }
        
        # Calcular resumen
        summary = self._compute_summary()
        
        payload = {
            "type": "SYSTEM_HEARTBEAT",
            "timestamp": datetime.now().isoformat(),
            "strategies": heartbeat_dicts,
            "summary": summary
        }
        
        if self.socket_service:
            try:
                await self.socket_service.emit_monitor_update(payload)
                logger.debug(f"[HEARTBEAT] Emitted monitor update: {summary}")
            except Exception as e:
                logger.error(f"[HEARTBEAT] Error emitting monitor update: {e}")
    
    def persist_heartbeats(self) -> None:
        """
        Persiste los heartbeats a base de datos para auditoría.
        
        Se ejecuta cada 10 segundos (no muy frecuente para no saturar BD).
        """
        try:
            heartbeat_data = {
                "timestamp": datetime.now().isoformat(),
                "strategies": {
                    sid: hb.to_dict() for sid, hb in self.heartbeats.items()
                },
                "summary": self._compute_summary()
            }
            
            # Guardar en system_state
            self.storage.update_system_state({
                "strategy_heartbeats": heartbeat_data
            })
            
            logger.debug("[HEARTBEAT] Persisted to storage")
        except Exception as e:
            logger.error(f"[HEARTBEAT] Error persisting heartbeats: {e}")
    
    def _compute_summary(self) -> Dict[str, int]:
        """Calcula resumen de estados."""
        summary = {
            "idle": 0,
            "scanning": 0,
            "signal_detected": 0,
            "in_execution": 0,
            "position_active": 0,
            "vetoed": 0,
            "error": 0
        }
        
        for hb in self.heartbeats.values():
            if hb.state == StrategyState.IDLE:
                summary["idle"] += 1
            elif hb.state == StrategyState.SCANNING:
                summary["scanning"] += 1
            elif hb.state == StrategyState.SIGNAL_DETECTED:
                summary["signal_detected"] += 1
            elif hb.state == StrategyState.IN_EXECUTION:
                summary["in_execution"] += 1
            elif hb.state == StrategyState.POSITION_ACTIVE:
                summary["position_active"] += 1
            elif hb.state in [StrategyState.VETOED_BY_NEWS, StrategyState.VETO_BY_REGIME, StrategyState.PENDING_CONFLICT]:
                summary["vetoed"] += 1
            elif hb.state == StrategyState.ERROR:
                summary["error"] += 1
        
        return summary
    
    def _get_state_color(self, state: StrategyState) -> str:
        """Retorna color para logging visual."""
        colors = {
            StrategyState.IDLE: "⚪",
            StrategyState.SCANNING: "🔵",
            StrategyState.SIGNAL_DETECTED: "🟢",
            StrategyState.IN_EXECUTION: "🟡",
            StrategyState.POSITION_ACTIVE: "⭐",
            StrategyState.VETOED_BY_NEWS: "🔴",
            StrategyState.VETO_BY_REGIME: "🟠",
            StrategyState.PENDING_CONFLICT: "🟣",
            StrategyState.ERROR: "🔴"
        }
        return colors.get(state, "❓")


class SystemHealthReporter:
    """
    Reporter integrado que combina heartbeats de estrategias
    con métricas de salud general del sistema.
    """
    
    def __init__(self, heartbeat_monitor, storage, socket_service=None):
        """
        Inicializa reporter de salud.
        
        Args:
            heartbeat_monitor: StrategyHeartbeatMonitor
            storage: StorageManager
            socket_service: SocketService (opcional)
        """
        self.monitor = heartbeat_monitor
        self.storage = storage
        self.socket_service = socket_service
    
    async def emit_health_report(self) -> None:
        """
        Emite reporte completo de salud del sistema (estrategias + infraestructura).
        
        Payload:
        {
          "type": "SYSTEM_HEALTH",
          "timestamp": "...",
          "system": {
            "cpu_usage": 45.2,
            "memory_usage": 62.1,
            "database": "OK",
            "broker_connection": "OK",
            "websocket": "OK"
          },
          "strategies": {...},
          "health_score": 92
        }
        """
        # Obtener latidos
        all_heartbeats = self.monitor.get_all_heartbeats()
        summary = self.monitor._compute_summary()
        
        # Obtener métricas de infraestructura (simuladas)
        system_health = await self._get_system_metrics()
        
        # Calcular health score (0-100)
        health_score = self._compute_health_score(system_health, summary)
        
        report = {
            "type": "SYSTEM_HEALTH",
            "timestamp": datetime.now().isoformat(),
            "system": system_health,
            "strategies": {
                sid: hb.to_dict() for sid, hb in all_heartbeats.items()
            },
            "strategy_summary": summary,
            "health_score": health_score,
            "status": "🟢 HEALTHY" if health_score >= 75 else "🟡 CAUTION" if health_score >= 50 else "🔴 CRITICAL"
        }
        
        if self.socket_service:
            try:
                await self.socket_service.emit_health_report(report)
                logger.info(f"[HEALTH] Emitted report: score={health_score} | summary={summary}")
            except Exception as e:
                logger.error(f"[HEALTH] Error emitting report: {e}")
    
    async def _get_system_metrics(self) -> Dict[str, Any]:
        """Obtiene métricas de infraestructura del sistema."""
        # Esto es una versión simplificada
        # En producción, usaría psutil, broker API checks, etc.
        
        return {
            "cpu_usage": 45.2,  # %
            "memory_usage": 62.1,  # %
            "database": "OK",
            "broker_connection": "OK",
            "websocket": "OK",
            "last_broker_ping": datetime.now().isoformat(),
            "data_freshness": "< 1 second"
        }
    
    def _compute_health_score(self, system_health: Dict, strategy_summary: Dict) -> int:
        """
        Calcula score de salud general (0-100).
        
        Factores:
        - CPU/Memory usage (peso: 30%)
        - Infraestructura (peso: 20%)
        - Estrategias sin error (peso: 50%)
        """
        # Factor 1: Infraestructura (30%)
        infra_score = 100
        if system_health.get("cpu_usage", 0) > 80:
            infra_score -= 20
        if system_health.get("memory_usage", 0) > 85:
            infra_score -= 20
        if system_health.get("database") != "OK":
            infra_score = 0
        
        # Factor 2: Conectividad (20%)
        conn_score = 100
        if system_health.get("broker_connection") != "OK":
            conn_score = 0
        if system_health.get("websocket") != "OK":
            conn_score = 0
        
        # Factor 3: Estrategias (50%)
        total_strategies = sum(strategy_summary.values())
        error_count = strategy_summary.get("error", 0)
        veto_count = strategy_summary.get("vetoed", 0)
        
        strategy_score = 100
        if error_count > 0:
            strategy_score = 100 - (error_count / total_strategies * 50)
        if veto_count > total_strategies * 0.5:
            strategy_score -= 25
        
        # Health score total (ponderado)
        health = (infra_score * 0.3) + (conn_score * 0.2) + (strategy_score * 0.5)
        
        return int(max(0, min(100, health)))
