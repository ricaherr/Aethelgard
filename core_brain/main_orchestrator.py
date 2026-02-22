"""
Main Orchestrator - Aethelgard Trading System
=============================================

Orchestrates the complete trading cycle: Scan -> Signal -> Risk -> Execute.

Key Features:
- Asynchronous event loop for non-blocking operation
- Dynamic frequency adjustment based on market regime
- Session statistics with DB reconstruction (Resilient Recovery)
- Adaptive heartbeat (faster when signals active)
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
- Persistencia completa de trades ejecutados del día
"""
import sys
import os
import asyncio
import json
import logging
import signal
from dataclasses import dataclass, field
from datetime import date, datetime
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
from core_brain.tuner import EdgeTuner
from core_brain.trade_closure_listener import TradeClosureListener
from core_brain.strategy_ranker import StrategyRanker

logger = logging.getLogger(__name__)

def _resolve_storage(storage: Optional[StorageManager]) -> StorageManager:
    """
    Resolve storage dependency with legacy fallback.
    Main path should inject StorageManager from composition root.
    """
    if storage is not None:
        return storage
    logger.warning("MainOrchestrator initialized without explicit storage! Falling back to default storage.")
    return StorageManager()


# Global references for API/Control
scanner = None
orchestrator = None

@dataclass
class SessionStats:
    """
    Tracks session statistics for the current trading day.
    Resets automatically when a new day begins.
    
    RESILIENCIA: Can reconstruct state from database on initialization.
    This ensures trades executed today are not forgotten after restarts.
    """
    date: date = field(default_factory=lambda: date.today())
    signals_processed: int = 0
    signals_executed: int = 0
    cycles_completed: int = 0
    errors_count: int = 0
    # Pipeline tracking
    scans_total: int = 0
    signals_generated: int = 0
    signals_risk_passed: int = 0
    signals_vetoed: int = 0
    
    @classmethod
    def from_storage(cls, storage: StorageManager) -> 'SessionStats':
        """
        Reconstruct SessionStats from persistent storage.
        
        This method enables recovery after system restarts, ensuring
        we don't lose track of today's executed signals.
        
        Args:
            storage: StorageManager instance to query
            
        Returns:
            SessionStats instance reconstructed from DB
        """
        today = date.today()
        
        # Query DB for today's executed signals (marked with status='executed')
        executed_count = storage.count_executed_signals(today)
        
        # Retrieve system state for other metrics
        system_state = storage.get_system_state()
        session_data = system_state.get("session_stats", {})
        
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
                signals_processed=session_data.get("signals_processed", 0),
                signals_executed=executed_count,  # Always source from DB
                cycles_completed=session_data.get("cycles_completed", 0),
                errors_count=session_data.get("errors_count", 0)
            )
            logger.info(f"SessionStats reconstructed from DB: {stats}")
        else:
            # Fresh start for new day
            stats = cls(date=today, signals_executed=executed_count)
            logger.info(f"New day detected. Fresh SessionStats initialized: {stats}")
        
        return stats
    
    def reset_if_new_day(self) -> None:
        """Reset stats if a new day has started"""
        today = date.today()
        if self.date != today:
            logger.info(f"New day detected. Resetting stats. Previous: {self}")
            self.date = today
            self.signals_processed = 0
            self.signals_executed = 0
            self.cycles_completed = 0
            self.errors_count = 0
    
    def __str__(self) -> str:
        return (
            f"SessionStats(date={self.date}, "
            f"processed={self.signals_processed}, "
            f"executed={self.signals_executed}, "
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
    2. Signal Factory: Generates trading signals
    3. Risk Manager: Validates risk parameters
    4. Executor: Places orders
    
    Features:
    - Dynamic loop frequency based on market regime
    - Adaptive heartbeat: faster sleep when active signals present
    - Resilient recovery: reconstructs session state from DB
    - Latido de Guardia: CPU-friendly monitoring
    """
    
    # Adaptive heartbeat constants
    MIN_SLEEP_INTERVAL = 3  # Seconds (when signals active)
    HEARTBEAT_CHECK_INTERVAL = 1  # Check every second for shutdown
    
    def __init__(
        self,
        scanner: Any,
        signal_factory: Any,
        risk_manager: Any,
        executor: Any,
        storage: Optional[StorageManager] = None,
        position_manager: Optional[Any] = None,
        trade_closure_listener: Optional[Any] = None,
        coherence_monitor: Optional[Any] = None,
        expiration_manager: Optional[Any] = None,
        regime_classifier: Optional[Any] = None,
        strategy_ranker: Optional[StrategyRanker] = None,
        thought_callback: Optional[Any] = None,
        config_path: Optional[str] = None
    ):
        """
        Initialize MainOrchestrator with backward-compatible Dependency Injection.
        """
        self.thought_callback = thought_callback
        # 1. Base dependencies and config
        self._init_core_dependencies(scanner, signal_factory, risk_manager, executor, storage, config_path, strategy_ranker)
        
        # 2. Classifier and Position Management
        self.regime_classifier = regime_classifier or RegimeClassifier(storage=self.storage)
        if position_manager is None:
            self._init_position_management()
        else:
            self.position_manager = position_manager

        # 3. Ancillary Services (Expiration, Coherence, Listeners)
        self._init_ancillary_services(expiration_manager, coherence_monitor, trade_closure_listener)

        # 4. System State and Session Tracking (SSOT)
        self._init_system_state()
        
        # 5. Cycle intervals and Heartbeat
        self._init_loop_intervals()

        # 6. Broker Discovery and Status
        self._init_broker_discovery()

    def _init_core_dependencies(self, scanner: Any, factory: Any, risk: Any, executor: Any, storage: Optional[Any], config_path: Optional[str], strategy_ranker: Optional[StrategyRanker] = None) -> None:
        """Initializes core engines and resolves storage/config."""
        self.scanner = scanner
        self.signal_factory = factory
        self.risk_manager = risk
        self.executor = executor
        self.storage = _resolve_storage(storage)
        self.strategy_ranker = strategy_ranker or StrategyRanker(storage=self.storage)
        self.config = self._load_config(config_path)

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
                edge_tuner=EdgeTuner(storage=self.storage)
            )
        else:
            self.trade_closure_listener = listener

    def _init_system_state(self) -> None:
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
        self._active_signals = []
        self._last_checked_deal_ticket = 0

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

    def _init_broker_discovery(self) -> None:
        """Discovers and classifies available brokers from storage."""
        self.brokers = self._discover_brokers()
        self.broker_status = self._classify_brokers(self.brokers)

    def _discover_brokers(self) -> List[Dict]:
        """Descubre todos los brokers registrados en la base de datos."""
        try:
            return self.storage.get_brokers()
        except Exception as e:
            logger.error(f"Error discovering brokers: {e}")
            return []

    def _classify_brokers(self, brokers: List[Dict]) -> Dict[str, Dict]:
        """Clasifica brokers según provisión automática o manual."""
        status = {}
        for broker in brokers:
            broker_id = broker.get('broker_id')
            auto = broker.get('auto_provision_available', False)
            status[broker_id] = {
                'name': broker.get('name'),
                'auto_provision': bool(auto),
                'manual_required': not bool(auto),
                'platforms': broker.get('platforms_available'),
                'website': broker.get('website'),
                'status': 'pending',
            }
        return status

    async def provision_all_demo_accounts(self) -> None:
        """Provisiona cuentas demo maestras para todos los brokers con provisión automática."""
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
        
        # Active signals tracking (for adaptive heartbeat)
        self._active_signals: List[Signal] = []

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
        logger.info(f"Adaptive heartbeat: MIN={self.MIN_SLEEP_INTERVAL}s when signals active")
    
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
        
        LATIDO DE GUARDIA: Reduces sleep interval when active signals present,
        enabling faster response to market conditions.
        
        Returns:
            Sleep interval in seconds
        """
        base_interval = self.intervals.get(self.current_regime, 30)
        
        # Adaptive heartbeat: faster when signals are active
        if self._active_signals:
            adaptive_interval = min(base_interval, self.MIN_SLEEP_INTERVAL)
            logger.debug(
                f"Adaptive heartbeat active: {len(self._active_signals)} signals, "
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
    
    async def _check_closed_positions(self) -> None:
        """
        Check connectors for newly closed positions and process them through TradeClosureListener.
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
            closed_positions = mt5_connector.get_closed_positions(hours=24)
            
            if not closed_positions:
                return
            
            # Filter for new ones (ticket > last_checked)
            new_positions = [p for p in closed_positions if p['ticket'] > self._last_checked_deal_ticket]
            
            if not new_positions:
                return
            
            logger.info(f"Found {len(new_positions)} new closed positions to process via Listener")
            
            # Process each position
            for pos in new_positions:
                # Find corresponding signal in DB
                signal_id = pos.get('signal_id')
                matching_signal = None
                
                if signal_id:
                    matching_signal = self.storage.get_signal_by_id(signal_id)
                
                if not matching_signal:
                    # Fallback: search by ticket
                    signals = self.storage.get_signals(limit=100)
                    for sig in signals:
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
            logger.error(f"Error checking closed positions: {e}")

    async def run_single_cycle(self) -> None:
        """
        Execute a single complete trading cycle.
        
        Cycle steps:
        1. Scan market for opportunities
        2. Generate signals from scan results
        3. Validate with risk manager
        4. Execute approved signals (with DB persistence)
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
            
            # EDGE: Expire old PENDING signals based on timeframe window
            # This prevents stale signals from accumulating in database
            if self.thought_callback:
                await self.thought_callback("Verificando caducidad de señales no ejecutadas...", module="ALPHA")
                
            expiration_stats = self.expiration_manager.expire_old_signals()
            logger.info(f"[EXPIRATION] Processed {expiration_stats.get('total_checked', 0)} signals, "
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
                position_stats = self.position_manager.monitor_positions()
                if position_stats['actions']:
                    logger.info(
                        f"[POSITION_MANAGER] Monitored {position_stats['monitored']} positions, "
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
            
            # Extraer solo regímenes para actualizar estado
            scan_results = {sym: data["regime"] for sym, data in scan_results_with_data.items()}
            
            # Update current regime based on scan
            self._update_regime_from_scan(scan_results)
            self.storage.update_module_heartbeat("scanner")
            
            # Generate unique trace ID for this cycle
            trace_id = str(uuid.uuid4())
            logger.debug(f"Starting cycle with trace_id: {trace_id}")
            
            # Step 2: Generate signals WITH DataFrames
            logger.debug("Generating signals from scan results with data...")
            signals = await self.signal_factory.generate_signals_batch(scan_results_with_data, trace_id)
            self.storage.update_module_heartbeat("signal_factory")
            
            if not signals:
                logger.debug("No signals generated")
                if self.thought_callback:
                    await self.thought_callback("Silencio en el mercado. No se detectan setups institucionales.", module="ALPHA")
                # Clear active signals if none generated
                self._active_signals.clear()
                self.stats.cycles_completed += 1
                return
            
            # Signal processing continues (unreachable code bug fixed)
            if self.thought_callback:
                await self.thought_callback(f"Setup detectado: {len(signals)} señales en pipeline alpha.", module="ALPHA")
            
            logger.info(f"Generated {len(signals)} signals")
            self.stats.signals_processed += len(signals)
            self.stats.signals_generated += len(signals)
            
            # Step 3: Validate signals with risk manager
            validated_signals = []
            for signal in signals:
                is_valid = True
                if hasattr(self.risk_manager, "validate_signal"):
                    is_valid = bool(self.risk_manager.validate_signal(signal))
                if is_valid:
                    validated_signals.append(signal)
                else:
                    logger.info(f"Signal {signal.symbol} rejected by risk manager (Trace ID: {signal.trace_id})")
            
            if not validated_signals:
                logger.info("No signals passed risk validation")
                self._active_signals.clear()
                self.stats.cycles_completed += 1
                return
            
            logger.info(f"{len(validated_signals)} signals passed risk validation")
            
            # Update pipeline stats
            self.stats.signals_risk_passed += len(validated_signals)
            self.stats.signals_vetoed += (len(signals) - len(validated_signals))
            self.storage.update_module_heartbeat("risk_manager")
            
            # Update active signals for adaptive heartbeat
            self._active_signals = validated_signals
            
            # MODULE TOGGLE: Executor
            if not self.modules_enabled_global.get("executor", True):
                logger.info(
                    f"[TOGGLE] executor deshabilitado globalmente - "
                    f"{len(validated_signals)} señales aprobadas NO ejecutadas"
                )
                self.stats.cycles_completed += 1
                self._active_signals.clear()
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
            
            # Step 5: Execute validated signals with DB persistence
            for signal in validated_signals:
                try:
                    logger.info(f"Executing signal: {signal.symbol} {signal.signal_type}")
                    
                    # Check if strategy is authorized for LIVE execution (Shadow Ranking)
                    if not self._is_strategy_authorized_for_execution(signal):
                        logger.warning(
                            f"Signal for {signal.symbol} blocked: Strategy {getattr(signal, 'strategy', 'unknown')} "
                            f"not authorized for LIVE execution (checking strategy_ranking table)"
                        )
                        self.stats.signals_vetoed += 1
                        continue
                    
                    success = await self.executor.execute_signal(signal)
                    
                    if success:
                        if self.thought_callback:
                            await self.thought_callback(f"ORDEN EJECUTADA: {signal.symbol} via {signal.connector}", level="success", module="EXEC")
                        if not getattr(self.executor, "persists_signals", False):
                            signal_id = self.storage.save_signal(signal)
                            logger.info(
                                f"Signal executed and persisted: {signal.symbol} (ID: {signal_id})"
                            )
                        self.stats.signals_executed += 1
                    else:
                        logger.warning(f"Signal execution failed: {signal.symbol}")
                        
                except Exception as e:
                    logger.error(f"Error executing signal {signal.symbol}: {e}")
                    self.stats.errors_count += 1
            
            
            self.storage.update_module_heartbeat("executor")
            
            # Step 6: Check for closed positions and update signal status
            await self._check_closed_positions()
            
            # Step 7: Clear active signals after execution and update cycle count
            self._active_signals.clear()
            self.stats.cycles_completed += 1
            self._persist_session_stats()
            
            # Coherence monitoring
            coherence_events = self.coherence_monitor.run_once()
            if coherence_events:
                    for event in coherence_events:
                        logger.warning(
                            f"Coherence inconsistency: symbol={event.symbol}, stage={event.stage}, status={event.status}, reason={event.reason}, connector={event.connector_type}"
                        )
            
            logger.info(f"Cycle completed. Stats: {self.stats}")
            
        except Exception as e:
            logger.error(f"Error in cycle execution: {e}", exc_info=True)
            self.stats.errors_count += 1
            self.stats.cycles_completed += 1
    
    def _persist_session_stats(self) -> None:
        """
        Persist current session stats to storage.
        
        Called after each cycle to ensure stats are not lost on crash.
        """
        session_data = {
            "date": self.stats.date.isoformat(),
            "signals_processed": self.stats.signals_processed,
            "signals_executed": self.stats.signals_executed,
            "cycles_completed": self.stats.cycles_completed,
            "errors_count": self.stats.errors_count,
            "scans_total": self.stats.scans_total,
            "signals_generated": self.stats.signals_generated,
            "signals_risk_passed": self.stats.signals_risk_passed,
            "signals_vetoed": self.stats.signals_vetoed,
            "last_update": datetime.now().isoformat()
        }
        
        self.storage.update_system_state({"session_stats": session_data})
    
    def _is_strategy_authorized_for_execution(self, signal: Signal) -> bool:
        """
        Check if a signal's strategy is authorized for LIVE execution.
        
        This implements the Shadow Ranking System:
        - Only LIVE strategies execute real orders
        - SHADOW strategies generate metrics but don't execute
        - QUARANTINE strategies are blocked
        
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
            ranking = self.storage.get_strategy_ranking(strategy_id)
            
            if not ranking:
                # Strategy not found in ranking table - allow execution for new strategies
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
        - Adaptive heartbeat (faster with active signals)
        - Graceful shutdown on SIGINT/SIGTERM
        - Session persistence after each cycle
        """
        logger.info("MainOrchestrator starting event loop...")
        
        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()
        
        try:
            while not self._shutdown_requested:
                # Execute one complete cycle
                await self.run_single_cycle()
                
                # Dynamic sleep based on current regime and active signals
                sleep_interval = self._get_sleep_interval()
                logger.debug(
                    f"Sleeping for {sleep_interval}s "
                    f"(regime: {self.current_regime}, "
                    f"active_signals: {len(self._active_signals)})"
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
            system_state = {
                "last_shutdown": datetime.now().isoformat(),
                "lockdown_active": self.risk_manager.is_lockdown_active(),
                "consecutive_losses": self.risk_manager.consecutive_losses,
                "last_regime": self.current_regime.value,
                "session_stats": {
                    "date": self.stats.date.isoformat(),
                    "signals_processed": self.stats.signals_processed,
                    "signals_executed": self.stats.signals_executed,
                    "cycles_completed": self.stats.cycles_completed,
                    "errors_count": self.stats.errors_count
                }
            }
            self.storage.update_system_state(system_state)
            
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
    from core_brain.tuner import EdgeTuner
    
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
        print("[CRITICAL] No enabled instruments found in DB (system_state['instruments_config']). Aborting.")
        return
    
    print(f"[SCAN] Scanning {len(enabled_assets)} enabled instruments: {enabled_assets[:10]}...")
    
    # Scanner (Only scans enabled instruments from configuration)
    _scanner = ScannerEngine(assets=enabled_assets, data_provider=data_provider, storage=storage)
    
    # --- Strategies & Analyzers (DI) ---
    from core_brain.confluence import MultiTimeframeConfluenceAnalyzer
    from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
    from core_brain.strategies.oliver_velez import OliverVelezStrategy
    
    dynamic_params = storage.get_dynamic_params()
    
    confluence_analyzer = MultiTimeframeConfluenceAnalyzer(storage=storage)
    trifecta_analyzer = TrifectaAnalyzer(storage=storage)
    
    # Initialize Strategies
    ov_strategy = OliverVelezStrategy(config=dynamic_params, instrument_manager=instrument_mgr)
    strategies = [ov_strategy]

    # 2. Component Initialization (Signal Factory)
    signal_factory = SignalFactory(
        storage_manager=storage,
        strategies=strategies,
        confluence_analyzer=confluence_analyzer,
        trifecta_analyzer=trifecta_analyzer
    )
    
    # Risk Manager ($10k starting capital) - Dependency Injection
    risk_manager = RiskManager(storage=storage, initial_capital=10000.0, instrument_manager=instrument_mgr)
    
    # EdgeTuner (Parameter auto-calibration)
    edge_tuner = EdgeTuner(storage=storage)
    
    # Trade Closure Listener (Autonomous feedback loop)
    trade_listener = TradeClosureListener(
        storage=storage,
        risk_manager=risk_manager,
        edge_tuner=edge_tuner,
        max_retries=3,
        retry_backoff=0.5
    )
    logger.info("✅ TradeClosureListener initialized with idempotent event handling")
    
    # Order Executor
    notifier = get_notifier()
    executor = OrderExecutor(risk_manager=risk_manager, storage=storage, notificator=notifier)
    
    # 3. Create Orchestrator
    _orchestrator = MainOrchestrator(
        scanner=_scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
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
