"""
Trade execution phase extracted from MainOrchestrator.run_single_cycle().

run_execute_phase → dedup, strategy auth, quality scoring, execute, ranking, stats
"""
from __future__ import annotations

import logging
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

from core_brain.orchestrators._types import ScanBundle
from core_brain.orchestrators._lifecycle import (
    is_strategy_authorized_for_execution,
    persist_session_stats_impl,
    update_all_usr_strategies_heartbeat,
)
logger = logging.getLogger(__name__)


def _default_funnel(trace_id: str | None = None) -> dict:
    return {
        "trace_id": trace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "stages": {
            "STAGE_SCAN_INPUT": {"in": 0, "out": 0},
            "STAGE_RAW_SIGNAL_GENERATION": {"in": 0, "out": 0},
            "STAGE_DEDUP_COOLDOWN": {"in": 0, "out": 0},
            "STAGE_STRATEGY_AUTH": {"in": 0, "out": 0},
            "STAGE_QUALITY_GATE": {"in": 0, "out": 0},
            "STAGE_EXECUTION_OUTCOME": {"in": 0, "out": 0},
        },
        "reasons": {},
    }


def _classify_execution_failure(reason: Any, last_rejection_reason: str) -> str:
    value = (getattr(reason, "value", None) or str(reason or "")).upper()
    last = (last_rejection_reason or "").lower()
    if "RISK" in value or "LOCKDOWN" in value or "risk" in last:
        return "executor_failed_risk"
    if (
        "CONNECTION" in value
        or "ORDER_REJECTED" in value
        or "TIMEOUT" in value
        or "BROKER" in value
        or "connector" in last
        or "broker" in last
    ):
        return "executor_failed_broker"
    return "executor_failed_unknown"


