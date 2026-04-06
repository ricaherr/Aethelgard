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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core_brain.orchestrators._types import PriceSnapshot, ScanBundle
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

    # CPU veto (HU 5.3 — The Pulse)
    _dyn = orch.storage.get_dynamic_params() or {}
    _cpu_threshold = _dyn.get("cpu_veto_threshold", 90)
    _cpu_now = main_orchestrator_module.psutil.cpu_percent(interval=None)
    if _cpu_now > _cpu_threshold:
        logger.warning(
            f"[PULSE] CPU veto: {_cpu_now:.1f}% > {_cpu_threshold}% — skipping trade scan cycle"
        )
        orch.storage.save_notification({
            "category": "SYSTEM_STRESS",
            "priority": "high",
            "title": "CPU Critical — Scan Cycle Vetoed",
            "message": (
                f"CPU at {_cpu_now:.1f}% exceeds {_cpu_threshold}% threshold. "
                "Trade scanning skipped."
            ),
            "details": {"cpu_percent": _cpu_now, "threshold": _cpu_threshold},
            "read": False,
        })
        orch.stats.cycles_completed += 1
        return False

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
    if assets_to_scan:
        logger.info(
            f"[OPTION-A] {len(assets_to_scan)} assets due: "
            f"{', '.join([f'{s}|{tf}' for s, tf in assets_to_scan[:5]])}{'...' if len(assets_to_scan) > 5 else ''}"
        )
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
        logger.warning("No scan results available yet (first cycle or all offline)")
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
                                    "confidence": result.get("confidence", 0.0),
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
                                f"[Conf: {result.get('confidence', 0.0):.0f}%]"
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
    )
