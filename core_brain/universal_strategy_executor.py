"""
Universal Strategy Executor Adapter
Wraps the JSON-based UniversalStrategyEngine for execution
within the dual-motor architecture.

Trace_ID: STRATEGY-GENESIS-2026-001
"""
import logging
from typing import Any, Optional, Dict, List
from pathlib import Path
import json

from core_brain.universal_strategy_engine import UniversalStrategyEngine, ExecutionMode

logger = logging.getLogger(__name__)


class UniversalStrategyExecutor:
    """
    Adapter that delegates to UniversalStrategyEngine
    for JSON-based strategy execution.
    
    Features:
    - Loads strategy schemas from file system
    - Instantiates UniversalStrategyEngine per strategy
    - Manages multiple concurrent JSON-based strategies
    """
    
    def __init__(
        self,
        indicator_provider: Any,
        strategy_schemas_dir: Optional[str] = None,
        trace_id: str = None
    ):
        """
        Args:
            indicator_provider: Object with calculate_* async methods (RSI, MA, FVG, etc.)
            strategy_schemas_dir: Directory containing strategy JSON files
                                 Defaults to: core_brain/strategies/universal/
            trace_id: Request trace ID for auditing
        """
        self.indicator_provider = indicator_provider
        self.strategy_schemas_dir = strategy_schemas_dir or self._default_schemas_dir()
        self.trace_id = trace_id
        
        # Cache of loaded engines (strategy_id -> Engine instance)
        self._engine_cache: Dict[str, UniversalStrategyEngine] = {}
        
        logger.info(f"UniversalStrategyExecutor initialized with schemas in: {self.strategy_schemas_dir}")
    
    @staticmethod
    def _default_schemas_dir() -> str:
        """Returns default path for strategy schemas."""
        return str(Path(__file__).parent.parent / "strategies" / "universal")
    
    async def execute(
        self,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any] = None,
        strategy_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute universal JSON strategy.
        
        Args:
            symbol: Trading instrument
            data_frame: OHLC market data
            regime: MarketRegime context
            strategy_id: Optional specific strategy to run
            
        Returns:
            Signal result or STRATEGY_CRASH_VETO on error
        """
        try:
            # Load all available strategies if none specified
            strategies_to_run = [strategy_id] if strategy_id else await self._discover_strategies()
            
            if not strategies_to_run:
                logger.warning(
                    f"No universal strategies found in {self.strategy_schemas_dir}"
                )
                return None
            
            # Execute strategies and collect results
            results = []
            for strat_id in strategies_to_run:
                engine = await self._get_or_create_engine(strat_id)
                
                if not engine:
                    continue
                
                result = await engine.execute(
                    symbol=symbol,
                    data_frame=data_frame,
                    regime=regime
                )
                
                # Check for execution errors
                if result.execution_mode == ExecutionMode.CRASH_VETO:
                    logger.warning(
                        f"[STRATEGY_CRASH_VETO] Strategy '{strat_id}' failed: {result.error_message}"
                    )
                    continue
                
                results.append({
                    "strategy_id": result.strategy_id,
                    "signal": result.signal,
                    "confidence": result.confidence,
                    "source": "universal_json",
                    "mode": result.execution_mode.value
                })
            
            # Return first valid signal (or None if all crashed)
            if results:
                return results[0]
            
            return None
        
        except Exception as e:
            logger.error(
                f"[UNIVERSAL EXECUTOR] Error executing {symbol}: {e}",
                exc_info=True
            )
            raise
    
    async def _get_or_create_engine(self, strategy_id: str) -> Optional[UniversalStrategyEngine]:
        """
        Retrieve cached engine or load and create new one.
        
        Args:
            strategy_id: Strategy identifier (matches JSON filename)
            
        Returns:
            UniversalStrategyEngine instance or None if schema not found
        """
        # Check cache
        if strategy_id in self._engine_cache:
            return self._engine_cache[strategy_id]
        
        # Load schema from file
        schema = await self._load_strategy_schema(strategy_id)
        if not schema:
            return None
        
        # Create engine
        try:
            engine = UniversalStrategyEngine(
                strategy_schema=schema,
                indicator_provider=self.indicator_provider
            )
            self._engine_cache[strategy_id] = engine
            return engine
        
        except Exception as e:
            logger.error(f"Failed to create engine for strategy '{strategy_id}': {e}")
            return None
    
    async def _load_strategy_schema(self, strategy_id: str) -> Optional[Dict]:
        """
        Load strategy JSON schema from file.
        
        Args:
            strategy_id: Strategy identifier
            
        Returns:
            Schema dict or None if not found
        """
        schema_path = Path(self.strategy_schemas_dir) / f"{strategy_id}.json"
        
        try:
            if not schema_path.exists():
                logger.warning(f"Strategy schema not found: {schema_path}")
                return None
            
            with open(schema_path, 'r') as f:
                schema = json.load(f)
            
            return schema
        
        except Exception as e:
            logger.error(f"Failed to load strategy schema '{strategy_id}': {e}")
            return None
    
    async def _discover_strategies(self) -> List[str]:
        """
        Discover all available strategy JSON files.
        
        Returns:
            List of strategy IDs (filenames without .json)
        """
        try:
            schemas_dir = Path(self.strategy_schemas_dir)
            
            if not schemas_dir.exists():
                logger.warning(f"Schemas directory does not exist: {schemas_dir}")
                return []
            
            strategies = [
                f.stem for f in schemas_dir.glob("*.json")
                if f.is_file()
            ]
            
            logger.debug(f"Discovered {len(strategies)} universal strategies")
            return sorted(strategies)
        
        except Exception as e:
            logger.error(f"Failed to discover strategies: {e}")
            return []
