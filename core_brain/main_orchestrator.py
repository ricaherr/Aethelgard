"""
Main Orchestrator - Aethelgard Trading System
=============================================

Orchestrates the complete trading cycle: Scan -> Signal -> Risk -> Execute.

Key Features:
- Asynchronous event loop for non-blocking operation
- Dynamic frequency adjustment based on market regime
- Session statistics with DB reconstruction (Resilient Recovery)
- Adaptive heartbeat (faster when usr_signals active)
- Graceful shutdown with state persistence
- Error resilience with automatic recovery

Principles Applied:
- Autonomy: Self-regulating loop frequency + adaptive heartbeat
- Resilience: Reconstructs session state from DB after restart
- Agnosticism: Works with any injected components
- Security: Persists critical state before shutdown

Architecture: "Orquestador Resiliente"
- SessionStats se reconstruye desde la DB al iniciar
- Latido de Guardia: sleep se reduce si hay señales activas
- Persistencia completa de usr_trades ejecutados del día
"""
import sys
import os
import asyncio
import json
import logging
import signal
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional, Any, List
import uuid

# Add project root to path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from models.signal import MarketRegime, Signal
from data_vault.storage import StorageManager
from core_brain.coherence_monitor import CoherenceMonitor
from core_brain.signal_expiration_manager import SignalExpirationManager
from core_brain.position_manager import PositionManager
from core_brain.regime import RegimeClassifier
from core_brain.edge_tuner import EdgeTuner
from core_brain.threshold_optimizer import ThresholdOptimizer
from core_brain.execution_feedback import ExecutionFeedbackCollector, ExecutionFailureReason
from core_brain.trade_closure_listener import TradeClosureListener
from core_brain.strategy_ranker import StrategyRanker

logger = logging.getLogger(__name__)

def _resolve_storage(storage: Optional[StorageManager], user_id: Optional[str] = None) -> StorageManager:
    """
    Resolve storage dependency with legacy fallback.
    Main path should inject StorageManager from composition root.
    
    Multi-tenant architecture: Supports user_id for user-aware DB isolation.
    
    Raises:
        RuntimeError: If StorageManager initialization fails and storage is None.
    """
    if storage is not None:
        return storage
    
    logger.warning(f"MainOrchestrator initialized without explicit storage! Falling back to default storage (user_id={user_id}).")
    
    try:
        return StorageManager(user_id=user_id)
    except Exception as e:
        logger.error(f"CRITICAL: Failed to initialize StorageManager with user_id={user_id}. Error: {str(e)}", exc_info=True)
        raise RuntimeError(f"StorageManager initialization failed: {str(e)}") from e


@dataclass
class PriceSnapshot:
    """Atomic snapshot of price data with provider traceability.
    
    Ensures every decision in the pipeline knows:
    - WHAT data was used (df)
    - WHERE it came from (provider_source)
    - WHEN it was captured (timestamp)
    
    Rule: If MT5 is connected, MT5 is the SSOT for live prices.
    Yahoo is strictly a historical fallback.
    """
    symbol: str
    timeframe: str
    df: Any  # pd.DataFrame
    provider_source: str
    timestamp: datetime = field(default_factory=datetime.now)
    regime: Optional[Any] = None  # MarketRegime


# Global references for API/Control
scanner = None
orchestrator = None

@dataclass
class SessionStats:
    """
    Tracks session statistics for the current trading day.
    Resets automatically when a new day begins.
    
    RESILIENCIA: Can reconstruct state from database on initialization.
    This ensures usr_trades executed today are not forgotten after restarts.
    """
    date: date = field(default_factory=lambda: date.today())
    usr_signals_processed: int = 0
    usr_signals_executed: int = 0
    cycles_completed: int = 0
    errors_count: int = 0
    # Pipeline tracking
    scans_total: int = 0
    usr_signals_generated: int = 0
    usr_signals_risk_passed: int = 0
    usr_signals_vetoed: int = 0
    
    @classmethod
    def from_storage(cls, storage: StorageManager) -> 'SessionStats':
        """
        Reconstruct SessionStats from persistent storage.
        
        This method enables recovery after system restarts, ensuring
        we don't lose track of today's executed usr_signals.
        
        Args:
            storage: StorageManager instance to query
            
        Returns:
            SessionStats instance reconstructed from DB
        """
        today = date.today()
        
        # Query DB for today's executed usr_signals (marked with status='executed')
        executed_count = storage.count_executed_usr_signals(today)
        
        # Retrieve system state for other metrics
        sys_config = storage.get_sys_config()
        session_data = sys_config.get("session_stats", {})
        
        # Check if session data is from today
        stored_date_str = session_data.get("date", "")
        try:
            stored_date = date.fromisoformat(stored_date_str)
            is_today = stored_date == today
        except (ValueError, TypeError):
            is_today = False
        
        if is_today:
            # Restore full stats from storage
            stats = cls(
                date=today,
                usr_signals_processed=session_data.get("usr_signals_processed", 0),
                usr_signals_executed=executed_count,  # Always source from DB
                cycles_completed=session_data.get("cycles_completed", 0),
                errors_count=session_data.get("errors_count", 0)
            )
            logger.info(f"SessionStats reconstructed from DB: {stats}")
        else:
            # Fresh start for new day
            stats = cls(date=today, usr_signals_executed=executed_count)
            logger.info(f"New day detected. Fresh SessionStats initialized: {stats}")
        
        return stats
    
    def reset_if_new_day(self) -> None:
        """Reset stats if a new day has started"""
        today = date.today()
        if self.date != today:
            logger.info(f"New day detected. Resetting stats. Previous: {self}")
            self.date = today
            self.usr_signals_processed = 0
            self.usr_signals_executed = 0
            self.cycles_completed = 0
            self.errors_count = 0
    
    def __str__(self) -> str:
        return (
            f"SessionStats(date={self.date}, "
            f"processed={self.usr_signals_processed}, "
            f"executed={self.usr_signals_executed}, "
            f"cycles={self.cycles_completed}, "
            f"errors={self.errors_count})"
        )


