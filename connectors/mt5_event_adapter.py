"""
Example: MT5 Broker Event Adapter
==================================

Shows how to adapt MT5 trade closure data to the standard BrokerTradeClosedEvent interface.

This is the pattern that every broker connector must follow.
The Listener doesn't care about MT5-specific details; it only sees the standardized event.
"""

from datetime import datetime
from models.broker_event import BrokerTradeClosedEvent, TradeResult, BrokerEvent


def adapt_mt5_trade_closed_to_event(mt5_trade_data: dict) -> BrokerEvent:
    """
    Adapter: Converts MT5 trade data to standard BrokerTradeClosedEvent.
    
    This is an example. In real code, this would live in connectors/mt5_connector.py
    
    Args:
        mt5_trade_data: Raw trade data from MT5 (from DealInfo or OrderSendResult)
    
    Returns:
        BrokerEvent ready for TradeClosureListener
    
    Example MT5 input:
    {
        'ticket': 123456789,
        'symbol': 'EURUSD',
        'open_price': 1.0850,
        'close_price': 1.0840,
        'open_time': datetime(...),
        'close_time': datetime(...),
        'commission': -10.0,
        'profit': 100.0,  # Profit/loss
        'comment': 'SL',  # Stop Loss
    }
    """
    
    # Extract MT5-specific fields
    ticket = str(mt5_trade_data.get('ticket', 'unknown'))
    symbol = mt5_trade_data.get('symbol', 'UNKNOWN')
    entry_price = float(mt5_trade_data.get('open_price', 0))
    exit_price = float(mt5_trade_data.get('close_price', 0))
    entry_time = mt5_trade_data.get('open_time', datetime.now())
    exit_time = mt5_trade_data.get('close_time', datetime.now())
    profit_loss = float(mt5_trade_data.get('profit', 0))
    
    # Calculate pips (distance between entry and exit)
    pip_value = 0.0001 if 'JPY' not in symbol else 0.01
    pips = abs(exit_price - entry_price) / pip_value
    
    # Determine result
    if profit_loss > 0:
        result = TradeResult.WIN
    elif profit_loss < 0:
        result = TradeResult.LOSS
    else:
        result = TradeResult.BREAKEVEN
    
    # Map MT5 exit reason to standard format
    comment = mt5_trade_data.get('comment', '').upper()
    if 'SL' in comment or 'STOP' in comment:
        exit_reason = "stop_loss_hit"
    elif 'TP' in comment or 'PROFIT' in comment:
        exit_reason = "take_profit_hit"
    elif 'CLOSE' in comment:
        exit_reason = "manual_close"
    else:
        exit_reason = "other"
    
    # Create standardized event
    trade_event = BrokerTradeClosedEvent(
        ticket=ticket,
        symbol=symbol,
        entry_price=entry_price,
        exit_price=exit_price,
        entry_time=entry_time,
        exit_time=exit_time,
        pips=pips,
        profit_loss=profit_loss,
        result=result,
        exit_reason=exit_reason,
        broker_id="MT5",
        signal_id=None,  # Could extract from trade comment if tagged
        metadata={
            "commission": mt5_trade_data.get('commission', 0),
            "mt5_comment": comment,
            "mt5_magic": mt5_trade_data.get('magic', 0)
        }
    )
    
    # Wrap in BrokerEvent
    event = BrokerEvent.from_trade_closed(trade_event)
    return event


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    # Simulate MT5 returning a closed trade
    mt5_trade = {
        'ticket': 123456789,
        'symbol': 'EURUSD',
        'open_price': 1.0850,
        'close_price': 1.0840,
        'open_time': datetime(2026, 2, 2, 10, 0, 0),
        'close_time': datetime(2026, 2, 2, 10, 5, 0),
        'profit': -100.0,  # Loss
        'comment': 'SL',   # Stop Loss hit
        'commission': -10.0,
        'magic': 999
    }
    
    # Adapt to standard event
    event = adapt_mt5_trade_closed_to_event(mt5_trade)
    
    # Now the TradeClosureListener can process this
    print(f"Event ready for listener: {event.data.symbol} - {event.data.result.value}")
    # Output: Event ready for listener: EURUSD - loss
