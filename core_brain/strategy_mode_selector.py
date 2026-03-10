"""
Strategy Mode Selector (HU 3.9)
Trace_ID: STRATEGY-GENESIS-2026-001

Hot-swap runtime selection between:
- MODE_LEGACY: Python-based usr_strategies in core_brain/usr_strategies/
- MODE_UNIVERSAL: JSON-based usr_strategies via UniversalStrategyEngine

Features:
- Tenant-specific configuration (SSOT: database)
- Hot-swap at runtime without restart
- Audit trail in SYSTEM_LEDGER
- Forbids ambiguity at startup
"""
import asyncio
import logging
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime
import uuid

logger = logging.getLogger(__name__)


class RuntimeMode(Enum):
    """Strategy execution runtime modes."""
    MODE_LEGACY = "legacy"
    MODE_UNIVERSAL = "universal"


class StrategyModeSelector:
    """
    Selects strategy runtime mode for a tenant.
    
    Responsibilities:
    - Load tenant's configured mode from database (SSOT)
    - Route strategy execution to appropriate executor
    - Enable hot-swap mode switching with audit trail
    - Forbid ambiguous configurations at startup
    
    Architecture:
    - Zero coupling to strategy implementations
    - Dependency injection of executors
    - Async-first for non-blocking operation
    """
    
    def __init__(
        self,
        storage_manager: Any,
        legacy_executor: Any,
        universal_executor: Any,
        tenant_id: str,
        trace_id: str = None
    ):
        """
        Initialize mode selector for a tenant.
        
        Args:
            storage_manager: StorageManager instance (SSOT)
            legacy_executor: Executor for MODE_LEGACY (Python scripts)
            universal_executor: Executor for MODE_UNIVERSAL (JSON)
            tenant_id: Tenant identifier
            trace_id: Optional request trace ID
            
        Raises:
            ValueError: If configuration is ambiguous or invalid
        """
        self.storage = storage_manager
        self.legacy_executor = legacy_executor
        self.universal_executor = universal_executor
        self.user_id = user_id
        self.trace_id = trace_id or str(uuid.uuid4())
        
        # Will be populated during async initialization
        self._current_mode: Optional[RuntimeMode] = None
        self._initialized = False
    
    async def initialize(self) -> None:
        """
        Load user's configured mode from database.
        
        This must be called after construction (async initialization pattern).
        
        Raises:
            ValueError: If mode is ambiguous or missing
        """
        try:
            user_config = await self.storage.get_user_config(self.user_id)
            
            if not user_config:
                raise ValueError(
                    f"User '{self.user_id}' configuration not found"
                )
            
            mode_str = user_config.get("strategy_runtime_mode")
            
            if not mode_str:
                raise ValueError(
                    f"User '{self.user_id}' has ambiguous strategy_runtime_mode "
                    "(missing from config). Refusing to start."
                )
            
            # Validate mode string
            try:
                self._current_mode = RuntimeMode(mode_str)
            except ValueError:
                raise ValueError(
                    f"Invalid runtime mode '{mode_str}' for user '{self.user_id}'. "
                    f"Allowed: {[m.value for m in RuntimeMode]}"
                )
            
            logger.info(
                f"[Trace: {self.trace_id}] User '{self.user_id}' "
                f"initialized with MODE_{self._current_mode.value.upper()}"
            )
            self._initialized = True
        
        except Exception as e:
            logger.error(f"[Trace: {self.trace_id}] Mode selector initialization failed: {e}")
            raise
    
    async def execute(
        self,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute strategy using configured runtime mode.
        
        Args:
            symbol: Trading instrument
            data_frame: Market data
            regime: Optional market regime context
            **kwargs: Additional execution parameters
            
        Returns:
            Signal result from appropriate executor
            
        Raises:
            RuntimeError: If selector not initialized
        """
        if not self._initialized:
            raise RuntimeError(
                f"StrategyModeSelector for user '{self.user_id}' not initialized. "
                "Call initialize() first."
            )
        
        try:
            if self._current_mode == RuntimeMode.MODE_LEGACY:
                return await self._execute_legacy(symbol, data_frame, regime, **kwargs)
            
            elif self._current_mode == RuntimeMode.MODE_UNIVERSAL:
                return await self._execute_universal(symbol, data_frame, regime, **kwargs)
            
            else:
                raise ValueError(f"Unknown runtime mode: {self._current_mode}")
        
        except Exception as e:
            logger.error(
                f"[Trace: {self.trace_id}] Execution failed in {self._current_mode.value} mode: {e}",
                exc_info=True
            )
            raise
    
    async def _execute_legacy(
        self,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Execute via legacy Python strategy files."""
        logger.debug(f"Executing {symbol} via LEGACY mode")
        
        if not self.legacy_executor:
            raise RuntimeError("Legacy executor not available")
        
        return await self.legacy_executor.execute(
            symbol=symbol,
            data_frame=data_frame,
            regime=regime,
            **kwargs
        )
    
    async def _execute_universal(
        self,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any],
        **kwargs
    ) -> Dict[str, Any]:
        """Execute via universal JSON-based engine."""
        logger.debug(f"Executing {symbol} via UNIVERSAL mode")
        
        if not self.universal_executor:
            raise RuntimeError("Universal executor not available")
        
        return await self.universal_executor.execute(
            symbol=symbol,
            data_frame=data_frame,
            regime=regime,
            **kwargs
        )
    
    async def switch_mode(
        self,
        target_mode: RuntimeMode,
        reason: str = None,
        wait_for_in_flight: bool = True
    ) -> None:
        """
        Hot-swap strategy execution mode at runtime.
        
        Args:
            target_mode: Destination RuntimeMode
            reason: Human-readable reason for switch (logged in ledger)
            wait_for_in_flight: Wait for pending usr_signals before switching
            
        Raises:
            ValueError: If target mode is invalid
            RuntimeError: If switch fails
        """
        if not isinstance(target_mode, RuntimeMode):
            raise ValueError(
                f"Invalid target mode type: {type(target_mode)}. "
                f"Must be RuntimeMode enum."
            )
        
        if target_mode == self._current_mode:
            logger.info(
                f"[Trace: {self.trace_id}] Already in {target_mode.value} mode. "
                f"No switch needed."
            )
            return
        
        try:
            # Optional: Wait for in-flight usr_signals (implementation-specific)
            if wait_for_in_flight:
                await asyncio.sleep(0.1)  # Placeholder for graceful shutdown
            
            # Update database (SSOT)
            old_mode = self._current_mode
            await self.storage.update_user_config(
                user_id=self.user_id,
                updates={"strategy_runtime_mode": target_mode.value}
            )
            
            # Update in-memory state
            self._current_mode = target_mode
            
            # Audit in SYSTEM_LEDGER
            ledger_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "trace_id": self.trace_id,
                "event_type": "MODE_SWITCH",
                "user_id": self.user_id,
                "old_mode": old_mode.value,
                "new_mode": target_mode.value,
                "reason": reason or "Not specified",
                "execution_model": "hot_swap"
            }
            
            await self.storage.append_to_system_ledger(ledger_entry)
            
            logger.info(
                f"[Trace: {self.trace_id}] Mode switched: "
                f"{old_mode.value} → {target_mode.value}. Reason: {reason}"
            )
        
        except Exception as e:
            logger.error(
                f"[Trace: {self.trace_id}] Failed to switch mode from {self._current_mode.value} "
                f"to {target_mode.value}: {e}",
                exc_info=True
            )
            raise RuntimeError(f"Mode switch failed: {e}")
    
    @property
    def current_mode(self) -> Optional[RuntimeMode]:
        """Returns current execution mode."""
        return self._current_mode
    
    @property
    def is_initialized(self) -> bool:
        """Returns True if selector is ready to execute."""
        return self._initialized
    
    async def get_status(self) -> Dict[str, Any]:
        """Return current mode status and configuration."""
        return {
            "user_id": self.user_id,
            "current_mode": self._current_mode.value if self._current_mode else None,
            "initialized": self._initialized,
            "trace_id": self.trace_id,
            "timestamp": datetime.utcnow().isoformat()
        }
