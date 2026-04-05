"""
Lifecycle implementations extracted from MainOrchestrator.

Contains: heartbeat helpers, session stats, strategy authorization,
main loop (run), graceful shutdown, and the module-level main() entry point.
"""
from __future__ import annotations

import asyncio
import importlib
import json
import logging
import signal
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


def update_all_usr_strategies_heartbeat(orch: Any) -> None:
    """Update heartbeat for all usr_strategies to reflect cycle end (Vector V4)."""
    if not orch.heartbeat_monitor:
        return
    from core_brain.services.strategy_heartbeat_monitor import StrategyState
    for strategy_id in getattr(orch.heartbeat_monitor, "STRATEGY_IDS", []):
        try:
            orch.heartbeat_monitor.update_heartbeat(
                strategy_id=strategy_id,
                state=StrategyState.IDLE,
                asset=None,
                position_open=False,
            )
        except Exception as e:
            logger.debug(f"[HEARTBEAT] Error updating {strategy_id}: {e}")


def persist_session_stats_impl(orch: Any) -> None:
    """Persist current session stats to storage after each cycle."""
    session_data = {
        "date": orch.stats.date.isoformat(),
        "usr_signals_processed": orch.stats.usr_signals_processed,
        "usr_signals_executed": orch.stats.usr_signals_executed,
        "cycles_completed": orch.stats.cycles_completed,
        "errors_count": orch.stats.errors_count,
        "scans_total": orch.stats.scans_total,
        "usr_signals_generated": orch.stats.usr_signals_generated,
        "usr_signals_risk_passed": orch.stats.usr_signals_risk_passed,
        "usr_signals_vetoed": orch.stats.usr_signals_vetoed,
        "last_update": datetime.now().isoformat(),
    }
    orch.storage.update_sys_config({"session_stats": session_data})


def is_strategy_authorized_for_execution(orch: Any, signal: Any) -> bool:
    """
    Check if a signal's strategy is authorized for LIVE execution.

    Implements the Shadow Ranking System:
    - LIVE → execute on real account
    - SHADOW → route to DEMO account (paper metrics accumulate toward promotion)
    - QUARANTINE → blocked
    - BACKTEST → batch-only, ignored here
    """
    strategy_id = getattr(signal, "strategy", None)
    if not strategy_id:
        return True  # legacy compatibility — no strategy tag means allow

    try:
        ranking = orch.storage.get_signal_ranking(strategy_id)
        if not ranking:
            logger.debug(f"Strategy {strategy_id} not in ranking table — allowing execution")
            return True

        execution_mode = ranking.get("execution_mode", "SHADOW")
        if execution_mode == "LIVE":
            return True
        elif execution_mode == "SHADOW":
            logger.info(
                f"Strategy {strategy_id} in SHADOW mode — routing to DEMO for paper execution"
            )
            return True
        elif execution_mode == "QUARANTINE":
            logger.warning(
                f"Strategy {strategy_id} in QUARANTINE — blocked until risk metrics improve"
            )
            return False
        elif execution_mode == "BACKTEST":
            logger.info(f"Strategy {strategy_id} in BACKTEST mode — ignored for direct execution")
            return False
        else:
            logger.warning(f"Unknown execution mode for strategy {strategy_id}: {execution_mode}")
            return False
    except Exception as e:
        logger.error(f"Error checking strategy authorization for {strategy_id}: {e}")
        return False  # conservative: block on error


def register_signal_handlers(orch: Any) -> None:
    """Register SIGINT/SIGTERM handlers for graceful shutdown."""
    def _handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}. Requesting shutdown...")
        orch._shutdown_requested = True

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


