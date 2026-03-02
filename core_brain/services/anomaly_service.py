"""
Anomaly Sentinel Service (HU 4.6: Anomaly Sentinel - Antifragility Engine)
Detecta eventos extremos, Flash Crashes, cisnes negros y activa protecciones defensivas.

Trace_ID: BLACK-SWAN-SENTINEL-2026-001
Dominio: 04 (Risk Governance) + 10 (Infrastructure Resiliency)
"""

import logging
import uuid
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, List, Any

import pandas as pd
import numpy as np

from data_vault.storage import StorageManager
from core_brain.services.socket_service import get_socket_service
from core_brain.services.anomaly_suggestions import generate_thought_console_suggestion
from core_brain.services.anomaly_health import calculate_anomaly_health_status
from core_brain.services.anomaly_detectors import (
    detect_volatility_anomalies as detect_volatility,
    detect_flash_crashes as detect_crashes,
)
from core_brain.services.anomaly_models import AnomalyEvent, AnomalyType

logger = logging.getLogger(__name__)


class AnomalyService:
    """
    Motor de Detección de Anomalías y Coordinación de Defensa.
    
    Responsabilidades:
    1. Detectar picos de volatilidad extrema (Z-Score > 3)
    2. Detectar Flash Crashes (caída > -2% en 1 vela)
    3. Activar protocolo defensivo (Lockdown, cancelar órdenes, SL -> Breakeven)
    4. Persistir eventos en DB con Trace_ID
    5. Broadcast de [ANOMALY_DETECTED] a la UI
    6. Sugerencias inteligentes (Thought Console)
    7. Integración con Health System
    """
    
    def __init__(
        self,
        storage: StorageManager,
        risk_manager: Optional[Any] = None,
        socket_service: Optional[Any] = None,
    ):
        """
        Inicializa el AnomalyService con dependencias inyectadas.
        
        Args:
            storage: StorageManager para persistencia
            risk_manager: RiskManager para activar Lockdown
            socket_service: SocketService para broadcast de eventos
        """
        self.storage = storage
        self.risk_manager = risk_manager
        self.socket_service = socket_service or get_socket_service()
        
        # Cargar umbrales desde Storage (SSOT)
        params = storage.get_dynamic_params()
        self.volatility_zscore_threshold = params.get("volatility_zscore_threshold", 3.0)
        self.flash_crash_threshold = params.get("flash_crash_threshold", -2.0)  # -2%
        self.anomaly_lookback_period = params.get("anomaly_lookback_period", 50)
        self.anomaly_persistence_candles = params.get("anomaly_persistence_candles", 3)
        self.volume_spike_percentile = params.get("volume_spike_percentile", 90)
        
        # Estado de salud
        self._anomaly_history: Dict[str, List[AnomalyEvent]] = {}
        self._health_status: Dict[str, Dict[str, Any]] = {}
        
        logger.info(
            f"[ANOMALY_SERVICE] Initialized with Z-Score threshold={self.volatility_zscore_threshold}, "
            f"Flash Crash threshold={self.flash_crash_threshold}%, "
            f"Lookback={self.anomaly_lookback_period} candles. Trace_ID: BLACK-SWAN-SENTINEL-2026-001"
        )

    # ────────────────────────────────────────────────────────────────────────────
    # DETECTOR DE VOLATILIDAD EXTREMA (Z-Score > 3)
    # ────────────────────────────────────────────────────────────────────────────

    async def detect_volatility_anomalies(
        self,
        symbol: str,
        df: pd.DataFrame,
        timeframe: str,
    ) -> List[AnomalyEvent]:
        """
        Detecta picos de volatilidad anómala usando Z-Score.
        Regla: Si Z-Score > 3.0, es una anomalía estadística (3-sigma).
        """
        try:
            # Llamar a detector importado
            anomalies_dicts = detect_volatility(
                symbol=symbol,
                df=df,
                timeframe=timeframe,
                volatility_zscore_threshold=self.volatility_zscore_threshold,
            )
            
            # Convertir dicts a AnomalyEvent
            anomalies: List[AnomalyEvent] = []
            for anom_dict in anomalies_dicts:
                event = AnomalyEvent(
                    symbol=anom_dict["symbol"],
                    anomaly_type=AnomalyType.EXTREME_VOLATILITY,
                    timestamp=anom_dict["timestamp"],
                    z_score=anom_dict["z_score"],
                    confidence=anom_dict["confidence"],
                    trace_id=anom_dict["trace_id"],
                    details=anom_dict["details"],
                )
                anomalies.append(event)
            
            # Actualizar historial
            if symbol not in self._anomaly_history:
                self._anomaly_history[symbol] = []
            self._anomaly_history[symbol].extend(anomalies)
            
            return anomalies
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error in detect_volatility_anomalies: {e}")
            return []

    # ────────────────────────────────────────────────────────────────────────────
    # DETECTOR DE FLASH CRASHES
    # ────────────────────────────────────────────────────────────────────────────

    async def detect_flash_crashes(
        self,
        symbol: str,
        df: pd.DataFrame,
        timeframe: str,
    ) -> List[AnomalyEvent]:
        """
        Detecta Flash Crashes: caída > -2% en una sola vela con volumen anómalo.
        """
        try:
            # Llamar a detector importado
            anomalies_dicts = detect_crashes(
                symbol=symbol,
                df=df,
                timeframe=timeframe,
                flash_crash_threshold=self.flash_crash_threshold,
                volume_percentile=self.volume_spike_percentile,
            )
            
            # Convertir dicts a AnomalyEvent
            anomalies: List[AnomalyEvent] = []
            for anom_dict in anomalies_dicts:
                event = AnomalyEvent(
                    symbol=anom_dict["symbol"],
                    anomaly_type=AnomalyType.FLASH_CRASH,
                    timestamp=anom_dict["timestamp"],
                    drop_percentage=anom_dict["drop_percentage"],
                    volume_spike_detected=anom_dict["volume_spike_detected"],
                    confidence=anom_dict["confidence"],
                    trace_id=anom_dict["trace_id"],
                    details=anom_dict["details"],
                )
                anomalies.append(event)
            
            # Actualizar historial
            if symbol not in self._anomaly_history:
                self._anomaly_history[symbol] = []
            self._anomaly_history[symbol].extend(anomalies)
            
            return anomalies
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error in detect_flash_crashes: {e}")
            return []

    # ────────────────────────────────────────────────────────────────────────────
    # PROTOCOLO DEFENSIVO (LOCKDOWN ACTIVATION)
    # ────────────────────────────────────────────────────────────────────────────

    async def activate_defensive_protocol(
        self,
        anomaly: AnomalyEvent,
        symbol: str,
    ) -> Dict[str, Any]:
        """
        Activa el protocolo defensivo cuando se detecta una anomalía sistémica.
        
        Acciones:
        1. Activar Lockdown en RiskManager
        2. Cancelar todas las órdenes pendientes
        3. Ajustar Stop Loss a Breakeven
        
        Args:
            anomaly: Evento de anomalía detectado
            symbol: Instrumento afectado
            
        Returns:
            Dict con resultado de las acciones defensivas
        """
        response = {
            "lockdown_activated": False,
            "orders_cancelled": 0,
            "positions_adjusted": 0,
            "trace_id": anomaly.trace_id,
        }
        
        try:
            if self.risk_manager is None:
                logger.warning(f"[ANOMALY_SERVICE] RiskManager not available for {symbol}")
                return response
            
            # 1. Activar Lockdown
            logger.critical(
                f"[LOCKDOWN_PROTOCOL] Anomalía sistémica en {symbol}. "
                f"Tipo: {anomaly.anomaly_type.value}, Z-Score: {anomaly.z_score:.2f}. "
                f"Activando Lockdown Preventivo. Trace_ID: {anomaly.trace_id}"
            )
            
            lockdown_result = await self.risk_manager.activate_lockdown(
                symbol=symbol,
                reason=f"Anomalía: {anomaly.anomaly_type.value}",
                trace_id=anomaly.trace_id
            )
            response["lockdown_activated"] = lockdown_result
            
            # 2. Cancelar órdenes pendientes
            cancel_result = await self.risk_manager.cancel_pending_orders(
                symbol=symbol,
                reason="Lockdown Mode Activated"
            )
            response["orders_cancelled"] = cancel_result.get("cancelled", 0) if cancel_result else 0
            
            # 3. Ajustar SL a Breakeven
            adjust_result = await self.risk_manager.adjust_stops_to_breakeven(
                symbol=symbol,
                reason="Anomaly Detected - Protective Measure"
            )
            response["positions_adjusted"] = adjust_result.get("adjusted", 0) if adjust_result else 0
            
            logger.critical(
                f"[LOCKDOWN_COMPLETE] {symbol} - Órdenes canceladas: {response['orders_cancelled']}, "
                f"Posiciones ajustadas: {response['positions_adjusted']}. Trace_ID: {anomaly.trace_id}"
            )
            
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error activating defensive protocol: {e}")
        
        return response

    # ────────────────────────────────────────────────────────────────────────────
    # PERSISTENCIA EN DB
    # ────────────────────────────────────────────────────────────────────────────

    async def persist_anomaly_event(self, event: AnomalyEvent) -> bool:
        """
        Persiste el evento de anomalía en la DB (aethelgard.db).
        
        Args:
            event: Evento de anomalía a persistir
            
        Returns:
            True si se persistió correctamente
        """
        try:
            await self.storage.persist_anomaly_event(
                symbol=event.symbol,
                anomaly_type=event.anomaly_type.value,
                z_score=event.z_score,
                confidence=event.confidence,
                timestamp=event.timestamp,
                trace_id=event.trace_id,
                details=event.details
            )
            logger.debug(f"[ANOMALY_SERVICE] Event persisted. Trace_ID: {event.trace_id}")
            return True
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error persisting event: {e}")
            return False

    async def get_anomaly_history(self, symbol: str) -> List[AnomalyEvent]:
        """
        Recupera el historial de anomalías para un símbolo.
        
        Args:
            symbol: Instrumento
            
        Returns:
            Lista de eventos de anomalía históricos
        """
        try:
            history = await self.storage.get_anomaly_history(symbol=symbol)
            return history or []
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error retrieving anomaly history: {e}")
            return []

    # ────────────────────────────────────────────────────────────────────────────
    # BROADCAST DE EVENTOS (THOUGHT CONSOLE)
    # ────────────────────────────────────────────────────────────────────────────

    async def broadcast_anomaly_event(self, event: AnomalyEvent) -> None:
        """
        Emite un evento [ANOMALY_DETECTED] a la UI vía WebSocket.
        
        Args:
            event: Evento de anomalía a broadcast
        """
        try:
            suggestion = generate_thought_console_suggestion(event)
            payload = {
                "type": "ANOMALY_DETECTED",
                "timestamp": datetime.now().isoformat(),
                "anomaly": event.to_dict(),
                "suggestion": suggestion,
                "trace_id": event.trace_id,
            }
            
            await self.socket_service.broadcast(payload)
            logger.info(f"[THOUGHT_CONSOLE] [ANOMALY_DETECTED] Event broadcast. Trace_ID: {event.trace_id}")
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error broadcasting event: {e}")

    # ────────────────────────────────────────────────────────────────────────────
    # INTEGRACIÓN CON HEALTH SYSTEM (HU 10.1)
    # ────────────────────────────────────────────────────────────────────────────

    async def get_anomaly_health_status(self, symbol: str) -> Dict[str, Any]:
        """
        Retorna estado de salud del símbolo basado en historial de anomalías.
        
        Args:
            symbol: Instrumento
            
        Returns:
            Dict con métricas de salud
        """
        try:
            history = self._anomaly_history.get(symbol, [])
            # Convertir objetos AnomalyEvent a dicts con timestamp como ISO string
            history_dicts = [
                {
                    "timestamp": e.timestamp.isoformat() if hasattr(e.timestamp, 'isoformat') else str(e.timestamp),
                    "symbol": e.symbol,
                    "anomaly_type": e.anomaly_type.value,
                    "z_score": e.z_score,
                    "confidence": e.confidence,
                    "drop_percentage": e.drop_percentage,
                    "volume_spike_detected": e.volume_spike_detected,
                    "trace_id": e.trace_id,
                    "details": e.details,
                }
                for e in history
            ]
            return calculate_anomaly_health_status(symbol, history_dicts)
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error in get_anomaly_health_status: {e}")
            return {
                "symbol": symbol,
                "mode": "UNKNOWN",
                "anomaly_count": 0,
                "consecutive_anomalies": 0,
                "system_stability": 0.5,
            }

    # ────────────────────────────────────────────────────────────────────────────
    # EXECUTOR: Scan Completo de Múltiples Timeframes
    # ────────────────────────────────────────────────────────────────────────────

    async def execute_full_anomaly_scan(
        self,
        symbol: str,
        data_by_timeframe: Dict[str, pd.DataFrame],
    ) -> Dict[str, Any]:
        """
        Ejecuta un scan completo de anomalías en múltiples timeframes.
        Coordina detección multi-escalar y activación de defensas si es necesario.
        
        Args:
            symbol: Instrumento
            data_by_timeframe: Dict {timeframe: DataFrame}
            
        Returns:
            Resumen de anomalías detectadas y acciones tomadas
        """
        result = {
            "symbol": symbol,
            "timestamp": datetime.now().isoformat(),
            "anomalies_by_timeframe": {},
            "systemic_anomaly_detected": False,
            "lockdown_activated": False,
            "trace_id": f"SCAN-{uuid.uuid4().hex[:8].upper()}",
        }
        
        try:
            all_anomalies: List[AnomalyEvent] = []
            
            for timeframe, df in data_by_timeframe.items():
                # Detectar volatilidad extrema
                volatility_anomalies = await self.detect_volatility_anomalies(symbol, df, timeframe)
                all_anomalies.extend(volatility_anomalies)
                
                # Detectar Flash Crashes
                crash_anomalies = await self.detect_flash_crashes(symbol, df, timeframe)
                all_anomalies.extend(crash_anomalies)
                
                if volatility_anomalies or crash_anomalies:
                    result["anomalies_by_timeframe"][timeframe] = {
                        "volatility": len(volatility_anomalies),
                        "crashes": len(crash_anomalies),
                    }
            
            # Si hay anomalías en múltiples timeframes, es sistémica
            if len(result["anomalies_by_timeframe"]) >= 2:
                result["systemic_anomaly_detected"] = True
                
                # Activar protocolo defensivo
                if all_anomalies:
                    critical_anomaly = max(all_anomalies, key=lambda x: x.confidence)
                    defense_result = await self.activate_defensive_protocol(critical_anomaly, symbol)
                    result["lockdown_activated"] = defense_result["lockdown_activated"]
            
            # Persistir todos los eventos
            for anomaly in all_anomalies:
                await self.persist_anomaly_event(anomaly)
                await self.broadcast_anomaly_event(anomaly)
            
            result["total_anomalies"] = len(all_anomalies)
            logger.info(
                f"[ANOMALY_SCAN] Complete for {symbol}. "
                f"Total anomalies: {len(all_anomalies)}, "
                f"Systemic: {result['systemic_anomaly_detected']}, "
                f"Trace_ID: {result['trace_id']}"
            )
            
        except Exception as e:
            logger.error(f"[ANOMALY_SERVICE] Error in execute_full_anomaly_scan: {e}")
        
        return result
