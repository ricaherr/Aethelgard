"""
Universal Strategy Engine (HU 3.6)
Trace_ID: STRATEGY-GENESIS-2026-001

Interpreter for JSON-based strategy execution with:
- Dynamic function mapping to existing indicators
- Error isolation (STRATEGY_CRASH_VETO)
- Memory-resident schema loading
- Type-safe execution with comprehensive validation

Principles:
- Agnostic: Works with any indicator provider
- Resilient: Crashes don't affect system
- Efficient: Single schema load, multiple executions
- Transparent: Full audit trail of decisions
"""
import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutionMode(Enum):
    """Strategy execution result codes."""
    SIGNAL_GENERATED = "signal_generated"
    NO_SIGNAL = "no_signal"
    CRASH_VETO = "strategy_crash_veto"


@dataclass
class StrategySignal:
    """Result of strategy execution."""
    strategy_id: str
    signal: Optional[str]  # "BUY", "SELL", None
    confidence: float  # 0.0-1.0
    execution_mode: ExecutionMode
    error_message: Optional[str] = None
    timestamp: Optional[str] = None


class StrategyExecutionError(Exception):
    """Raised when strategy execution encounters a fatal error."""
    pass


class StrategySchemaValidator:
    """Validates strategy JSON schema before execution."""
    
    REQUIRED_FIELDS = ["strategy_id", "version", "indicators"]
    REQUIRED_LOGIC_FIELDS = ["condition", "direction"]
    
    @staticmethod
    def validate(schema: Dict[str, Any]) -> None:
        """
        Validates strategy schema structure.
        
        Args:
            schema: Strategy dictionary from JSON
            
        Raises:
            ValueError: If schema is invalid
        """
        if not isinstance(schema, dict):
            raise ValueError("Strategy must be a dictionary")
        
        # Check required fields
        for field in StrategySchemaValidator.REQUIRED_FIELDS:
            if field not in schema:
                raise ValueError(f"Missing required field: {field}")
        
        # Validate indicators
        indicators = schema.get("indicators", {})
        if not isinstance(indicators, dict):
            raise ValueError("Indicators must be a dictionary")
        
        if not indicators:
            raise ValueError("At least one indicator is required")
        
        for ind_name, ind_config in indicators.items():
            if not isinstance(ind_config, dict):
                raise ValueError(f"Indicator '{ind_name}' config must be dict")
            if "type" not in ind_config:
                raise ValueError(f"Indicator '{ind_name}' missing 'type' field")
        
        # Validate entry logic
        if "entry_logic" in schema and schema["entry_logic"]:
            entry = schema["entry_logic"]
            for field in StrategySchemaValidator.REQUIRED_LOGIC_FIELDS:
                if field not in entry:
                    raise ValueError(f"Entry logic missing '{field}'")
        
        # Validate exit logic
        if "exit_logic" in schema and schema["exit_logic"]:
            exit_log = schema["exit_logic"]
            for field in StrategySchemaValidator.REQUIRED_LOGIC_FIELDS:
                if field not in exit_log:
                    raise ValueError(f"Exit logic missing '{field}'")


class IndicatorFunctionMapper:
    """Maps strategy indicator references to actual calculation functions."""
    
    def __init__(self, indicator_provider: Any):
        """
        Args:
            indicator_provider: Object with calculate_* methods
        """
        self.provider = indicator_provider
        self._function_cache: Dict[str, Callable] = {}
    
    def get_function(self, indicator_type: str) -> Callable:
        """
        Retrieves calculation function for indicator type.
        
        Args:
            indicator_type: Type string (e.g., "RSI", "MA", "FVG")
            
        Returns:
            Async callable for indicator calculation
            
        Raises:
            ValueError: If indicator type is unsupported
        """
        if indicator_type in self._function_cache:
            return self._function_cache[indicator_type]
        
        # Map indicator type to provider method
        method_name = f"calculate_{indicator_type.lower()}"
        
        if not hasattr(self.provider, method_name):
            raise ValueError(
                f"Unsupported indicator type: {indicator_type}. "
                f"Provider must have method: {method_name}"
            )
        
        func = getattr(self.provider, method_name)
        self._function_cache[indicator_type] = func
        return func


