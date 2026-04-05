"""
Main Orchestrator - Aethelgard Trading System
=============================================

Thin coordinator after DISC-003 mass decomposition.
Orchestrates Scan -> Signal -> Risk -> Execute through extracted modules.
"""
import sys
import asyncio
import logging
import psutil
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

# Add project root to path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from data_vault.storage import StorageManager
from models.signal import MarketRegime
from core_brain.regime import RegimeClassifier
from core_brain.dedup_learner import DedupLearner
from core_brain.signal_expiration_manager import SignalExpirationManager
from core_brain.api.routers.shadow_ws import broadcast_shadow_update
from core_brain.services.integrity_guard import IntegrityGuard
from core_brain.services.anomaly_sentinel import AnomalySentinel
from core_brain.services.coherence_service import CoherenceService
from core_brain.services.signal_review_manager import SignalReviewManager
from core_brain.resilience_manager import ResilienceManager
from core_brain.orchestrators import _background_tasks as background_tasks
from core_brain.orchestrators import _cycle_exec as cycle_exec
from core_brain.orchestrators import _cycle_scan as cycle_scan
from core_brain.orchestrators import _cycle_trade as cycle_trade
from core_brain.orchestrators import _discovery as discovery
from core_brain.orchestrators import _init_methods as init_methods
from core_brain.orchestrators import _lifecycle as lifecycle
from core_brain.orchestrators import _scan_methods as scan_methods
from core_brain.orchestrators._types import PriceSnapshot, ScanBundle

logger = logging.getLogger(__name__)


def _resolve_storage(storage: Optional[StorageManager], user_id: Optional[str] = None) -> StorageManager:
    """Resolve storage dependency with legacy fallback."""
    if storage is not None:
        return storage

    logger.warning(
        "MainOrchestrator initialized without explicit storage! Falling back to default storage (user_id=%s).",
        user_id,
    )
    try:
        return StorageManager(user_id=user_id)
    except Exception as e:
        logger.error(
            "CRITICAL: Failed to initialize StorageManager with user_id=%s. Error: %s",
            user_id,
            str(e),
            exc_info=True,
        )
        raise RuntimeError(f"StorageManager initialization failed: {str(e)}") from e

# Global references for API/Control
scanner = None
orchestrator = None


@dataclass
class SessionStats:
    """
    Tracks session statistics for the current trading day.
    Reconstructs state from DB on initialization.
    """
    date: date = field(default_factory=lambda: date.today())
    usr_signals_processed: int = 0
    usr_signals_executed: int = 0
    cycles_completed: int = 0
    errors_count: int = 0
    scans_total: int = 0
    usr_signals_generated: int = 0
    usr_signals_risk_passed: int = 0
    usr_signals_vetoed: int = 0

    @classmethod
    def from_storage(cls, storage: StorageManager) -> "SessionStats":
        today = date.today()
        executed_count = storage.count_executed_usr_signals(today)
        sys_config = storage.get_sys_config()
        session_data = sys_config.get("session_stats", {})

        stored_date_str = session_data.get("date", "")
        try:
            stored_date = date.fromisoformat(stored_date_str)
            is_today = stored_date == today
        except (ValueError, TypeError):
            is_today = False

        if is_today:
            stats = cls(
                date=today,
                usr_signals_processed=session_data.get("usr_signals_processed", 0),
                usr_signals_executed=executed_count,
                cycles_completed=session_data.get("cycles_completed", 0),
                errors_count=session_data.get("errors_count", 0),
                scans_total=session_data.get("scans_total", 0),
                usr_signals_generated=session_data.get("usr_signals_generated", 0),
                usr_signals_risk_passed=session_data.get("usr_signals_risk_passed", 0),
                usr_signals_vetoed=session_data.get("usr_signals_vetoed", 0),
            )
            logger.info(f"SessionStats reconstructed from DB: {stats}")
        else:
            stats = cls(date=today, usr_signals_executed=executed_count)
            logger.info(f"New day detected. Fresh SessionStats initialized: {stats}")
        return stats

    def reset_if_new_day(self) -> None:
        today = date.today()
        if self.date != today:
            logger.info(f"New day detected. Resetting stats. Previous: {self}")
            self.date = today
            self.usr_signals_processed = 0
            self.usr_signals_executed = 0
            self.cycles_completed = 0
            self.errors_count = 0
            self.scans_total = 0
            self.usr_signals_generated = 0
            self.usr_signals_risk_passed = 0
            self.usr_signals_vetoed = 0

    def __str__(self) -> str:
        return (
            f"SessionStats(date={self.date}, processed={self.usr_signals_processed}, "
            f"executed={self.usr_signals_executed}, cycles={self.cycles_completed}, "
            f"errors={self.errors_count})"
        )


