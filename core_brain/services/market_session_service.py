"""
Market Session Service (HU 2.2: Global Liquidity Clock).
Trace_ID: EXEC-STRAT-OPEN-001

Trackea sesiones globales (Sydney, Tokyo, London, NY) y proporciona
métodos para detectar ventanas de liquidez pre-apertura NY.

Arquitectura:
- Inyección de dependencias estricta (StorageManager)
- Cálculos basados en UTC
- SSOT: configuración persistida en storage
- Trazabilidad con Trace_ID
"""

import logging
import uuid
from typing import Dict, Optional, List, Any, Tuple
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class MarketSessionService:
    """
    Motor de Sesiones Globales de Liquidez.
    
    Responsabilidades:
    1. Trackear estado de sesiones (Sydney, Tokyo, London, NY)
    2. Detectar ventanas de pre-mercado para NY
    3. Calcular métricas de liquidez por sesión
    4. Sincronizar estado en ledger
    """
    
    # Definición de sesiones (UTC offset, hora apertura, hora cierre en zona local)
    SESSION_CONFIG = {
        "sydney": {
            "utc_offset_hours": 11,  # AEDT
            "open_time": "23:00",     # Hora local (día anterior)
            "close_time": "07:00",    # Hora local
            "name_display": "Sydney"
        },
        "tokyo": {
            "utc_offset_hours": 9,
            "open_time": "00:00",
            "close_time": "09:00",
            "name_display": "Tokyo"
        },
        "london": {
            "utc_offset_hours": 0,
            "open_time": "08:00",
            "close_time": "17:00",
            "name_display": "London"
        },
        "ny": {
            "utc_offset_hours": -5,
            "open_time": "13:30",
            "close_time": "21:00",
            "name_display": "New York"
        }
    }
    
    # Volatilidad esperada y volumen por sesión
    SESSION_PROFILES = {
        "sydney": {"pip_volatility_avg": 25, "volume_profile": "low-medium"},
        "tokyo": {"pip_volatility_avg": 30, "volume_profile": "medium"},
        "london": {"pip_volatility_avg": 50, "volume_profile": "high"},
        "ny": {"pip_volatility_avg": 60, "volume_profile": "very-high"}
    }
    
    def __init__(self, storage: StorageManager):
        """
        Inicializa MarketSessionService con inyección de dependencias.
        
        Args:
            storage: StorageManager para persistencia de configuración y estado
        """
        self.storage = storage
        self.trace_id = f"SESSION-{uuid.uuid4().hex[:8].upper()}"
        
        # Cache de rango pre-market para evitar recálculos frecuentes
        self._cached_pre_market_range: Optional[Dict[str, Any]] = None
        self._cache_timestamp: Optional[datetime] = None
        
        logger.info(f"[MarketSessionService] Inicializado con Trace_ID: {self.trace_id}")
        
    def _load_session_config(self) -> Dict[str, Dict[str, Any]]:
        """
        Carga configuración de sesiones desde storage o usa defaults.
        
        Returns:
            Diccionario con configuración de todas las sesiones
        """
        try:
            params = self.storage.get_dynamic_params()
            if isinstance(params, dict) and "market_sessions" in params:
                return params["market_sessions"]
        except Exception as e:
            logger.debug(f"Could not load session config from storage: {e}")
        
        return self.SESSION_CONFIG
    
    def _parse_time(self, time_str: str) -> Tuple[int, int]:
        """
        Convierte string "HH:MM" a tupla (horas, minutos).
        
        Args:
            time_str: String en formato "HH:MM"
            
        Returns:
            Tupla (hours, minutes)
        """
        parts = time_str.split(":")
        return int(parts[0]), int(parts[1])
    
    def _utc_time_from_local(self, local_hour: int, local_minute: int, 
                             utc_offset: int) -> Tuple[int, int]:
        """
        Convierte hora local a hora UTC considerando offset.
        
        Args:
            local_hour: Hora en zona local
            local_minute: Minuto en zona local
            utc_offset: Offset UTC (ej. -5 para NY)
            
        Returns:
            Tupla (utc_hour, utc_minute)
        """
        total_minutes = local_hour * 60 + local_minute
        total_minutes -= (utc_offset * 60)  # Restar offset para obtener UTC
        
        # Normalizar a rango 0-1440 minutos (24 horas)
        while total_minutes < 0:
            total_minutes += 1440
        while total_minutes >= 1440:
            total_minutes -= 1440
        
        return total_minutes // 60, total_minutes % 60
    
    def is_session_active(self, session_name: str, utc_time: datetime) -> bool:
        """
        Determina si una sesión está activa en un momento específico UTC.
        
        Args:
            session_name: Nombre de sesión ("sydney", "tokyo", "london", "ny")
            utc_time: Datetime en UTC
            
        Returns:
            True si la sesión está activa, False en caso contrario
        """
        if session_name not in self.SESSION_CONFIG:
            return False
        
        config = self.SESSION_CONFIG[session_name]
        offset = config["utc_offset_hours"]
        
        open_str = config["open_time"]
        close_str = config["close_time"]
        
        open_hour, open_minute = self._parse_time(open_str)
        close_hour, close_minute = self._parse_time(close_str)
        
        # Convertir horarios de apertura/cierre a UTC
        open_utc_hour, open_utc_minute = self._utc_time_from_local(
            open_hour, open_minute, offset
        )
        close_utc_hour, close_utc_minute = self._utc_time_from_local(
            close_hour, close_minute, offset
        )
        
        current_hour = utc_time.hour
        current_minute = utc_time.minute
        
        # Calcular minutos desde inicio del día
        current_total = current_hour * 60 + current_minute
        open_total = open_utc_hour * 60 + open_utc_minute
        close_total = close_utc_hour * 60 + close_utc_minute
        
        # Manejar sesiones que cruzan medianoche (por ejemplo, Tokyo)
        if open_total > close_total:
            # Sesión cruza medianoche
            return current_total >= open_total or current_total < close_total
        else:
            # Sesión normal
            return open_total <= current_total < close_total
    
    def get_pre_market_range(self, utc_time: datetime) -> Optional[Dict[str, Any]]:
        """
        Obtiene el rango de liquidez pre-apertura NY.
        
        NY abre a 13:30 EST (18:30 UTC). Este método retorna la ventana
        desde 30 minutos antes hasta la apertura (configurable).
        
        Args:
            utc_time: Datetime en UTC del momento actual
            
        Returns:
            Dict con inicio/fin del rango pre-market, o None si no aplica
        """
        # Verificar cache
        if self._cached_pre_market_range is not None and self._cache_timestamp is not None:
            if (utc_time - self._cache_timestamp).total_seconds() < 60:  # Cache válido 1 min
                return self._cached_pre_market_range
        
        # Obtener configuración de buffer
        try:
            params = self.storage.get_dynamic_params()
            buffer_minutes = params.get("pre_market_buffer_minutes", 30)
        except:
            buffer_minutes = 30
        
        config = self.SESSION_CONFIG["ny"]
        offset = config["utc_offset_hours"]
        
        # NY abre a 13:30 EST
        open_str = config["open_time"]
        open_hour, open_minute = self._parse_time(open_str)
        
        # Convertir a UTC
        open_utc_hour, open_utc_minute = self._utc_time_from_local(
            open_hour, open_minute, offset
        )
        
        # Crear datetime de apertura NY (hoy o mañana)
        ny_open_today_utc = utc_time.replace(
            hour=open_utc_hour, 
            minute=open_utc_minute, 
            second=0, 
            microsecond=0
        )
        
        # Si la apertura programada de hoy ya pasó, ajustar a mañana
        if ny_open_today_utc < utc_time:
            ny_open_today_utc += timedelta(days=1)
        
        # Calcular inicio del rango pre-market
        pre_market_start = ny_open_today_utc - timedelta(minutes=buffer_minutes)
        
        # Verificar si estamos dentro de la ventana pre-market
        if pre_market_start <= utc_time <= ny_open_today_utc:
            result = {
                "start_utc": pre_market_start,
                "end_utc": ny_open_today_utc,
                "session_name": "ny",
                "buffer_minutes": buffer_minutes,
                "trace_id": self.trace_id
            }
            
            # Cachear resultado
            self._cached_pre_market_range = result
            self._cache_timestamp = utc_time
            
            return result
        
        return None
    
    def get_session_liquidity_metrics(self, session_name: str) -> Dict[str, Any]:
        """
        Obtiene métricas de liquidez para una sesión específica.
        
        Args:
            session_name: Nombre de sesión
            
        Returns:
            Dict con volatilidad esperada, perfil de volumen, etc.
        """
        if session_name not in self.SESSION_PROFILES:
            return {}
        
        profile = self.SESSION_PROFILES[session_name]
        config = self.SESSION_CONFIG.get(session_name, {})
        
        return {
            "session_name": session_name,
            "display_name": config.get("name_display", "Unknown"),
            "pip_volatility_expected": profile["pip_volatility_avg"],
            "volume_profile": profile["volume_profile"],
            "timezone_offset": config.get("utc_offset_hours", 0),
            "trace_id": self.trace_id
        }
    
    def get_session_overlap_analysis(self, utc_time: datetime) -> Dict[str, Dict[str, Any]]:
        """
        Analiza overlaps de sesiones activas en el momento.
        Útil para detectar volatilidad alta (ej. London-NY overlap).
        
        Args:
            utc_time: Datetime en UTC
            
        Returns:
            Dict con estado activo de cada sesión
        """
        result = {}
        
        for session_name in self.SESSION_CONFIG.keys():
            is_active = self.is_session_active(session_name, utc_time)
            metrics = self.get_session_liquidity_metrics(session_name)
            
            result[session_name] = {
                "is_active": is_active,
                **metrics
            }
        
        return result
    
    def sync_ledger(self, utc_time: datetime) -> Dict[str, Any]:
        """
        Sincroniza el estado actual de sesiones en el ledger de persistencia.
        
        Args:
            utc_time: Datetime en UTC
            
        Returns:
            Dict con resultado de sincronización
        """
        active_sessions = []
        pre_market = self.get_pre_market_range(utc_time)
        
        for session_name in self.SESSION_CONFIG.keys():
            if self.is_session_active(session_name, utc_time):
                active_sessions.append(session_name)
        
        state = {
            "timestamp": utc_time.isoformat(),
            "active_sessions": active_sessions,
            "pre_market_ny": pre_market is not None,
            "trace_id": self.trace_id
        }
        
        try:
            self.storage.set_system_state("market_session_state", state)
            logger.debug(f"[{self.trace_id}] Ledger sincronizado: {active_sessions}")
        except Exception as e:
            logger.error(f"[{self.trace_id}] Error sincronizando ledger: {e}")
        
        return state
    
    def get_next_session_start(self, utc_time: datetime) -> Tuple[str, datetime]:
        """
        Obtiene la próxima sesión que abrirá.
        
        Args:
            utc_time: Datetime en UTC
            
        Returns:
            Tupla (nombre_sesión, datetime_apertura_utc)
        """
        # Orden de sesiones por apertura (Sydney → Tokyo → London → NY)
        session_order = ["ny", "sydney", "tokyo", "london"]
        
        next_session = None
        next_time = None
        
        for session_name in session_order:
            config = self.SESSION_CONFIG[session_name]
            offset = config["utc_offset_hours"]
            open_str = config["open_time"]
            
            open_hour, open_minute = self._parse_time(open_str)
            open_utc_hour, open_utc_minute = self._utc_time_from_local(
                open_hour, open_minute, offset
            )
            
            session_open = utc_time.replace(
                hour=open_utc_hour, 
                minute=open_utc_minute, 
                second=0, 
                microsecond=0
            )
            
            # Si ya pasó hoy, calcular para mañana
            if session_open <= utc_time:
                session_open += timedelta(days=1)
            
            if next_time is None or session_open < next_time:
                next_session = session_name
                next_time = session_open
        
        return next_session, next_time