async def run_main_loop(orch: Any) -> None:
    """Main event loop — runs until shutdown requested."""
    from core_brain.orchestrators._guard_suite import (
        run_coherence_gate,
        write_integrity_veto,
        write_anomaly_lockdown,
    )
    from core_brain.resilience import SystemPosture, ResilienceLevel, EdgeAction, EdgeEventReport
    from core_brain.services.integrity_guard import HealthStatus
    from core_brain.services.anomaly_sentinel import DefenseProtocol

    logger.info("MainOrchestrator starting event loop...")

    # Cleanup orphan shadow instances on startup
    try:
        orphans = orch.storage.mark_orphan_shadow_instances_dead()
        if orphans:
            logger.warning(
                "[STARTUP] %d orphan shadow instance(s) marked DEAD "
                "(parent strategy still in BACKTEST mode).",
                orphans,
            )
    except Exception as exc:
        logger.warning("[STARTUP] mark_orphan_shadow_instances_dead failed (non-fatal): %s", exc)

    register_signal_handlers(orch)

    # WARMUP PHASE: wait for scanner to have data ready
    logger.info("[WARMUP] Waiting for scanner to populate initial data...")
    warmup_timeout = 30
    warmup_start = time.time()
    has_data = False
    while not has_data and (time.time() - warmup_start) < warmup_timeout:
        scan_results = await asyncio.to_thread(orch.scanner.get_scan_results_with_data)
        if scan_results:
            snapshots_ok = sum(
                1
                for data in scan_results.values()
                if data.get("df") is not None and len(data.get("df", [])) > 0
            )
            pct = (snapshots_ok / len(scan_results)) * 100
            if pct >= 50:
                has_data = True
                logger.info(
                    f"[WARMUP] [OK] {snapshots_ok}/{len(scan_results)} snapshots ready ({pct:.1f}%)"
                )
            else:
                logger.debug(f"[WARMUP] Loading: {snapshots_ok}/{len(scan_results)} ({pct:.1f}%)")
                await asyncio.sleep(0.5)
        else:
            logger.debug("[WARMUP] Waiting for first scan results...")
            await asyncio.sleep(0.5)

    if not has_data:
        logger.warning(
            f"[WARMUP] Timeout after {warmup_timeout}s; proceeding with partial data"
        )
    logger.info("[WARMUP] [OK] Scanner warmup complete, entering main loop")

    try:
        while not orch._shutdown_requested:
            # RESILIENCE: STRESSED posture halts loop
            if orch.resilience_manager.current_posture == SystemPosture.STRESSED:
                logger.critical(
                    "[ResilienceManager] Posture STRESSED — deteniendo loop. Narrative: %s",
                    orch.resilience_manager.get_current_status_narrative(),
                )
                orch._shutdown_requested = True
                break

            # EDGE-IGNITION-PHASE-1: Integrity Gate
            health = orch.integrity_guard.check_health()
            if health.overall == HealthStatus.CRITICAL:
                failed = [c for c in health.checks if c.status.value == "CRITICAL"]
                reason = "; ".join(f"[{c.name}] {c.message}" for c in failed)
                orch.resilience_manager.process_report(
                    EdgeEventReport(
                        level=ResilienceLevel.SERVICE,
                        scope="IntegrityGuard",
                        action=EdgeAction.SELF_HEAL,
                        reason=reason or "IntegrityGuard CRITICAL",
                        trace_id=health.trace_id,
                    )
                )
                write_integrity_veto(orch, health.trace_id, health.checks)

            # EDGE-IGNITION-PHASE-2: Anomaly Gate
            anomaly_protocol = orch.anomaly_sentinel.get_defense_protocol()
            if anomaly_protocol == DefenseProtocol.LOCKDOWN:
                _as_trace = getattr(orch.anomaly_sentinel, "last_trace_id", None)
                _as_trace = _as_trace or f"EDGE-{uuid.uuid4().hex[:8].upper()}"
                orch.resilience_manager.process_report(
                    EdgeEventReport(
                        level=ResilienceLevel.GLOBAL,
                        scope="AnomalySentinel",
                        action=EdgeAction.LOCKDOWN,
                        reason="AnomalySentinel LOCKDOWN protocol triggered.",
                        trace_id=_as_trace,
                    )
                )
                await write_anomaly_lockdown(orch, orch.anomaly_sentinel.last_trace_id)

            # EDGE-IGNITION-PHASE-3: Coherence Gate (per-strategy, does not stop loop)
            await run_coherence_gate(orch)

            await orch.run_single_cycle()

            sleep_interval = orch._get_sleep_interval()
            logger.debug(
                f"Sleeping {sleep_interval}s "
                f"(regime: {orch.current_regime}, "
                f"active_signals: {len(orch._active_usr_signals)})"
            )
            for _ in range(sleep_interval):
                if orch._shutdown_requested:
                    break
                await asyncio.sleep(orch.HEARTBEAT_CHECK_INTERVAL)

    except asyncio.CancelledError:
        logger.info("Event loop cancelled")
    except Exception as e:
        logger.critical(f"Fatal error in event loop: {e}", exc_info=True)
    finally:
        await orch.shutdown()


