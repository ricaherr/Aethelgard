"""
Trade execution phase extracted from MainOrchestrator.run_single_cycle().

run_execute_phase → dedup, strategy auth, quality scoring, execute, ranking, stats
"""
from __future__ import annotations

import logging
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
                continue

            # Strategy authorization (Shadow Ranking)
            if not is_strategy_authorized_for_execution(orch, signal):
                logger.warning(
                    f"Signal for {signal.symbol} blocked: Strategy "
                    f"{getattr(signal, 'strategy', 'unknown')} not authorized"
                )
                orch.stats.usr_signals_vetoed += 1
                continue

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
                        continue
                except Exception as e:
                    logger.error(f"[PHASE4-QUALITY] Error assessing signal quality: {e}")
                    # Graceful degradation: proceed with execution

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
                if cooldown_result["retry_count"] >= 4 and orch.thought_callback:
                    await orch.thought_callback(
                        f"ESCALADA: Señal {signal.symbol} ha fallado "
                        f"{cooldown_result['retry_count']} veces. Requiere revisión.",
                        level="critical",
                        module="ESCALATE",
                    )

        except Exception as e:
            logger.error(f"Error executing signal {signal.symbol}: {e}")
            orch.stats.errors_count += 1

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
