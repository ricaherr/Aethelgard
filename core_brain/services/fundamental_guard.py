"""
FundamentalGuardService - "Escudo de Noticias"

Sistema de veto fundamental para proteger contra noticias económicas de alto impacto.

Arquitectura:
- Consulta calendario económico de storage_manager (SSOT)
- Define ventanas de LOCKDOWN (15 min) para eventos alto impacto
- Define ventanas de VOLATILITY (30 min) para eventos impacto medio
- Integración con SignalFactory para enriquecer usr_signals con reasoning

TRACE_ID: EXEC-FUNDAMENTAL-GUARD-2026

Filtros:
- ROJO (LOCKDOWN): CPI, FOMC, NFP, ECB Rate Decision, BOJ Statement
  - Ventana: -15 min before, +15 min after event time
  - Acción: VETO TOTAL de nuevas señales
  - Log: "🔴 LOCKDOWN FUNDAMENTAL: CPI release +/- 15min"

- NARANJA (VOLATILITY): PMI, Jobless Claims, Retail Sales
  - Ventana: -30 min before, +30 min after event time
  - Acción: Solo estrategias ANT_FRAG permitidas + min_threshold += 0.15
  - Log: "🟠 VOLATILITY FILTER: PMI release - restricciones activas"
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class FundamentalGuardService:
    """
    "Escudo de Noticias" — Veto por impacto económico.
    
    Responsabilidades:
    1. Cargar calendario económico desde storage
    2. Identificar eventos alto/medio impacto
    3. Definir ventanas de veto (LOCKDOWN/VOLATILITY)
    4. Proporcionar métodos de consulta rápida (in-memory)
    5. Integración con SignalFactory para enriquecimiento de señales
    """

    # Eventos de alto impacto (LOCKDOWN)
    HIGH_IMPACT_EVENTS = {
        "CPI", "CORE CPI", "PPI", "CORE PPI",  # Inflación
        "FOMC", "ECB", "BOE", "BOJ", "RBA", "CNB",  # Bancos centrales (abreviuras)
        "NFP", "UNEMPLOYMENT", "JOBLESS",  # Empleo
        "GDP", "MANUFACTURING", "INDUSTRIAL",  # Economia
    }

    # Eventos de impacto medio (VOLATILITY)
    MEDIUM_IMPACT_EVENTS = {
        "PMI", "Manufacturing PMI", "Services PMI",
        "Initial Jobless Claims", "Continuing Jobless Claims",
        "Retail Sales", "Core Retail Sales",
        "Housing Starts", "Building Permits",
        "Durable Orders", "Factory Orders",
        "ISM Manufacturing", "ISM Non-Manufacturing",
    }

    # Ventanas de tiempo
    LOCKDOWN_WINDOW_MINUTES = 15  # ±15 min desde evento
    VOLATILITY_WINDOW_MINUTES = 30  # ±30 min desde evento

    def __init__(self, storage: StorageManager):
        """
        Inicializa FundamentalGuardService con inyección de dependencias.

        Args:
            storage: StorageManager para consultas del calendario económico
        """
        self.storage = storage
        self.calendar_cache: List[Dict] = []
        self.last_calendar_update: Optional[datetime] = None

        # Cargar calendario económico inicial
        self._refresh_calendar()

        logger.info(
            f"[FundamentalGuard] Initialized with {len(self.calendar_cache)} "
            f"economic events in cache"
        )

    def _refresh_calendar(self) -> None:
        """Recarga el calendario económico desde storage (SSOT)."""
        try:
            events = self.storage.get_economic_calendar()
            if events:
                self.calendar_cache = events
                self.last_calendar_update = datetime.now()
                logger.debug(f"[FundamentalGuard] Calendar refreshed: {len(events)} events")
            else:
                self.calendar_cache = []
                logger.debug("[FundamentalGuard] No economic events found")
        except Exception as e:
            logger.error(f"[FundamentalGuard] Failed to refresh calendar: {e}")
            self.calendar_cache = []

    def is_lockdown_period(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Determina si el mercado está en LOCKDOWN por evento alto impacto.

        Ventana: ±15 minutos desde el momento del evento.

        Args:
            symbol: Símbolo del mercado (ej: 'EUR/USD')
            current_time: Hora actual (default: datetime.now() UTC)

        Returns:
            True si está en ventana de LOCKDOWN, False en caso contrario
        """
        if not current_time:
            current_time = datetime.now()

        # Buscar eventos de alto impacto en la ventana
        for event in self.calendar_cache:
            event_impact = event.get("impact", "").upper()
            event_name = event.get("event", "").upper()

            # Solo eventos HIGH detectan LOCKDOWN
            if event_impact != "HIGH":
                continue

            # Verificar si es un evento conocido de alto impacto
            if not self._is_high_impact_event(event_name):
                continue

            # Obtener hora del evento
            try:
                event_time = event.get("time_utc")
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time)
                elif not isinstance(event_time, datetime):
                    continue

                # Calcular ventanas
                before_window = event_time - timedelta(minutes=self.LOCKDOWN_WINDOW_MINUTES)
                after_window = event_time + timedelta(minutes=self.LOCKDOWN_WINDOW_MINUTES)

                # Verificar si current_time está dentro de ventana
                if before_window <= current_time <= after_window:
                    logger.warning(
                        f"🔴 LOCKDOWN FUNDAMENTAL: {event_name} release ±{self.LOCKDOWN_WINDOW_MINUTES}min "
                        f"(Current: {current_time.isoformat()}, Event: {event_time.isoformat()})"
                    )
                    return True

            except Exception as e:
                logger.debug(f"[FundamentalGuard] Error processing event {event}: {e}")
                continue

        return False

    def is_volatility_period(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> bool:
        """
        Determina si el mercado está en VOLATILITY por evento impacto medio.

        Ventana: ±30 minutos desde el momento del evento.

        Args:
            symbol: Símbolo del mercado (ej: 'EUR/USD')
            current_time: Hora actual (default: datetime.now() UTC)

        Returns:
            True si está en ventana de VOLATILITY, False en caso contrario
        """
        if not current_time:
            current_time = datetime.now()

        # Buscar eventos de impacto medio en la ventana
        for event in self.calendar_cache:
            event_impact = event.get("impact", "").upper()
            event_name = event.get("event", "").upper()

            # Solo eventos MEDIUM detectan VOLATILITY
            if event_impact != "MEDIUM":
                continue

            # Verificar si es un evento conocido de impacto medio
            if not self._is_medium_impact_event(event_name):
                continue

            # Obtener hora del evento
            try:
                event_time = event.get("time_utc")
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time)
                elif not isinstance(event_time, datetime):
                    continue

                # Calcular ventanas
                before_window = event_time - timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES)
                after_window = event_time + timedelta(minutes=self.VOLATILITY_WINDOW_MINUTES)

                # Verificar si current_time está dentro de ventana
                if before_window <= current_time <= after_window:
                    logger.info(
                        f"🟠 VOLATILITY FILTER: {event_name} release ±{self.VOLATILITY_WINDOW_MINUTES}min "
                        f"(Current: {current_time.isoformat()}, Event: {event_time.isoformat()})"
                    )
                    return True

            except Exception as e:
                logger.debug(f"[FundamentalGuard] Error processing event {event}: {e}")
                continue

        return False

    def is_market_safe(
        self,
        symbol: str,
        current_time: Optional[datetime] = None
    ) -> Tuple[bool, str]:
        """
        Determina si el mercado es seguro para operar.

        Lógica:
        - Si está en LOCKDOWN → False "FUNDAMENTAL_LOCKDOWN: {event}"
        - Si está en VOLATILITY → True "VOLATILITY_FILTER: {event} (only ANT_FRAG allowed)"
        - Si no hay eventos → True ""

        Args:
            symbol: Símbolo del mercado
            current_time: Hora actual (default: datetime.now() UTC)

        Returns:
            Tuple[bool, str]: (is_safe, reason)
        """
        if not current_time:
            current_time = datetime.now()

        # Refrescar calendario cada vez (mantener SSOT)
        try:
            self._refresh_calendar()
        except Exception as e:
            logger.warning(f"[FundamentalGuard] Failed to refresh calendar: {e}")
            # Fallback a cache existente

        # Revisar LOCKDOWN primero (más restrictivo)
        if self.is_lockdown_period(symbol, current_time):
            event = self._get_active_event(symbol, current_time, "HIGH")
            return False, f"FUNDAMENTAL_LOCKDOWN: {event.get('event', 'Unknown')} release"

        # Revisar VOLATILITY (menos restrictivo)
        if self.is_volatility_period(symbol, current_time):
            event = self._get_active_event(symbol, current_time, "MEDIUM")
            return True, f"VOLATILITY_FILTER: {event.get('event', 'Unknown')} (only ANT_FRAG allowed)"

        # Mercado seguro
        return True, ""

    def _is_high_impact_event(self, event_name: str) -> bool:
        """Verifica si un evento está en lista de alto impacto."""
        # Búsqueda flexible (substring matching)
        event_name_upper = event_name.upper()
        for high_impact in self.HIGH_IMPACT_EVENTS:
            if high_impact in event_name_upper:
                return True
        return False

    def _is_medium_impact_event(self, event_name: str) -> bool:
        """Verifica si un evento está en lista de impacto medio."""
        # Búsqueda flexible (substring matching)
        event_name_upper = event_name.upper()
        for medium_impact in self.MEDIUM_IMPACT_EVENTS:
            if medium_impact in event_name_upper:
                return True
        return False

    def _get_active_event(
        self,
        symbol: str,
        current_time: datetime,
        impact_level: str
    ) -> Dict:
        """
        Obtiene el evento activo (dentro de ventana) más próximo.

        Args:
            symbol: Símbolo del mercado
            current_time: Hora actual
            impact_level: "HIGH" o "MEDIUM"

        Returns:
            Dict con detalles del evento
        """
        for event in self.calendar_cache:
            event_impact = event.get("impact", "").upper()
            event_name = event.get("event", "").upper()

            if event_impact != impact_level:
                continue

            try:
                event_time = event.get("time_utc")
                if isinstance(event_time, str):
                    event_time = datetime.fromisoformat(event_time)
                elif not isinstance(event_time, datetime):
                    continue

                # Determinar ventana según impacto
                window_minutes = (
                    self.LOCKDOWN_WINDOW_MINUTES
                    if impact_level == "HIGH"
                    else self.VOLATILITY_WINDOW_MINUTES
                )

                before_window = event_time - timedelta(minutes=window_minutes)
                after_window = event_time + timedelta(minutes=window_minutes)

                if before_window <= current_time <= after_window:
                    return event

            except Exception:
                continue

        # Retornar evento vacío si no hay coincidencia
        return {"event": "Unknown"}
