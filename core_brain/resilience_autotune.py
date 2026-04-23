"""
resilience_autotune.py — ResilienceAutoTuner: calibración dinámica de parámetros.

Analiza el historial de recuperaciones LOCKDOWN/STRESSED para autoajustar umbrales,
preservando el EDGE al endurecer parámetros tras erosión post-recuperación y
suavizarlos tras falsos positivos. Cada ajuste queda auditado y persistido (SSOT).

ETI: Autoajuste Dinámico de Resiliencia — Épica E4 / HU 4.1
Trace_ID: ARCH-RESILIENCE-AUTOTUNE-V1
"""

from __future__ import annotations

import json
import logging
import math
import uuid
from typing import Any

logger = logging.getLogger(__name__)

# ── Clave SSOT en sys_config ─────────────────────────────────────────────────
PARAM_KEY = "resilience:params"

# ── Valores por defecto (espejo de constantes en resilience_manager.py) ──────
DEFAULT_PARAMS: dict[str, Any] = {
    "l0_caution_threshold": 3,
    "l0_degraded_threshold": 6,
    "correlation_window_seconds": 60.0,
    "correlation_l0_threshold": 3,
    "max_heal_retries": 3,
    "spread_cooldown_seconds": 300.0,
    "min_stability_cycles": 3,
}

# ── Límites duros para cada parámetro (lo, hi) ───────────────────────────────
PARAM_BOUNDS: dict[str, tuple[float, float]] = {
    "l0_caution_threshold": (2.0, 8.0),
    "l0_degraded_threshold": (4.0, 12.0),
    "correlation_window_seconds": (30.0, 180.0),
    "correlation_l0_threshold": (2.0, 6.0),
    "max_heal_retries": (1.0, 6.0),
    "spread_cooldown_seconds": (120.0, 900.0),
    "min_stability_cycles": (1.0, 10.0),
}

# ── Factores de ajuste ────────────────────────────────────────────────────────
_HARDEN_FACTOR = 1.15   # +15 % de conservadurismo tras erosión de EDGE
_SOFTEN_FACTOR = 0.90   # -10 % de sensibilidad tras falso positivo


