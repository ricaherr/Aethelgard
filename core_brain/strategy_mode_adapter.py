"""
Strategy Mode Adapter
Wraps StrategyModeSelector to provide SignalFactory-like interface
for backward compatibility with MainOrchestrator.

Trace_ID: STRATEGY-GENESIS-2026-001
"""
import logging
from typing import Any, Optional, Dict, List

logger = logging.getLogger(__name__)


class StrategyModeAdapter:
    """
    Adapter that provides SignalFactory-like interface
    but delegates execution to StrategyModeSelector.
    
    This maintains backward compatibility with MainOrchestrator
    while enabling the dual-motor architecture.
    
    Implements generate_usr_signals_batch() which is what MainOrchestrator uses.
    """
    
    def __init__(self, strategy_mode_selector: Any):
        """
        Args:
            strategy_mode_selector: StrategyModeSelector instance
        """
        self.selector = strategy_mode_selector
    
    async def generate_usr_signals_batch(
        self,
        scan_results: Dict[str, Dict],
        trace_id: Optional[str] = None
    ) -> List[Any]:
        """
        Generate usr_signals from batch scan results (SignalFactory interface).
        
        Delegates to StrategyModeSelector which routes to legacy or universal executor.
        
        Args:
            scan_results: Dict with "symbol|timeframe" -> {"regime", "df", "symbol", "timeframe"}
            trace_id: Optional trace ID for auditing
            
        Returns:
            List of Signal objects
        """
        try:
            from models.signal import Signal, ConnectorType, SignalType, MarketRegime
            
            usr_signals = []
            
            for key, data in scan_results.items():
                symbol = data.get("symbol")
                df = data.get("df")
                regime = data.get("regime")
                
                if not symbol or df is None or not regime:
                    continue
                
                result = await self.selector.execute(
                    symbol=symbol,
                    data_frame=df,
                    regime=regime,
                    trace_id=trace_id
                )
                
                if result:
                    # Convert dict result back to Signal object
                    signal_direction = result.get("signal")  # "BUY" or "SELL"
                    
                    try:
                        signal_type = SignalType(signal_direction)
                    except (ValueError, TypeError):
                        signal_type = SignalType.HOLD  # Default if invalid
                    
                    signal = Signal(
                        symbol=symbol,
                        signal_type=signal_type,
                        confidence=result.get("confidence", 0.0),
                        entry_price=0.0,
                        stop_loss=0.0,
                        take_profit=0.0,
                        strategy_id=result.get("strategy_id", "universal"),
                        connector_type=ConnectorType.PAPER,
                        timeframe=data.get("timeframe", "M15"),
                        trace_id=trace_id,
                        metadata={
                            "source": result.get("source", "unknown"),
                            "mode": result.get("mode", "unknown"),
                            "regime": regime
                        }
                    )
                    usr_signals.append(signal)
            
            return usr_signals
        
        except Exception as e:
            logger.error(f"Error in StrategyModeAdapter.generate_usr_signals_batch(): {e}", exc_info=True)
            return []
    
    # Legacy method for backward compatibility
    async def analyze(
        self,
        symbol: str,
        df: Any,
        regime: Optional[Any] = None,
        **kwargs
    ) -> Optional[Any]:
        """
        Legacy analyze method (for potential other code paths).
        
        Args:
            symbol: Trading instrument
            df: OHLC DataFrame
            regime: MarketRegime context
            
        Returns:
            Signal object or None
        """
        try:
            from models.signal import Signal, ConnectorType, SignalType
            
            result = await self.selector.execute(
                symbol=symbol,
                data_frame=df,
                regime=regime,
                **kwargs
            )
            
            if result:
                signal_direction = result.get("signal")  # "BUY" or "SELL"
                try:
                    signal_type = SignalType(signal_direction)
                except (ValueError, TypeError):
                    signal_type = SignalType.HOLD
                
                signal = Signal(
                    symbol=symbol,
                    signal_type=signal_type,
                    confidence=result.get("confidence", 0.0),
                    entry_price=0.0,
                    stop_loss=0.0,
                    take_profit=0.0,
                    strategy_id=result.get("strategy_id", "universal"),
                    connector_type=ConnectorType.PAPER,
                    timeframe="M15",
                    trace_id=kwargs.get("trace_id"),
                    metadata={
                        "source": result.get("source", "unknown"),
                        "mode": result.get("mode", "unknown")
                    }
                )
                return signal
            
            return None
        
        except Exception as e:
            logger.error(f"Error in StrategyModeAdapter.analyze({symbol}): {e}", exc_info=True)
            return None
    
    @property
    def current_mode(self) -> Optional[str]:
        """Get current execution mode (for status/debugging)."""
        if hasattr(self.selector, 'current_mode') and self.selector.current_mode:
            return self.selector.current_mode.value
        return None