class MainOrchestrator:
    """Thin coordinator for the Aethelgard trading cycle."""

    # FASE 2: usr_strategies initialization now lives in
    # core_brain.orchestrators._lifecycle.main() and _init_methods.py.
    # The runtime path uses StrategyEngineFactory to build strategy_engines,
    # then injects them into SignalFactory without any hardcoded strategy class.

    MIN_SLEEP_INTERVAL = 3
    HEARTBEAT_CHECK_INTERVAL = 1

    def __init__(
        self,
        scanner: Any,
        signal_factory: Optional[Any] = None,
        risk_manager: Any = None,
        executor: Any = None,
        storage: Optional[StorageManager] = None,
        position_manager: Optional[Any] = None,
        trade_closure_listener: Optional[Any] = None,
        coherence_monitor: Optional[Any] = None,
        expiration_manager: Optional[Any] = None,
        regime_classifier: Optional[Any] = None,
        strategy_ranker: Optional[Any] = None,
        thought_callback: Optional[Any] = None,
        config_path: Optional[str] = None,
        ui_mapping_service: Optional[Any] = None,
        heartbeat_monitor: Optional[Any] = None,
        conflict_resolver: Optional[Any] = None,
        execution_feedback_collector: Optional[Any] = None,
        signal_quality_scorer: Optional[Any] = None,
        consensus_engine: Optional[Any] = None,
        failure_pattern_registry: Optional[Any] = None,
        strategy_gatekeeper: Optional[Any] = None,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        from core_brain.server import set_resilience_manager

        self.thought_callback = thought_callback
        effective_user_id = user_id or tenant_id
        self.user_id = effective_user_id
        self.available_sensors: Dict[str, Any] = {}
        self._signal_factory = signal_factory

        self._init_core_dependencies(
            scanner,
            signal_factory,
            risk_manager,
            executor,
            storage,
            config_path,
            strategy_ranker,
            execution_feedback_collector,
            effective_user_id,
            tenant_id,
        )

        self.regime_classifier = regime_classifier or RegimeClassifier(storage=self.storage)
        if position_manager is None:
            self._init_position_management()
        else:
            self.position_manager = position_manager

        self._init_ancillary_services(expiration_manager, coherence_monitor, trade_closure_listener)
        self._init_sys_config()
        self._init_loop_intervals()
        self._init_broker_discovery()
        self._init_orchestration_services(ui_mapping_service, heartbeat_monitor, conflict_resolver)
        self._init_market_analysis_services()
        self._init_economic_integration()

        self.dedup_learner = DedupLearner(storage_manager=self.storage)
        self._last_dedup_learning = datetime.now(timezone.utc)

        self._init_shadow_manager()
        self._init_backtest_orchestrator()
        self._init_phase4_intelligence_services(
            signal_quality_scorer,
            consensus_engine,
            failure_pattern_registry,
        )

        self.signal_review_manager = SignalReviewManager(storage_manager=self.storage)
        self.strategy_gatekeeper = strategy_gatekeeper
        self.integrity_guard = IntegrityGuard(storage=self.storage)
        self.anomaly_sentinel = AnomalySentinel(storage=self.storage)
        self.coherence_service = CoherenceService(storage=self.storage)
        self.resilience_manager = ResilienceManager(storage=self.storage)
        try:
            set_resilience_manager(self.resilience_manager)
        except Exception:
            pass

    @property
    def signal_factory(self) -> Optional[Any]:
        return self._signal_factory

    @signal_factory.setter
    def signal_factory(self, factory: Optional[Any]) -> None:
        self._signal_factory = factory

    async def ensure_optimal_demo_accounts(self) -> None:
        from core_brain.orchestrators._discovery import ensure_optimal_demo_accounts_impl
        await ensure_optimal_demo_accounts_impl(self)

    def _init_core_dependencies(
        self,
        scanner: Any,
        factory: Optional[Any] = None,
        risk: Any = None,
        executor: Any = None,
        storage: Optional[StorageManager] = None,
        config_path: Optional[str] = None,
        strategy_ranker: Optional[Any] = None,
        execution_feedback_collector: Optional[Any] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
    ) -> None:
        init_methods.init_core_dependencies(
            self,
            scanner,
            factory,
            risk,
            executor,
            storage,
            config_path,
            strategy_ranker,
            execution_feedback_collector,
            user_id,
            tenant_id,
        )

    def _load_dynamic_usr_strategies(self) -> None:
        init_methods.load_dynamic_usr_strategies(self)

    def _init_position_management(self) -> None:
        init_methods.init_position_management(self)

    def _init_ancillary_services(
        self,
        expiration: Optional[Any],
        coherence: Optional[Any],
        listener: Optional[Any],
    ) -> None:
        init_methods.init_ancillary_services(self, expiration, coherence, listener)

    def _init_sys_config(self) -> None:
        init_methods.init_sys_config(self)

    def _init_loop_intervals(self) -> None:
        init_methods.init_loop_intervals(self)

    def _init_broker_discovery(self) -> None:
        init_methods.init_broker_discovery(self)

    def _init_orchestration_services(
        self,
        ui_mapping: Optional[Any],
        heartbeat: Optional[Any],
        resolver: Optional[Any],
    ) -> None:
        init_methods.init_orchestration_services(self, ui_mapping, heartbeat, resolver)

    def _init_market_analysis_services(self) -> None:
        init_methods.init_market_analysis_services(self)

    def _init_economic_integration(self) -> None:
        init_methods.init_economic_integration(self)

    def _init_phase4_intelligence_services(
        self,
        signal_quality_scorer: Optional[Any],
        consensus_engine: Optional[Any],
        failure_pattern_registry: Optional[Any],
    ) -> None:
        init_methods.init_phase4_intelligence_services(
            self,
            signal_quality_scorer,
            consensus_engine,
            failure_pattern_registry,
        )

    def _init_shadow_manager(self) -> None:
        init_methods.init_shadow_manager(self)

    def _init_backtest_orchestrator(self) -> None:
        init_methods.init_backtest_orchestrator(self)

    async def initialize_shadow_pool(
        self,
        strategy_engines: Dict[str, Any],
        account_id: str = "DEMO_MT5_001",
        variations_per_strategy: int = 2,
    ) -> Dict[str, Any]:
        return await discovery.initialize_shadow_pool_impl(
            self,
            strategy_engines,
            account_id,
            variations_per_strategy,
        )

    async def provision_all_demo_accounts(self) -> None:
        await discovery.provision_all_demo_accounts_impl(self)

    def initialize_sensors(self) -> Dict[str, Any]:
        return init_methods.initialize_sensors_impl(self)

    def set_signal_factory(self, signal_factory: Optional[Any]) -> None:
        self.signal_factory = signal_factory
        if signal_factory is None:
            init_methods.load_dynamic_usr_strategies(self)

    def _get_sleep_interval(self) -> int:
        return discovery.get_sleep_interval_impl(self)

    def _is_market_closed(self) -> bool:
        return init_methods.is_market_closed_impl(self)

    async def _sync_economic_caution_state(self, caution_symbols: set, trace_id: str) -> None:
        await init_methods.sync_economic_caution_state(self, caution_symbols, trace_id)

    async def _check_and_run_daily_backtest(self) -> None:
        await background_tasks.check_and_run_daily_backtest(self)

    async def _check_and_run_weekly_dedup_learning(self) -> None:
        await background_tasks.check_and_run_weekly_dedup_learning(self)

    async def _check_and_run_weekly_shadow_evolution(self) -> None:
        await background_tasks.check_and_run_weekly_shadow_evolution(self)

    async def _consume_oem_repair_flags(self) -> None:
        await background_tasks.consume_oem_repair_flags(self)

    async def emit_shadow_status_update(
        self,
        instance_id: str,
        health_status: str,
        pilar1_status: str,
        pilar2_status: str,
        pilar3_status: str,
        metrics: dict,
        trace_id: str,
        action: str,
    ) -> None:
        try:
            metrics_payload = metrics
            if hasattr(metrics, "model_dump"):
                metrics_payload = metrics.model_dump()
            elif hasattr(metrics, "dict"):
                metrics_payload = metrics.dict()
            elif hasattr(metrics, "__dict__") and not isinstance(metrics, dict):
                metrics_payload = vars(metrics)

            payload = {
                "event_type": "SHADOW_STATUS_UPDATE",
                "instance_id": instance_id,
                "health_status": getattr(health_status, "value", health_status),
                "pilar1_status": pilar1_status,
                "pilar2_status": pilar2_status,
                "pilar3_status": pilar3_status,
                "metrics": metrics_payload,
                "action": action,
                "trace_id": trace_id,
            }
            await broadcast_shadow_update(self.user_id, payload)
        except Exception as e:
            logger.error(f"[SHADOW_WS] Error emitting shadow status update: {e}")

    async def _check_closed_usr_positions(self) -> None:
        await background_tasks.check_closed_usr_positions(self)

    def _get_scan_schedule(self) -> Dict[str, Any]:
        return scan_methods.get_scan_schedule(self)

    def _should_scan_now(self, schedule: Dict[str, Any]) -> Any:
        return scan_methods.should_scan_now(self, schedule)

    async def _request_scan(self, assets_to_scan: Any) -> Dict[str, Any]:
        return await scan_methods.request_scan(self, assets_to_scan)

    def _update_regime_from_scan(self, scan_results: Dict[str, Any]) -> None:
        scan_methods.update_regime_from_scan(self, scan_results)

    def _persist_scan_telemetry(self, scan_results_with_data: Dict[str, Any]) -> None:
        scan_methods.persist_scan_telemetry(self, scan_results_with_data)

    async def run_single_cycle(self) -> None:
        try:
            if not await cycle_scan.run_pre_phase(self):
                return
            scan_bundle = await cycle_scan.run_scan_phase(self)
            if scan_bundle is None:
                return
            if not await cycle_exec.run_econ_phase(self, scan_bundle):
                return
            signals = await cycle_exec.run_signal_filter(self, scan_bundle)
            if signals is None:
                return
            await cycle_trade.run_execute_phase(self, signals, scan_bundle)
        except Exception as e:
            logger.error(f"Error in cycle execution: {e}", exc_info=True)
            self.stats.errors_count += 1
            self.stats.cycles_completed += 1

    def _update_all_usr_strategies_heartbeat(self) -> None:
        lifecycle.update_all_usr_strategies_heartbeat(self)

    def _persist_session_stats(self) -> None:
        lifecycle.persist_session_stats_impl(self)

    def _is_strategy_authorized_for_execution(self, signal: Any) -> bool:
        return lifecycle.is_strategy_authorized_for_execution(self, signal)

    async def run(self) -> None:
        await lifecycle.run_main_loop(self)

    async def shutdown(self) -> None:
        await lifecycle.shutdown_impl(self)

    def _register_signal_handlers(self) -> None:
        lifecycle.register_signal_handlers(self)


async def main() -> None:
    await lifecycle.main()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown by user.")
