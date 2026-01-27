"""
Main Orchestrator - Aethelgard Trading System
=============================================

Orchestrates the complete trading cycle: Scan -> Signal -> Risk -> Execute.

Key Features:
- Asynchronous event loop for non-blocking operation
- Dynamic frequency adjustment based on market regime
- Session statistics tracking
- Graceful shutdown with state persistence
- Error resilience with automatic recovery

Principles Applied:
- Autonomy: Self-regulating loop frequency
- Resilience: Continues operation on component failures
- Agnosticism: Works with any injected components
- Security: Persists critical state before shutdown
"""
import asyncio
import json
import logging
import signal
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Optional, Any

from models.signal import MarketRegime, Signal
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


@dataclass
class SessionStats:
    """
    Tracks session statistics for the current trading day.
    Resets automatically when a new day begins.
    """
    date: date = field(default_factory=date.today)
    signals_processed: int = 0
    signals_executed: int = 0
    cycles_completed: int = 0
    errors_count: int = 0
    
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
    """
    Main orchestrator for the Aethelgard trading system.
    
    Manages the complete trading cycle:
    1. Scanner: Identifies market opportunities
    2. Signal Factory: Generates trading signals
    3. Risk Manager: Validates risk parameters
    4. Executor: Places orders
    
    Features dynamic loop frequency based on market regime to optimize
    CPU usage and trading responsiveness.
    """
    
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
        
        # Session tracking
        self.stats = SessionStats()
        
        # Current market regime (updated after each scan)
        self.current_regime: MarketRegime = MarketRegime.RANGE
        
        # Shutdown flag
        self._shutdown_requested = False
        
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
        
        Returns:
            Sleep interval in seconds
        """
        return self.intervals.get(self.current_regime, 30)
    
    def _update_regime_from_scan(self, scan_results: Dict[str, Dict]) -> None:
        """
        Update current regime based on scan results.
        Uses the most aggressive regime found across all symbols.
        
        Args:
            scan_results: Dictionary of symbol -> regime data
        """
        if not scan_results:
            return
        
        # Priority order: SHOCK > VOLATILE > TREND > RANGE
        regime_priority = {
            MarketRegime.SHOCK: 4,
            MarketRegime.VOLATILE: 3,
            MarketRegime.TREND: 2,
            MarketRegime.RANGE: 1
        }
        
        max_priority = 0
        new_regime = MarketRegime.RANGE
        
        for symbol_data in scan_results.values():
            regime = symbol_data.get("regime", MarketRegime.RANGE)
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
        4. Execute approved signals
        5. Update statistics
        """
        try:
            # Check if we need to reset stats for new day
            self.stats.reset_if_new_day()
            
            # Step 1: Scan market
            logger.debug("Starting market scan...")
            scan_results = await self.scanner.scan_all_symbols()
            
            if not scan_results:
                logger.warning("No scan results received")
                return
            
            # Update current regime based on scan
            self._update_regime_from_scan(scan_results)
            
            # Step 2: Generate signals
            logger.debug("Generating signals from scan results...")
            signals = await self.signal_factory.process_scan_results(scan_results)
            
            if not signals:
                logger.debug("No signals generated")
                self.stats.cycles_completed += 1
                return
            
            logger.info(f"Generated {len(signals)} signals")
            self.stats.signals_processed += len(signals)
            
            # Step 3: Check risk manager lockdown
            if self.risk_manager.is_lockdown_active():
                logger.warning("Lockdown mode active. Skipping signal execution.")
                self.stats.cycles_completed += 1
                return
            
            # Step 4: Execute signals
            for signal in signals:
                try:
                    logger.info(f"Executing signal: {signal.symbol} {signal.signal_type}")
                    success = await self.executor.execute_signal(signal)
                    
                    if success:
                        self.stats.signals_executed += 1
                        logger.info(f"Signal executed successfully: {signal.symbol}")
                    else:
                        logger.warning(f"Signal execution failed: {signal.symbol}")
                        
                except Exception as e:
                    logger.error(f"Error executing signal {signal.symbol}: {e}")
                    self.stats.errors_count += 1
            
            # Step 5: Update cycle count
            self.stats.cycles_completed += 1
            logger.info(f"Cycle completed. Stats: {self.stats}")
            
        except Exception as e:
            logger.error(f"Error in cycle execution: {e}", exc_info=True)
            self.stats.errors_count += 1
    
    async def run(self) -> None:
        """
        Main event loop.
        
        Runs continuously until shutdown is requested.
        Adjusts loop frequency dynamically based on market regime.
        """
        logger.info("MainOrchestrator starting event loop...")
        
        # Register signal handlers for graceful shutdown
        self._register_signal_handlers()
        
        try:
            while not self._shutdown_requested:
                # Execute one complete cycle
                await self.run_single_cycle()
                
                # Dynamic sleep based on current regime
                sleep_interval = self._get_sleep_interval()
                logger.debug(
                    f"Sleeping for {sleep_interval}s "
                    f"(regime: {self.current_regime})"
                )
                
                # Use small sleep chunks to allow quick shutdown
                for _ in range(sleep_interval):
                    if self._shutdown_requested:
                        break
                    await asyncio.sleep(1)
                    
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
            self.storage.save_system_state(system_state)
            
            # Close broker connections (if connectors have cleanup methods)
            if hasattr(self.executor, 'close_connections'):
                logger.info("Closing broker connections...")
                await self.executor.close_connections()
            
            logger.info("Shutdown completed successfully")
            
        except Exception as e:
            logger.error(f"Error during shutdown: {e}", exc_info=True)
    
    def _register_signal_handlers(self) -> None:
        """Register signal handlers for Ctrl+C and SIGTERM"""
        def signal_handler(signum, frame):
            logger.info(f"Received signal {signum}. Requesting shutdown...")
            self._shutdown_requested = True
        
        # Register handlers
        signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
        signal.signal(signal.SIGTERM, signal_handler)  # Kill command


async def main():
    """
    Example usage of MainOrchestrator.
    
    In production, components would be properly initialized.
    This is just a demonstration of the async entry point.
    """
    from core_brain.scanner import ScannerEngine
    from core_brain.signal_factory import SignalFactory
    from core_brain.risk_manager import RiskManager
    from core_brain.executor import OrderExecutor
    
    # Initialize components (would use real implementations in production)
    storage = StorageManager()
    risk_manager = RiskManager(initial_capital=10000.0)
    
    # Create orchestrator (components would be fully initialized)
    orchestrator = MainOrchestrator(
        scanner=None,  # Would be ScannerEngine instance
        signal_factory=None,  # Would be SignalFactory instance
        risk_manager=risk_manager,
        executor=None,  # Would be OrderExecutor instance
        storage=storage
    )
    
    # Run the main loop
    await orchestrator.run()


if __name__ == "__main__":
    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Run the orchestrator
    asyncio.run(main())
