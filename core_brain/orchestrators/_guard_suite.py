"""
Guard Suite — EDGE-IGNITION defense protocol implementations.

Extracted from MainOrchestrator to comply with .ai_rules.md §4 (500-line limit).
Pattern: module-level functions receive `orch: MainOrchestrator` via DI.

Gates:
  - PHASE-1 IntegrityGuard  (_write_integrity_veto)
  - PHASE-2 AnomalySentinel (_write_anomaly_lockdown)
  - PHASE-3 CoherenceService (_run_coherence_gate, _write_coherence_veto)
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

logger = logging.getLogger(__name__)


async def run_coherence_gate(orch: "MainOrchestrator") -> None:
    """EDGE-IGNITION-PHASE-3: Coherence Gate — model vs reality drift."""
    try:
        live_strategies = orch.storage.get_strategies_by_mode("LIVE")
        if not live_strategies:
            return

        for strategy in live_strategies:
            strategy_id = strategy.get("strategy_id")
            if not strategy_id:
                continue

            symbol = strategy_id.split("_")[0] if "_" in strategy_id else None
            veto = orch.coherence_service.check_coherence_veto(
                strategy_id=strategy_id,
                symbol=symbol,
            )
            if veto:
                trace_id = f"COH-VETO-{uuid.uuid4().hex[:8].upper()}"
                await write_coherence_veto(orch, strategy_id=strategy_id, trace_id=trace_id)

    except Exception as e:
        logger.error("[COHERENCE_GATE] Error en coherence check: %s", e, exc_info=True)


async def write_coherence_veto(orch: "MainOrchestrator", strategy_id: str, trace_id: str) -> None:
    """Persist COHERENCE_VETO and quarantine affected strategy."""
    logger.warning(
        "[COHERENCE_GATE] VETO activado — estrategia en cuarentena. "
        "strategy_id=%s | trace_id=%s",
        strategy_id,
        trace_id,
    )

    # 1. Registrar en sys_audit_logs
    try:
        conn = orch.storage._get_conn()
        conn.execute(
            """
            INSERT INTO sys_audit_logs
                (user_id, action, resource, resource_id, status, reason, trace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "system",
                "COHERENCE_VETO",
                "CoherenceService",
                strategy_id,
                "failure",
                "Coherence drift detectado. Estrategia cuarentenada por EDGE-IGNITION-PHASE-3.",
                trace_id,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.error("[COHERENCE_GATE] No se pudo escribir en sys_audit_logs: %s", exc)

    # 2. Marcar instancias shadow como QUARANTINED
    try:
        conn = orch.storage._get_conn()
        conn.execute(
            """
            UPDATE sys_shadow_instances
            SET status = 'QUARANTINED', updated_at = ?
            WHERE strategy_id = ? AND status NOT IN ('DEAD', 'PROMOTED_TO_REAL')
            """,
            (datetime.now(timezone.utc).isoformat(), strategy_id),
        )
        conn.commit()
        logger.info(
            "[COHERENCE_GATE] sys_shadow_instances de '%s' marcadas QUARANTINED.", strategy_id
        )
    except Exception as exc:
        logger.error(
            "[COHERENCE_GATE] No se pudo actualizar sys_shadow_instances: %s", exc
        )

    # 3. Actualizar execution_mode en sys_signal_ranking a QUARANTINE
    try:
        ranking = orch.storage.get_signal_ranking(strategy_id)
        if ranking:
            ranking["execution_mode"] = "QUARANTINE"
            ranking["trace_id"] = trace_id
            orch.storage.save_signal_ranking(strategy_id, ranking)
            logger.info(
                "[COHERENCE_GATE] sys_signal_ranking de '%s' → QUARANTINE.", strategy_id
            )
    except Exception as exc:
        logger.error(
            "[COHERENCE_GATE] No se pudo actualizar sys_signal_ranking: %s", exc
        )


def write_integrity_veto(orch: "MainOrchestrator", trace_id: str, checks: list) -> None:
    """Persist IntegrityGuard CRITICAL veto to sys_audit_logs."""
    failed = [c for c in checks if c.status.value == "CRITICAL"]
    reason = "; ".join(f"[{c.name}] {c.message}" for c in failed)
    audit_trace_id = f"{trace_id}:IV:{uuid.uuid4().hex[:6]}"
    logger.critical(
        "[IntegrityGuard] VETO CRÍTICO — ciclo de trading detenido. "
        "trace_id=%s | %s",
        trace_id,
        reason,
    )
    try:
        conn = orch.storage._get_conn()
        conn.execute(
            """
            INSERT INTO sys_audit_logs
                (user_id, action, resource, resource_id, status, reason, trace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "system",
                "INTEGRITY_VETO",
                "IntegrityGuard",
                "main_orchestrator",
                "failure",
                f"parent_trace_id={trace_id}; {reason}"[:1000],
                audit_trace_id,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        logger.warning(
            "[IntegrityGuard] Entrada duplicada en sys_audit_logs: %s", exc
        )
    except sqlite3.OperationalError as exc:
        logger.error(
            "[IntegrityGuard] DB locked — no se pudo persistir veto: %s", exc
        )
    except Exception as exc:
        logger.error("[IntegrityGuard] Error inesperado en sys_audit_logs: %s", exc)


async def write_anomaly_lockdown(orch: "MainOrchestrator", trace_id: str) -> None:
    """Persist AnomalySentinel LOCKDOWN and cancel pending orders."""
    logger.critical(
        "[ANOMALY_SENTINEL] LOCKDOWN activado — ciclo de trading detenido. trace_id=%s",
        trace_id,
    )

    if hasattr(orch, "executor") and hasattr(orch.executor, "cancel_all_pending_orders"):
        try:
            await orch.executor.cancel_all_pending_orders()
            logger.info("[ANOMALY_SENTINEL] Órdenes pendientes canceladas. trace_id=%s", trace_id)
        except Exception as exc:
            logger.error("[ANOMALY_SENTINEL] Error cancelando órdenes: %s", exc)

    try:
        conn = orch.storage._get_conn()
        conn.execute(
            """
            INSERT INTO sys_audit_logs
                (user_id, action, resource, resource_id, status, reason, trace_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "system",
                "ANOMALY_LOCKDOWN",
                "AnomalySentinel",
                "main_orchestrator",
                "failure",
                "Flash Crash o anomalía sistémica detectada por AnomalySentinel",
                trace_id,
            ),
        )
        conn.commit()
    except Exception as exc:
        logger.error("[ANOMALY_SENTINEL] No se pudo escribir en sys_audit_logs: %s", exc)
