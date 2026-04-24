"""
StrategyPendingDiagnosticsService — HU 3.1
===========================================

Detecta estrategias en estado LOGIC_PENDING, ejecuta diagnósticos automáticos
e intenta autocorrección. Si no es posible resolver, almacena el diagnóstico
en la DB para que la UI lo muestre con acción sugerida.

Causas diagnosticadas:
- MISSING_CLASS_FILE   → class_file apunta a un archivo inexistente
- MISSING_LOGIC        → estrategia JSON_SCHEMA sin campo logic definido
- INVALID_LOGIC_JSON   → campo logic no parseable como dict válido
- MISSING_SCHEMA_FILE  → schema_file apunta a un archivo inexistente
- NEEDS_IMPLEMENTATION → nota explícita en readiness_notes sin fix automático
- UNKNOWN              → causa no determinada

Auto-fix aplicado cuando:
- El archivo class_file o schema_file YA existe (fue añadido externamente)
  → promueve a READY_FOR_ENGINE
- El campo logic tiene JSON válido ahora
  → promueve a READY_FOR_ENGINE

Trace_ID: ETI-E3-HU3.1
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).parent.parent


@dataclass
class StrategyDiagnosis:
    """Resultado del diagnóstico de una estrategia LOGIC_PENDING."""
    class_id: str
    mnemonic: str
    strategy_type: str
    readiness: str
    cause: str
    cause_detail: str
    suggestion: str
    auto_fixed: bool
    new_readiness: str
    last_checked: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "class_id": self.class_id,
            "mnemonic": self.mnemonic,
            "strategy_type": self.strategy_type,
            "readiness": self.readiness,
            "cause": self.cause,
            "cause_detail": self.cause_detail,
            "suggestion": self.suggestion,
            "auto_fixed": self.auto_fixed,
            "new_readiness": self.new_readiness,
            "last_checked": self.last_checked,
        }


class StrategyPendingDiagnosticsService:
    """
    Servicio que diagnostica y autocorrige estrategias LOGIC_PENDING.

    Uso:
        service = StrategyPendingDiagnosticsService(storage)
        results = service.run_full_cycle()
    """

    def __init__(self, storage: Any) -> None:
        self._storage = storage

    # ──────────────────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────────────────

    def run_full_cycle(self) -> List[StrategyDiagnosis]:
        """
        Ejecuta diagnóstico completo sobre todas las estrategias LOGIC_PENDING.
        Persiste el resultado en DB y retorna la lista de diagnósticos.
        """
        pending = self._storage.get_pending_strategies()
        results: List[StrategyDiagnosis] = []

        for strategy in pending:
            diagnosis = self._diagnose(strategy)
            self._persist_diagnosis(diagnosis)
            results.append(diagnosis)
            if diagnosis.auto_fixed:
                logger.info(
                    "[PENDING_DIAGNOSTICS] Auto-fixed %s → %s",
                    diagnosis.class_id,
                    diagnosis.new_readiness,
                )
            else:
                logger.warning(
                    "[PENDING_DIAGNOSTICS] Unresolved %s — cause: %s",
                    diagnosis.class_id,
                    diagnosis.cause,
                )

        return results

    def diagnose_one(self, class_id: str) -> Optional[StrategyDiagnosis]:
        """Diagnostica una estrategia específica y persiste el resultado."""
        strategy = self._storage.get_strategy(class_id)
        if strategy is None:
            return None
        if strategy.get("readiness") != "LOGIC_PENDING":
            return None
        diagnosis = self._diagnose(strategy)
        self._persist_diagnosis(diagnosis)
        return diagnosis

    # ──────────────────────────────────────────────────────────────────────────
    # Internal diagnostics
    # ──────────────────────────────────────────────────────────────────────────

    def _diagnose(self, strategy: Dict[str, Any]) -> StrategyDiagnosis:
        class_id = strategy.get("class_id", "")
        mnemonic = strategy.get("mnemonic", class_id)
        strategy_type = strategy.get("type", "PYTHON_CLASS")
        readiness_notes = strategy.get("readiness_notes") or ""

        cause, cause_detail, suggestion = self._detect_cause(strategy)
        auto_fixed, new_readiness = self._attempt_auto_fix(strategy, cause)

        return StrategyDiagnosis(
            class_id=class_id,
            mnemonic=mnemonic,
            strategy_type=strategy_type,
            readiness="LOGIC_PENDING",
            cause=cause,
            cause_detail=cause_detail,
            suggestion=suggestion,
            auto_fixed=auto_fixed,
            new_readiness=new_readiness,
        )

    def _detect_cause(
        self, strategy: Dict[str, Any]
    ) -> tuple[str, str, str]:
        """Retorna (cause, cause_detail, suggestion)."""
        strategy_type = strategy.get("type", "PYTHON_CLASS")
        class_file = strategy.get("class_file")
        schema_file = strategy.get("schema_file")
        logic = strategy.get("logic")
        readiness_notes = strategy.get("readiness_notes") or ""

        # readiness_notes con señal explícita tiene la mayor prioridad
        if readiness_notes:
            notes_lower = readiness_notes.lower()
            if any(kw in notes_lower for kw in ("refinement", "implementa", "pendiente", "todo", "wip")):
                return (
                    "NEEDS_IMPLEMENTATION",
                    f"Nota de implementación pendiente: {readiness_notes}",
                    "Completa la implementación de la lógica indicada en las notas.",
                )

        if strategy_type == "PYTHON_CLASS":
            if not class_file:
                return (
                    "MISSING_CLASS_FILE",
                    "El campo class_file no está definido en la estrategia.",
                    "Define class_file con la ruta relativa al archivo Python de la estrategia.",
                )
            resolved = _PROJECT_ROOT / class_file
            if not resolved.exists():
                return (
                    "MISSING_CLASS_FILE",
                    f"El archivo '{class_file}' no existe en el proyecto.",
                    f"Crea el archivo '{class_file}' con la clase de la estrategia.",
                )

        if strategy_type == "JSON_SCHEMA":
            if schema_file:
                resolved = _PROJECT_ROOT / schema_file
                if not resolved.exists():
                    return (
                        "MISSING_SCHEMA_FILE",
                        f"El archivo de schema '{schema_file}' no existe.",
                        f"Crea el schema JSON en '{schema_file}'.",
                    )
            if logic is None:
                return (
                    "MISSING_LOGIC",
                    "El campo 'logic' está vacío. La estrategia no tiene lógica definida.",
                    "Define el campo 'logic' con el JSON de condiciones entry/exit de la estrategia.",
                )
            if not isinstance(logic, dict):
                try:
                    json.loads(logic)
                except (TypeError, ValueError, json.JSONDecodeError):
                    return (
                        "INVALID_LOGIC_JSON",
                        "El campo 'logic' no es un JSON válido.",
                        "Corrige el campo 'logic' para que sea un objeto JSON válido con entry_conditions y exit_conditions.",
                    )

        return (
            "UNKNOWN",
            readiness_notes or "Sin información adicional disponible.",
            "Revisa la configuración de la estrategia y sus dependencias.",
        )

    def _attempt_auto_fix(
        self, strategy: Dict[str, Any], cause: str
    ) -> tuple[bool, str]:
        """
        Intenta autocorrección. Retorna (auto_fixed, new_readiness).
        Solo promueve a READY_FOR_ENGINE si TODAS las validaciones pasan.
        Causa NEEDS_IMPLEMENTATION requiere intervención humana, no tiene auto-fix.
        """
        if cause == "NEEDS_IMPLEMENTATION":
            return False, "LOGIC_PENDING"

        strategy_type = strategy.get("type", "PYTHON_CLASS")

        if strategy_type == "PYTHON_CLASS":
            class_file = strategy.get("class_file")
            if class_file and (_PROJECT_ROOT / class_file).exists():
                return True, "READY_FOR_ENGINE"

        if strategy_type == "JSON_SCHEMA":
            logic = strategy.get("logic")
            schema_file = strategy.get("schema_file")
            schema_ok = (not schema_file) or (_PROJECT_ROOT / schema_file).exists()
            logic_ok = isinstance(logic, dict) and bool(logic)
            if schema_ok and logic_ok:
                return True, "READY_FOR_ENGINE"

        return False, "LOGIC_PENDING"

    # ──────────────────────────────────────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────────────────────────────────────

    def _persist_diagnosis(self, diagnosis: StrategyDiagnosis) -> None:
        """Persiste el diagnóstico codificado en readiness_notes como JSON."""
        notes_payload = json.dumps({
            "cause": diagnosis.cause,
            "cause_detail": diagnosis.cause_detail,
            "suggestion": diagnosis.suggestion,
            "auto_fixed": diagnosis.auto_fixed,
            "last_checked": diagnosis.last_checked,
        })
        self._storage.update_strategy_readiness(
            class_id=diagnosis.class_id,
            readiness=diagnosis.new_readiness,
            readiness_notes=notes_payload,
        )
