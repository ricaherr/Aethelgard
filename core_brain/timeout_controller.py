"""
TimeoutController — Dynamic Timeout Calibration for EDGE Operations
====================================================================
Ajusta el timeout de operaciones EDGE de forma dinámica en función de:

- Modo operacional actual (LIVE_ACTIVE / SHADOW_ACTIVE / BACKTEST_ONLY).
- Latencia observada del proveedor de datos.
- Disponibilidad de proveedores (degradación → más tolerancia).
- Configuración persistida en BD (``sys_config.edge_timeout_*``).

Sigue Regla §7 (Auto-Calibración) y §1 (Agnosticismo de infraestructura).
"""
from __future__ import annotations

import logging
from typing import Optional

from data_vault.storage import StorageManager

logger: logging.Logger = logging.getLogger(__name__)


class TimeoutController:
    """
    Controlador de timeout dinámico para operaciones EDGE.

    Expone un único método público principal: ``get_timeout(context)``.
    Todos los valores base se leen desde ``sys_config`` en BD; el código
    solo provee defaults de último recurso.

    Ciclo de auto-calibración
    -------------------------
    1. Leer base desde BD (``edge_timeout_{context}``).
    2. Aplicar factor de latencia si se ha registrado latencia observada.
    3. Retornar valor entero en segundos.
    """

    # Defaults de último recurso por contexto/modo (segundos)
    _MODE_DEFAULTS: dict[str, int] = {
        "LIVE_ACTIVE":    30,
        "SHADOW_ACTIVE":  60,
        "BACKTEST_ONLY": 120,
        "DEFAULT":        30,
    }

    # Límites absolutos (segundos) para evitar bloqueos o timeouts prematuros
    _MIN_TIMEOUT:  int = 5
    _MAX_TIMEOUT: int = 300

    def __init__(self, storage: Optional[StorageManager] = None) -> None:
        """
        Inicializa el TimeoutController.

        Args:
            storage: ``StorageManager`` inyectado (DI).  Si es ``None``,
                     el controlador opera solo con defaults de código.
        """
        self.storage = storage
        self._latency_ms: float = 0.0

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def get_timeout(self, context: str = "DEFAULT") -> int:
        """
        Retorna el timeout apropiado (en segundos) para el contexto dado.

        Orden de prioridad:
        1. Valor en BD (``sys_config.edge_timeout_{context.lower()}``)
        2. Ajuste por latencia observada
        3. Default por modo operacional

        Args:
            context: Nombre del contexto/modo.  Valores reconocidos:
                     ``"LIVE_ACTIVE"``, ``"SHADOW_ACTIVE"``,
                     ``"BACKTEST_ONLY"``, ``"DEFAULT"``.

        Returns:
            Timeout en segundos, acotado a [_MIN_TIMEOUT, _MAX_TIMEOUT].
        """
        base = self._get_base_from_db(context)
        adjusted = self._adjust_for_latency(base)
        clamped = max(self._MIN_TIMEOUT, min(adjusted, self._MAX_TIMEOUT))
        return clamped

    def record_latency(self, latency_ms: float) -> None:
        """
        Registra la latencia observada del proveedor para calibración.

        Args:
            latency_ms: Latencia de la última operación en milisegundos.
        """
        if latency_ms < 0:
            return
        self._latency_ms = latency_ms
        logger.debug("[TimeoutController] Latencia registrada: %.0f ms", latency_ms)

    def get_current_latency_ms(self) -> float:
        """Retorna la última latencia registrada (ms). Solo lectura."""
        return self._latency_ms

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _get_base_from_db(self, context: str) -> int:
        """
        Lee el timeout base desde ``sys_config`` en BD.

        Clave buscada: ``edge_timeout_{context.lower()}``.
        Retorna el default de código si la clave no existe o la BD falla.
        """
        if self.storage is None:
            return self._MODE_DEFAULTS.get(context, self._MODE_DEFAULTS["DEFAULT"])

        try:
            cfg = self.storage.get_sys_config()
            key = f"edge_timeout_{context.lower()}"
            raw = cfg.get(key)
            if raw is not None:
                value = int(raw)
                logger.debug(
                    "[TimeoutController] Base desde BD para '%s': %ds", context, value
                )
                return value
        except Exception as exc:
            logger.debug("[TimeoutController] Error leyendo BD: %s — usando default", exc)

        return self._MODE_DEFAULTS.get(context, self._MODE_DEFAULTS["DEFAULT"])

    def _adjust_for_latency(self, base_seconds: int) -> int:
        """
        Ajusta el timeout base en función de la latencia observada.

        Lógica:
        - Latencia ≤ 0 → sin ajuste.
        - Latencia > 0 → factor = 1 + (latencia_s / 10), acotado a [1, 3].
          Ejemplo: 500 ms → factor 1.05 (ajuste mínimo).
                  5 000 ms → factor 1.5  (50% más).
                  30 000 ms → factor 3.0 (triple, máx).

        Args:
            base_seconds: Timeout base en segundos.

        Returns:
            Timeout ajustado en segundos.
        """
        if self._latency_ms <= 0:
            return base_seconds

        latency_s = self._latency_ms / 1000.0
        factor = min(1.0 + (latency_s / 10.0), 3.0)
        adjusted = int(base_seconds * factor)

        if adjusted != base_seconds:
            logger.debug(
                "[TimeoutController] Ajuste por latencia: %ds → %ds (latencia=%.0f ms, factor=%.2f)",
                base_seconds,
                adjusted,
                self._latency_ms,
                factor,
            )

        return adjusted
