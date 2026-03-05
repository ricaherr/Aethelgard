"""
Signal Lifecycle Manager Service
Handles signal registration through all lifecycle states: PENDING → EXECUTED/REJECTED.
Separates persistence and notification concerns from OrderExecutor.
"""
import logging
from typing import Dict, Optional, Any
from datetime import datetime

from models.signal import Signal
from data_vault.storage import StorageManager
from core_brain.risk_calculator import RiskCalculator

logger = logging.getLogger(__name__)


class SignalLifecycleManager:
    """
    Manages signal state transitions and persistence.
    
    Responsibilities:
    - Register pending signals
    - Update successful executions
    - Update failed/rejected signals
    - Persist position metadata
    """
    
    def __init__(
        self,
        storage: StorageManager,
        risk_calculator: Optional[RiskCalculator] = None
    ):
        """
        Initialize lifecycle manager.
        
        Args:
            storage: StorageManager for persistence
            risk_calculator: RiskCalculator for position metadata (optional)
        """
        self.storage = storage
        self.risk_calculator = risk_calculator
    
    def register_pending(self, signal: Signal) -> None:
        """
        Register signal with PENDING status in data_vault.
        
        Args:
            signal: Signal to register as pending
        """
        signal_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "signal_type": self._extract_value(signal.signal_type),
            "confidence": signal.confidence,
            "connector_type": signal.connector_type.value,
            "status": "PENDING",
            "entry_price": signal.entry_price,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "volume": signal.volume
        }
        
        self.storage.update_system_state({
            "pending_signals": [signal_record]
        })
        
        logger.debug(f"[SIGNAL_LIFECYCLE] Signal registered as PENDING: {signal.symbol}")
    
    def register_successful(self, signal: Signal, result: Dict) -> None:
        """
        Update signal to EXECUTED status (signal already saved by SignalFactory).
        
        Args:
            signal: Original signal executed
            result: Execution result from connector
        """
        # Extract signal ID assigned by SignalFactory
        signal_id = signal.metadata.get('signal_id')
        if not signal_id:
            logger.error(f"[SIGNAL_LIFECYCLE] Signal missing ID from SignalFactory: {signal.symbol}")
            return
        
        ticket = result.get('ticket') or result.get('order_id')
        
        metadata_update = {
            'ticket': ticket,
            'execution_price': result.get('price'),
            'execution_time': datetime.now().isoformat(),
            'connector': self._extract_value(signal.connector_type),
            'reason': f"Executed successfully. Ticket={ticket}",
            'stop_loss': signal.stop_loss,
            'take_profit': signal.take_profit,
            'lot_size': getattr(signal, 'volume', None)
        }
        
        self.storage.update_signal_status(signal_id, 'EXECUTED', metadata_update)
        logger.debug(f"[SIGNAL_LIFECYCLE] Signal updated to EXECUTED: {signal.symbol}, Ticket: {ticket}")
    
    def register_failed(self, signal: Signal, reason: str) -> None:
        """
        Update signal to REJECTED status (signal already saved by SignalFactory).
        
        Args:
            signal: Signal that failed execution
            reason: Rejection reason
        """
        signal_id = signal.metadata.get('signal_id')
        if not signal_id:
            logger.warning(f"[SIGNAL_LIFECYCLE] Signal missing ID from SignalFactory: {signal.symbol}")
            return
        
        self.storage.update_signal_status(signal_id, 'REJECTED', {
            'reason': reason
        })
        
        signal_record = {
            "timestamp": datetime.now().isoformat(),
            "symbol": signal.symbol,
            "signal_type": self._extract_value(signal.signal_type),
            "confidence": signal.confidence,
            "status": "REJECTED",
            "reason": reason,
            "connector_type": self._extract_value(signal.connector_type) if signal.connector_type else "UNKNOWN"
        }
        
        self.storage.update_system_state({
            "rejected_signals": [signal_record]
        })
        logger.debug(f"[SIGNAL_LIFECYCLE] Signal updated to REJECTED: {signal.symbol}, Reason: {reason}")
    
    def save_position_metadata(self, signal: Signal, result: Dict, ticket: int) -> None:
        """
        Save position metadata for PositionManager monitoring.
        
        Args:
            signal: Original signal executed
            result: Execution result from connector
            ticket: Order ticket/ID from broker
        """
        try:
            entry_price = result.get('entry_price', signal.entry_price)
            sl = result.get('sl', signal.stop_loss)
            tp = result.get('tp', signal.take_profit)
            volume = result.get('volume', signal.volume)
            
            regime_str = signal.metadata.get('regime', 'NEUTRAL')
            if hasattr(regime_str, 'value'):
                regime_str = regime_str.value
            
            # Calculate initial risk using RiskCalculator (universal)
            if self.risk_calculator:
                try:
                    initial_risk_usd = self.risk_calculator.calculate_initial_risk_usd(
                        symbol=signal.symbol,
                        entry_price=entry_price,
                        stop_loss=sl,
                        volume=volume
                    )
                except Exception as exc:
                    logger.warning(f"[SIGNAL_LIFECYCLE] Failed to calculate initial risk: {exc}")
                    initial_risk_usd = None
            else:
                initial_risk_usd = None
            
            # Persist position metadata (FASE 2.3)
            position_data = {
                'ticket': ticket,
                'symbol': signal.symbol,
                'entry_price': entry_price,
                'sl': sl,
                'tp': tp,
                'volume': volume,
                'entry_regime': regime_str,
                'entry_time': datetime.now().isoformat(),
                'initial_risk_usd': initial_risk_usd,
                'strategy_id': signal.metadata.get('strategy_id'),
                'timeframe': signal.metadata.get('timeframe')
            }
            
            self.storage.update_position_metadata(ticket, position_data)
            logger.debug(f"[SIGNAL_LIFECYCLE] Position metadata saved: {signal.symbol}, Ticket: {ticket}")
            
        except Exception as exc:
            logger.error(f"[SIGNAL_LIFECYCLE] Failed to save position metadata: {exc}")
    
    @staticmethod
    def _extract_value(obj: Any) -> str:
        """Extract value from Enum-like objects."""
        if hasattr(obj, 'value'):
            return obj.value
        return str(obj)
