"""
AnomalySentinel — Lightweight Synchronous Market Anomaly Gate
=============================================================

Gate defensivo para el loop principal del orquestador.
Detecta anomalías de mercado en tiempo real usando solo la biblioteca estándar.

Responsibilities:
  - Flash_Crash_Detector: Z-Score de velocidad de precio (últimos 5-10 ticks)
  - Spread_Anomaly: spread actual > 300% del promedio histórico → WARNING
  - get_defense_protocol(): retorna NONE, WARNING o LOCKDOWN

Design constraints:
  - Usa solo statistics / math (sin pandas / numpy)
  - Sincrónico (sin async/await) — apto para uso inline en el loop
  - < 30 KB
  - Agnóstico al broker: procesa listas de dicts con precios/spreads
  - Umbrales leídos de sys_config o defaults seguros

TRACE_ID: EDGE-IGNITION-PHASE-2-ANOMALY-SENTINEL
"""
import logging
import math
import statistics
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence

logger = logging.getLogger(__name__)

# ── Defaults seguros (§3 Restricciones Técnicas) ────────────────────────────
_DEFAULT_ZSCORE_THRESHOLD = 3.5        # Flash Crash: |Z| > 3.5
_DEFAULT_SPREAD_RATIO_THRESHOLD = 3.0  # Spread > 300 % del promedio histórico
_DEFAULT_TICK_WINDOW = 10              # Ventana máxima de ticks en memoria
_MIN_TICKS_FOR_ZSCORE = 5             # Mínimo de ticks para calcular Z-Score válido


class DefenseProtocol(str, Enum):
    """Protocolo defensivo retornado por el Sentinel."""
    NONE = "NONE"
    WARNING = "WARNING"
    LOCKDOWN = "LOCKDOWN"


