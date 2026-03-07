"""
Legacy Strategy Executor Adapter
Wraps existing Python-based usr_strategies (OliverVelezStrategy, etc.)
for execution within the dual-motor architecture.

Trace_ID: STRATEGY-GENESIS-2026-001
"""
import logging
from typing import Any, Optional, Dict
from models.signal import Signal

logger = logging.getLogger(__name__)


class LegacyStrategyExecutor:
    """
    Adapter that wraps legacy Python strategy execution.
    
    Delegates to SignalFactory + BaseStrategy implementations
    (OliverVelezStrategy, TrifectaAnalyzer, etc.)
    """
    
    def __init__(self, signal_factory: Any, trace_id: str = None):
        """
        Args:
            signal_factory: SignalFactory instance with usr_strategies loaded
            trace_id: Request trace ID for auditing
        """
        self.signal_factory = signal_factory
        self.trace_id = trace_id
    
    async def execute(
        self,
        symbol: str,
        data_frame: Any,
        regime: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Execute legacy strategy pipeline.
        
        Delegates to SignalFactory which runs all loaded usr_strategies
        (primarily OliverVelezStrategy in current setup).
        
        Args:
            symbol: Trading instrument
            data_frame: OHLC market data
            regime: MarketRegime context
            
        Returns:
            Signal result or None
        """
        try:
            # Delegate to existing SignalFactory
            usr_signals = await self.signal_factory.analyze(
                symbol=symbol,
                df=data_frame,
                regime=regime
            )
            
            if usr_signals:
                # Convert Signal object to dict if needed
                if isinstance(usr_signals, Signal):
                    return {
                        "signal": usr_signals.direction,
                        "confidence": usr_signals.confidence,
                        "source": "legacy_python",
                        "strategy_id": getattr(usr_signals, 'strategy_id', 'oliver_velez')
                    }
                elif isinstance(usr_signals, list):
                    # Return first signal if list
                    if usr_signals and isinstance(usr_signals[0], Signal):
                        return {
                            "signal": usr_signals[0].direction,
                            "confidence": usr_signals[0].confidence,
                            "source": "legacy_python",
                            "strategy_id": getattr(usr_signals[0], 'strategy_id', 'oliver_velez')
                        }
            
            return None
        
        except Exception as e:
            logger.error(f"[LEGACY EXECUTOR] Error executing {symbol}: {e}", exc_info=True)
            raise
