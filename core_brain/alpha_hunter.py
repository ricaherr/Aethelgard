"""
AlphaHunter — Motor Autónomo de Generación de Variantes (Mutación + Auto-Promoción).
====================================================================================
Responsabilidad única: clonar una estrategia existente, variar sus
parameter_overrides mediante distribución normal alrededor de los valores
óptimos actuales, y promover automáticamente la variante al pool SHADOW si
el ScenarioBacktester retorna overall_score > 0.85.

Constraints de gobernanza:
  - MAX_SHADOW_POPULATION (default 20): no se insertan nuevas instancias si el
    pool DEMO ya alcanzó el límite de instancias activas (no terminales).
  - account_type siempre 'DEMO' para las variantes generadas.

Trace_ID: TRACE_ALPHAHUNTER_{YYYYMMDD}_{HHMMSS}_{strategy_id[:8].upper()}
RULE DB-1: todas las tablas usan prefijo sys_.
RULE ID-1: todas las decisiones generan TRACE_ID con patrón temporal.
"""

from __future__ import annotations

import logging
import random
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Estados activos: todo lo que NO sea terminal
_TERMINAL_STATUSES = ("DEAD", "PROMOTED_TO_REAL")


class AlphaHunter:
    """
    Motor de Mutación y Auto-Promoción de estrategias SHADOW.

    Flujo principal:
      1. ``mutate_parameters(strategy_id, params)``
         Clona los parámetros y aplica ruido gaussiano a cada valor numérico.
      2. ``try_promote_mutant(matrix, mutated_params)``
         Evalúa el score de la AptitudeMatrix; si supera el umbral Y el pool no
         está lleno, inserta la variante en sys_shadow_instances.

    Args:
        storage_conn:              Conexión SQLite inyectada (SSOT pattern).
        demo_account_id:           ID de la cuenta DEMO destino.
        max_shadow_population:     Límite de instancias activas simultáneas.
        promotion_score_threshold: Score mínimo *estricto* (>) para promover.
        mutation_sigma_ratio:      Desvío estándar como fracción del valor original
                                   (default 0.05 → 5 % de variación).
    """

    def __init__(
        self,
        storage_conn: sqlite3.Connection,
        demo_account_id: str,
        max_shadow_population: int = 20,
        promotion_score_threshold: float = 0.85,
        mutation_sigma_ratio: float = 0.05,
    ) -> None:
        self._conn = storage_conn
        self._demo_account_id = demo_account_id
        self._max_population = max_shadow_population
        self._promotion_threshold = promotion_score_threshold
        self._sigma_ratio = mutation_sigma_ratio

    # ── Public API ────────────────────────────────────────────────────────────

    def mutate_parameters(
        self,
        strategy_id: str,
        parameter_overrides: Dict[str, Any],
        *,
        seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Clonar parámetros y aplicar ruido gaussiano a valores numéricos.

        Para cada key en ``parameter_overrides``:
          - Si el valor es ``int`` o ``float``: aplica ``N(μ=value, σ=|value| * sigma_ratio)``.
            El resultado se recorta en 0.0 para evitar valores negativos.
          - En otro caso: se copia sin modificar.

        Args:
            strategy_id:         Identificador de la estrategia origen.
            parameter_overrides: Parámetros actuales (valores óptimos conocidos).
            seed:                Semilla aleatoria opcional (útil en tests deterministas).

        Returns:
            Dict con claves:
              ``strategy_id``         — strategy_id original (sin modificar).
              ``parameter_overrides`` — Dict mutado.
              ``trace_id``            — TRACE_ALPHAHUNTER_... de esta mutación.
        """
        rng = random.Random(seed)
        mutated: Dict[str, Any] = {}

        for key, value in parameter_overrides.items():
            if isinstance(value, bool):
                # bool es subclase de int; debe ir primero para no perturbarlo
                mutated[key] = value
            elif isinstance(value, (int, float)):
                sigma = abs(float(value)) * self._sigma_ratio
                noisy = rng.gauss(float(value), sigma)
                mutated[key] = max(0.0, noisy)
            else:
                mutated[key] = value

        trace_id = self.generate_mutation_trace_id(strategy_id)

        logger.debug(
            "[ALPHAHUNTER] Mutated strategy=%s trace_id=%s overrides=%s",
            strategy_id,
            trace_id,
            mutated,
        )

        return {
            "strategy_id": strategy_id,
            "parameter_overrides": mutated,
            "trace_id": trace_id,
        }

    def try_promote_mutant(
        self,
        matrix: Any,
        mutated_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Intentar insertar una variante mutada en sys_shadow_instances.

        Reglas de gobernanza (en orden de evaluación):
          1. ``matrix.overall_score > promotion_score_threshold``  (estricto)
          2. ``count_active_shadow_instances() < max_shadow_population``

        Si ambas se cumplen, se inserta con status='INCUBATING', account_type='DEMO'.

        Args:
            matrix:        AptitudeMatrix retornado por ScenarioBacktester.
            mutated_params: Dict de parámetros mutados a persisitr.

        Returns:
            Dict con claves:
              ``promoted``    — bool.
              ``reason``      — descripción textual del resultado.
              ``instance_id`` — UUID de la instancia creada (o None si no promovida).
              ``trace_id``    — Trace_ID de la operación.
        """
        trace_id = self.generate_mutation_trace_id(matrix.strategy_id)

        if matrix.overall_score <= self._promotion_threshold:
            reason = (
                f"score {matrix.overall_score:.4f} no supera umbral "
                f"{self._promotion_threshold:.4f}"
            )
            logger.info(
                "[ALPHAHUNTER] Mutant rejected — %s trace_id=%s", reason, trace_id
            )
            return {"promoted": False, "reason": reason, "instance_id": None, "trace_id": trace_id}

        active_count = self.count_active_shadow_instances()
        if active_count >= self._max_population:
            reason = (
                f"population_limit alcanzado: {active_count}/{self._max_population} "
                "instancias activas"
            )
            logger.warning(
                "[ALPHAHUNTER] Mutant rejected — %s trace_id=%s", reason, trace_id
            )
            return {"promoted": False, "reason": reason, "instance_id": None, "trace_id": trace_id}

        instance_id = self._insert_shadow_instance(
            strategy_id=matrix.strategy_id,
            parameter_overrides=mutated_params,
            backtest_score=matrix.overall_score,
            backtest_trace_id=matrix.trace_id,
        )

        reason = (
            f"score {matrix.overall_score:.4f} > {self._promotion_threshold:.4f}, "
            f"population {active_count + 1}/{self._max_population}"
        )
        logger.info(
            "[ALPHAHUNTER] Mutant promoted instance_id=%s strategy=%s score=%.4f trace_id=%s",
            instance_id,
            matrix.strategy_id,
            matrix.overall_score,
            trace_id,
        )
        return {
            "promoted": True,
            "reason": reason,
            "instance_id": instance_id,
            "trace_id": trace_id,
        }

    def count_active_shadow_instances(self) -> int:
        """
        Contar instancias SHADOW activas (excluye DEAD y PROMOTED_TO_REAL).

        Returns:
            Número de instancias no terminales en sys_shadow_instances.
        """
        placeholders = ",".join("?" for _ in _TERMINAL_STATUSES)
        cursor = self._conn.execute(
            f"SELECT COUNT(*) FROM sys_shadow_instances WHERE status NOT IN ({placeholders})",
            _TERMINAL_STATUSES,
        )
        return int(cursor.fetchone()[0])

    def generate_mutation_trace_id(self, strategy_id: str) -> str:
        """
        Generar TRACE_ID para una operación de mutación/promoción.

        Formato: ``TRACE_ALPHAHUNTER_{YYYYMMDD}_{HHMMSS}_{strategy_id[:8].upper()}``

        Args:
            strategy_id: Identificador de la estrategia origen.

        Returns:
            Trace_ID con patrón temporal (RULE ID-1).
        """
        now = datetime.now(timezone.utc)
        return (
            f"TRACE_ALPHAHUNTER"
            f"_{now.strftime('%Y%m%d')}"
            f"_{now.strftime('%H%M%S')}"
            f"_{strategy_id[:8].upper()}"
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _insert_shadow_instance(
        self,
        strategy_id: str,
        parameter_overrides: Dict[str, Any],
        backtest_score: float,
        backtest_trace_id: str,
    ) -> str:
        """
        Insertar una nueva instancia SHADOW en sys_shadow_instances.

        Args:
            strategy_id:         Estrategia origen.
            parameter_overrides: Parámetros mutados.
            backtest_score:      overall_score de la AptitudeMatrix.
            backtest_trace_id:   trace_id del ScenarioBacktester.

        Returns:
            instance_id (UUID) de la instancia creada.
        """
        instance_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """
            INSERT INTO sys_shadow_instances (
                instance_id, strategy_id, account_id, account_type,
                parameter_overrides, regime_filters, birth_timestamp,
                status, backtest_score, backtest_trace_id,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                instance_id,
                strategy_id,
                self._demo_account_id,
                "DEMO",
                str(parameter_overrides),
                "",
                now,
                "INCUBATING",
                backtest_score,
                backtest_trace_id,
                now,
                now,
            ),
        )
        self._conn.commit()
        return instance_id