class AnomalySentinel:
    """
    Centinela ligero y sincrónico de anomalías de mercado.

    Uso típico en el loop del orquestador::

        # Alimentar con datos del ciclo anterior
        sentinel.push_ticks(df.tail(10).to_dict("records"))

        # Gate antes del siguiente ciclo
        protocol = sentinel.get_defense_protocol()
        if protocol == DefenseProtocol.LOCKDOWN:
            # detener ciclo
    """

    def __init__(
        self,
        storage: Optional[Any] = None,
        zscore_threshold: Optional[float] = None,
        spread_ratio_threshold: Optional[float] = None,
        tick_window: int = _DEFAULT_TICK_WINDOW,
    ) -> None:
        """
        Inicializa el Sentinel con dependencias inyectadas.

        Args:
            storage: StorageManager (opcional). Si se provee, lee umbrales de
                     ``get_dynamic_params()`` antes de usar los defaults.
            zscore_threshold: Umbral de Z-Score para Flash Crash (default 3.5).
            spread_ratio_threshold: Ratio spread/avg para WARNING (default 3.0).
            tick_window: Tamaño máximo del buffer de ticks (default 10).
        """
        params: Dict[str, Any] = {}
        if storage is not None:
            try:
                params = storage.get_dynamic_params() or {}
            except Exception:
                pass

        self.zscore_threshold: float = float(
            zscore_threshold
            if zscore_threshold is not None
            else params.get("anomaly_zscore_threshold", _DEFAULT_ZSCORE_THRESHOLD)
        )
        self.spread_ratio_threshold: float = float(
            spread_ratio_threshold
            if spread_ratio_threshold is not None
            else params.get("anomaly_spread_ratio_threshold", _DEFAULT_SPREAD_RATIO_THRESHOLD)
        )

        self._tick_window = tick_window
        self._prices: deque = deque(maxlen=tick_window)
        self._spreads: deque = deque(maxlen=tick_window)
        self.last_trace_id: str = ""
        self._last_protocol: DefenseProtocol = DefenseProtocol.NONE

        logger.info(
            "[ANOMALY_SENTINEL] Initialized. Z-Score threshold=%.1f, "
            "Spread ratio=%.1f×, Tick window=%d. "
            "Trace_ID: EDGE-IGNITION-PHASE-2-ANOMALY-SENTINEL",
            self.zscore_threshold,
            self.spread_ratio_threshold,
            tick_window,
        )

    # ── API pública ──────────────────────────────────────────────────────────

    def push_tick(self, price: float, spread: float = 0.0) -> None:
        """
        Añade un tick individual al buffer del Sentinel.

        Args:
            price: Precio de cierre o último precio disponible.
            spread: Spread actual del instrumento (en pips o puntos).
        """
        if price > 0:
            self._prices.append(float(price))
        if spread >= 0:
            self._spreads.append(float(spread))

    def push_ticks(self, ticks: Sequence[Dict[str, Any]]) -> None:
        """
        Añade en batch una secuencia de ticks desde una lista de dicts.

        Claves aceptadas para precio: ``close``, ``price``, ``bid``.
        Clave aceptada para spread:   ``spread``.

        Args:
            ticks: Lista de dicts con datos de mercado (p.ej. df.to_dict("records")).
        """
        for tick in ticks:
            price = (
                tick.get("close")
                or tick.get("price")
                or tick.get("bid")
                or 0.0
            )
            spread = tick.get("spread", 0.0)
            self.push_tick(float(price), float(spread))

    def get_defense_protocol(self) -> DefenseProtocol:
        """
        Evalúa las condiciones actuales de mercado y retorna el protocolo defensivo.

        Prioridad:
          1. LOCKDOWN — Flash Crash detectado (Z-Score ≥ threshold)
          2. WARNING  — Spread anómalo (ratio ≥ spread_ratio_threshold)
          3. NONE     — Condiciones normales

        Returns:
            DefenseProtocol: NONE, WARNING o LOCKDOWN.
        """
        trace_id = f"SEN-{uuid.uuid4().hex[:8].upper()}"
        self.last_trace_id = trace_id

        crash_protocol = self._detect_flash_crash(trace_id)
        if crash_protocol == DefenseProtocol.LOCKDOWN:
            self._last_protocol = DefenseProtocol.LOCKDOWN
            return DefenseProtocol.LOCKDOWN

        spread_protocol = self._detect_spread_anomaly(trace_id)
        if spread_protocol != DefenseProtocol.NONE:
            self._last_protocol = spread_protocol
            return spread_protocol

        self._last_protocol = DefenseProtocol.NONE
        return DefenseProtocol.NONE

    # ── Detectores internos ──────────────────────────────────────────────────

    def _detect_flash_crash(self, trace_id: str) -> DefenseProtocol:
        """
        Flash_Crash_Detector: Z-Score del retorno del último tick.

        Enfoque leave-one-out: calcula media y stdev sobre los retornos
        históricos (todos menos el último) y evalúa el último retorno
        contra esa distribución de referencia.
        Esto evita que el propio crash contamine la distribución base.

        Regla: |Z| >= zscore_threshold → LOCKDOWN
               |Z| >= zscore_threshold * 0.7 → WARNING
        """
        if len(self._prices) < _MIN_TICKS_FOR_ZSCORE:
            return DefenseProtocol.NONE

        prices = list(self._prices)
        returns = [
            (prices[i] - prices[i - 1]) / prices[i - 1]
            for i in range(1, len(prices))
            if prices[i - 1] != 0
        ]

        # Necesitamos al menos 2 retornos de referencia + 1 a evaluar
        if len(returns) < 3:
            return DefenseProtocol.NONE

        reference_returns = returns[:-1]  # Distribución histórica (sin el último)
        last_return = returns[-1]         # Retorno a evaluar

        try:
            mean_ret = statistics.mean(reference_returns)
            stdev_ret = statistics.stdev(reference_returns)
        except statistics.StatisticsError:
            return DefenseProtocol.NONE

        if stdev_ret == 0:
            return DefenseProtocol.NONE

        z_score = (last_return - mean_ret) / stdev_ret

        if abs(z_score) >= self.zscore_threshold:
            logger.critical(
                "[ANOMALY_SENTINEL] FLASH_CRASH detected. "
                "Z-Score=%.2f (threshold=%.1f), last_return=%.4f%%. "
                "Trace_ID: %s",
                z_score,
                self.zscore_threshold,
                last_return * 100,
                trace_id,
            )
            return DefenseProtocol.LOCKDOWN

        if abs(z_score) >= self.zscore_threshold * 0.7:
            logger.warning(
                "[ANOMALY_SENTINEL] Elevated volatility. Z-Score=%.2f. Trace_ID: %s",
                z_score,
                trace_id,
            )
            return DefenseProtocol.WARNING

        return DefenseProtocol.NONE

    def _detect_spread_anomaly(self, trace_id: str) -> DefenseProtocol:
        """
        Spread_Anomaly: spread actual vs. promedio histórico de la ventana.

        Regla: current_spread / avg_spread >= spread_ratio_threshold → WARNING
        """
        if len(self._spreads) < 2:
            return DefenseProtocol.NONE

        spreads = list(self._spreads)
        historical = spreads[:-1]
        current_spread = spreads[-1]

        try:
            avg_spread = statistics.mean(historical)
        except statistics.StatisticsError:
            return DefenseProtocol.NONE

        if avg_spread <= 0:
            return DefenseProtocol.NONE

        ratio = current_spread / avg_spread

        if ratio >= self.spread_ratio_threshold:
            logger.warning(
                "[ANOMALY_SENTINEL] SPREAD_ANOMALY detected. "
                "Current=%.5f, Avg=%.5f, Ratio=%.1f× (threshold=%.1f×). "
                "Trace_ID: %s",
                current_spread,
                avg_spread,
                ratio,
                self.spread_ratio_threshold,
                trace_id,
            )
            return DefenseProtocol.WARNING

        return DefenseProtocol.NONE
