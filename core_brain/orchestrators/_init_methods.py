"""
Initialization helper implementations extracted from MainOrchestrator.__init__.

All functions receive `orch: MainOrchestrator` and set attributes on it.
Pattern: called directly from __init__ body (no thin wrapper on class needed).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

logger = logging.getLogger(__name__)


def init_core_dependencies(
    orch: "MainOrchestrator",
    scanner: Any,
    factory: Optional[Any],
    risk: Any,
    executor: Any,
    storage: Optional[Any],
    config_path: Optional[str],
    strategy_ranker: Any,
    execution_feedback_collector: Any,
    user_id: Optional[str],
    tenant_id: Optional[str],
) -> None:
    """Initialize core engines and resolve storage/config."""
    from core_brain.main_orchestrator import _resolve_storage
    from core_brain.strategy_ranker import StrategyRanker
    from core_brain.execution_feedback import ExecutionFeedbackCollector
    from core_brain.signal_selector import SignalSelector
    from core_brain.cooldown_manager import CooldownManager
    from core_brain.orchestrators._discovery import load_config

    effective_user_id = user_id or tenant_id
    orch.scanner = scanner
    orch._signal_factory = factory
    orch.risk_manager = risk
    orch.executor = executor

    # Resolve storage with user isolation
    orch.storage = _resolve_storage(storage, user_id=effective_user_id)

    orch.strategy_ranker = strategy_ranker or StrategyRanker(storage=orch.storage)
    orch.config = load_config(orch, config_path)
    orch.execution_feedback_collector = (
        execution_feedback_collector or ExecutionFeedbackCollector(storage=orch.storage)
    )
    logger.info("[FEEDBACK] ExecutionFeedbackCollector initialized (DOMINIO-10 Auto-Healing)")

    orch.signal_selector = SignalSelector(storage_manager=orch.storage)
    orch.cooldown_manager = CooldownManager(storage_manager=orch.storage)
    logger.info("[DEDUP] Signal Selector & Cooldown Manager initialized (HU 3.3/4.7)")


def load_dynamic_usr_strategies(orch: "MainOrchestrator") -> None:
    """Load all usr_strategies dynamically from DB (MANIFESTO II.3-II.4)."""
    try:
        from core_brain.services.strategy_engine_factory import StrategyEngineFactory
        from core_brain.signal_factory import SignalFactory
        from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
        from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
        from core_brain.strategy_validator_quanter import StrategySignalValidator
        from core_brain.services.shadow_penalty_injector import ShadowPenaltyInjector

        logger.info("[STRATEGIES] Initiating dynamic loading from BD (SSOT)...")

        if not orch.available_sensors:
            logger.info("[STRATEGIES] Sensors not yet initialized, initializing now...")
            orch.initialize_sensors()

        dynamic_params = orch.storage.get_dynamic_params()
        confluence_analyzer = MultiTimeframeConfluenceAnalyzer(storage=orch.storage)
        trifecta_analyzer = TrifectaAnalyzer(storage=orch.storage)
        logger.info(f"[STRATEGIES] Using sensors: {list(orch.available_sensors.keys())}")

        strategy_factory = StrategyEngineFactory(
            storage=orch.storage,
            config=dynamic_params,
            available_sensors=orch.available_sensors,
        )
        active_engines = strategy_factory.instantiate_all_sys_strategies()
        stats = strategy_factory.get_stats()

        signal_validator = StrategySignalValidator(storage_manager=orch.storage)
        shadow_penalty_injector = ShadowPenaltyInjector(storage_manager=orch.storage)

        orch.signal_factory = SignalFactory(
            storage_manager=orch.storage,
            strategy_engines=active_engines,
            confluence_analyzer=confluence_analyzer,
            trifecta_analyzer=trifecta_analyzer,
            execution_feedback_collector=orch.execution_feedback_collector,
            signal_validator=signal_validator,
            shadow_penalty_injector=shadow_penalty_injector,
        )
        logger.info(
            f"[STRATEGIES] Dynamic loading complete: "
            f"{stats['active_engines']} active, {stats['failed_loads']} skipped"
        )
    except Exception as e:
        logger.error(f"[STRATEGIES] Failed to load usr_strategies dynamically: {e}", exc_info=True)
        logger.warning("[STRATEGIES] Continuing with existing SignalFactory (may have 0 engines)")


def initialize_sensors_impl(orch: "MainOrchestrator") -> Dict[str, Any]:
    """Explicitly initialize ALL sensors and store in orch.available_sensors."""
    try:
        from core_brain.services.fundamental_guard import FundamentalGuardService
        from core_brain.sensors import (
            MovingAverageSensor,
            ElephantCandleDetector,
            SessionLiquiditySensor,
            LiquiditySweepDetector,
            MarketStructureAnalyzer,
            SessionStateDetector,
            ReasoningEventBuilder,
        )

        logger.info("[SENSORS] Initializing all sensors (explicit DI)...")
        moving_avg_sensor = MovingAverageSensor(storage=orch.storage)
        elephant_detector = ElephantCandleDetector(
            storage=orch.storage, moving_average_sensor=moving_avg_sensor
        )
        liq_sensor = SessionLiquiditySensor(storage=orch.storage)
        liq_sweep_detector = LiquiditySweepDetector(storage=orch.storage)
        market_struct_analyzer = MarketStructureAnalyzer(storage=orch.storage)
        session_state = SessionStateDetector(storage=orch.storage)
        reasoning_builder = ReasoningEventBuilder(
            storage=orch.storage, market_structure_analyzer=market_struct_analyzer
        )
        fundamental_guard = FundamentalGuardService(storage=orch.storage)

        orch.available_sensors = {
            "moving_average_sensor": moving_avg_sensor,
            "elephant_candle_detector": elephant_detector,
            "session_liquidity_sensor": liq_sensor,
            "liquidity_sweep_detector": liq_sweep_detector,
            "market_structure_analyzer": market_struct_analyzer,
            "session_state_detector": session_state,
            "reasoning_event_builder": reasoning_builder,
            "fundamental_guard": fundamental_guard,
        }
        logger.info(f"[SENSORS] All sensors initialized: {list(orch.available_sensors.keys())}")
        return orch.available_sensors
    except Exception as e:
        logger.error(f"[SENSORS] Failed to initialize sensors: {e}", exc_info=True)
        raise


def is_market_closed_impl(orch: "MainOrchestrator") -> bool:
    """Returns True when forex market is closed (weekend / no active session). Fail-open."""
    try:
        _utc_now = datetime.now(timezone.utc)
        _weekday = _utc_now.weekday()
        if _weekday == 5 or (_weekday == 6 and _utc_now.hour < 22):
            return True
        from core_brain.services.market_session_service import MarketSessionService

        _active_sessions = MarketSessionService(orch.storage).get_active_sessions_utc(_utc_now)
        return not _active_sessions
    except Exception:
        return False  # fail-open


def init_position_management(orch: "MainOrchestrator") -> None:
    """Initialize PositionManager with configuration mapping and connector resolution."""
    from core_brain.position_manager import PositionManager
    from typing import List, Dict

    pm_cfg_raw = orch.config.get("position_management", {}) if isinstance(orch.config, dict) else {}
    pm_cfg = dict(pm_cfg_raw) if isinstance(pm_cfg_raw, dict) else {}

    map_keys = {
        "modification_cooldown_seconds": "cooldown_seconds",
        "stale_position_thresholds": "stale_thresholds_hours",
        "sl_tp_adjustments": "regime_adjustments",
    }
    for old, new in map_keys.items():
        if old in pm_cfg and new not in pm_cfg:
            pm_cfg[new] = pm_cfg[old]

    pm_cfg.setdefault("max_drawdown_multiplier", 2.0)
    pm_cfg.setdefault("cooldown_seconds", 300)
    pm_cfg.setdefault("max_modifications_per_day", 10)

    connector = None
    connectors = getattr(orch.executor, "connectors", None)
    if isinstance(connectors, dict) and connectors:
        connector = next(iter(connectors.values()))

    if connector is None:
        class _NullConnector:
            def get_open_positions(self) -> List[Dict[str, Any]]:
                return []
        connector = _NullConnector()

    orch.position_manager = PositionManager(
        storage=orch.storage,
        connector=connector,
        regime_classifier=orch.regime_classifier,
        config=pm_cfg,
    )


def init_ancillary_services(
    orch: "MainOrchestrator",
    expiration: Optional[Any],
    coherence: Optional[Any],
    listener: Optional[Any],
) -> None:
    """Initialize secondary services: expiration, coherence monitor, trade closure."""
    from core_brain.main_orchestrator import SignalExpirationManager
    from core_brain.coherence_monitor import CoherenceMonitor
    from core_brain.trade_closure_listener import TradeClosureListener
    from core_brain.edge_tuner import EdgeTuner
    from core_brain.threshold_optimizer import ThresholdOptimizer

    orch.expiration_manager = expiration or SignalExpirationManager(storage=orch.storage)
    orch.coherence_monitor = coherence or CoherenceMonitor(storage=orch.storage)

    if listener is None:
        orch.trade_closure_listener = TradeClosureListener(
            storage=orch.storage,
            risk_manager=orch.risk_manager,
            edge_tuner=EdgeTuner(storage=orch.storage),
            threshold_optimizer=ThresholdOptimizer(storage=orch.storage),
        )
    else:
        orch.trade_closure_listener = listener


def init_sys_config(orch: "MainOrchestrator") -> None:
    """Load global module status and session statistics from SSOT."""
    from core_brain.main_orchestrator import SessionStats

    modules = (
        orch.storage.get_global_modules_enabled()
        if hasattr(orch.storage, "get_global_modules_enabled")
        else {}
    )
    orch.modules_enabled_global = modules if isinstance(modules, dict) else {}

    disabled = [k for k, v in orch.modules_enabled_global.items() if not v]
    if disabled:
        logger.warning(f"[WARNING] Modules DISABLED globally: {', '.join(disabled)}")
    else:
        logger.info("[OK] Todos los módulos están HABILITADOS globalmente")

    orch.stats = SessionStats.from_storage(orch.storage)
    orch.current_regime = None  # set properly below via import
    from models.signal import MarketRegime
    orch.current_regime = MarketRegime.RANGE
    orch._shutdown_requested = False
    orch._active_usr_signals = []
    orch._last_checked_deal_ticket = 0
    orch._consecutive_empty_structure_cycles = 0
    orch._max_consecutive_empty_cycles = 3


def init_loop_intervals(orch: "MainOrchestrator") -> None:
    """Set up main orchestrator loop intervals per regime."""
    from models.signal import MarketRegime
    from datetime import timedelta

    orchestrator_config = orch.config.get("orchestrator", {})
    orch.intervals = {
        MarketRegime.TREND: orchestrator_config.get("loop_interval_trend", 5),
        MarketRegime.RANGE: orchestrator_config.get("loop_interval_range", 30),
        MarketRegime.VOLATILE: orchestrator_config.get("loop_interval_volatile", 15),
        MarketRegime.SHOCK: orchestrator_config.get("loop_interval_shock", 60),
    }
    logger.info(f"MainOrchestrator heartbeat: MIN={orch.MIN_SLEEP_INTERVAL}s")

    orch._last_ranking_cycle = datetime.now(timezone.utc) - timedelta(minutes=10)
    orch._ranking_interval = 300  # 5 minutes


def init_broker_discovery(orch: "MainOrchestrator") -> None:
    """Discover and classify available sys_brokers from storage."""
    from core_brain.orchestrators._discovery import discover_brokers, classify_brokers

    orch.sys_brokers = discover_brokers(orch)
    orch.broker_status = classify_brokers(orch, orch.sys_brokers)


def init_orchestration_services(
    orch: "MainOrchestrator",
    ui_mapping: Optional[Any],
    heartbeat: Optional[Any],
    resolver: Optional[Any],
) -> None:
    """Initialize orchestration & reporting services (Vector V4)."""
    if ui_mapping is not None:
        orch.ui_mapping_service = ui_mapping
        logger.info("[ORCHESTRATOR] UI_Mapping_Service injected from parameter")
    else:
        try:
            from core_brain.services.ui_mapping_service import UIMappingService
            from core_brain.services.socket_service import get_socket_service
            socket_svc = get_socket_service()
            orch.ui_mapping_service = UIMappingService(socket_service=socket_svc)
            logger.info("[ORCHESTRATOR] UI_Mapping_Service initialized successfully")
        except ImportError as e:
            logger.error(f"[ORCHESTRATOR] ImportError initializing UI_Mapping_Service: {e}", exc_info=True)
            orch.ui_mapping_service = None
        except Exception as e:
            logger.error(f"[ORCHESTRATOR] Exception initializing UI_Mapping_Service: {e}", exc_info=True)
            orch.ui_mapping_service = None

    if heartbeat is not None:
        orch.heartbeat_monitor = heartbeat
    else:
        try:
            from core_brain.services.strategy_heartbeat_monitor import StrategyHeartbeatMonitor
            socket_svc = getattr(orch, "socket_service", None)
            orch.heartbeat_monitor = StrategyHeartbeatMonitor(
                storage=orch.storage, socket_service=socket_svc
            )
            logger.info("[ORCHESTRATOR] StrategyHeartbeatMonitor initialized (default)")
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not initialize StrategyHeartbeatMonitor: {e}")
            orch.heartbeat_monitor = None

    if resolver is not None:
        orch.conflict_resolver = resolver
    else:
        try:
            from core_brain.conflict_resolver import ConflictResolver
            fundamental_guard = getattr(orch.risk_manager, "fundamental_guard", None)
            orch.conflict_resolver = ConflictResolver(
                storage=orch.storage,
                regime_classifier=orch.regime_classifier,
                fundamental_guard=fundamental_guard,
            )
            logger.info("[ORCHESTRATOR] ConflictResolver initialized (default)")
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not initialize ConflictResolver: {e}")
            orch.conflict_resolver = None


def init_market_analysis_services(orch: "MainOrchestrator") -> None:
    """Initialize MarketStructureAnalyzer for UI integration."""
    try:
        from core_brain.sensors.market_structure_analyzer import MarketStructureAnalyzer
        orch.market_structure_analyzer = MarketStructureAnalyzer(storage=orch.storage)
        logger.info("[ORCHESTRATOR] MarketStructureAnalyzer initialized for UI data feed")
    except Exception as e:
        logger.warning(f"[ORCHESTRATOR] Could not initialize MarketStructureAnalyzer: {e}")
        orch.market_structure_analyzer = None


def init_economic_integration(orch: "MainOrchestrator") -> None:
    """Initialize Economic Calendar Veto Interface (PHASE 8)."""
    orch._econ_veto_symbols = set()
    orch._econ_caution_symbols = set()
    orch._prev_econ_caution_symbols = set()

    try:
        from core_brain.economic_integration import create_economic_integration
        from connectors.economic_data_gateway import EconomicDataProviderRegistry
        from core_brain.news_sanitizer import NewsSanitizer

        logger.info("[ECON-INTEGRATION] Initializing Economic Calendar Veto Interface...")
        orch.economic_integration = create_economic_integration(
            gateway=EconomicDataProviderRegistry(),
            sanitizer=NewsSanitizer(),
            storage=orch.storage,
            scheduler_config=None,
        )
        logger.info("[ECON-INTEGRATION] Economic integration ready for use")
    except Exception as e:
        logger.warning(f"[ECON-INTEGRATION] Could not initialize: {e}")
        orch.economic_integration = None


async def sync_economic_caution_state(
    orch: "MainOrchestrator",
    caution_symbols: set,
    trace_id: str,
) -> None:
    """Sync CAUTION symbol transitions and trigger post-CAUTION rebalance (DISC-005)."""
    previous_symbols = getattr(orch, "_prev_econ_caution_symbols", set())
    entered_caution = caution_symbols - previous_symbols
    exited_caution = previous_symbols - caution_symbols

    if not entered_caution and not exited_caution:
        return

    for symbol in entered_caution:
        try:
            orch.storage.update_sys_config({f"econ_risk_multiplier_{symbol}": 0.5})
            logger.info(
                f"[ECON-CAUTION] [TRACE_ID: {trace_id}] {symbol} entered CAUTION "
                f"(risk multiplier=0.5)"
            )
        except Exception as e:
            logger.error(
                f"[ECON-CAUTION] [TRACE_ID: {trace_id}] Failed persisting CAUTION "
                f"state for {symbol}: {e}",
                exc_info=True,
            )

    for symbol in exited_caution:
        try:
            if hasattr(orch.risk_manager, "rebalance_after_caution"):
                await orch.risk_manager.rebalance_after_caution(
                    symbol=symbol, trace_id=trace_id
                )
            else:
                orch.storage.update_sys_config({f"econ_risk_multiplier_{symbol}": 1.0})
            logger.info(
                f"[ECON-CAUTION] [TRACE_ID: {trace_id}] {symbol} exited CAUTION "
                f"(risk multiplier restored)"
            )
        except Exception as e:
            logger.error(
                f"[ECON-CAUTION] [TRACE_ID: {trace_id}] Failed post-CAUTION rebalance "
                f"for {symbol}: {e}",
                exc_info=True,
            )

    orch._prev_econ_caution_symbols = set(caution_symbols)


def init_phase4_intelligence_services(
    orch: "MainOrchestrator",
    signal_quality_scorer: Optional[Any],
    consensus_engine: Optional[Any],
    failure_pattern_registry: Optional[Any],
) -> None:
    """Initialize PHASE 4 Signal Quality Scoring components."""
    try:
        from core_brain.intelligence import (
            SignalQualityScorer,
            ConsensusEngine,
            FailurePatternRegistry,
        )
        logger.info("[PHASE4] Initializing Signal Quality Scoring Intelligence...")
        orch.signal_quality_scorer = signal_quality_scorer or SignalQualityScorer(
            storage_manager=orch.storage
        )
        orch.consensus_engine = consensus_engine or ConsensusEngine(
            storage_manager=orch.storage
        )
        orch.failure_pattern_registry = failure_pattern_registry or FailurePatternRegistry(
            storage_manager=orch.storage
        )
        logger.info("[PHASE4] All signal quality intelligence components ready")
    except Exception as e:
        logger.warning(f"[PHASE4] Could not initialize intelligence services: {e}")
        orch.signal_quality_scorer = None
        orch.consensus_engine = None
        orch.failure_pattern_registry = None


def init_shadow_manager(orch: "MainOrchestrator") -> None:
    """Initialize ShadowManager with EdgeTuner (extracted from __init__ try/except)."""
    try:
        from core_brain.shadow_manager import ShadowManager
        from core_brain.edge_tuner import EdgeTuner

        dyn = orch.storage.get_dynamic_params() or {}
        pilar3_min = int(dyn.get("pilar3_min_trades", 5))
        orch.shadow_manager = ShadowManager(
            storage=orch.storage,
            regime_classifier=orch.regime_classifier,
            edge_tuner=EdgeTuner(orch.storage),
            pilar3_min_trades=pilar3_min,
        )
        orch.last_shadow_evolution = None
    except Exception as e:
        logger.warning(f"[WEEK3] Failed to initialize ShadowManager: {e}")
        orch.shadow_manager = None
        orch.last_shadow_evolution = None


def init_backtest_orchestrator(orch: "MainOrchestrator") -> None:
    """Initialize BacktestOrchestrator + OperationalModeManager (extracted from __init__)."""
    orch.backtest_orchestrator = None
    orch._last_backtest_run = None
    try:
        from core_brain.backtest_orchestrator import BacktestOrchestrator
        from core_brain.scenario_backtester import ScenarioBacktester
        from core_brain.data_provider_manager import DataProviderManager

        bkt_dpm = DataProviderManager(storage=orch.storage)
        orch.backtest_orchestrator = BacktestOrchestrator(
            storage=orch.storage,
            data_provider_manager=bkt_dpm,
            scenario_backtester=ScenarioBacktester(orch.storage),
            shadow_manager=orch.shadow_manager,
        )
    except Exception as e:
        logger.warning(f"[BACKTEST] Failed to initialize BacktestOrchestrator: {e}")

    orch.operational_mode_manager = None
    try:
        from core_brain.operational_mode_manager import OperationalModeManager

        orch.operational_mode_manager = OperationalModeManager(storage=orch.storage)
        if orch.backtest_orchestrator is not None:
            orch.backtest_orchestrator.mode_manager = orch.operational_mode_manager
    except Exception as e:
        logger.warning(f"[MODE_MGR] Failed to initialize OperationalModeManager: {e}")
