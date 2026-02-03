"""
Broker Events - Standardized Interface
=====================================

Defines the standard event contract that all brokers must follow.
This enables broker-agnostic event handling in the Listener.

Principle: Independent of broker implementation (MT5, NinjaTrader 8, etc.)
"""
from dataclasses import dataclass
from enum import Enum
from datetime import datetime
from typing import Optional, Dict, Any


class BrokerEventType(Enum):
    """Standard event types from any broker"""
    TRADE_OPENED = "trade_opened"
    TRADE_CLOSED = "trade_closed"
    TRADE_MODIFIED = "trade_modified"
    ORDER_PLACED = "order_placed"
    ORDER_CANCELLED = "order_cancelled"


class TradeResult(Enum):
    """Standardized trade result (broker-agnostic)"""
    WIN = "win"
    LOSS = "loss"
    BREAKEVEN = "breakeven"


@dataclass
class BrokerTradeClosedEvent:
    """
    Standard contract for TRADE_CLOSED events from any broker.
    
    Principle: This is the ONLY interface the Listener needs.
    Different brokers (MT5, NT8) adapt their data to this format.
    """
    # Core trade identification
    ticket: str  # Unique trade ID (MT5 ticket, NT8 order ID, etc.)
    symbol: str  # Normalized symbol (EURUSD, not EURUSD=X)
    
    # Trade execution details
    entry_price: float
    exit_price: float
    entry_time: datetime
    exit_time: datetime
    
    # Trade outcome
    pips: float  # Distance in pips
    profit_loss: float  # Profit/Loss in account currency
    result: TradeResult  # WIN, LOSS, BREAKEVEN
    
    # Additional context
    exit_reason: str  # "take_profit_hit", "stop_loss_hit", "manual_close", etc.
    broker_id: str  # Which broker sent this (MT5, NT8, etc.)
    signal_id: Optional[str] = None  # Link to original signal if exists
    metadata: Optional[Dict[str, Any]] = None  # Extra data from broker
    
    def is_loss(self) -> bool:
        """Convenience method"""
        return self.result == TradeResult.LOSS
    
    def is_win(self) -> bool:
        """Convenience method"""
        return self.result == TradeResult.WIN


@dataclass
class BrokerEvent:
    """
    Generic broker event wrapper.
    All events from any broker get wrapped in this structure.
    """
    event_type: BrokerEventType
    timestamp: datetime
    data: Any  # BrokerTradeClosedEvent, or other event data
    broker_id: str
    
    @staticmethod
    def from_trade_closed(event: BrokerTradeClosedEvent) -> 'BrokerEvent':
        """Factory method to wrap a trade closed event"""
        return BrokerEvent(
            event_type=BrokerEventType.TRADE_CLOSED,
            timestamp=event.exit_time,
            data=event,
            broker_id=event.broker_id
        )
