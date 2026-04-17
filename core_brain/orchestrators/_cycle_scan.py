"""
Cycle pre-phase and scan-phase extracted from MainOrchestrator.run_single_cycle().

run_pre_phase  → background tasks, module toggles, guards → returns False to abort cycle
run_scan_phase → OPTION-A orchestrated scan, snapshot building, UI mapping → ScanBundle or None
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from core_brain.orchestrators._types import PriceSnapshot, ScanBundle
from core_brain.services.ui_mapping_service import _normalize_structure_confidence
from core_brain.orchestrators._background_tasks import (
    check_and_run_weekly_dedup_learning,
    check_and_run_weekly_shadow_evolution,
    consume_oem_repair_flags,
    check_closed_usr_positions,
)
from core_brain.orchestrators._scan_methods import (
    update_regime_from_scan,
    persist_scan_telemetry,
    get_scan_schedule,
    should_scan_now,
    request_scan,
)

logger = logging.getLogger(__name__)


# Reuse the canonical normalizer as single SSOT for runtime confidence contract.
_normalize_ui_structure_confidence = _normalize_structure_confidence


class CpuPressureState(Enum):
    NORMAL = "NORMAL"
    THROTTLED = "THROTTLED"
    VETO = "VETO"


def _evaluate_cpu_pressure(orch: Any, dyn: Dict[str, Any]) -> CpuPressureState:
    """Evaluate CPU pressure using a sliding average persisted on orchestrator state."""
    from core_brain import main_orchestrator as main_orchestrator_module

    raw_window_size = dyn.get("cpu_pressure_window_size", 5)
    try:
        window_size = max(1, int(raw_window_size))
    except (TypeError, ValueError):
        window_size = 5

    existing_window = getattr(orch, "_cpu_pressure_window", None)
    if not isinstance(existing_window, deque) or existing_window.maxlen != window_size:
        seed_values = list(existing_window) if isinstance(existing_window, deque) else []
        existing_window = deque(seed_values[-window_size:], maxlen=window_size)
        orch._cpu_pressure_window = existing_window

    current_cpu = float(main_orchestrator_module.psutil.cpu_percent(interval=None))
    existing_window.append(current_cpu)
    avg_cpu = sum(existing_window) / len(existing_window)

    try:
        throttle_threshold = float(dyn.get("cpu_throttle_threshold", 75))
    except (TypeError, ValueError):
        throttle_threshold = 75.0
    try:
        veto_threshold = float(dyn.get("cpu_veto_threshold", 90))
    except (TypeError, ValueError):
        veto_threshold = 90.0

    if avg_cpu >= veto_threshold:
        return CpuPressureState.VETO
    if avg_cpu >= throttle_threshold:
        return CpuPressureState.THROTTLED
    return CpuPressureState.NORMAL


def _get_phase_timeout_seconds(orch: Any, key: str, default: float) -> float:
    """Read per-phase timeout from sys_config with safe fallback."""
    try:
        sys_config = orch.storage.get_sys_config() or {}
        value = sys_config.get(key, default)
        timeout_value = float(value)
        if timeout_value <= 0:
            return default
        return timeout_value
    except Exception:
        return default


def _record_phase_timeout(orch: Any, phase: str, timeout_s: float) -> None:
    """Emit structured timeout telemetry to logs + sys_audit_logs + sys_config."""
    timeout_payload = {
        "phase": phase,
        "timeout_s": timeout_s,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    logger.warning(
        "[TIMEOUT] phase=%s exceeded %.2fs — cycle continues in fail-safe mode",
        phase,
        timeout_s,
    )

    try:
        orch.storage.log_audit_event(
            user_id="SYSTEM",
            action="PHASE_TIMEOUT",
            resource="MainOrchestrator",
            resource_id=phase,
            status="failure",
            reason=f"Timeout in phase={phase} after {timeout_s:.2f}s",
            trace_id=f"TIMEOUT_{phase}_{uuid.uuid4().hex[:8].upper()}",
        )
    except Exception as exc:
        logger.debug("[TIMEOUT] Could not write audit event: %s", exc)

    try:
        orch.storage.update_sys_config({"last_phase_timeout": timeout_payload})
    except Exception as exc:
        logger.debug("[TIMEOUT] Could not persist timeout payload to sys_config: %s", exc)


def _db_backpressure_state(orch: Any) -> Dict[str, Any]:
    """
    Evaluate DB transaction latency and decide whether scan_request should pause.

    Returns a dict with:
        active        — True when backpressure guard should engage
        threshold_ms  — configured threshold
        observed_ms   — max(avg_ms, last_ms, p95_ms) from the rolling window
        p95_ms        — 95th-percentile latency from the rolling window
        count         — total samples in the window
        by_operation  — per-origin breakdown dict (empty if unavailable)
    """
    default_threshold_ms = 200.0
    try:
        sys_config = orch.storage.get_sys_config() or {}
    except Exception:
        sys_config = {}

    try:
        threshold_ms = float(sys_config.get("scan_backpressure_latency_ms", default_threshold_ms))
    except (TypeError, ValueError):
        threshold_ms = default_threshold_ms

    metrics: Dict[str, Any] = {}
    if hasattr(orch.storage, "get_db_transaction_metrics"):
        try:
            metrics = orch.storage.get_db_transaction_metrics() or {}
        except Exception:
            metrics = {}

    global_metrics = metrics.get("global") if isinstance(metrics, dict) else None
    if not isinstance(global_metrics, dict):
        return {
            "active": False,
            "threshold_ms": threshold_ms,
            "observed_ms": 0.0,
            "p95_ms": 0.0,
            "count": 0,
            "by_operation": {},
        }

    avg_ms = float(global_metrics.get("avg_ms", 0.0) or 0.0)
    last_ms = float(global_metrics.get("last_ms", 0.0) or 0.0)
    p95_ms = float(global_metrics.get("p95_ms", 0.0) or 0.0)
    count = int(global_metrics.get("count", 0) or 0)
    # Use the most conservative signal: whichever of avg/last/p95 is highest
    observed = max(avg_ms, last_ms, p95_ms)

    by_operation: Dict[str, Any] = {}
    if isinstance(metrics.get("by_operation"), dict):
        by_operation = metrics["by_operation"]

    return {
        "active": count > 0 and observed >= threshold_ms,
        "threshold_ms": threshold_ms,
        "observed_ms": observed,
        "p95_ms": p95_ms,
        "count": count,
        "by_operation": by_operation,
    }


def _handle_consecutive_backpressure(orch: Any, backpressure: Dict[str, Any]) -> None:
    """
    Track consecutive scan_backpressure activations and escalate to CRITICAL when
    the configurable threshold is reached.  Writes:
      - orch._consecutive_scan_backpressure (int counter, reset on clear)
      - sys_config["oem_scan_backpressure_consecutive"] — read by OEM check
    Fires a SYSTEM_STRESS notification on first CRITICAL crossing only.
    """
    try:
        sys_config = orch.storage.get_sys_config() or {}
    except Exception:
        sys_config = {}

    try:
        crit_threshold = int(sys_config.get("scan_backpressure_critical_threshold", 3))
    except (TypeError, ValueError):
        crit_threshold = 3

    counter = int(getattr(orch, "_consecutive_scan_backpressure", 0))

    if backpressure.get("active"):
        counter += 1
        orch._consecutive_scan_backpressure = counter
        logger.info(
            "[SCAN_BACKPRESSURE] Consecutive activations: %d (critical_threshold=%d)",
            counter,
            crit_threshold,
        )
        try:
            orch.storage.update_sys_config({"oem_scan_backpressure_consecutive": counter})
        except Exception as exc:
            logger.debug("[SCAN_BACKPRESSURE] Could not persist consecutive counter: %s", exc)

        if counter == crit_threshold:
            logger.critical(
                "[SCAN_BACKPRESSURE] CRITICAL threshold reached (%d consecutive activations). "
                "DB observed_ms=%.1f p95_ms=%.1f threshold_ms=%.1f",
                counter,
                backpressure.get("observed_ms", 0.0),
                backpressure.get("p95_ms", 0.0),
                backpressure.get("threshold_ms", 0.0),
            )
            try:
                orch.storage.save_notification({
                    "category": "SYSTEM_STRESS",
                    "priority": "critical",
                    "title": "DB Backpressure — CRITICAL: scan paused consecutively",
                    "message": (
                        f"Scan paused {counter}x consecutively due to DB latency. "
                        f"observed_ms={backpressure.get('observed_ms', 0.0):.1f} "
                        f"p95_ms={backpressure.get('p95_ms', 0.0):.1f} "
                        f"threshold_ms={backpressure.get('threshold_ms', 0.0):.1f}. "
                        "Investigate DB I/O or increase scan_backpressure_latency_ms."
                    ),
                    "details": {
                        "consecutive": counter,
                        "observed_ms": backpressure.get("observed_ms", 0.0),
                        "p95_ms": backpressure.get("p95_ms", 0.0),
                        "threshold_ms": backpressure.get("threshold_ms", 0.0),
                        "by_operation": backpressure.get("by_operation", {}),
                    },
                    "read": False,
                })
            except Exception as exc:
                logger.debug("[SCAN_BACKPRESSURE] Could not save critical notification: %s", exc)
    else:
        if counter > 0:
            logger.info(
                "[SCAN_BACKPRESSURE] Cleared after %d consecutive activation(s)", counter
            )
            orch._consecutive_scan_backpressure = 0
            try:
                orch.storage.update_sys_config({"oem_scan_backpressure_consecutive": 0})
            except Exception as exc:
                logger.debug("[SCAN_BACKPRESSURE] Could not reset consecutive counter: %s", exc)


def _persist_scan_funnel_kpi(orch: Any, payload: Dict[str, Any]) -> None:
    """Persist scanner funnel KPIs for operational observability."""
    try:
        orch.storage.update_sys_config({"scanner_signal_funnel_last_cycle": payload})
    except Exception as exc:
        logger.debug("[SCAN_KPI] Could not persist funnel KPI payload: %s", exc)


async def _run_with_timeout(orch: Any, phase: str, awaitable: Any, timeout_s: float) -> bool:
    """Run awaitable with timeout; return False on timeout/error and keep cycle alive."""
    try:
        await asyncio.wait_for(awaitable, timeout=timeout_s)
        return True
    except asyncio.TimeoutError:
        _record_phase_timeout(orch, phase, timeout_s)
        return False
    except Exception as exc:
        logger.warning("[TIMEOUT-GUARD] phase=%s failed: %s", phase, exc)
        return False


async def run_pre_phase(orch: Any) -> bool:
    """
    Pre-cycle phase: background tasks, module toggles, guards.

    Returns False if the cycle should be aborted (stats.cycles_completed already incremented).
    Returns True to continue into scan phase.
    """
    from models.signal import Signal, SignalType, ConnectorType
    from core_brain import main_orchestrator as main_orchestrator_module

    # HOT-RELOAD: detect module changes from UI
    orch.modules_enabled_global = orch.storage.get_global_modules_enabled()

    # Check if new trading day
    orch.stats.reset_if_new_day()

    # Background weekly/daily tasks
    await orch._check_and_run_weekly_dedup_learning()
    await orch._check_and_run_weekly_shadow_evolution()

    backtest_timeout_s = _get_phase_timeout_seconds(
        orch,
        key="phase_timeout_backtest_s",
        default=300.0,
    )
    await _run_with_timeout(
        orch,
        phase="daily_backtest",
        awaitable=orch._check_and_run_daily_backtest(),
        timeout_s=backtest_timeout_s,
    )

    orch.storage.update_module_heartbeat("orchestrator")
    # executor heartbeat: updated here so idle cycles (no signals) don't trigger false FAIL
    orch.storage.update_module_heartbeat("executor")

    # DISC-001: Process timed-out review queue entries (auto-execution marker)
    review_manager = getattr(orch, "signal_review_manager", None)
    if review_manager:
        timeout_stats = await review_manager.check_and_execute_timed_out_reviews()
        if timeout_stats.get("auto_executed", 0) > 0:
            logger.info(
                f"[REVIEW_QUEUE] {timeout_stats['auto_executed']} signals marked AUTO_EXECUTED by timeout"
            )
            for timeout_signal_id in timeout_stats.get("auto_executed_ids", []):
                try:
                    timeout_signal = orch.storage.get_signal_by_id(timeout_signal_id)
                    if not timeout_signal:
                        logger.warning(f"[REVIEW_QUEUE] Timed-out signal not found: {timeout_signal_id}")
                        continue

                    timeout_metadata = timeout_signal.get("metadata", {})
                    if isinstance(timeout_metadata, str):
                        try:
                            timeout_metadata = json.loads(timeout_metadata)
                        except Exception:
                            timeout_metadata = {}

                    timeout_model = Signal(
                        symbol=timeout_signal["symbol"],
                        signal_type=SignalType(timeout_signal.get("signal_type", "BUY")),
                        confidence=timeout_signal.get(
                            "confidence", timeout_signal.get("score", 0.75)
                        ),
                        connector_type=ConnectorType(
                            timeout_signal.get("connector_type", "METATRADER5")
                        ),
                        entry_price=timeout_signal.get("entry_price")
                        or timeout_signal.get("price", 0.0),
                        stop_loss=timeout_signal.get("stop_loss", 0.0),
                        take_profit=timeout_signal.get("take_profit", 0.0),
                        timeframe=timeout_signal.get("timeframe", "M15"),
                        metadata=timeout_metadata,
                    )
                    timeout_model.metadata["signal_id"] = timeout_signal_id
                    timeout_model.metadata["execution_method"] = "auto_timeout"

                    timeout_exec_ok = await orch.executor.execute_signal(timeout_model)
                    if timeout_exec_ok:
                        orch.storage.update_signal_status(
                            timeout_signal_id,
                            "EXECUTED",
                            {
                                "executed_at": datetime.now(timezone.utc).isoformat(),
                                "execution_method": "auto_timeout",
                            },
                        )
                        orch.stats.usr_signals_executed += 1
                        logger.info(f"[REVIEW_QUEUE] Timed-out signal executed: {timeout_signal_id}")
                    else:
                        orch.storage.update_signal_status(
                            timeout_signal_id,
                            "REJECTED",
                            {
                                "rejected_at": datetime.now(timezone.utc).isoformat(),
                                "execution_method": "auto_timeout",
                                "reason": getattr(
                                    orch.executor, "last_rejection_reason", "timeout_execution_failed"
                                ),
                            },
                        )
                        logger.warning(
                            f"[REVIEW_QUEUE] Timed-out signal execution failed: {timeout_signal_id}"
                        )
                except Exception as timeout_exec_error:
                    logger.error(
                        f"[REVIEW_QUEUE] Error executing timed-out signal {timeout_signal_id}: "
                        f"{timeout_exec_error}",
                        exc_info=True,
                    )

    await orch._consume_oem_repair_flags()

    if orch.thought_callback:
        await orch.thought_callback("Iniciando ciclo de monitoreo autónomo...", module="CORE")
    if orch.thought_callback:
        await orch.thought_callback(
            "Verificando caducidad de señales no ejecutadas...", module="ALPHA"
        )

    expiration_stats = orch.expiration_manager.expire_old_sys_signals()
    logger.info(
        f"[EXPIRATION] Processed {expiration_stats.get('total_checked', 0)} sys_signals, "
        f"expired {expiration_stats['total_expired']}"
    )
    if expiration_stats["total_expired"] > 0:
        logger.info(f"[EXPIRATION] [OK] Breakdown: {expiration_stats['by_timeframe']}")

    # MODULE TOGGLE: Position Manager
    if not orch.modules_enabled_global.get("position_manager", True):
        logger.debug("[TOGGLE] position_manager deshabilitado globalmente - saltado")
    elif orch.position_manager:
        if orch.thought_callback:
            await orch.thought_callback("Evaluando salud de posiciones abiertas...", module="MGMT")
        from core_brain.connectivity_orchestrator import ConnectivityOrchestrator
        _co = ConnectivityOrchestrator()
        exec_connectors = {
            pid: conn
            for pid, conn in _co.connectors.items()
            if _co.supports_info.get(pid, {}).get("exec", False)
            and getattr(conn, "is_connected", False)
        }
        if not exec_connectors:
            logger.debug("[POSITION_MANAGER] No active execution connectors — position monitoring skipped")
        else:
            combined_actions: List[Any] = []
            total_monitored = 0
            position_timeout_s = _get_phase_timeout_seconds(
                orch,
                key="phase_timeout_positions_s",
                default=60.0,
            )
            for account_id, exec_connector in exec_connectors.items():
                try:
                    position_stats = await asyncio.wait_for(
                        asyncio.to_thread(
                            orch.position_manager.monitor_usr_positions,
                            connector=exec_connector,
                        ),
                        timeout=position_timeout_s,
                    )
                    total_monitored += position_stats.get("monitored", 0)
                    combined_actions.extend(position_stats.get("actions", []))
                except asyncio.TimeoutError:
                    _record_phase_timeout(
                        orch,
                        phase=f"position_monitor:{account_id}",
                        timeout_s=position_timeout_s,
                    )
                except Exception as pm_err:
                    logger.error(
                        f"[POSITION_MANAGER] Error monitoring account '{account_id}': {pm_err}"
                    )
            if combined_actions:
                logger.info(
                    f"[POSITION_MANAGER] Monitored {total_monitored} positions across "
                    f"{len(exec_connectors)} account(s), executed {len(combined_actions)} actions"
                )
                for action in combined_actions:
                    logger.info(
                        f"[POSITION_MANAGER] {action['action']}: ticket={action.get('ticket')}"
                    )

    # MODULE TOGGLE: Scanner
    if not orch.modules_enabled_global.get("scanner", True):
        logger.debug("[TOGGLE] scanner deshabilitado globalmente - ciclo terminado")
        orch.stats.cycles_completed += 1
        return False

    # DEGRADED POSTURE GUARD (EDGE-IGNITION-PHASE-4B)
    from core_brain.resilience import SystemPosture
    if orch.resilience_manager.current_posture in (SystemPosture.DEGRADED, SystemPosture.STRESSED):
        logger.warning(
            "[ResilienceManager] Posture %s — scan y generación de señales bloqueados. %s",
            orch.resilience_manager.current_posture.value,
            orch.resilience_manager.get_current_status_narrative(),
        )
        orch.stats.cycles_completed += 1
        return False

    # CPU guardrail (HU 5.3 + HU 10.27)
    _dyn = orch.storage.get_dynamic_params() or {}
    _cpu_state = _evaluate_cpu_pressure(orch, _dyn)
    _cpu_window = getattr(orch, "_cpu_pressure_window", deque(maxlen=1))
    _cpu_avg = (sum(_cpu_window) / len(_cpu_window)) if len(_cpu_window) > 0 else 0.0
    _cpu_now = _cpu_window[-1] if len(_cpu_window) > 0 else 0.0
    _cpu_throttle_threshold = _dyn.get("cpu_throttle_threshold", 75)
    _cpu_veto_threshold = _dyn.get("cpu_veto_threshold", 90)

    if _cpu_state == CpuPressureState.VETO:
        logger.warning(
            "[PULSE] CPU veto: avg=%.1f%% current=%.1f%% >= veto_threshold=%s%% — skipping trade scan cycle",
            _cpu_avg,
            _cpu_now,
            _cpu_veto_threshold,
        )
        orch.storage.save_notification({
            "category": "SYSTEM_STRESS",
            "priority": "high",
            "title": "CPU Critical — Scan Cycle Vetoed",
            "message": (
                f"CPU pressure avg {_cpu_avg:.1f}% exceeds veto threshold {_cpu_veto_threshold}%. "
                "Trade scanning skipped."
            ),
            "details": {
                "cpu_percent": _cpu_avg,
                "cpu_sample_percent": _cpu_now,
                "threshold": _cpu_veto_threshold,
                "state": CpuPressureState.VETO.value,
            },
            "read": False,
        })
        orch.stats.cycles_completed += 1
        return False

    if _cpu_state == CpuPressureState.THROTTLED:
        _skip_counter = int(getattr(orch, "_cpu_throttle_skip_counter", 0)) + 1
        orch._cpu_throttle_skip_counter = _skip_counter
        if _skip_counter % 2 == 1:
            logger.warning(
                "[PULSE] CPU throttled: avg=%.1f%% current=%.1f%% in [%s%%, %s%%) — skipping this cycle (1/2 policy)",
                _cpu_avg,
                _cpu_now,
                _cpu_throttle_threshold,
                _cpu_veto_threshold,
            )
            orch.stats.cycles_completed += 1
            return False
        logger.info(
            "[PULSE] CPU throttled: avg=%.1f%% current=%.1f%% — allowing this cycle (1/2 policy)",
            _cpu_avg,
            _cpu_now,
        )
    else:
        orch._cpu_throttle_skip_counter = 0

    # Market session guard
    if orch._is_market_closed():  # thin wrapper — patched in tests
        logger.info(
            "[MARKET-GUARD] Mercado cerrado (fin de semana / fuera de sesión) — ciclo omitido"
        )
        orch.stats.cycles_completed += 1
        return False

    return True


async def run_scan_phase(orch: Any) -> Optional[ScanBundle]:
    """
    Orchestrate OPTION-A scan, build PriceSnapshots, feed UI mapping.

    Returns a ScanBundle on success, None if no data available (cycle continues from caller).
    Stats.scans_total is incremented here; cycles_completed is NOT incremented on None return.
    """
    if orch.thought_callback:
        await orch.thought_callback(
            "Escaneando mercados en busca de anomalías...", module="SCANNER"
        )

    # OPTION-A: MainOrchestrator orchestrates timing + execution
    scan_schedule = orch._get_scan_schedule()
    logger.debug(f"[OPTION-A] Built scan schedule: {len(scan_schedule)} symbol|timeframe pairs")

    assets_to_scan = orch._should_scan_now(scan_schedule)
    discard_reasons: Dict[str, int] = {}
    infra_skip_reason: Optional[str] = None
    if assets_to_scan:
        logger.info(
            f"[OPTION-A] {len(assets_to_scan)} assets due: "
            f"{', '.join([f'{s}|{tf}' for s, tf in assets_to_scan[:5]])}{'...' if len(assets_to_scan) > 5 else ''}"
        )
        backpressure = _db_backpressure_state(orch)
        _handle_consecutive_backpressure(orch, backpressure)
        if backpressure.get("active"):
            discard_reasons["backpressure_db_latency"] = len(assets_to_scan)
            logger.warning(
                "[SCAN_BACKPRESSURE] scan_request paused — "
                "observed_ms=%.1f p95_ms=%.1f threshold_ms=%.1f count=%s",
                backpressure.get("observed_ms", 0.0),
                backpressure.get("p95_ms", 0.0),
                backpressure.get("threshold_ms", 0.0),
                backpressure.get("count", 0),
            )
            top_ops = sorted(
                backpressure.get("by_operation", {}).items(),
                key=lambda kv: kv[1].get("p95_ms", 0.0) if isinstance(kv[1], dict) else 0.0,
                reverse=True,
            )[:3]
            if top_ops:
                logger.warning(
                    "[SCAN_BACKPRESSURE] Top-3 slowest operations: %s",
                    ", ".join(
                        f"{op}(p95={m.get('p95_ms', 0.0):.1f}ms avg={m.get('avg_ms', 0.0):.1f}ms)"
                        for op, m in top_ops
                        if isinstance(m, dict)
                    ),
                )
            try:
                orch.storage.log_audit_event(
                    user_id="SYSTEM",
                    action="SCAN_BACKPRESSURE",
                    resource="scan_request",
                    resource_id="db_latency",
                    status="warning",
                    reason=(
                        f"paused: observed_ms={backpressure.get('observed_ms', 0.0):.2f} "
                        f"p95_ms={backpressure.get('p95_ms', 0.0):.2f} "
                        f"threshold_ms={backpressure.get('threshold_ms', 0.0):.2f}"
                    ),
                    trace_id=f"SCAN_BACKPRESSURE_{uuid.uuid4().hex[:8].upper()}",
                )
            except Exception as exc:
                logger.debug("[SCAN_BACKPRESSURE] Could not write audit event: %s", exc)
            infra_skip_reason = "backpressure_db_latency"
            new_scan_results = {}
        else:
            scan_timeout_s = _get_phase_timeout_seconds(
                orch,
                key="phase_timeout_scan_s",
                default=120.0,
            )
            try:
                new_scan_results = await asyncio.wait_for(
                    orch._request_scan(assets_to_scan),
                    timeout=scan_timeout_s,
                )
            except asyncio.TimeoutError:
                _record_phase_timeout(orch, "scan_request", scan_timeout_s)
                discard_reasons["scan_timeout"] = len(assets_to_scan)
                infra_skip_reason = "scan_timeout"
                new_scan_results = {}
    else:
        logger.debug("[OPTION-A] No assets due — using cached results")
        new_scan_results = {}

    # Merge new results with cached (ScannerEngine.last_results)
    raw_last = getattr(orch.scanner, "last_results", {})
    scan_results_with_data: Dict[str, Any] = raw_last.copy() if isinstance(raw_last, dict) else {}
    if new_scan_results:
        scan_results_with_data.update(new_scan_results)
        logger.info(
            f"[OPTION-A] Merged {len(new_scan_results)} new scans with "
            f"{len(scan_results_with_data) - len(new_scan_results)} cached"
        )

    # Fallback: legacy path (tests / older integrations)
    if not scan_results_with_data and hasattr(orch.scanner, "get_scan_results_with_data"):
        scan_results_with_data = orch.scanner.get_scan_results_with_data() or {}
        if scan_results_with_data:
            logger.debug("[OPTION-A] Fallback to get_scan_results_with_data() succeeded")

    if not scan_results_with_data:
        if infra_skip_reason:
            logger.warning(
                "[SCAN_INFRA_FALLBACK] No cached scan results and scan was blocked by infra cause=%s. "
                "STAGE_RAW_SIGNAL_GENERATION will be 0 this cycle (infra-driven silence, not business logic).",
                infra_skip_reason,
            )
        else:
            logger.warning("No scan results available yet (first cycle or all offline)")
        _persist_scan_funnel_kpi(
            orch,
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "scheduled_pairs": len(scan_schedule),
                "due_pairs": len(assets_to_scan),
                "new_results": len(new_scan_results),
                "active_results": 0,
                "completion_rate": 0.0,
                "discard_reasons": discard_reasons or {"no_scan_results": len(assets_to_scan)},
                "infra_skip_reason": infra_skip_reason,
            },
        )
        return None

    orch.stats.scans_total += len(scan_results_with_data)

    # Build PriceSnapshots for atomic traceability
    price_snapshots: Dict[str, PriceSnapshot] = {}
    for key, data in scan_results_with_data.items():
        provider = data.get("provider_source", "UNKNOWN")
        price_snapshots[key] = PriceSnapshot(
            symbol=data.get("symbol", key.split("|")[0]),
            timeframe=data.get("timeframe", key.split("|")[-1] if "|" in key else "M5"),
            df=data.get("df"),
            provider_source=provider,
            regime=data.get("regime"),
        )
        data["provider_source"] = provider

    logger.info(
        f"[PRICE_SNAPSHOT] Built {len(price_snapshots)} atomic snapshots. "
        f"Providers: {set(s.provider_source for s in price_snapshots.values())}"
    )

    completion_rate = (len(scan_results_with_data) / len(scan_schedule) * 100.0) if scan_schedule else 0.0
    _persist_scan_funnel_kpi(
        orch,
        {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scheduled_pairs": len(scan_schedule),
            "due_pairs": len(assets_to_scan),
            "new_results": len(new_scan_results),
            "active_results": len(scan_results_with_data),
            "completion_rate": round(completion_rate, 2),
            "discard_reasons": discard_reasons,
            "scan_sources": sorted({s.provider_source for s in price_snapshots.values()}),
            "infra_skip_reason": infra_skip_reason,
        },
    )

    # Feed AnomalySentinel (EDGE-IGNITION-PHASE-2)
    for snapshot in price_snapshots.values():
        if snapshot.df is not None and len(snapshot.df) >= 2:
            orch.anomaly_sentinel.push_ticks(snapshot.df.tail(10).to_dict("records"))

    # Extract regimes + update orchestrator state
    scan_results: Dict[str, Any] = {
        sym: data["regime"] for sym, data in scan_results_with_data.items()
    }
    orch._update_regime_from_scan(scan_results)
    orch.storage.update_module_heartbeat("scanner")
    orch._persist_scan_telemetry(scan_results_with_data)

    # UI structure analysis + trader page update
    if orch.market_structure_analyzer and orch.ui_mapping_service:
        snapshots_with_data = sum(
            1 for s in price_snapshots.values() if s.df is not None and len(s.df) > 0
        )
        if snapshots_with_data == 0:
            logger.warning(
                f"[UI_MAPPING] All {len(price_snapshots)} snapshots have df=None "
                "— skipping structure analysis this cycle"
            )

        available_pct = (snapshots_with_data / len(price_snapshots) * 100) if price_snapshots else 0
        logger.info(
            f"[UI_MAPPING] Starting structure analysis: {len(price_snapshots)} snapshots "
            f"({available_pct:.1f}% with data)"
        )
        structure_count = 0
        try:
            for key, snapshot in price_snapshots.items():
                if snapshot.df is not None and len(snapshot.df) > 0:
                    result = orch.market_structure_analyzer.detect_market_structure(
                        snapshot.symbol, snapshot.df
                    )
                    if result:
                        normalized_confidence = _normalize_ui_structure_confidence(
                            result.get("confidence", 0.0)
                        )
                        has_some_pivots = any(
                            result.get(f"{p}_count", 0) > 0 for p in ("hh", "hl", "lh", "ll")
                        )
                        if result.get("is_valid") or has_some_pivots:
                            orch.ui_mapping_service.add_structure_signal(
                                asset=snapshot.symbol,
                                structure_data={
                                    "hh_indices": result.get("hh_indices", []),
                                    "hl_indices": result.get("hl_indices", []),
                                    "lh_indices": result.get("lh_indices", []),
                                    "ll_indices": result.get("ll_indices", []),
                                    "structure_type": result.get("type", "UNKNOWN"),
                                    "is_valid": result.get("is_valid", False),
                                    "validation_level": result.get("validation_level", "INSUFFICIENT"),
                                    "confidence": normalized_confidence,
                                },
                            )
                            structure_count += 1
                            level_icon = (
                                "[OK]"
                                if result.get("validation_level") == "STRONG"
                                else "[WARNING]"
                            )
                            logger.info(
                                f"[UI_MAPPING] {level_icon} {snapshot.symbol}: "
                                f"{result.get('type')} ({result.get('validation_level')}) "
                                f"[Conf: {normalized_confidence:.1f}%]"
                            )

            logger.info(
                f"[UI_MAPPING] Structure analysis complete: {structure_count} structures "
                f"out of {len(price_snapshots)}"
            )

            # Health monitor: consecutive empty structure cycles
            if structure_count == 0:
                orch._consecutive_empty_structure_cycles += 1
                if orch._consecutive_empty_structure_cycles == orch._max_consecutive_empty_cycles:
                    logger.critical(
                        f"[HEALTH_CHECK] ALERT: {orch._consecutive_empty_structure_cycles} "
                        "consecutive cycles with 0 structures detected."
                    )
                elif orch._consecutive_empty_structure_cycles > orch._max_consecutive_empty_cycles:
                    logger.error(
                        f"[HEALTH_CHECK] PERSISTENT: {orch._consecutive_empty_structure_cycles} "
                        "cycles with 0 structures. System may be degraded."
                    )
            else:
                if orch._consecutive_empty_structure_cycles > 0:
                    logger.info(
                        f"[HEALTH_CHECK] Recovery: structures detected after "
                        f"{orch._consecutive_empty_structure_cycles} empty cycles"
                    )
                orch._consecutive_empty_structure_cycles = 0

        except Exception as e:
            logger.error(f"[UI_MAPPING] Error analyzing structure: {type(e).__name__}: {e}", exc_info=True)

        try:
            await orch.ui_mapping_service.emit_trader_page_update()
        except Exception as e:
            logger.error(
                f"[UI_MAPPING] Error emitting trader page update: {type(e).__name__}: {e}",
                exc_info=True,
            )

    trace_id = str(uuid.uuid4())
    logger.debug(f"Starting cycle with trace_id: {trace_id}")

    return ScanBundle(
        scan_results_with_data=scan_results_with_data,
        price_snapshots=price_snapshots,
        scan_results=scan_results,
        trace_id=trace_id,
        infra_skip_reason=infra_skip_reason,
    )