class UniversalStrategyEngine:
    """
    JSON-based strategy interpreter for MODE_UNIVERSAL execution.
    
    Features:
    - Single schema load (memory-resident)
    - Dynamic indicator function mapping
    - Error isolation with STRATEGY_CRASH_VETO
    - Type-safe condition evaluation
    
    Usage:
        engine = UniversalStrategyEngine(schema, indicator_provider)
        result = await engine.execute(symbol="EURUSD", data_frame=df)
    """
    
    def __init__(self, strategy_schema: Dict[str, Any], indicator_provider: Any):
        """
        Initialize engine with strategy schema.
        
        Args:
            strategy_schema: Strategy configuration dict (from JSON)
            indicator_provider: Object with calculate_* async methods
            
        Raises:
            ValueError: If schema is invalid
            StrategyExecutionError: If initialization fails
        """
        # Validate schema BEFORE anything else
        try:
            StrategySchemaValidator.validate(strategy_schema)
        except ValueError as e:
            raise ValueError(f"Schema validation failed: {e}")
        
        self._schema_cache = strategy_schema
        self._indicator_provider = indicator_provider
        self._function_mapper = IndicatorFunctionMapper(indicator_provider)
        
        self.strategy_id = strategy_schema["strategy_id"]
        logger.info(f"UniversalStrategyEngine initialized for '{self.strategy_id}'")
    
    async def execute(
        self,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any] = None
    ) -> StrategySignal:
        """
        Execute strategy logic against market data.
        
        Args:
            symbol: Trading instrument (e.g., "EURUSD")
            data_frame: pandas DataFrame with OHLC data
            regime: Optional MarketRegime context
            
        Returns:
            StrategySignal with result
        """
        try:
            # Calculate all required indicators
            indicator_results = await self._calculate_indicators(data_frame)
            
            # Evaluate entry logic
            entry_signal = await self._evaluate_logic(
                self._schema_cache.get("entry_logic"),
                indicator_results
            )
            
            # Evaluate exit logic
            exit_signal = await self._evaluate_logic(
                self._schema_cache.get("exit_logic"),
                indicator_results
            )
            
            # Determine final signal
            final_signal = entry_signal or exit_signal
            
            if final_signal:
                signal_data = final_signal if isinstance(final_signal, dict) else {}
                return StrategySignal(
                    strategy_id=self.strategy_id,
                    signal=signal_data.get("direction"),
                    confidence=signal_data.get("confidence", 0.0),
                    execution_mode=ExecutionMode.SIGNAL_GENERATED
                )
            
            return StrategySignal(
                strategy_id=self.strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.NO_SIGNAL
            )
        
        except Exception as e:
            error_msg = f"Strategy execution error: {str(e)}"
            logger.error(f"[STRATEGY_CRASH_VETO] {self.strategy_id}: {error_msg}")
            
            return StrategySignal(
                strategy_id=self.strategy_id,
                signal=None,
                confidence=0.0,
                execution_mode=ExecutionMode.CRASH_VETO,
                error_message=error_msg
            )
    
    async def _calculate_indicators(self, data_frame: Any) -> Dict[str, Any]:
        """
        Calculate all indicators required by strategy.
        
        Args:
            data_frame: Input market data
            
        Returns:
            Dictionary mapping indicator names to calculated values
            
        Raises:
            ValueError: If indicator calculation fails
        """
        indicators = self._schema_cache.get("indicators", {})
        results = {}
        
        for ind_name, ind_config in indicators.items():
            try:
                ind_type = ind_config.get("type")
                func = self._function_mapper.get_function(ind_type)
                
                # Call indicator calculation with config params
                # (excluding 'type' key)
                calc_params = {k: v for k, v in ind_config.items() if k != "type"}
                
                # Execute indicator calculation
                if asyncio.iscoroutinefunction(func):
                    value = await func(data_frame, **calc_params)
                else:
                    value = func(data_frame, **calc_params)
                
                results[ind_name] = value
                logger.debug(f"Calculated {ind_name} ({ind_type}): {value}")
            
            except Exception as e:
                raise ValueError(
                    f"Failed to calculate indicator '{ind_name}': {str(e)}"
                )
        
        return results
    
    async def _evaluate_logic(
        self,
        logic: Optional[Dict[str, Any]],
        indicators: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Evaluate entry/exit logic against calculated indicators.
        
        Args:
            logic: Logic block (entry_logic or exit_logic)
            indicators: Calculated indicator values
            
        Returns:
            Signal dict if condition evaluates to True, None otherwise
        """
        if not logic:
            return None
        
        condition = logic.get("condition", "")
        
        if not condition:
            return None
        
        try:
            # SAFETY: Create safe evaluation namespace
            # Only allow indicator values and constants
            safe_namespace = {
                "__builtins__": {},
                **{ind: val for ind, val in indicators.items()}
            }
            
            # Evaluate condition
            result = eval(condition, safe_namespace)
            
            if result:
                return {
                    "direction": logic.get("direction"),
                    "confidence": logic.get("confidence", 0.5)
                }
            
            return None
        
        except Exception as e:
            raise ValueError(f"Logic evaluation failed: {str(e)}")
    
    def get_schema(self) -> Dict[str, Any]:
        """Return cached schema (for inspection/audit)."""
        return self._schema_cache.copy()