class ResilienceAutoTuner:
    """
    Calibrador incremental de umbrales para ResilienceManager.

    Se invoca tras cada reversión exitosa de LOCKDOWN para evaluar si la
    recuperación fue prematura (falso positivo) o demasiado tardía (EDGE erosionado),
    y ajusta los parámetros dentro de límites acotados.

    Args:
        storage: Instancia de StorageManager (contexto DB global).
    """

    def __init__(self, storage: Any) -> None:
        self._storage = storage
        self._params: dict[str, Any] = dict(DEFAULT_PARAMS)
        self._load_params()

    # ── API pública ───────────────────────────────────────────────────────────

    def get_param(self, name: str) -> Any:
        """Retorna el valor actual (posiblemente ajustado) del parámetro."""
        return self._params.get(name, DEFAULT_PARAMS[name])

    def get_all_params(self) -> dict[str, Any]:
        """Retorna una copia del mapa completo de parámetros activos."""
        return dict(self._params)

    def record_recovery(
        self,
        stability_cycles: int,
        edge_eroded: bool,
        trace_id: str = "",
    ) -> dict[str, Any]:
        """
        Evalúa una recuperación de LOCKDOWN completada y ajusta parámetros si procede.

        Lógica de decisión:
          - edge_eroded=True                → endurecer (prioritario sobre falso positivo)
          - stability_cycles < min_cycles   → suavizar (falso positivo)
          - ninguna condición               → sin cambios (recuperación correcta)

        Args:
            stability_cycles: Nº de llamadas a try_auto_revert() antes de la reversión.
            edge_eroded:      True si la calidad de ejecución empeoró post-recuperación.
            trace_id:         Trace upstream para trazabilidad.

        Returns:
            Dict {param: nuevo_valor} de los parámetros modificados (vacío si ninguno).
        """
        tid = trace_id or str(uuid.uuid4())

        if edge_eroded:
            return self._harden(tid, stability_cycles)

        false_positive = stability_cycles < int(self._params["min_stability_cycles"])
        if false_positive:
            return self._soften(tid, stability_cycles)

        return {}

    # ── Ajustes internos ──────────────────────────────────────────────────────

    def _harden(self, trace_id: str, cycles: int) -> dict[str, Any]:
        """Aumenta umbrales y cooldowns para hacer el sistema más conservador."""
        targets = [
            "l0_caution_threshold",
            "l0_degraded_threshold",
            "min_stability_cycles",
            "spread_cooldown_seconds",
        ]
        changes = self._apply_factor(targets, _HARDEN_FACTOR)
        reason = (
            f"EDGE erosionado post-recuperación (cycles={cycles}). "
            f"Endurecimiento de parámetros +{int((_HARDEN_FACTOR - 1) * 100)}%."
        )
        self._persist_adjustment(trace_id, reason, changes)
        logger.warning("[AutoTune][HARDEN] %s | delta=%s", reason, changes)
        return changes

    def _soften(self, trace_id: str, cycles: int) -> dict[str, Any]:
        """Reduce umbrales para disminuir la frecuencia de LOCKDOWN por falsos positivos."""
        targets = [
            "l0_caution_threshold",
            "l0_degraded_threshold",
            "min_stability_cycles",
        ]
        changes = self._apply_factor(targets, _SOFTEN_FACTOR)
        reason = (
            f"Falso positivo detectado (cycles={cycles} < min={int(self._params['min_stability_cycles'])}). "
            f"Suavizado de parámetros -{int((1 - _SOFTEN_FACTOR) * 100)}%."
        )
        self._persist_adjustment(trace_id, reason, changes)
        logger.info("[AutoTune][SOFTEN] %s | delta=%s", reason, changes)
        return changes

    def _apply_factor(
        self,
        param_names: list[str],
        factor: float,
    ) -> dict[str, Any]:
        """
        Multiplica los parámetros por el factor dado, respeta límites y actualiza _params.

        Para parámetros enteros usa math.ceil (endurecer, factor>1) o math.floor
        (suavizar, factor<1) para garantizar al menos un cambio unitario.

        Returns:
            Dict con solo los parámetros que cambiaron de valor.
        """
        is_harden = factor >= 1.0
        changes: dict[str, Any] = {}
        for name in param_names:
            old_val = self._params[name]
            raw = old_val * factor
            lo, hi = PARAM_BOUNDS[name]
            clamped = max(lo, min(hi, raw))
            if isinstance(DEFAULT_PARAMS[name], int):
                new_val: Any = math.ceil(clamped) if is_harden else math.floor(clamped)
            else:
                new_val = clamped
            if new_val != old_val:
                self._params[name] = new_val
                changes[name] = new_val
        return changes

    # ── Persistencia ──────────────────────────────────────────────────────────

    def _load_params(self) -> None:
        """Carga parámetros persistidos desde sys_config; usa defaults si falla."""
        try:
            stored = self._storage.get_resilience_params()
            for key, val in stored.items():
                if key in DEFAULT_PARAMS:
                    self._params[key] = val
        except Exception as exc:
            logger.warning("[AutoTune] No se pudieron cargar parámetros persistidos: %s", exc)

    def _persist_adjustment(
        self,
        trace_id: str,
        reason: str,
        changes: dict[str, Any],
    ) -> None:
        """Guarda el estado actualizado en storage (fire-and-forget)."""
        if not changes:
            return
        try:
            self._storage.save_resilience_params(
                params=self._params,
                trace_id=trace_id,
                reason=reason,
            )
        except Exception as exc:
            logger.warning("[AutoTune] No se pudo persistir ajuste: %s", exc)