async def run_execute_phase(
    orch: "MainOrchestrator",
    signals: List[Any],
    bundle: ScanBundle,
) -> None:
    """
    Execute validated signals with full dedup / quality / feedback pipeline.

    After the loop: closed positions check, strategy ranking, stats flush.
    """
    from core_brain.execution_feedback import ExecutionFailureReason

    market_context: dict = {
        "volatility_zscore": getattr(orch, "volatility_zscore", 0.0),
        "regime": (
            getattr(orch.regime_classifier, "current_regime", "UNKNOWN")
            if orch.regime_classifier
            else "UNKNOWN"
        ),
    }
    base_funnel = getattr(getattr(orch, "signal_factory", None), "last_funnel_summary", None)
    funnel = dict(base_funnel) if isinstance(base_funnel, dict) else _default_funnel(bundle.trace_id)
    funnel.setdefault("trace_id", bundle.trace_id)
    funnel["timestamp"] = datetime.now(timezone.utc).isoformat()
    stages = funnel.setdefault("stages", {})
    default_stages = _default_funnel(bundle.trace_id)["stages"]
    for stage_name, values in default_stages.items():
        stage = stages.setdefault(stage_name, {})
        stage.setdefault("in", values["in"])
        stage.setdefault("out", values["out"])

    reasons: Counter = Counter(funnel.get("reasons") or {})
    stages["STAGE_DEDUP_COOLDOWN"]["in"] = len(signals)
    dedup_passed = 0
    auth_passed = 0
    quality_passed = 0
    execution_attempts = 0
    execution_successes = 0

    for signal in signals:
        try:
            logger.info(f"Executing signal: {signal.symbol} {signal.signal_type}")

            # PHASE 1: Deduplication check
            recent_signals = orch.storage.get_recent_sys_signals(
                symbol=signal.symbol,
                timeframe=getattr(signal, "timeframe", "M5"),
                minutes=120,
            )
            recent_signals_dicts: List[dict] = []
            for s in (recent_signals or []):
                if isinstance(s, dict):
                    recent_signals_dicts.append(s)
                elif hasattr(s, "model_dump"):
                    recent_signals_dicts.append(s.model_dump())
                elif hasattr(s, "__dict__"):
                    recent_signals_dicts.append(vars(s))

            signal_dict = (
                signal.model_dump() if hasattr(signal, "model_dump") else vars(signal)
            )
            signal_dict["signal_id"] = signal_dict.get("trace_id") or signal_dict.get("signal_id")
            signal_dict["strategy"] = signal_dict.get("strategy_id")

            dedup_decision, dedup_metadata = await orch.signal_selector.should_operate_signal(
                signal_dict, recent_signals_dicts, market_context
            )

            if dedup_decision.value == "REJECT_DUPLICATE":
                logger.warning(
                    f"Signal {signal.symbol} REJECTED — dedup: {dedup_metadata.get('reason')}"
                )
                orch.stats.usr_signals_vetoed += 1
                if orch.thought_callback:
                    await orch.thought_callback(
                        f"Señal duplicada rechazada: {signal.symbol} "
                        f"({dedup_metadata.get('category', 'unknown')})",
                        level="warning",
                        module="DEDUP",
                    )
                reasons["reject_duplicate"] += 1
                continue

            if dedup_decision.value == "REJECT_COOLDOWN":
                remaining = dedup_metadata.get("remaining_minutes", 0)
                logger.warning(
                    f"Signal {signal.symbol} en COOLDOWN por {dedup_metadata.get('failure_reason')} "
                    f"- {remaining:.1f} min restantes"
                )
                orch.stats.usr_signals_vetoed += 1
                if orch.thought_callback:
                    await orch.thought_callback(
                        f"Señal en enfriamiento: {signal.symbol} (vence en {remaining:.1f} min)",
                        level="info",
                        module="COOLDOWN",
                    )
                reasons["reject_cooldown"] += 1
                continue

            dedup_passed += 1

            # Strategy authorization (Shadow Ranking)
            is_authorized, auth_reason = is_strategy_authorized_for_execution(
                orch, signal, with_reason=True
            )
            if not is_authorized:
                logger.warning(
                    f"Signal for {signal.symbol} blocked: Strategy "
                    f"{getattr(signal, 'strategy', 'unknown')} not authorized"
                )
                orch.stats.usr_signals_vetoed += 1
                reasons[auth_reason or "strategy_not_authorized"] += 1
                continue

            auth_passed += 1

            # PHASE 4: Signal Quality Scoring
            quality_result = None
            signal_origin = getattr(signal, "origin_mode", None) or signal_dict.get("origin_mode")
            if signal_origin == "SHADOW":
                logger.debug(f"[PHASE4] SHADOW signal {signal.symbol} bypasses quality gate")
            elif orch.signal_quality_scorer:
                try:
                    signal_id = (
                        signal_dict.get("id")
                        or signal_dict.get("signal_id")
                        or signal_dict.get("trace_id")
                        or (signal_dict.get("metadata") or {}).get("signal_id")
                    )
                    if signal_id:
                        signal_dict["id"] = signal_id

                    quality_result = await orch.signal_quality_scorer.assess_signal_quality(
                        signal_dict, recent_signals_dicts, market_context
                    )
                    logger.info(
                        f"[PHASE4-QUALITY] {signal.symbol}: Grade={quality_result.grade.value} "
                        f"Score={quality_result.overall_score:.1f}% "
                        f"(Tech={quality_result.technical_score:.1f}% "
                        f"Ctx={quality_result.contextual_score:.1f}%)"
                    )

                    if quality_result.grade.value in ("B", "C"):
                        review_manager = getattr(orch, "signal_review_manager", None)
                        if not review_manager:
                            logger.warning(
                                f"Signal {signal.symbol} BLOCKED: review manager unavailable "
                                f"for grade {quality_result.grade.value}"
                            )
                            orch.stats.usr_signals_vetoed += 1
                            reasons["quality_blocked"] += 1
                            continue
                        queue_reason = (
                            "B_GRADE_MODERATE_CONFIDENCE"
                            if quality_result.grade.value == "B"
                            else "C_GRADE_LOW_CONFIDENCE"
                        )
                        queued, queue_msg = await review_manager.queue_for_review(
                            signal=signal_dict,
                            grade=quality_result.grade.value,
                            score=quality_result.overall_score,
                            reason=queue_reason,
                        )
                        if queued:
                            logger.info(
                                f"Signal {signal.symbol} queued for review: "
                                f"Grade {quality_result.grade.value} ({quality_result.overall_score:.1f}%)"
                            )
                            if orch.thought_callback:
                                await orch.thought_callback(
                                    f"Señal en revisión manual: {signal.symbol} "
                                    f"(Calificación {quality_result.grade.value})",
                                    level="info",
                                    module="PHASE4",
                                )
                        else:
                            logger.warning(f"Signal {signal.symbol} review queue failed: {queue_msg}")
                        orch.stats.usr_signals_vetoed += 1
                        reasons["quality_blocked"] += 1
                        continue

                    if quality_result.grade.value not in ("A+", "A"):
                        logger.warning(
                            f"Signal {signal.symbol} BLOCKED: Grade {quality_result.grade.value} "
                            "(threshold: A+/A only)"
                        )
                        orch.stats.usr_signals_vetoed += 1
                        if orch.thought_callback:
                            await orch.thought_callback(
                                f"Señal bloqueada por calidad: {signal.symbol} "
                                f"(Calificación {quality_result.grade.value})",
                                level="info",
                                module="PHASE4",
                            )
                        reasons["quality_blocked"] += 1
                        continue
                except Exception as e:
                    logger.error(f"[PHASE4-QUALITY] Error assessing signal quality: {e}")
                    # Graceful degradation: proceed with execution

            quality_passed += 1
            execution_attempts += 1

            success = await orch.executor.execute_signal(signal)

            if success:
                if orch.thought_callback:
                    await orch.thought_callback(
                        f"ORDEN EJECUTADA: {signal.symbol} via {signal.connector}",
                        level="success",
                        module="EXEC",
                    )
                if not getattr(orch.executor, "persists_usr_signals", False):
                    signal_id = orch.storage.save_signal(signal)
                    logger.info(f"Signal executed and persisted: {signal.symbol} (ID: {signal_id})")
                orch.stats.usr_signals_executed += 1
                execution_successes += 1
            else:
                logger.warning(f"Signal execution failed: {signal.symbol}")
                failure_reason = ExecutionFailureReason.UNKNOWN
                failure_details: dict = {
                    "signal_type": str(signal.signal_type) if signal.signal_type else None
                }
                if (
                    hasattr(orch.executor, "last_execution_response")
                    and orch.executor.last_execution_response
                ):
                    last_response = orch.executor.last_execution_response
                    if hasattr(last_response, "failure_reason") and last_response.failure_reason:
                        failure_reason = last_response.failure_reason
                    if hasattr(last_response, "failure_context") and last_response.failure_context:
                        failure_details.update(last_response.failure_context)

                await orch.execution_feedback_collector.record_failure(
                    signal_id=getattr(signal, "id", None),
                    symbol=signal.symbol,
                    strategy_name=getattr(signal, "strategy", None),
                    reason=failure_reason,
                    details=failure_details,
                )
                cooldown_result = await orch.cooldown_manager.apply_cooldown(
                    getattr(signal, "signal_id", None) or getattr(signal, "id", None),
                    signal.symbol,
                    getattr(signal, "strategy", "unknown"),
                    failure_reason.value
                    if isinstance(failure_reason, ExecutionFailureReason)
                    else str(failure_reason),
                    market_context,
                )
                logger.warning(
                    f"Cooldown applied for {signal.symbol}: {cooldown_result['cooldown_minutes']} min "
                    f"(retry #{cooldown_result['retry_count']})"
                )
                reasons[_classify_execution_failure(
                    failure_reason, getattr(orch.executor, "last_rejection_reason", "")
                )] += 1
                if cooldown_result["retry_count"] >= 4 and orch.thought_callback:
                    await orch.thought_callback(
                        f"ESCALADA: Señal {signal.symbol} ha fallado "
                        f"{cooldown_result['retry_count']} veces. Requiere revisión.",
                        level="critical",
                        module="ESCALATE",
                    )

        except Exception as e:
            logger.error(f"Error executing signal {signal.symbol}: {e}", exc_info=True)
            # ETI-ERROR-TRACKER-001: Persist error to sys_audit_logs
            try:
                orch.storage.log_audit_event(
                    user_id="SYSTEM",
                    action="SIGNAL_EXECUTION_ERROR",
                    resource=signal.symbol,
                    resource_id=signal.id if hasattr(signal, 'id') else None,
                    status="failure",
                    reason=f"{type(e).__name__}: {str(e)[:500]}",
                    trace_id=f"EXEC_ERROR_{uuid.uuid4().hex[:8]}",
                )
            except Exception as audit_err:
                logger.debug(f"[AUDIT] Could not log signal error: {audit_err}")
            orch.stats.errors_count += 1
            reasons["execution_exception"] += 1

    orch.storage.update_module_heartbeat("executor")

    # Check for closed user positions
    await orch._check_closed_usr_positions()

    # Strategy Ranking Cycle (every 5 minutes)
    from datetime import timedelta
    time_since_last_ranking = datetime.now(timezone.utc) - orch._last_ranking_cycle
    if time_since_last_ranking.total_seconds() >= orch._ranking_interval:
        try:
            logger.info("[RANKER] Starting ranking cycle (interval: 5 minutes)")
            ranking_results = orch.strategy_ranker.evaluate_all_usr_strategies()
            for strategy_id, result in ranking_results.items():
                action = result.get("action")
                if action == "promoted":
                    logger.critical(
                        f"[RANKER] PROMOTION: {strategy_id} SHADOW→LIVE "
                        f"(Trace: {result.get('trace_id')})"
                    )
                elif action == "degraded":
                    logger.critical(
                        f"[RANKER] DEGRADATION: {strategy_id} LIVE→QUARANTINE "
                        f"(Reason: {result.get('reason')}, Trace: {result.get('trace_id')})"
                    )
                elif action == "recovered":
                    logger.critical(
                        f"[RANKER] RECOVERY: {strategy_id} QUARANTINE→SHADOW "
                        f"(Trace: {result.get('trace_id')})"
                    )
            orch._last_ranking_cycle = datetime.now(timezone.utc)
        except Exception as e:
            logger.error(f"[RANKER] Error in ranking cycle (non-blocking): {e}", exc_info=False)

    # Finalize cycle
    orch._active_usr_signals.clear()
    orch.stats.cycles_completed += 1

    stages["STAGE_DEDUP_COOLDOWN"]["out"] = dedup_passed
    stages["STAGE_STRATEGY_AUTH"]["in"] = dedup_passed
    stages["STAGE_STRATEGY_AUTH"]["out"] = auth_passed
    stages["STAGE_QUALITY_GATE"]["in"] = auth_passed
    stages["STAGE_QUALITY_GATE"]["out"] = quality_passed
    stages["STAGE_EXECUTION_OUTCOME"]["in"] = execution_attempts
    stages["STAGE_EXECUTION_OUTCOME"]["out"] = execution_successes
    # Merge gatekeeper veto reasons propagated from _cycle_exec
    gk_veto_reasons: dict = getattr(orch, "_gk_veto_reasons", {})
    for code, count in gk_veto_reasons.items():
        reasons[code] += count
    orch._gk_veto_reasons = {}  # reset for next cycle

    funnel["reasons"] = dict(reasons)
    orch._latest_signal_funnel = funnel
    logger.info("[FUNNEL][CYCLE] %s", funnel)

    # HU 5.5: persist snapshot contractually (storage is SSOT, not just session_stats)
    try:
        orch.storage.persist_funnel_snapshot(funnel)
    except Exception as _snap_err:
        logger.warning("[FUNNEL][SNAPSHOT] persist_funnel_snapshot failed: %s", _snap_err)

    persist_session_stats_impl(orch)

    # Coherence monitoring
    usr_coherence_events = orch.coherence_monitor.run_once()
    if usr_coherence_events:
        for event in usr_coherence_events:
            logger.warning(
                f"Coherence inconsistency: symbol={event.symbol}, stage={event.stage}, "
                f"status={event.status}, reason={event.reason}, connector={event.connector_type}"
            )

    # Heartbeat for all strategies (Vector V4 — Monitor)
    if orch.heartbeat_monitor:
        try:
            update_all_usr_strategies_heartbeat(orch)
        except Exception as e:
            logger.warning(f"[HEARTBEAT] Error updating heartbeats: {e}")

    logger.info(f"Cycle completed. Stats: {orch.stats}")