class MainOrchestrator:
    async def ensure_optimal_demo_accounts(self) -> None:
        """
        Provisiona cuentas demo maestras solo cuando sea óptimo:
        - Al inicio si no existe cuenta válida
        - Si falla la conexión o expira la cuenta
        - Cuando el usuario activa modo DEMO y no hay cuenta
        """
        from connectors.auto_provisioning import BrokerProvisioner
        provisioner = BrokerProvisioner(storage=self.storage)
        for broker_id, info in self.broker_status.items():
            if info['auto_provision']:
                # Verificar si existe cuenta demo válida
                if not provisioner.has_demo_account(broker_id):
                    logger.info(f"[EDGE] No existe cuenta demo válida para {broker_id}. Provisionando...")
                    success, result = await provisioner.ensure_demo_account(broker_id)
                    if success:
                        self.broker_status[broker_id]['status'] = 'demo_ready'
                        logger.info(f"[OK] Cuenta demo lista para {broker_id}")
                    else:
                        self.broker_status[broker_id]['status'] = f"error: {result.get('error', 'unknown')}"
                        logger.warning(f"[ERROR] Error al provisionar demo {broker_id}: {result}")
                else:
                    logger.info(f"[EDGE] Ya existe cuenta demo válida para {broker_id}. No se reprovisiona.")
            else:
                self.broker_status[broker_id]['status'] = 'manual_required'
                logger.info(f"[WARNING]  {broker_id} requiere provisión manual")
    """
    Main orchestrator for the Aethelgard trading system.
    
    Manages the complete trading cycle:
    1. Scanner: Identifies market opportunities
    2. Signal Factory: Generates trading usr_signals
    3. Risk Manager: Validates risk parameters
    4. Executor: Places usr_orders
    
    Features:
    - Dynamic loop frequency based on market regime
    - Adaptive heartbeat: faster sleep when active usr_signals present
    - Resilient recovery: reconstructs session state from DB
    - Latido de Guardia: CPU-friendly monitoring
    """
    
    # Adaptive heartbeat constants
    MIN_SLEEP_INTERVAL = 3  # Seconds (when usr_signals active)
    HEARTBEAT_CHECK_INTERVAL = 1  # Check every second for shutdown
    
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
        strategy_ranker: Optional[StrategyRanker] = None,
        thought_callback: Optional[Any] = None,
        config_path: Optional[str] = None,
        ui_mapping_service: Optional[Any] = None,
        heartbeat_monitor: Optional[Any] = None,
        conflict_resolver: Optional[Any] = None,
        execution_feedback_collector: Optional[ExecutionFeedbackCollector] = None,
        tenant_id: Optional[str] = None,  # DEPRECATED: Use user_id instead
        user_id: Optional[str] = None  # Multi-user support: User identifier for DB isolation
    ):
        """
        Initialize MainOrchestrator with Explicit Dependency Injection (SOLID).
        
        TRACE_ID: MAIN-ORCHESTRATOR-DI-SEPARATION-2026
        
        signal_factory is NOW OPTIONAL:
        - If None: User must call initialize_sensors() then set_signal_factory() afterwards
        - If provided: Uses it immediately (backward compatible)
        
        This separation allows:
        1. Sensors to be initialized FIRST
        2. SignalFactory created WITH sensores already available
        3. Zero duplicate strategy loads
        """
        self.thought_callback = thought_callback
        # Support both old (tenant_id) and new (user_id) parameters
        effective_user_id = user_id or tenant_id
        self.user_id = effective_user_id  # Store user context
        
        # Initialize sensor dictionary early (will be populated by initialize_sensors())
        self.available_sensors = {}
        self._signal_factory = signal_factory  # Store for later injection if None
        
        # 1. Base dependencies and config
        self._init_core_dependencies(scanner, signal_factory, risk_manager, executor, storage, config_path, strategy_ranker, execution_feedback_collector=execution_feedback_collector, user_id=effective_user_id, tenant_id=tenant_id)
        
        # 1.5 Load usr_strategies dynamically ONLY if signal_factory was provided
        # Otherwise, user must call initialize_sensors() + set_signal_factory() explicitly
        if signal_factory is not None:
            self._load_dynamic_usr_strategies()
        
        # 2. Classifier and Position Management
        self.regime_classifier = regime_classifier or RegimeClassifier(storage=self.storage)
        if position_manager is None:
            self._init_position_management()
        else:
            self.position_manager = position_manager

        # 3. Ancillary Services (Expiration, Coherence, Listeners)
        self._init_ancillary_services(expiration_manager, coherence_monitor, trade_closure_listener)

        # 4. System State and Session Tracking (SSOT)
        self._init_sys_config()
        
        # 5. Cycle intervals and Heartbeat
        self._init_loop_intervals()

        # 6. Broker Discovery and Status
        self._init_broker_discovery()

        # 7. Orchestration & Reporting (NEW - Vector V4)
        self._init_orchestration_services(ui_mapping_service, heartbeat_monitor, conflict_resolver)

        # 8. Market Analysis & UI Integration (EXEC-UI-DATA-INTEGRATION)
        self._init_market_analysis_services()
        
        # 9. Economic Calendar Veto Interface (PHASE 8: News-Based Trading Lockdown)
        self._init_economic_integration()

    @property
    def signal_factory(self) -> Optional[Any]:
        """Public property for backward compatibility. Returns _signal_factory."""
        return self._signal_factory
    
    @signal_factory.setter
    def signal_factory(self, factory: Optional[Any]) -> None:
        """Setter for backward compatibility."""
        self._signal_factory = factory

    def _init_core_dependencies(self, scanner: Any, factory: Optional[Any] = None, risk: Any = None, executor: Any = None, storage: Optional[Any] = None, config_path: Optional[str] = None, strategy_ranker: Optional[StrategyRanker] = None, execution_feedback_collector: Optional[ExecutionFeedbackCollector] = None, user_id: Optional[str] = None, tenant_id: Optional[str] = None) -> None:
        """Initializes core engines and resolves storage/config.
        
        Multi-user architecture: Passes user_id to storage resolution for per-user DB isolation.
        tenant_id is deprecated (kept for backward compatibility).
        signal_factory (factory) is optional - can be set later via set_signal_factory().
        execution_feedback_collector is optional - auto-created if None.
        """
        self.scanner = scanner
        self._signal_factory = factory  # Optional - may be None
        self.risk_manager = risk
        self.executor = executor
        effective_user_id = user_id or tenant_id
        self.storage = _resolve_storage(storage, user_id=effective_user_id)
        self.strategy_ranker = strategy_ranker or StrategyRanker(storage=self.storage)
        self.config = self._load_config(config_path)
        
        # Initialize ExecutionFeedbackCollector for autonomous learning loop
        self.execution_feedback_collector = execution_feedback_collector or ExecutionFeedbackCollector(storage=self.storage)
        logger.info(f"[FEEDBACK] ExecutionFeedbackCollector initialized (DOMINIO-10 Auto-Healing)")

    def _load_dynamic_usr_strategies(self) -> None:
        """
        Load all usr_strategies dynamically from BD (MANIFESTO II.3-II.4).
        Creates a new SignalFactory with populated strategy engines.
        CUMPLE: DEVELOPMENT_GUIDELINES 1.6 (Service Layer) + Dynamic Registry.
        
        Uses already-initialized sensors from initialize_sensors() or initializes them if needed.
        """
        try:
            from core_brain.services.strategy_engine_factory import StrategyEngineFactory
            from core_brain.signal_factory import SignalFactory
            from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
            from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
            
            logger.info("[STRATEGIES] Initiating dynamic loading from BD (SSOT)...")
            
            # Ensure sensors are initialized (use existing or create new)
            if not self.available_sensors:
                logger.info("[STRATEGIES] Sensors not yet initialized, initializing now...")
                self.initialize_sensors()
            
            available_sensors = self.available_sensors
            
            # Load required dependencies
            dynamic_params = self.storage.get_dynamic_params()
            confluence_analyzer = MultiTimeframeConfluenceAnalyzer(storage=self.storage)
            trifecta_analyzer = TrifectaAnalyzer(storage=self.storage)
            
            logger.info(f"[STRATEGIES] Using sensors: {list(available_sensors.keys())}")
            
            # Create factory and instantiate all usr_strategies
            strategy_factory = StrategyEngineFactory(
                storage=self.storage,
                config=dynamic_params,
                available_sensors=available_sensors
            )
            active_engines = strategy_factory.instantiate_all_sys_strategies()
            stats = strategy_factory.get_stats()
            
            # Create new SignalFactory with loaded usr_strategies
            self.signal_factory = SignalFactory(
                storage_manager=self.storage,
                strategy_engines=active_engines,
                confluence_analyzer=confluence_analyzer,
                trifecta_analyzer=trifecta_analyzer,
                execution_feedback_collector=self.execution_feedback_collector
            )
            
            logger.info(
                f"[STRATEGIES] ✅ Dynamic loading complete: "
                f"{stats['active_engines']} active, {stats['failed_loads']} skipped"
            )
        except Exception as e:
            logger.error(f"[STRATEGIES] ⚠️  Failed to load usr_strategies dynamically: {e}", exc_info=True)
            logger.warning("[STRATEGIES] Continuing with existing SignalFactory (may have 0 engines)")

    def initialize_sensors(self) -> Dict[str, Any]:
        """
        Explicitly initialize ALL sensors (DI).
        
        Returns:
            Dict[sensor_name -> sensor_instance]
            
        Called BEFORE creating SignalFactory to ensure sensores are ready.
        This method replaces the implicit initialization that was hidden in _load_dynamic_usr_strategies().
        
        TRACE_ID: MAIN-ORCHESTRATOR-SENSOR-INIT-2026
        """
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
            
            # Create all sensors
            moving_avg_sensor = MovingAverageSensor(storage=self.storage)
            elephant_detector = ElephantCandleDetector(
                storage=self.storage, 
                moving_average_sensor=moving_avg_sensor
            )
            liq_sensor = SessionLiquiditySensor(storage=self.storage)
            liq_sweep_detector = LiquiditySweepDetector(storage=self.storage)
            market_struct_analyzer = MarketStructureAnalyzer(storage=self.storage)
            session_state = SessionStateDetector(storage=self.storage)
            reasoning_builder = ReasoningEventBuilder(
                storage=self.storage,
                market_structure_analyzer=market_struct_analyzer
            )
            fundamental_guard = FundamentalGuardService(storage=self.storage)
            
            # Map sensors
            self.available_sensors = {
                "moving_average_sensor": moving_avg_sensor,
                "elephant_candle_detector": elephant_detector,
                "session_liquidity_sensor": liq_sensor,
                "liquidity_sweep_detector": liq_sweep_detector,
                "market_structure_analyzer": market_struct_analyzer,
                "session_state_detector": session_state,
                "reasoning_event_builder": reasoning_builder,
                "fundamental_guard": fundamental_guard,
            }
            
            logger.info(f"[SENSORS] ✓ All sensors initialized: {list(self.available_sensors.keys())}")
            return self.available_sensors
            
        except Exception as e:
            logger.error(f"[SENSORS] ✗ Failed to initialize sensors: {e}", exc_info=True)
            raise

    def set_signal_factory(self, signal_factory: Any) -> None:
        """
        Explicitly inject SignalFactory AFTER sensors are ready.
        
        Args:
            signal_factory: Configured SignalFactory instance
            
        This method is called after initialize_sensors() and main initialization is complete.
        Ensures sensors are available BEFORE strategies are loaded.
        
        TRACE_ID: MAIN-ORCHESTRATOR-SIGNAL-FACTORY-INJECT-2026
        """
        if signal_factory is None:
            raise ValueError("signal_factory cannot be None")
        
        logger.info("[DI] Injecting SignalFactory (sensores already initialized)")
        self._signal_factory = signal_factory  # Property setter handles backward compatibility
        logger.info("[DI] ✓ SignalFactory injected successfully")

    def _init_position_management(self) -> None:
        """Initializes PositionManager with configuration mapping and connector resolution."""
        pm_cfg_raw = self.config.get("position_management", {}) if isinstance(self.config, dict) else {}
        pm_cfg = dict(pm_cfg_raw) if isinstance(pm_cfg_raw, dict) else {}
        
        # Map legacy keys
        map_keys = {
            "modification_cooldown_seconds": "cooldown_seconds",
            "stale_position_thresholds": "stale_thresholds_hours",
            "sl_tp_adjustments": "regime_adjustments"
        }
        for old, new in map_keys.items():
            if old in pm_cfg and new not in pm_cfg:
                pm_cfg[new] = pm_cfg[old]
        
        pm_cfg.setdefault("max_drawdown_multiplier", 2.0)
        pm_cfg.setdefault("cooldown_seconds", 300)
        pm_cfg.setdefault("max_modifications_per_day", 10)

        # Resolve connector from executor
        connector = None
        connectors = getattr(self.executor, "connectors", None)
        if isinstance(connectors, dict) and connectors:
            connector = next(iter(connectors.values()))
        
        if connector is None:
            class _NullConnector:
                def get_open_positions(self) -> List[Dict[str, Any]]: return []
            connector = _NullConnector()

        self.position_manager = PositionManager(
            storage=self.storage,
            connector=connector,
            regime_classifier=self.regime_classifier,
            config=pm_cfg
        )

    def _init_ancillary_services(self, expiration: Optional[Any], coherence: Optional[Any], listener: Optional[Any]) -> None:
        """Initializes secondary services for signal lifecycle and monitoring."""
        self.expiration_manager = expiration or SignalExpirationManager(storage=self.storage)
        self.coherence_monitor = coherence or CoherenceMonitor(storage=self.storage)

        if listener is None:
            self.trade_closure_listener = TradeClosureListener(
                storage=self.storage,
                risk_manager=self.risk_manager,
                edge_tuner=EdgeTuner(storage=self.storage),
                threshold_optimizer=ThresholdOptimizer(storage=self.storage)
            )
        else:
            self.trade_closure_listener = listener

    def _init_sys_config(self) -> None:
        """Loads global module status and session statistics from SSOT."""
        modules = self.storage.get_global_modules_enabled() if hasattr(self.storage, "get_global_modules_enabled") else {}
        self.modules_enabled_global = modules if isinstance(modules, dict) else {}
        
        # Log module states
        disabled = [k for k, v in self.modules_enabled_global.items() if not v]
        if disabled:
            logger.warning(f"[WARNING] Modules DISABLED globally: {', '.join(disabled)}")
        else:
            logger.info("[OK] Todos los módulos están HABILITADOS globalmente")
        
        self.stats = SessionStats.from_storage(self.storage)
        self.current_regime = MarketRegime.RANGE
        self._shutdown_requested = False
        self._active_usr_signals = []
        self._last_checked_deal_ticket = 0
        
        # Health check: Track consecutive cycles with 0 structures detected
        self._consecutive_empty_structure_cycles = 0
        self._max_consecutive_empty_cycles = 3  # Trigger alert after this many

    def _init_loop_intervals(self) -> None:
        """Sets up the intervals for the main orchestrator loop based on regimes."""
        orchestrator_config = self.config.get("orchestrator", {})
        self.intervals = {
            MarketRegime.TREND: orchestrator_config.get("loop_interval_trend", 5),
            MarketRegime.RANGE: orchestrator_config.get("loop_interval_range", 30),
            MarketRegime.VOLATILE: orchestrator_config.get("loop_interval_volatile", 15),
            MarketRegime.SHOCK: orchestrator_config.get("loop_interval_shock", 60)
        }
        logger.info(f"MainOrchestrator heartbeat: MIN={self.MIN_SLEEP_INTERVAL}s")
        
        # Initialize ranking cycle timing (PHASE 4: StrategyRanker integration)
        self._last_ranking_cycle = datetime.now(timezone.utc) - timedelta(minutes=10)  # Force first eval
        self._ranking_interval = 300  # 5 minutes in seconds

    def _init_broker_discovery(self) -> None:
        """Discovers and classifies available sys_brokers from storage."""
        self.sys_brokers = self._discover_brokers()
        self.broker_status = self._classify_brokers(self.sys_brokers)

    def _init_orchestration_services(self, ui_mapping: Optional[Any], heartbeat: Optional[Any], resolver: Optional[Any]) -> None:
        """Initializes orchestration & reporting services (Vector V4)."""
        # UI Mapping Service (NEW)
        if ui_mapping is not None:
            self.ui_mapping_service = ui_mapping
            logger.info("[ORCHESTRATOR] UI_Mapping_Service injected from parameter")
        else:
            try:
                from core_brain.services.ui_mapping_service import UIMappingService
                from core_brain.services.socket_service import get_socket_service
                
                socket_svc = get_socket_service()  # Get singleton instance
                logger.debug(f"[ORCHESTRATOR] SocketService obtained: {socket_svc}")
                
                self.ui_mapping_service = UIMappingService(socket_service=socket_svc)
                logger.info("[ORCHESTRATOR][✅] UI_Mapping_Service initialized successfully")
            except ImportError as e:
                logger.error(f"[ORCHESTRATOR] ImportError initializing UI_Mapping_Service: {e}", exc_info=True)
                self.ui_mapping_service = None
            except Exception as e:
                logger.error(f"[ORCHESTRATOR] Exception initializing UI_Mapping_Service: {e}", exc_info=True)
                self.ui_mapping_service = None
        
        # Strategy Heartbeat Monitor (NEW)
        if heartbeat is not None:
            self.heartbeat_monitor = heartbeat
        else:
            try:
                from core_brain.services.strategy_heartbeat_monitor import StrategyHeartbeatMonitor
                socket_svc = getattr(self, 'socket_service', None)
                self.heartbeat_monitor = StrategyHeartbeatMonitor(storage=self.storage, socket_service=socket_svc)
                logger.info("[ORCHESTRATOR] StrategyHeartbeatMonitor initialized (default)")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Could not initialize StrategyHeartbeatMonitor: {e}")
                self.heartbeat_monitor = None
        
        # Conflict Resolver (NEW)
        if resolver is not None:
            self.conflict_resolver = resolver
        else:
            try:
                from core_brain.conflict_resolver import ConflictResolver
                fundamental_guard = getattr(self.risk_manager, 'fundamental_guard', None)
                self.conflict_resolver = ConflictResolver(
                    storage=self.storage,
                    regime_classifier=self.regime_classifier,
                    fundamental_guard=fundamental_guard
                )
                logger.info("[ORCHESTRATOR] ConflictResolver initialized (default)")
            except Exception as e:
                logger.warning(f"[ORCHESTRATOR] Could not initialize ConflictResolver: {e}")
                self.conflict_resolver = None

    def _init_market_analysis_services(self) -> None:
        """Initializes market structure analyzer for UI integration (EXEC-UI-DATA-INTEGRATION)."""
        try:
            from core_brain.sensors.market_structure_analyzer import MarketStructureAnalyzer
            self.market_structure_analyzer = MarketStructureAnalyzer(storage=self.storage)
            logger.info("[ORCHESTRATOR] MarketStructureAnalyzer initialized for UI data feed")
        except Exception as e:
            logger.warning(f"[ORCHESTRATOR] Could not initialize MarketStructureAnalyzer: {e}")
            self.market_structure_analyzer = None
    
    def _init_economic_integration(self) -> None:
        """
        Initializes Economic Calendar Veto Interface (PHASE 8: News-Based Trading Lockdown).
        
        Responsibilities:
        - Initialize EconomicIntegrationManager with scheduler
        - Setup non-blocking fetch-persist job
        - Preserve agnosis (MainOrchestrator never contacts providers directly)
        """
        try:
            from core_brain.economic_integration import create_economic_integration
            from connectors.economic_data_gateway import EconomicDataProviderRegistry
            from core_brain.news_sanitizer import NewsSanitizer
            
            logger.info("[ECON-INTEGRATION] Initializing Economic Calendar Veto Interface...")
            
            # Create integration manager with all dependencies
            self.economic_integration = create_economic_integration(
                gateway=EconomicDataProviderRegistry(),
                sanitizer=NewsSanitizer(),
                storage=self.storage,
                scheduler_config=None  # Use defaults
            )
            
            # Setup and start scheduler asynchronously (non-blocking)
            # Note: Scheduled as asyncio task in the main event loop
            
            logger.info("[ECON-INTEGRATION] ✅ Economic integration ready for use")
        
        except Exception as e:
            logger.warning(f"[ECON-INTEGRATION] ⚠️ Could not initialize: {e}")
            self.economic_integration = None

    def _discover_brokers(self) -> List[Dict]:
        """Descubre todos los sys_brokers registrados en la base de datos."""
        try:
            return self.storage.get_brokers()
        except Exception as e:
            logger.error(f"Error discovering sys_brokers: {e}")
            return []

    def _classify_brokers(self, sys_brokers: List[Dict]) -> Dict[str, Dict]:
        """Clasifica sys_brokers según provisión automática o manual."""
        status = {}
        for broker in sys_brokers:
            broker_id = broker.get('broker_id')
            auto = broker.get('auto_provision_available', False)
            status[broker_id] = {
                'name': broker.get('name'),
                'auto_provision': bool(auto),
                'manual_required': not bool(auto),
                'sys_platforms': broker.get('platforms_available'),
                'website': broker.get('website'),
                'status': 'pending',
            }
        return status

    async def provision_all_demo_accounts(self) -> None:
        """Provisiona cuentas demo maestras para todos los sys_brokers con provisión automática."""
        from connectors.auto_provisioning import BrokerProvisioner
        provisioner = BrokerProvisioner(storage=self.storage)
        for broker_id, info in self.broker_status.items():
            if info['auto_provision']:
                logger.info(f"[EDGE] Provisionando cuenta demo para broker: {broker_id}")
                success, result = await provisioner.ensure_demo_account(broker_id)
                if success:
                    self.broker_status[broker_id]['status'] = 'demo_ready'
                    logger.info(f"[OK] Cuenta demo lista para {broker_id}")
                else:
                    self.broker_status[broker_id]['status'] = f"error: {result.get('error', 'unknown')}"
                    logger.warning(f"[ERROR] Error al provisionar demo {broker_id}: {result}")
            else:
                self.broker_status[broker_id]['status'] = 'manual_required'
                logger.info(f"[WARNING]  {broker_id} requiere provisión manual")
        
        # Session tracking - RECONSTRUCT FROM DB
        self.stats = SessionStats.from_storage(self.storage)
        
        # Current market regime (updated after each scan)
        self.current_regime: MarketRegime = MarketRegime.RANGE
        
        # Shutdown flag
        self._shutdown_requested = False
        
        # Active usr_signals tracking (for adaptive heartbeat)
        self._active_usr_signals: List[Signal] = []

        # Coherence monitor
        self.coherence_monitor = CoherenceMonitor(storage=self.storage)
        
        # Loop intervals by regime (seconds)
        orchestrator_config = self.config.get("orchestrator", {})
        self.intervals = {
            MarketRegime.TREND: orchestrator_config.get("loop_interval_trend", 5),
            MarketRegime.RANGE: orchestrator_config.get("loop_interval_range", 30),
            MarketRegime.VOLATILE: orchestrator_config.get("loop_interval_volatile", 15),
            MarketRegime.SHOCK: orchestrator_config.get("loop_interval_shock", 60)
        }
        
        logger.info(
            f"MainOrchestrator initialized with intervals: "
            f"TREND={self.intervals[MarketRegime.TREND]}s, "
            f"RANGE={self.intervals[MarketRegime.RANGE]}s, "
            f"VOLATILE={self.intervals[MarketRegime.VOLATILE]}s, "
            f"SHOCK={self.intervals[MarketRegime.SHOCK]}s"
        )
        logger.info(f"Adaptive heartbeat: MIN={self.MIN_SLEEP_INTERVAL}s when usr_signals active")
    
    def _load_config(self, config_path: Optional[str]) -> Dict:
        """
        Load configuration using DB as SSOT, with optional file merge for legacy compatibility.
        """
        config: Dict[str, Any] = {}

        try:
            db_config = self.storage.get_dynamic_params()
            if isinstance(db_config, dict):
                config.update(db_config)
        except Exception as e:
            logger.warning("Failed to load dynamic params from DB: %s", e)

        if config_path:
            try:
                cfg_path = Path(config_path)
                if cfg_path.exists():
                    with open(cfg_path, "r", encoding="utf-8") as f:
                        file_cfg = json.load(f)
                    if isinstance(file_cfg, dict):
                        config.update(file_cfg)
            except Exception as e:
                logger.warning("Failed loading legacy config files: %s", e)

        return config
    
    def _get_sleep_interval(self) -> int:
        """
        Get sleep interval based on current market regime.
        
        LATIDO DE GUARDIA: Reduces sleep interval when active usr_signals present,
        enabling faster response to market conditions.
        
        Returns:
            Sleep interval in seconds
        """
        base_interval = self.intervals.get(self.current_regime, 30)
        
        # Adaptive heartbeat: faster when usr_signals are active
        if self._active_usr_signals:
            adaptive_interval = min(base_interval, self.MIN_SLEEP_INTERVAL)
            logger.debug(
                f"Adaptive heartbeat active: {len(self._active_usr_signals)} usr_signals, "
                f"interval reduced to {adaptive_interval}s"
            )
            return adaptive_interval
        
        return base_interval
    
    def _update_regime_from_scan(self, scan_results: Dict[str, MarketRegime]) -> None:
        """
        Update current regime based on scan results.
        Uses the most aggressive regime found across all symbols.
        
        Args:
            scan_results: Dictionary of symbol -> MarketRegime
        """
        if not scan_results:
            return
        
        # Priority order: SHOCK > VOLATILE > TREND > RANGE
        regime_priority: Dict[MarketRegime, int] = {
            MarketRegime.SHOCK: 4,
            MarketRegime.VOLATILE: 3,
            MarketRegime.TREND: 2,
            MarketRegime.RANGE: 1
        }
        
        max_priority = 0
        new_regime: MarketRegime = MarketRegime.RANGE
        
        # scan_results es un Dict[str, MarketRegime] donde key=symbol, value=MarketRegime
        for symbol, regime in scan_results.items():
            priority = regime_priority.get(regime, 1)
            
            if priority > max_priority:
                max_priority = priority
                new_regime = regime
        
        if new_regime != self.current_regime:
            logger.info(f"Regime changed: {self.current_regime} -> {new_regime}")
            self.current_regime = new_regime
    
    async def _check_closed_usr_positions(self) -> None:
        """
        Check connectors for newly closed usr_positions and process them through TradeClosureListener.
        """
        try:
            from datetime import datetime
            from models.broker_event import BrokerEvent, BrokerEventType, BrokerTradeClosedEvent
            from models.signal import ConnectorType
            
            # Get connector from executor
            if not hasattr(self.executor, 'connectors'):
                return
            
            mt5_connector = self.executor.connectors.get(ConnectorType.METATRADER5)
            if not mt5_connector or not mt5_connector.is_connected:
                return
            
            # Get closed positions from connector (agnostic)
            # This avoids direct MetaTrader5 import in core_brain
            closed_usr_positions = mt5_connector.get_closed_usr_positions(hours=24)
            
            if not closed_usr_positions:
                return
            
            # Filter for new ones (ticket > last_checked)
            new_usr_positions = [p for p in closed_usr_positions if p['ticket'] > self._last_checked_deal_ticket]
            
            if not new_usr_positions:
                return
            
            logger.info(f"Found {len(new_usr_positions)} new closed usr_positions to process via Listener")
            
            # Process each position
            for pos in new_usr_positions:
                # Find corresponding signal in DB
                signal_id = pos.get('signal_id')
                matching_signal = None
                
                if signal_id:
                    matching_signal = self.storage.get_signal_by_id(signal_id)
                
                if not matching_signal:
                    # Fallback: search by ticket
                    usr_signals = self.storage.get_usr_signals(limit=100)
                    for sig in usr_signals:
                        if sig.get('order_id') == str(pos['ticket']):
                            matching_signal = sig
                            break
                
                if not matching_signal:
                    continue
                
                # Create BrokerTradeClosedEvent
                trade_event = BrokerTradeClosedEvent(
                    ticket=pos['ticket'],
                    signal_id=matching_signal.get('id'),
                    symbol=pos['symbol'],
                    entry_price=pos.get('entry_price') or matching_signal.get('entry_price', 0.0),
                    exit_price=pos['exit_price'],
                    profit_loss=pos['profit'],
                    pips=0.0,
                    exit_reason=pos.get('exit_reason', "MT5_CLOSE"),
                    entry_time=datetime.fromisoformat(matching_signal['timestamp']) if 'timestamp' in matching_signal else datetime.now(),
                    exit_time=pos['close_time'],
                    broker_id="MT5",
                    metadata={"ticket": pos['ticket']}
                )
                
                # Wrap in BrokerEvent
                event = BrokerEvent(
                    event_type=BrokerEventType.TRADE_CLOSED,
                    data=trade_event,
                    timestamp=datetime.now()
                )
                
                # Process through listener
                await self.trade_closure_listener.handle_trade_closed_event(event)
                
                # Update last checked ticket
                self._last_checked_deal_ticket = max(self._last_checked_deal_ticket, pos['ticket'])
            
        except Exception as e:
            logger.error(f"Error checking closed usr_positions: {e}")

    async def run_single_cycle(self) -> None:
        """
        Execute a single complete trading cycle.
        
        Cycle steps:
        1. Scan market for opportunities
        2. Generate usr_signals from scan results
        3. Validate with risk manager
        4. Execute approved usr_signals (with DB persistence)
        5. Update statistics
        """
        try:
            # HOT-RELOAD: Recargar estado de módulos para detectar cambios desde UI
            self.modules_enabled_global = self.storage.get_global_modules_enabled()
            
            # Check if we need to reset stats for new day
            self.stats.reset_if_new_day()
            
            # Step 0: Initial heartbeat update and feedback
            self.storage.update_module_heartbeat("orchestrator")
            if self.thought_callback:
                await self.thought_callback("Iniciando ciclo de monitoreo autónomo...", module="CORE")
            
            # EDGE: Expire old PENDING usr_signals based on timeframe window
            # This prevents stale usr_signals from accumulating in database
            if self.thought_callback:
                await self.thought_callback("Verificando caducidad de señales no ejecutadas...", module="ALPHA")
                
            expiration_stats = self.expiration_manager.expire_old_usr_signals()
            logger.info(f"[EXPIRATION] Processed {expiration_stats.get('total_checked', 0)} usr_signals, "
                       f"expired {expiration_stats['total_expired']}")
            if expiration_stats['total_expired'] > 0:
                logger.info(f"[EXPIRATION] [OK] Breakdown: {expiration_stats['by_timeframe']}")
            
            # MODULE TOGGLE: Position Manager
            if not self.modules_enabled_global.get("position_manager", True):
                if self.thought_callback:
                    await self.thought_callback("Position Manager deshabilitado.", level="warning", module="MGMT")
                logger.debug("[TOGGLE] position_manager deshabilitado globalmente - saltado")
            elif self.position_manager:
                if self.thought_callback:
                    await self.thought_callback("Evaluando salud de posiciones abiertas...", module="MGMT")
                position_stats = self.position_manager.monitor_usr_positions()
                if position_stats['actions']:
                    logger.info(
                        f"[POSITION_MANAGER] Monitored {position_stats['monitored']} usr_positions, "
                        f"executed {len(position_stats['actions'])} actions"
                    )
                    for action in position_stats['actions']:
                        logger.info(f"[POSITION_MANAGER] [OK] {action['action']}: ticket={action.get('ticket')}")
            
            # MODULE TOGGLE: Scanner
            if not self.modules_enabled_global.get("scanner", True):
                logger.debug("[TOGGLE] scanner deshabilitado globalmente - ciclo terminado")
                self.stats.cycles_completed += 1
                return
            
            # Step 1: Get current market regimes from scanner WITH DataFrames
            if self.thought_callback:
                await self.thought_callback("Escaneando mercados en busca de anomalías...", module="SCANNER")
            
            logger.debug("Getting market regimes with data from scanner...")
            
            # Scanner trabaja de forma sincrónica en background
            # Obtenemos su último estado CON DataFrames
            scan_results_with_data = await asyncio.to_thread(self.scanner.get_scan_results_with_data)
            
            if not scan_results_with_data:
                logger.warning("No scan results available yet")
                return
            
            # Update pipeline stats: scans
            self.stats.scans_total += len(scan_results_with_data)
            
            # MILESTONE 6.3: Build PriceSnapshots for atomic traceability
            # Each scan result is wrapped with its provider_source for audit trail
            price_snapshots: Dict[str, PriceSnapshot] = {}
            for key, data in scan_results_with_data.items():
                provider = data.get("provider_source", "UNKNOWN")
                price_snapshots[key] = PriceSnapshot(
                    symbol=data.get("symbol", key.split("|")[0]),
                    timeframe=data.get("timeframe", key.split("|")[-1] if "|" in key else "M5"),
                    df=data.get("df"),
                    provider_source=provider,
                    regime=data.get("regime")
                )
                # Inject provider_source into scan_results_with_data for downstream consumers
                data["provider_source"] = provider
            
            logger.info(f"[PRICE_SNAPSHOT] Built {len(price_snapshots)} atomic snapshots. "
                       f"Providers: {set(s.provider_source for s in price_snapshots.values())}")
            
            # Extraer solo regímenes para actualizar estado
            scan_results = {sym: data["regime"] for sym, data in scan_results_with_data.items()}
            
            # Update current regime based on scan
            self._update_regime_from_scan(scan_results)
            self.storage.update_module_heartbeat("scanner")
            
            # EXEC-UI-DATA-INTEGRATION: Analyze market structure and populate UI mapping
            # (Always run, even if no trading usr_signals are generated)
            if self.market_structure_analyzer and self.ui_mapping_service:
                # Defensive check: if too many snapshots lack data, wait a bit
                snapshots_with_data = sum(
                    1 for s in price_snapshots.values() 
                    if s.df is not None and len(s.df) > 0
                )
                if snapshots_with_data == 0:
                    logger.warning(f"[UI_MAPPING] All {len(price_snapshots)} snapshots have df=None, waiting for data...")
                    await asyncio.sleep(0.5)  # Brief wait for scanner to populate data
                    # Re-fetch after wait
                    scan_results_with_data = await asyncio.to_thread(self.scanner.get_scan_results_with_data)
                    for key, data in scan_results_with_data.items():
                        if key in price_snapshots and data.get("df") is not None:
                            price_snapshots[key].df = data["df"]
                    snapshots_with_data = sum(
                        1 for s in price_snapshots.values() 
                        if s.df is not None and len(s.df) > 0
                    )
                
                available_pct = (snapshots_with_data / len(price_snapshots) * 100) if price_snapshots else 0
                logger.info(f"[UI_MAPPING][GATE PASSED] analyzer=✅ service=✅ | Starting structure analysis for {len(price_snapshots)} price snapshots ({available_pct:.1f}% with data)")
                structure_count = 0
                try:
                    for key, snapshot in price_snapshots.items():
                        if snapshot.df is not None and len(snapshot.df) > 0:
                            # Detect market structure (HH/HL/LH/LL, breakers, etc.)
                            structure_result = self.market_structure_analyzer.detect_market_structure(snapshot.df)
                            
                            if structure_result:
                                # Flexibilize: emit even if is_valid=False, as long as we have some pivots
                                has_some_pivots = (
                                    structure_result.get('hh_count', 0) > 0 or 
                                    structure_result.get('hl_count', 0) > 0 or 
                                    structure_result.get('lh_count', 0) > 0 or 
                                    structure_result.get('ll_count', 0) > 0
                                )
                                
                                if structure_result.get('is_valid') or has_some_pivots:
                                    # Provide structure data to UI mapping service
                                    self.ui_mapping_service.add_structure_signal(
                                        asset=snapshot.symbol,
                                        structure_data={
                                            'hh_indices': structure_result.get('hh_indices', []),
                                            'hl_indices': structure_result.get('hl_indices', []),
                                            'lh_indices': structure_result.get('lh_indices', []),
                                            'll_indices': structure_result.get('ll_indices', []),
                                            'structure_type': structure_result.get('type', 'UNKNOWN'),
                                            'is_valid': structure_result.get('is_valid', False),
                                            'confidence': 'high' if structure_result.get('is_valid') else 'partial'
                                        }
                                    )
                                    structure_count += 1
                                    struct_status = "✅ valid" if structure_result.get('is_valid') else "⚠️ partial"
                                    logger.info(
                                        f"[UI_MAPPING] {struct_status} Added structure for {snapshot.symbol}: "
                                        f"{structure_result.get('type')} "
                                        f"(HH={structure_result.get('hh_count')}, "
                                        f"HL={structure_result.get('hl_count')}, "
                                        f"LH={structure_result.get('lh_count')}, "
                                        f"LL={structure_result.get('ll_count')})"
                                    )
                    
                    logger.info(f"[UI_MAPPING] Structure analysis complete: {structure_count} structures detected out of {len(price_snapshots)}")
                    
                    # HEALTH CHECK: Monitor for consecutive empty structure cycles
                    if structure_count == 0:
                        self._consecutive_empty_structure_cycles += 1
                        if self._consecutive_empty_structure_cycles == self._max_consecutive_empty_cycles:
                            logger.critical(
                                f"[HEALTH_CHECK] ⚠️ ALERT: {self._consecutive_empty_structure_cycles} consecutive cycles with 0 structures detected. "
                                f"This indicates a potential data flow issue (e.g., DataFrames still None, analyzer bug, or timing problem). "
                                f"Check scanner status, market data providers, and MarketStructureAnalyzer logs."
                            )
                        elif self._consecutive_empty_structure_cycles > self._max_consecutive_empty_cycles:
                            # Keep alerting every cycle if still broken
                            logger.error(f"[HEALTH_CHECK] ⚠️ PERSISTENT: {self._consecutive_empty_structure_cycles} cycles with 0 structures. System may be degraded.")
                    else:
                        # Reset counter if we detect structures
                        if self._consecutive_empty_structure_cycles > 0:
                            logger.info(f"[HEALTH_CHECK] ✅ Recovery: Structures detected after {self._consecutive_empty_structure_cycles} empty cycles")
                        self._consecutive_empty_structure_cycles = 0

                except Exception as e:
                    logger.error(f"[UI_MAPPING] Error analyzing structure: {type(e).__name__}: {e}", exc_info=True)
                
                # Emit UI update (Vector V4 - Encendido Visual)
                try:
                    logger.debug(f"[UI_MAPPING] About to emit trader page update. socket_service={bool(self.ui_mapping_service.socket_service)}")
                    await self.ui_mapping_service.emit_trader_page_update()
                    logger.debug(f"[UI_MAPPING][✅] emit_trader_page_update() completed successfully")
                except Exception as e:
                    logger.error(f"[UI_MAPPING] Error emitting trader page update: {type(e).__name__}: {e}", exc_info=True)
            
            # Generate unique trace ID for this cycle
            trace_id = str(uuid.uuid4())
            logger.debug(f"Starting cycle with trace_id: {trace_id}")
            
            # ════════════════════════════════════════════════════════════════════════════════════
            # PHASE 8: Economic Veto Check (News-Based Trading Lockdown)
            # ════════════════════════════════════════════════════════════════════════════════════
            # Before generating usr_signals, verify trading is allowed by economic calendar.
            # If HIGH impact event: block new usr_positions, move SL to Break-Even.
            # If MEDIUM impact event: allow with CAUTION (unit R @ 50%).
            # Agnosis: MainOrchestrator never knows provider sources.
            
            if self.economic_integration:
                try:
                    current_time = datetime.now(timezone.utc)
                    
                    # Check each symbol in scan results for economic veto
                    veto_symbols = set()  # Symbols that should NOT have new usr_positions opened
                    caution_symbols = set()  # Symbols with MEDIUM impact (reduced size)
                    
                    for symbol in scan_results.keys():
                        status = await self.economic_integration.get_trading_status(symbol, current_time)
                        
                        if not status.get("is_tradeable", True):
                            veto_symbols.add(symbol)
                            reason = status.get("reason", "Economic veto")
                            logger.warning(
                                f"[ECON-VETO] ❌ {symbol}: {reason} "
                                f"(Next: {status.get('next_event')} @ {status.get('time_to_event', 0):.0f}s)"
                            )
                            
                            # HIGH impact: Prepare position management
                            if status.get("restriction_level") == "BLOCK":
                                logger.warning(f"[ECON-VETO] HIGH IMPACT: Adjusting open usr_positions for {symbol} to Break-Even")
                                # Activate RiskManager lockdown for BLOCK-level events
                                try:
                                    await self.risk_manager.activate_lockdown(
                                        symbol=symbol,
                                        reason=f'ECON_VETO: {status.get("next_event", "UNKNOWN")}',
                                        trace_id=trace_id
                                    )
                                    logger.info(f"[ECON-VETO] Lockdown activated for {symbol} due to high-impact economic event")
                                except Exception as e:
                                    logger.error(f"[ECON-VETO] Failed to activate lockdown for {symbol}: {e}", exc_info=True)
                                # Will be handled in position manager below
                        
                        elif status.get("restriction_level") == "CAUTION":
                            caution_symbols.add(symbol)
                            logger.info(
                                f"[ECON-VETO] ⚠️ {symbol}: MEDIUM impact (unit R @ 50%). "
                                f"Next: {status.get('next_event')}"
                            )
                    
                    # If ALL symbols are vetoed: enter SLEEP mode until buffer ends
                    if veto_symbols and len(veto_symbols) == len(scan_results):
                        # Find earliest buffer end time
                        earliest_recovery = None
                        for symbol in veto_symbols:
                            status = await self.economic_integration.get_trading_status(symbol, current_time)
                            if status.get("time_to_event") is not None:
                                # Calculate when we can resume trading
                                post_buffer_secs = (status.get("buffer_post_minutes", 0) * 60)
                                time_to_tradeable = status.get("time_to_event", 0) + post_buffer_secs
                                if earliest_recovery is None or time_to_tradeable < earliest_recovery:
                                    earliest_recovery = time_to_tradeable
                        
                        if earliest_recovery and earliest_recovery > 0:
                            sleep_duration = min(earliest_recovery, 60)  # Cap at 60s per cycle
                            logger.info(
                                f"[ECON-VETO] SYSTEM_IDLE: All symbols vetoed. "
                                f"Sleeping {sleep_duration:.0f}s until buffer ends."
                            )
                            if self.thought_callback:
                                await self.thought_callback(
                                    f"⏸️ Pausa prevista por evento económico. Reanudando en {int(sleep_duration)}s.",
                                    module="ECON",
                                    level="info"
                                )
                            await asyncio.sleep(min(sleep_duration, self.MIN_SLEEP_INTERVAL))
                            self.stats.cycles_completed += 1
                            return
                    
                    # Store veto and caution symbols for use in signal generation
                    self._econ_veto_symbols = veto_symbols
                    self._econ_caution_symbols = caution_symbols
                
                except Exception as e:
                    logger.error(f"[ECON-VETO] Error in economic check: {e}", exc_info=True)
                    # Fail-open: continue trading if check fails
                    self._econ_veto_symbols = set()
                    self._econ_caution_symbols = set()
            else:
                self._econ_veto_symbols = set()
                self._econ_caution_symbols = set()
            
            # Step 2: Generate usr_signals WITH DataFrames
            logger.debug("Generating usr_signals from scan results with data...")
            usr_signals = await self.signal_factory.generate_usr_signals_batch(scan_results_with_data, trace_id)
            self.storage.update_module_heartbeat("signal_factory")
            
            if not usr_signals:
                logger.debug("No usr_signals generated")
                if self.thought_callback:
                    await self.thought_callback("Silencio en el mercado. No se detectan setups institucionales.", module="ALPHA")
                # Clear active usr_signals if none generated
                self._active_usr_signals.clear()
                self.stats.cycles_completed += 1
                return
            
            # Signal processing continues (unreachable code bug fixed)
            if self.thought_callback:
                await self.thought_callback(f"Setup detectado: {len(usr_signals)} señales en pipeline alpha.", module="ALPHA")
            
            logger.info(f"Generated {len(usr_signals)} usr_signals")
            self.stats.usr_signals_processed += len(usr_signals)
            self.stats.usr_signals_generated += len(usr_signals)
            
            # Step 3: Validate usr_signals with risk manager
            validated_usr_signals = []
            for signal in usr_signals:
                is_valid = True
                if hasattr(self.risk_manager, "validate_signal"):
                    is_valid = bool(self.risk_manager.validate_signal(signal))
                if is_valid:
                    validated_usr_signals.append(signal)
                else:
                    logger.info(f"Signal {signal.symbol} rejected by risk manager (Trace ID: {signal.trace_id})")
            
            if not validated_usr_signals:
                logger.info("No usr_signals passed risk validation")
                self._active_usr_signals.clear()
                self.stats.cycles_completed += 1
                return
            
            logger.info(f"{len(validated_usr_signals)} usr_signals passed risk validation")
            
            # Update pipeline stats
            self.stats.usr_signals_risk_passed += len(validated_usr_signals)
            self.stats.usr_signals_vetoed += (len(usr_signals) - len(validated_usr_signals))
            self.storage.update_module_heartbeat("risk_manager")
            
            # Update active usr_signals for adaptive heartbeat
            self._active_usr_signals = validated_usr_signals
            
            # MODULE TOGGLE: Executor
            if not self.modules_enabled_global.get("executor", True):
                logger.info(
                    f"[TOGGLE] executor deshabilitado globalmente - "
                    f"{len(validated_usr_signals)} señales aprobadas NO ejecutadas"
                )
                self.stats.cycles_completed += 1
                self._active_usr_signals.clear()
                return
            
            # EDGE Auto-Correction: Verify lockdown BEFORE checking it (every 10 cycles)
            if self.stats.cycles_completed % 10 == 0:
                from core_brain.health import HealthManager
                health = HealthManager()
                lockdown_check = health.auto_correct_lockdown(self.storage, self.risk_manager)
                
                if lockdown_check.get("action_taken") == "LOCKDOWN_DEACTIVATED":
                    logger.warning(
                        f"[AUTO] EDGE AUTO-CORRECTION: {lockdown_check['reason']}"
                    )
            
            # Step 4: Check risk manager lockdown (additional check)
            if self.risk_manager.is_lockdown_active():
                logger.warning("Lockdown mode active. Skipping signal execution.")
                self.stats.cycles_completed += 1
                return
            
            # ════════════════════════════════════════════════════════════════════════════════════
            # PHASE 8: Filter usr_signals vetoed by economic calendar
            # ════════════════════════════════════════════════════════════════════════════════════
            
            # Remove usr_signals for symbols under economic veto
            econ_veto_symbols = getattr(self, '_econ_veto_symbols', set())
            filtered_usr_signals = []
            for signal in validated_usr_signals:
                if signal.symbol in econ_veto_symbols:
                    logger.info(
                        f"[ECON-VETO-EXEC] Signal for {signal.symbol} blocked: "
                        f"Economic veto active"
                    )
                    self.stats.usr_signals_vetoed += 1
                    
                    # HIGH impact: Adjust open usr_positions to Break-Even
                    try:
                        current_status = await self.economic_integration.get_trading_status(
                            signal.symbol,
                            datetime.now(timezone.utc)
                        )
                        if current_status.get("restriction_level") == "BLOCK":
                            logger.warning(
                                f"[ECON-VETO-EXEC] HIGH IMPACT: Adjusting usr_positions for {signal.symbol} to Break-Even"
                            )
                            # Activate lockdown for this symbol due to BLOCK-level event
                            try:
                                await self.risk_manager.activate_lockdown(
                                    symbol=signal.symbol,
                                    reason=f'ECON_VETO: {current_status.get("next_event", "UNKNOWN")}',
                                    trace_id=getattr(signal, 'trace_id', None)
                                )
                                logger.info(f"[ECON-VETO-EXEC] Lockdown activated for {signal.symbol}")
                            except Exception as e:
                                logger.error(f"[ECON-VETO-EXEC] Failed to activate lockdown: {e}", exc_info=True)
                            
                            breakeven_result = await self.risk_manager.adjust_stops_to_breakeven(
                                symbol=signal.symbol,
                                reason=f"HIGH impact economic event: {current_status.get('next_event', 'UNKNOWN')}"
                            )
                            if breakeven_result.get("adjusted", 0) > 0:
                                logger.info(
                                    f"[ECON-VETO-EXEC] ✅ Adjusted {breakeven_result['adjusted']} usr_positions to Break-Even"
                                )
                    except Exception as e:
                        logger.error(f"[ECON-VETO-EXEC] Error adjusting SL to Break-Even: {e}")
                else:
                    filtered_usr_signals.append(signal)
            
            validated_usr_signals = filtered_usr_signals
            
            if not validated_usr_signals:
                logger.info("All usr_signals filtered by economic veto")
                self.stats.cycles_completed += 1
                return
            
            # Step 5: Execute validated usr_signals with DB persistence
            for signal in validated_usr_signals:
                try:
                    logger.info(f"Executing signal: {signal.symbol} {signal.signal_type}")
                    
                    # Check if strategy is authorized for LIVE execution (Shadow Ranking)
                    if not self._is_strategy_authorized_for_execution(signal):
                        logger.warning(
                            f"Signal for {signal.symbol} blocked: Strategy {getattr(signal, 'strategy', 'unknown')} "
                            f"not authorized for LIVE execution (checking usr_performance table)"
                        )
                        self.stats.usr_signals_vetoed += 1
                        continue
                    
                    success = await self.executor.execute_signal(signal)
                    
                    if success:
                        if self.thought_callback:
                            await self.thought_callback(f"ORDEN EJECUTADA: {signal.symbol} via {signal.connector}", level="success", module="EXEC")
                        if not getattr(self.executor, "persists_usr_signals", False):
                            signal_id = self.storage.save_signal(signal)
                            logger.info(
                                f"Signal executed and persisted: {signal.symbol} (ID: {signal_id})"
                            )
                        self.stats.usr_signals_executed += 1
                    else:
                        logger.warning(f"Signal execution failed: {signal.symbol}")
                        # Record execution failure for autonomous learning (DOMINIO-10)
                        # Extract specific failure reason from ExecutionService response (IMPROVEMENT)
                        failure_reason = ExecutionFailureReason.UNKNOWN
                        failure_details = {"signal_type": str(signal.signal_type) if signal.signal_type else None}
                        if hasattr(self.executor, 'last_execution_response') and self.executor.last_execution_response:
                            last_response = self.executor.last_execution_response
                            if hasattr(last_response, 'failure_reason') and last_response.failure_reason:
                                failure_reason = last_response.failure_reason
                            if hasattr(last_response, 'failure_context') and last_response.failure_context:
                                failure_details.update(last_response.failure_context)
                        
                        await self.execution_feedback_collector.record_failure(
                            signal_id=getattr(signal, 'id', None),
                            symbol=signal.symbol,
                            strategy_name=getattr(signal, 'strategy', None),
                            reason=failure_reason,
                            details=failure_details
                        )
                        
                except Exception as e:
                    logger.error(f"Error executing signal {signal.symbol}: {e}")
                    self.stats.errors_count += 1
            
            
            self.storage.update_module_heartbeat("executor")
            
            # Step 6: Check for closed usr_positions and update signal status
            await self._check_closed_usr_positions()
            
            # PHASE 4: Strategy Ranking Cycle (every 5 minutes)
            # Evaluate all usr_strategies for mode transitions (SHADOW->LIVE, LIVE->QUARANTINE, etc.)
            time_since_last_ranking = datetime.now(timezone.utc) - self._last_ranking_cycle
            if time_since_last_ranking.total_seconds() >= self._ranking_interval:
                try:
                    logger.info(f"[RANKER] Starting ranking cycle (interval: 5 minutes)")
                    ranking_results = self.strategy_ranker.evaluate_all_usr_strategies()
                    
                    # Log transitions
                    for strategy_id, result in ranking_results.items():
                        action = result.get('action')
                        if action == 'promoted':
                            logger.critical(
                                f"[RANKER] ✅ PROMOTION: {strategy_id} SHADOW→LIVE "
                                f"(Trace: {result.get('trace_id')})"
                            )
                        elif action == 'degraded':
                            logger.critical(
                                f"[RANKER] ⚠️ DEGRADATION: {strategy_id} LIVE→QUARANTINE "
                                f"(Reason: {result.get('reason')}, Trace: {result.get('trace_id')})"
                            )
                        elif action == 'recovered':
                            logger.critical(
                                f"[RANKER] 🔄 RECOVERY: {strategy_id} QUARANTINE→SHADOW "
                                f"(Trace: {result.get('trace_id')})"
                            )
                    
                    self._last_ranking_cycle = datetime.now(timezone.utc)
                    
                except Exception as e:
                    logger.error(f"[RANKER] Error in ranking cycle (non-blocking): {e}", exc_info=False)
                    # Don't re-raise - ranking errors should not block trading
            
            # Step 7: Clear active usr_signals after execution and update cycle count
            self._active_usr_signals.clear()
            self.stats.cycles_completed += 1
            self._persist_session_stats()
            
            # Coherence monitoring
            usr_coherence_events = self.coherence_monitor.run_once()
            if usr_coherence_events:
                    for event in usr_coherence_events:
                        logger.warning(
                            f"Coherence inconsistency: symbol={event.symbol}, stage={event.stage}, status={event.status}, reason={event.reason}, connector={event.connector_type}"
                        )
            
            # NEW: Update heartbeat for all usr_strategies (Vector V4 - Monitor)
            if self.heartbeat_monitor:
                try:
                    self._update_all_usr_strategies_heartbeat()
                except Exception as e:
                    logger.warning(f"[HEARTBEAT] Error updating heartbeats: {e}")
            
            logger.info(f"Cycle completed. Stats: {self.stats}")
            
        except Exception as e:
            logger.error(f"Error in cycle execution: {e}", exc_info=True)
            self.stats.errors_count += 1
            self.stats.cycles_completed += 1
    
    def _update_all_usr_strategies_heartbeat(self) -> None:
        """Update heartbeat for all usr_strategies to reflect cycle end (Vector V4)."""
        if not self.heartbeat_monitor:
            return
        
        from core_brain.services.strategy_heartbeat_monitor import StrategyState
        
        # Mark all usr_strategies as IDLE at end of cycle
        for strategy_id in getattr(self.heartbeat_monitor, 'STRATEGY_IDS', []):
            try:
                self.heartbeat_monitor.update_heartbeat(
                    strategy_id=strategy_id,
                    state=StrategyState.IDLE,
                    asset=None,
                    position_open=False
                )
            except Exception as e:
                logger.debug(f"[HEARTBEAT] Error updating {strategy_id}: {e}")
    
    def _persist_session_stats(self) -> None:
        """
        Persist current session stats to storage.
        
        Called after each cycle to ensure stats are not lost on crash.
        """
        session_data = {
            "date": self.stats.date.isoformat(),
            "usr_signals_processed": self.stats.usr_signals_processed,
            "usr_signals_executed": self.stats.usr_signals_executed,
            "cycles_completed": self.stats.cycles_completed,
            "errors_count": self.stats.errors_count,
            "scans_total": self.stats.scans_total,
            "usr_signals_generated": self.stats.usr_signals_generated,
            "usr_signals_risk_passed": self.stats.usr_signals_risk_passed,
            "usr_signals_vetoed": self.stats.usr_signals_vetoed,
            "last_update": datetime.now().isoformat()
        }
        
        self.storage.update_sys_config({"session_stats": session_data})
    
    def _is_strategy_authorized_for_execution(self, signal: Signal) -> bool:
        """
        Check if a signal's strategy is authorized for LIVE execution.
        
        This implements the Shadow Ranking System:
        - Only LIVE usr_strategies execute real usr_orders
        - SHADOW usr_strategies generate metrics but don't execute
        - QUARANTINE usr_strategies are blocked
        
        Args:
            signal: Signal object with optional 'strategy' attribute
            
        Returns:
            True if authorized for execution, False otherwise
        """
        strategy_id = getattr(signal, 'strategy', None)
        
        # If signal doesn't have strategy attribute, allow execution (legacy compatibility)
        if not strategy_id:
            return True
        
        try:
            ranking = self.storage.get_signal_ranking(strategy_id)
            
            if not ranking:
                # Strategy not found in ranking table - allow execution for new usr_strategies
                logger.debug(f"Strategy {strategy_id} not in ranking table - allowing execution")
                return True
            
            execution_mode = ranking.get('execution_mode', 'SHADOW')
            
            if execution_mode == 'LIVE':
                return True
            elif execution_mode == 'SHADOW':
                # Log but don't execute - metrics will be tracked separately
                logger.info(
                    f"Strategy {strategy_id} in SHADOW mode - signal generated but not executed "
                    f"(waiting for promotion criteria)"
                )
                return False
            elif execution_mode == 'QUARANTINE':
                logger.warning(
                    f"Strategy {strategy_id} in QUARANTINE - signal blocked until risk metrics improve"
                )
                return False
            else:
                logger.warning(f"Unknown execution mode for strategy {strategy_id}: {execution_mode}")
                return False
                
        except Exception as e:
            logger.error(f"Error checking strategy authorization for {strategy_id}: {e}")
            # Conservative: block execution on error to avoid surprises
            return False
    
    async def run(self) -> None:
        """
        Main event loop.
        
        Runs continuously until shutdown is requested.
        
        Features:
        - Dynamic loop frequency based on market regime
        - Adaptive heartbeat (faster with active usr_signals)
        - Graceful shutdown on SIGINT/SIGTERM
        - Session persistence after each cycle
        - Scanner warmup phase to ensure data is available
        """
        logger.info("MainOrchestrator starting event loop...")
        
        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()
        
        # WARMUP PHASE: Wait for scanner to have data ready
        # This prevents "0 structures detected" on first cycles
        logger.info("[WARMUP] Waiting for scanner to populate initial data...")
        warmup_timeout = 30  # seconds
        warmup_start = time.time()
        has_data = False
        
        while not has_data and (time.time() - warmup_start) < warmup_timeout:
            scan_results = await asyncio.to_thread(self.scanner.get_scan_results_with_data)
            # Check if at least 50% of snapshots have data
            if scan_results:
                snapshots_with_data = sum(
                    1 for data in scan_results.values() 
                    if data.get("df") is not None and len(data.get("df", [])) > 0
                )
                available_pct = (snapshots_with_data / len(scan_results)) * 100 if scan_results else 0
                
                if available_pct >= 50:
                    has_data = True
                    logger.info(f"[WARMUP] ✅ Scanner ready: {snapshots_with_data}/{len(scan_results)} snapshots with data ({available_pct:.1f}%)")
                else:
                    logger.debug(f"[WARMUP] Data loading: {snapshots_with_data}/{len(scan_results)} snapshots ({available_pct:.1f}%)")
                    await asyncio.sleep(0.5)
            else:
                logger.debug("[WARMUP] Waiting for first scan results...")
                await asyncio.sleep(0.5)
        
        if not has_data:
            logger.warning(f"[WARMUP] Timeout after {warmup_timeout}s, proceeding with partial data (may see 0 structures initially)")
        
        logger.info("[WARMUP] ✅ Scanner warmup complete, entering main loop")
        
        try:
            while not self._shutdown_requested:
                # Execute one complete cycle
                await self.run_single_cycle()
                
                # Dynamic sleep based on current regime and active usr_signals
                sleep_interval = self._get_sleep_interval()
                logger.debug(
                    f"Sleeping for {sleep_interval}s "
                    f"(regime: {self.current_regime}, "
                    f"active_usr_signals: {len(self._active_usr_signals)})"
                )
                
                # Use small sleep chunks to allow quick shutdown
                # LATIDO DE GUARDIA: Check every second for responsiveness
                for _ in range(sleep_interval):
                    if self._shutdown_requested:
                        break
                    await asyncio.sleep(self.HEARTBEAT_CHECK_INTERVAL)
                    
        except asyncio.CancelledError:
            logger.info("Event loop cancelled")
        except Exception as e:
            logger.critical(f"Fatal error in event loop: {e}", exc_info=True)
        finally:
            await self.shutdown()
    
    async def shutdown(self) -> None:
        """
        Graceful shutdown procedure.
        
        Steps:
        1. Set shutdown flag
        2. Save current session stats
        3. Persist lockdown state
        4. Close broker connections
        """
        logger.info("Initiating graceful shutdown...")
        self._shutdown_requested = True
        
        try:
            # Save final session stats
            logger.info(f"Final session stats: {self.stats}")
            
            # Persist lockdown state
            logger.info("Saving system state...")
            sys_config = {
                "last_shutdown": datetime.now().isoformat(),
                "lockdown_active": self.risk_manager.is_lockdown_active(),
                "consecutive_losses": self.risk_manager.consecutive_losses,
                "last_regime": self.current_regime.value,
                "session_stats": {
                    "date": self.stats.date.isoformat(),
                    "usr_signals_processed": self.stats.usr_signals_processed,
                    "usr_signals_executed": self.stats.usr_signals_executed,
                    "cycles_completed": self.stats.cycles_completed,
                    "errors_count": self.stats.errors_count
                }
            }
            self.storage.update_sys_config(sys_config)
            
            # Close broker connections (if connectors have cleanup methods)
            if hasattr(self.executor, 'close_connections'):
                logger.info("Closing broker connections...")
                await self.executor.close_connections()
            
            logger.info("Shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def _register_signal_handlers(self) -> None:
        """Register signal handlers for Ctrl+C and SIGTERM"""
        def signal_handler(signum: int, frame: Any) -> None:
            logger.info(f"Received signal {signum}. Requesting shutdown...")
            self._shutdown_requested = True
        
        # Register handlers
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Kill command


async def main() -> None:
    """
    Main entry point for Aethelgard.
    Includes pre-flight health checks and component initialization.
    """
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
    
    print("=" * 50)
    print(">>> AETHELGARD ORCHESTRATOR STARTUP")
    print("=" * 50)
    
    # 1. Pre-flight Health Check
    health = HealthManager()
    summary = health.run_full_diagnostic()
    
    if summary["overall_status"] != "GREEN":
        print(f"[WARNING]  ISSUES DETECTED: {summary['overall_status']}. Attempting auto-repair...")
        if health.try_auto_repair():
            print("[OK] Auto-repair successful. Re-checking...")
            summary = health.run_full_diagnostic()
        else:
            print("[ERROR] Auto-repair failed.")

    if summary["overall_status"] == "RED":
        print("[CRITICAL] CRITICAL ERRORS STILL PRESENT. ABORTING STARTUP.")
        print(json.dumps(summary["config"], indent=2))
        print(json.dumps(summary["db"], indent=2))
        return
    
    if summary["overall_status"] == "YELLOW":
        print("[WARNING]  SYSTEM READY WITH WARNINGS. PROCEEDING...")
    else:
        print("[OK] HEALTH CHECK PASSED.")
    
    # 2. Component Initialization
    storage = StorageManager()
    
    # Data Provider (Using Yahoo as default for live test)
    provider_manager = DataProviderManager(storage=storage)
    data_provider = provider_manager.get_best_provider()
    
    if not data_provider:
        print("[CRITICAL] No data provider available. Aborting.")
        return
    
    # Instrument Manager: Get only enabled instruments for scanning
    from core_brain.instrument_manager import InstrumentManager
    instrument_mgr = InstrumentManager(storage=storage)
    enabled_assets = instrument_mgr.get_enabled_symbols()
    
    if not enabled_assets:
        print("[CRITICAL] No enabled instruments found in DB (sys_config['instruments_config']). Aborting.")
        return
    
    print(f"[SCAN] Scanning {len(enabled_assets)} enabled instruments: {enabled_assets[:10]}...")
    
    # Scanner (Only scans enabled instruments from configuration)
    _scanner = ScannerEngine(assets=enabled_assets, data_provider=data_provider, storage=storage)
    
    # --- Strategies & Analyzers (DI) ---
    from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
    from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
    from core_brain.services.strategy_engine_factory import StrategyEngineFactory
    
    dynamic_params = storage.get_dynamic_params()
    
    confluence_analyzer = MultiTimeframeConfluenceAnalyzer(storage=storage)
    trifecta_analyzer = TrifectaAnalyzer(storage=storage)
    
    # FASE 2: Load all usr_strategies dynamically from BD (SSOT via StrategyEngineFactory)
    # Cumple DEVELOPMENT_GUIDELINES 1.6 (Service Layer) + MANIFESTO II.3 (Dynamic Registry)
    try:
        strategy_factory = StrategyEngineFactory(
            storage=storage,
            config=dynamic_params,
            available_sensors={}  # TODO: Populate when sensors are fully instantiated
        )
        active_engines = strategy_factory.instantiate_all_sys_strategies()
        stats = strategy_factory.get_stats()
        logger.info(
            f"[STRATEGIES] ✓ Dynamic loading from BD completed: "
            f"{stats['active_engines']} active, {stats['failed_loads']} skipped"
        )
    except RuntimeError as e:
        logger.error(f"[STRATEGIES] ✗ CRITICAL: {e}")
        print(f"[CRITICAL] ABORTING STARTUP: {e}")
        return

    # Initialize ExecutionFeedbackCollector for autonomous learning (DOMINIO-10)
    execution_feedback_collector = ExecutionFeedbackCollector(storage=storage)
    
    # 2. Component Initialization (Signal Factory)
    signal_factory = SignalFactory(
        storage_manager=storage,
        strategy_engines=active_engines,
        confluence_analyzer=confluence_analyzer,
        trifecta_analyzer=trifecta_analyzer,
        execution_feedback_collector=execution_feedback_collector
    )
    
    # Risk Manager ($10k starting capital) - Dependency Injection
    risk_manager = RiskManager(storage=storage, initial_capital=10000.0, instrument_manager=instrument_mgr)
    
    # EdgeTuner (Parameter auto-calibration)
    edge_tuner = EdgeTuner(storage=storage)
    
    # ThresholdOptimizer (Confidence threshold adaptation - HU 7.1)
    threshold_optimizer = ThresholdOptimizer(storage=storage)
    
    # Trade Closure Listener (Autonomous feedback loop)
    trade_listener = TradeClosureListener(
        storage=storage,
        risk_manager=risk_manager,
        edge_tuner=edge_tuner,
        threshold_optimizer=threshold_optimizer,
        max_retries=3,
        retry_backoff=0.5
    )
    logger.info("✅ TradeClosureListener initialized with idempotent event handling | ThresholdOptimizer HU 7.1 enabled")
    
    # Order Executor
    notifier = get_notifier()
    executor = OrderExecutor(risk_manager=risk_manager, storage=storage, notificator=notifier)
    
    # ─────────────────────────────────────────────────────────────────
    # HU 3.6 & 3.9: DUAL MOTOR INITIALIZATION
    # ─────────────────────────────────────────────────────────────────
    logger.info("🔄 Initializing Hybrid Runtime (MODE_LEGACY + MODE_UNIVERSAL)")
    
    # Import required components for dual-motor
    from core_brain.legacy_strategy_executor import LegacyStrategyExecutor
    from core_brain.universal_strategy_executor import UniversalStrategyExecutor
    from core_brain.strategy_mode_selector import StrategyModeSelector, RuntimeMode
    from core_brain.strategy_mode_adapter import StrategyModeAdapter
    
    # Get or initialize tenant ID (for now, "default_tenant")
    tenant_id = "default_tenant"
    
    # Create executors
    legacy_executor = LegacyStrategyExecutor(signal_factory=signal_factory)
    universal_executor = UniversalStrategyExecutor(
        indicator_provider=data_provider,
        strategy_schemas_dir=None  # Uses default: core_brain/usr_strategies/universal/
    )
    
    # Create mode selector
    mode_selector = StrategyModeSelector(
        storage_manager=storage,
        legacy_executor=legacy_executor,
        universal_executor=universal_executor,
        tenant_id=tenant_id,
        trace_id="STARTUP-2026-001"
    )
    
    # Initialize mode selector (loads tenant config from DB)
    await mode_selector.initialize()
    
    logger.info(f"✅ Hybrid Runtime initialized | Current mode: {mode_selector.current_mode.value}")
    
    # Create adapter that makes StrategyModeSelector compatible with MainOrchestrator
    strategy_adapter = StrategyModeAdapter(strategy_mode_selector=mode_selector)
    
    # 3. Create Orchestrator
    # Note: We pass strategy_adapter instead of signal_factory
    # The adapter provides SignalFactory-like interface while delegating to StrategyModeSelector
    _orchestrator = MainOrchestrator(
        scanner=_scanner,
        signal_factory=strategy_adapter,  # Changed from signal_factory to strategy_adapter
        risk_manager=risk_manager,
        executor=executor,
        storage=storage,
        execution_feedback_collector=execution_feedback_collector
    )
    
    # Store references for API/control access
    logger.info("🎛️  Strategy Mode Selector ready for hot-swap via API endpoint /api/tenant/config/strategy-mode")
    
    # 4. Start Scanner background thread (if needed by your architecture)
    # The ScannerEngine.run() usually runs in its own thread
    import threading
    scanner_thread = threading.Thread(target=_scanner.run, daemon=True)
    scanner_thread.start()
    
    # 5. Run the main loop
    print("🚀 System LIVE. Starting event loop...")
    
    global scanner, orchestrator
    scanner = _scanner
    orchestrator = _orchestrator
    
    await orchestrator.run()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the orchestrator
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Shutdown by user.")
