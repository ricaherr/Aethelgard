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

logger = logging.getLogger(__name__)


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
        config_path: str = "config/config.json"
    ):
        """
        Initialize MainOrchestrator.
        
        Args:
            scanner: ScannerEngine instance
            signal_factory: SignalFactory instance
            risk_manager: RiskManager instance
            executor: OrderExecutor instance
            storage: StorageManager instance (creates if None)
            config_path: Path to configuration file
        """
        self.scanner = scanner
        self.signal_factory = signal_factory
        self.risk_manager = risk_manager
        self.executor = executor
        self.storage = storage or StorageManager()
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # MODULE TOGGLES: Load global module enable/disable settings from DB
        # This allows runtime control without restarting the system
        self.modules_enabled_global = self.storage.get_global_modules_enabled()
        
        # Log module states on startup
        disabled_modules = [k for k, v in self.modules_enabled_global.items() if not v]
        if disabled_modules:
            logger.warning(f"[WARNING]  Módulos DESHABILITADOS globalmente: {', '.join(disabled_modules)}")
        else:
            logger.info("[OK] Todos los módulos están HABILITADOS globalmente")


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
        # Signal expiration manager (EDGE: auto-expire old signals)
        self.expiration_manager = SignalExpirationManager(storage=self.storage)
        
        # FASE 2: Position Manager (active position management)
        # Load dynamic_params.json for position_management config
        dynamic_config = self._load_config("config/dynamic_params.json")
        position_config = dynamic_config.get("position_management", {})
        
        # Instantiate PositionManager with dependencies
        # Note: We'll get connector from executor.connectors
        from models.signal import ConnectorType
        connector = None
        if hasattr(self.executor, 'connectors'):
            # Try to get MT5 connector first (most common)
            connector = self.executor.connectors.get(ConnectorType.METATRADER5)
        
        # Instantiate RegimeClassifier (needed by PositionManager)
        self.regime_classifier = RegimeClassifier()
        
        # Create PositionManager
        self.position_manager = PositionManager(
            storage=self.storage,
            connector=connector,
            regime_classifier=self.regime_classifier,
            config=position_config
        )
        logger.info(f"Position Manager initialized with config: enabled={position_config.get('enabled', False)}")
        
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

        # EDGE: Descubrimiento y clasificación dinámica de brokers (después de stats)
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
    
    def _load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file"""
        config_file = Path(config_path)
        
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_path}. Using defaults.")
            return {}
        
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading config: {e}. Using defaults.")
            return {}
    
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
            
            # EDGE: Expire old PENDING signals based on timeframe window
            # This prevents stale signals from accumulating in database
            expiration_stats = self.expiration_manager.expire_old_signals()
            logger.info(f"[EXPIRATION] Processed {expiration_stats.get('total_checked', 0)} signals, "
                       f"expired {expiration_stats['total_expired']}")
            if expiration_stats['total_expired'] > 0:
                logger.info(f"[EXPIRATION] [OK] Breakdown: {expiration_stats['by_timeframe']}")
            
            # MODULE TOGGLE: Position Manager
            if not self.modules_enabled_global.get("position_manager", True):
                logger.debug("[TOGGLE] position_manager deshabilitado globalmente - saltado")
            elif self.position_manager:
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
                # Clear active signals if none generated
                self._active_signals.clear()
                self.stats.cycles_completed += 1
                return
            
            # Signal processing continues (unreachable code bug fixed)
            logger.info(f"Generated {len(signals)} signals")
            self.stats.signals_processed += len(signals)
            self.stats.signals_generated += len(signals)
            
            # Step 3: Validate signals with risk manager
            validated_signals = []
            for signal in signals:
                if self.risk_manager.validate_signal(signal):
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
                    success = await self.executor.execute_signal(signal)
                    
                    if success:
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
            
            # Step 5: Clear active signals after execution and update cycle count
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
    provider_manager = DataProviderManager()
    data_provider = provider_manager.get_best_provider()
    
    if not data_provider:
        print("[CRITICAL] No data provider available. Aborting.")
        return
    
    # Instrument Manager: Get only enabled instruments for scanning
    from core_brain.instrument_manager import InstrumentManager
    instrument_mgr = InstrumentManager()
    enabled_assets = instrument_mgr.get_enabled_symbols()
    
    if not enabled_assets:
        print("[CRITICAL] No enabled instruments found in config/instruments.json. Aborting.")
        return
    
    print(f"[SCAN] Scanning {len(enabled_assets)} enabled instruments: {enabled_assets[:10]}...")
    
    # Scanner (Only scans enabled instruments from configuration)
    scanner = ScannerEngine(assets=enabled_assets, data_provider=data_provider)
    
    # Signal Factory
    signal_factory = SignalFactory(storage_manager=storage)
    
    # Risk Manager ($10k starting capital) - Dependency Injection
    risk_manager = RiskManager(storage=storage, initial_capital=10000.0)
    
    # EdgeTuner (Parameter auto-calibration)
    edge_tuner = EdgeTuner(storage=storage, config_path="config/dynamic_params.json")
    
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
    orchestrator = MainOrchestrator(
        scanner=scanner,
        signal_factory=signal_factory,
        risk_manager=risk_manager,
        executor=executor,
        storage=storage
    )
    
    # 4. Start Scanner background thread (if needed by your architecture)
    # The ScannerEngine.run() usually runs in its own thread
    import threading
    scanner_thread = threading.Thread(target=scanner.run, daemon=True)
    scanner_thread.start()
    
    # 5. Run the main loop
    print("🚀 System LIVE. Starting event loop...")
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
