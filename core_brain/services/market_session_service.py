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
from datetime import datetime, timedelta, timezone, time
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
    
    # Definición canónica de sesiones (hora local de mercado + timezone IANA)
    SESSION_CONFIG = {
        "sydney": {
            "timezone": "Australia/Sydney",
            "local_open": "07:00",
            "local_close": "16:00",
            "name_display": "Sydney"
        },
        "tokyo": {
            "timezone": "Asia/Tokyo",
            "local_open": "09:00",
            "local_close": "18:00",
            "name_display": "Tokyo"
        },
        "london": {
            "timezone": "Europe/London",
            "local_open": "08:00",
            "local_close": "17:00",
            "name_display": "London"
        },
        "ny": {
            "timezone": "America/New_York",
            "local_open": "08:00",
            "local_close": "17:00",
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
            params = self.storage.get_dynamic_params() if self.storage else {}
            if isinstance(params, dict) and "market_sessions" in params:
                return self._normalize_session_config(params["market_sessions"])
        except Exception as e:
            logger.debug(f"Could not load session config from storage: {e}")
        
        return self._normalize_session_config(self.SESSION_CONFIG)

    def _normalize_session_config(
        self, raw_config: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Dict[str, Any]]:
        """Normaliza configuraciones legacy a la forma canónica timezone/local_open/local_close."""
        normalized: Dict[str, Dict[str, Any]] = {}

        for session_name, default_config in self.SESSION_CONFIG.items():
            source = raw_config.get(session_name, {}) if isinstance(raw_config, dict) else {}

            normalized[session_name] = {
                "timezone": source.get("timezone", default_config["timezone"]),
                "local_open": source.get(
                    "local_open",
                    source.get("open_time", source.get("open", default_config["local_open"])),
                ),
                "local_close": source.get(
                    "local_close",
                    source.get("close_time", source.get("close", default_config["local_close"])),
                ),
                "name_display": source.get("name_display", default_config["name_display"]),
            }

        return normalized
    
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
    
    def _ensure_utc_datetime(self, utc_time: datetime) -> datetime:
        """Garantiza un datetime aware en UTC."""
        if utc_time.tzinfo is None:
            return utc_time.replace(tzinfo=timezone.utc)
        return utc_time.astimezone(timezone.utc)

    def _build_session_window_utc(
        self, session_config: Dict[str, Any], local_date: datetime.date
    ) -> Tuple[datetime, datetime]:
        """Construye una ventana local de sesión y la convierte a UTC."""
        session_tz = ZoneInfo(session_config["timezone"])
        open_hour, open_minute = self._parse_time(session_config["local_open"])
        close_hour, close_minute = self._parse_time(session_config["local_close"])

        session_open_local = datetime.combine(
            local_date,
            time(open_hour, open_minute),
            tzinfo=session_tz,
        )

        session_close_date = local_date
        if (close_hour, close_minute) <= (open_hour, open_minute):
            session_close_date += timedelta(days=1)

        session_close_local = datetime.combine(
            session_close_date,
            time(close_hour, close_minute),
            tzinfo=session_tz,
        )

        return (
            session_open_local.astimezone(timezone.utc),
            session_close_local.astimezone(timezone.utc),
        )

    def get_active_sessions_utc(self, utc_time: datetime) -> List[str]:
        """Retorna la lista de sesiones activas en un instante UTC concreto."""
        utc_time = self._ensure_utc_datetime(utc_time)
        session_config = self._load_session_config()

        return [
            session_name
            for session_name in session_config.keys()
            if self.is_session_active(session_name, utc_time)
        ]
    
    def is_session_active(self, session_name: str, utc_time: datetime) -> bool:
        """
        Determina si una sesión está activa en un momento específico UTC.
        
        Args:
            session_name: Nombre de sesión ("sydney", "tokyo", "london", "ny")
            utc_time: Datetime en UTC
            
        Returns:
            True si la sesión está activa, False en caso contrario
        """
        session_config = self._load_session_config()

        if session_name not in session_config:
            return False

        utc_time = self._ensure_utc_datetime(utc_time)
        config = session_config[session_name]
        local_dt = utc_time.astimezone(ZoneInfo(config["timezone"]))

        for day_offset in (0, -1):
            candidate_date = local_dt.date() + timedelta(days=day_offset)
            session_open_utc, session_close_utc = self._build_session_window_utc(
                config, candidate_date
            )
            if session_open_utc <= utc_time < session_close_utc:
                return True

        return False
    
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
        
        utc_time = self._ensure_utc_datetime(utc_time)
        config = self._load_session_config()["ny"]
        ny_timezone = ZoneInfo(config["timezone"])
        open_hour, open_minute = self._parse_time(config["local_open"])
        local_now = utc_time.astimezone(ny_timezone)

        ny_open_local = datetime.combine(
            local_now.date(),
            time(open_hour, open_minute),
            tzinfo=ny_timezone,
        )

        if local_now >= ny_open_local:
            ny_open_local += timedelta(days=1)

        ny_open_today_utc = ny_open_local.astimezone(timezone.utc)
        
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
        config = self._load_session_config().get(session_name, {})
        timezone_name = config.get("timezone", "UTC")
        offset_hours = (
            datetime.now(ZoneInfo(timezone_name)).utcoffset().total_seconds() / 3600
            if config
            else 0
        )
        
        return {
            "session_name": session_name,
            "display_name": config.get("name_display", "Unknown"),
            "pip_volatility_expected": profile["pip_volatility_avg"],
            "volume_profile": profile["volume_profile"],
            "timezone": timezone_name,
            "timezone_offset": offset_hours,
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
        session_config = self._load_session_config()
        active_sessions = set(self.get_active_sessions_utc(utc_time))

        for session_name in session_config.keys():
            is_active = session_name in active_sessions
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
        active_sessions = self.get_active_sessions_utc(utc_time)
        pre_market = self.get_pre_market_range(utc_time)

        state = {
            "timestamp": utc_time.isoformat(),
            "active_sessions": active_sessions,
            "pre_market_ny": pre_market is not None,
            "trace_id": self.trace_id
        }
        
        try:
            self.storage.set_sys_config("market_session_state", state)
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
        utc_time = self._ensure_utc_datetime(utc_time)
        session_config = self._load_session_config()

        # Orden de sesiones por apertura (Sydney → Tokyo → London → NY)
        session_order = ["ny", "sydney", "tokyo", "london"]
        
        next_session = None
        next_time = None
        
        for session_name in session_order:
            config = session_config[session_name]
            session_tz = ZoneInfo(config["timezone"])
            open_hour, open_minute = self._parse_time(config["local_open"])
            local_now = utc_time.astimezone(session_tz)

            session_open_local = datetime.combine(
                local_now.date(),
                time(open_hour, open_minute),
                tzinfo=session_tz,
            )

            if session_open_local <= local_now:
                session_open_local += timedelta(days=1)

            session_open = session_open_local.astimezone(timezone.utc)
            
            if next_time is None or session_open < next_time:
                next_session = session_name
                next_time = session_open
        
        return next_session, next_time