async def shutdown_impl(orch: Any) -> None:
    """Graceful shutdown: save state, close connections."""
    logger.info("Initiating graceful shutdown...")
    orch._shutdown_requested = True
    try:
        logger.info(f"Final session stats: {orch.stats}")
        sys_config = {
            "last_shutdown": datetime.now().isoformat(),
            "lockdown_active": orch.risk_manager.is_lockdown_active(),
            "consecutive_losses": orch.risk_manager.consecutive_losses,
            "last_regime": orch.current_regime.value,
            "session_stats": {
                "date": orch.stats.date.isoformat(),
                "usr_signals_processed": orch.stats.usr_signals_processed,
                "usr_signals_executed": orch.stats.usr_signals_executed,
                "cycles_completed": orch.stats.cycles_completed,
                "errors_count": orch.stats.errors_count,
            },
        }
        orch.storage.update_sys_config(sys_config)
        if hasattr(orch.executor, "close_connections"):
            logger.info("Closing broker connections...")
            await orch.executor.close_connections()
        logger.info("Shutdown completed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}", exc_info=True)


async def main() -> None:
    """Main entry point for Aethelgard. Health checks + component initialization."""
    from data_vault.storage import StorageManager
    from core_brain.health import HealthManager
    from core_brain.data_provider_manager import DataProviderManager
    from core_brain.scanner import ScannerEngine
    from core_brain.signal_factory import SignalFactory
    from core_brain.risk_manager import RiskManager
    from core_brain.executor import OrderExecutor
    from core_brain.notificator import get_notifier
    from core_brain.trade_closure_listener import TradeClosureListener
    from core_brain.edge_tuner import EdgeTuner
    from core_brain.threshold_optimizer import ThresholdOptimizer
    from core_brain.execution_feedback import ExecutionFeedbackCollector
    MainOrchestrator = importlib.import_module("core_brain.main_orchestrator").MainOrchestrator
    _orch_module = importlib.import_module("core_brain.main_orchestrator")

    print("=" * 50)
    print(">>> AETHELGARD ORCHESTRATOR STARTUP")
    print("=" * 50)

    health = HealthManager()
    summary = health.run_full_diagnostic()
    if summary["overall_status"] != "GREEN":
        print(f"[WARNING] ISSUES: {summary['overall_status']}. Attempting auto-repair...")
        if health.try_auto_repair():
            print("[OK] Auto-repair successful. Re-checking...")
            summary = health.run_full_diagnostic()
        else:
            print("[ERROR] Auto-repair failed.")

    if summary["overall_status"] == "RED":
        print("[CRITICAL] CRITICAL ERRORS PRESENT. ABORTING.")
        print(json.dumps(summary["config"], indent=2))
        print(json.dumps(summary["db"], indent=2))
        return
    if summary["overall_status"] == "YELLOW":
        print("[WARNING] SYSTEM READY WITH WARNINGS. PROCEEDING...")
    else:
        print("[OK] HEALTH CHECK PASSED.")

    storage = StorageManager()
    provider_manager = DataProviderManager(storage=storage)
    data_provider = provider_manager.get_best_provider()
    if not data_provider:
        print("[CRITICAL] No data provider available. Aborting.")
        return

    from core_brain.instrument_manager import InstrumentManager
    instrument_mgr = InstrumentManager(storage=storage)
    enabled_assets = instrument_mgr.get_enabled_symbols()
    if not enabled_assets:
        print("[CRITICAL] No enabled instruments found. Aborting.")
        return
    print(f"[SCAN] Scanning {len(enabled_assets)} instruments: {enabled_assets[:10]}...")

    _scanner = ScannerEngine(assets=enabled_assets, data_provider=data_provider, storage=storage)

    from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
    from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
    from core_brain.services.strategy_engine_factory import StrategyEngineFactory

    dynamic_params = storage.get_dynamic_params()
    confluence_analyzer = MultiTimeframeConfluenceAnalyzer(storage=storage)
    trifecta_analyzer = TrifectaAnalyzer(storage=storage)

    try:
        strategy_factory = StrategyEngineFactory(
            storage=storage,
            config=dynamic_params,
            available_sensors={},
        )
        active_engines = strategy_factory.instantiate_all_sys_strategies()
        stats_f = strategy_factory.get_stats()
        logger.info(
            f"[STRATEGIES] Dynamic loading done: {stats_f['active_engines']} active, "
            f"{stats_f['failed_loads']} skipped"
        )
    except RuntimeError as e:
        logger.error(f"[STRATEGIES] CRITICAL: {e}")
        print(f"[CRITICAL] ABORTING STARTUP: {e}")
        return

    execution_feedback_collector = ExecutionFeedbackCollector(storage=storage)
    signal_factory = SignalFactory(
        storage_manager=storage,
        strategy_engines=active_engines,
        confluence_analyzer=confluence_analyzer,
        trifecta_analyzer=trifecta_analyzer,
        execution_feedback_collector=execution_feedback_collector,
    )

    risk_manager = RiskManager(storage=storage, initial_capital=10000.0, instrument_manager=instrument_mgr)
    edge_tuner = EdgeTuner(storage=storage)
    threshold_optimizer = ThresholdOptimizer(storage=storage)
    trade_listener = TradeClosureListener(
        storage=storage,
        risk_manager=risk_manager,
        edge_tuner=edge_tuner,
        threshold_optimizer=threshold_optimizer,
        max_retries=3,
        retry_backoff=0.5,
    )
    logger.info("[OK] TradeClosureListener initialized | ThresholdOptimizer HU 7.1 enabled")

    notifier = get_notifier()
    executor = OrderExecutor(risk_manager=risk_manager, storage=storage, notificator=notifier)

    # Dual motor initialization (HU 3.6/3.9)
    logger.info("Initializing Hybrid Runtime (MODE_UNIVERSAL)")
    from core_brain.universal_strategy_executor import UniversalStrategyExecutor
    from core_brain.strategy_mode_selector import StrategyModeSelector
    from core_brain.strategy_mode_adapter import StrategyModeAdapter

    tenant_id = "default_tenant"
    universal_executor = UniversalStrategyExecutor(indicator_provider=data_provider, strategy_schemas_dir=None)
    mode_selector = StrategyModeSelector(
        storage_manager=storage,
        legacy_executor=None,
        universal_executor=universal_executor,
        tenant_id=tenant_id,
        trace_id="STARTUP-2026-001",
    )
    await mode_selector.initialize()
    logger.info(f"[OK] Hybrid Runtime | mode: {mode_selector.current_mode.value}")
    strategy_adapter = StrategyModeAdapter(strategy_mode_selector=mode_selector)

    _orchestrator = MainOrchestrator(
        scanner=_scanner,
        signal_factory=strategy_adapter,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage,
        execution_feedback_collector=execution_feedback_collector,
    )

    logger.info("OPTION A: MainOrchestrator sole scanner orchestrator")
    print("System LIVE. Starting event loop...")

    _orch_module.scanner = _scanner
    _orch_module.orchestrator = _orchestrator

    await _orchestrator.run()
