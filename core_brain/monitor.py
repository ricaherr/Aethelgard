"""
Closing Monitor (Feedback Loop)
Monitors executed signals and updates database with real results from broker.
Part of Aethelgard's autonomous learning system.
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class ClosingMonitor:
    """
    Monitors closed positions and updates database with real results.
    
    This component is critical for:
    - Feedback loop: real results feed into Tuner for parameter optimization
    - Win rate calculation: accurate performance metrics
    - Asset-level analysis: which symbols perform best
    - Risk management: track consecutive losses
    
    Features:
    - Periodic checking of executed signals
    - Connector-agnostic design (MT5, NT8, etc.)
    - Automatic PIP and profit calculation
    - Resilient error handling
    """
    
    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        connectors: Optional[Dict[str, Any]] = None,
        interval_seconds: int = 60
    ):
        """
        Initialize ClosingMonitor.
        
        Args:
            storage: StorageManager instance
            connectors: Dict of broker connectors (e.g., {'MT5': mt5_connector})
            interval_seconds: Frequency to check for closed positions (default: 60s)
        """
        self.storage = storage or StorageManager()
        self.connectors = connectors or {}
        self.interval_seconds = interval_seconds
        self.is_running = False
        
        logger.info(
            f"ClosingMonitor initialized. Interval: {interval_seconds}s, "
            f"Connectors: {list(self.connectors.keys())}"
        )
    
    def check_closed_positions(self) -> int:
        """
        Check all executed signals and update those that have closed.
        
        Returns:
            Number of signals updated
        """
        try:
            # Get all executed signals (not yet marked as closed)
            executed_signals = self.storage.get_signals_by_status('EXECUTED')
            
            if not executed_signals:
                logger.debug("No executed signals to monitor")
                return 0
            
            updates_count = 0
            
            # Check each connector for closed positions
            for connector_name, connector in self.connectors.items():
                try:
                    closed_positions = connector.get_closed_positions()
                    
                    # Match closed positions with executed signals
                    for position in closed_positions:
                        signal_id = position.get('signal_id')
                        
                        if not signal_id:
                            # Try to match by ticket number from metadata
                            ticket = position.get('ticket')
                            matching_signal = self._find_signal_by_ticket(
                                executed_signals, 
                                ticket
                            )
                            if matching_signal:
                                signal_id = matching_signal['id']
                        
                        if signal_id:
                            # Update trade result
                            self._update_trade_result(
                                signal_id=signal_id,
                                exit_price=position.get('exit_price'),
                                profit=position.get('profit'),
                                exit_reason=position.get('exit_reason', 'CLOSED'),
                                close_time=position.get('close_time'),
                                symbol=position.get('symbol')
                            )
                            updates_count += 1
                
                except Exception as e:
                    logger.error(f"Error checking {connector_name}: {e}")
            
            if updates_count > 0:
                logger.info(f"Updated {updates_count} closed positions")
            
            return updates_count
        
        except Exception as e:
            logger.error(f"Error in check_closed_positions: {e}")
            return 0
    
    def _find_signal_by_ticket(
        self, 
        signals: List[Dict], 
        ticket: int
    ) -> Optional[Dict]:
        """Find signal matching a broker ticket number"""
        for signal in signals:
            metadata = signal.get('metadata', {})
            if metadata.get('ticket') == ticket:
                return signal
        return None
    
    def _update_trade_result(
        self,
        signal_id: str,
        exit_price: float,
        profit: float,
        exit_reason: str,
        close_time: Optional[datetime] = None,
        symbol: Optional[str] = None
    ) -> None:
        """
        Update database with trade result.
        
        Args:
            signal_id: ID of the signal
            exit_price: Exit price from broker
            profit: Profit/loss in account currency
            exit_reason: Reason for exit (TAKE_PROFIT, STOP_LOSS, MANUAL, etc.)
            close_time: Time position was closed
            symbol: Trading symbol
        """
        try:
            # Get original signal
            signal = self.storage.get_signal_by_id(signal_id)
            
            if not signal:
                logger.warning(f"Signal {signal_id} not found")
                return
            
            # Calculate PIPs
            entry_price = signal.get('price') or signal.get('entry_price')
            if entry_price is None:
                logger.error(f"Signal {signal_id} has no entry price")
                return
            
            symbol = symbol or signal['symbol']
            pips = self._calculate_pips(symbol, entry_price, exit_price)
            
            # Determine if win or loss
            is_win = profit > 0
            
            # Calculate duration
            signal_time = datetime.fromisoformat(signal['timestamp'])
            close_time = close_time or datetime.now()
            duration_minutes = int((close_time - signal_time).total_seconds() / 60)
            
            # Save trade result
            self.storage.save_trade_result({
                'signal_id': signal_id,
                'symbol': symbol,
                'entry_price': entry_price,
                'exit_price': exit_price,
                'profit': profit,
                'exit_reason': exit_reason,
                'close_time': close_time
            })
            
            # Update signal status to CLOSED
            self.storage.update_signal_status(signal_id, 'CLOSED', {
                'exit_price': exit_price,
                'profit': profit,
                'pips': pips,
                'exit_reason': exit_reason
            })
            
            logger.info(
                f"Trade closed: {symbol} | Profit: {profit:.2f} | "
                f"PIPs: {pips:.1f} | Reason: {exit_reason}"
            )
        
        except Exception as e:
            logger.error(f"Error updating trade result: {e}")
    
    def _calculate_pips(
        self, 
        symbol: str, 
        entry_price: float, 
        exit_price: float
    ) -> float:
        """
        Calculate PIPs based on symbol type.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            exit_price: Exit price
        
        Returns:
            PIPs gained/lost
        """
        # Detect instrument type
        if 'JPY' in symbol:
            # JPY pairs: 2 decimal places
            pip_multiplier = 100
        elif 'XAU' in symbol or 'GOLD' in symbol:
            # Gold: 10 = 1000 pips
            pip_multiplier = 100
        else:
            # Standard forex: 4 decimal places
            pip_multiplier = 10000
        
        pips = abs(exit_price - entry_price) * pip_multiplier
        
        # Apply sign (positive for profit, negative for loss)
        if exit_price < entry_price:
            pips = -pips
        
        return round(pips, 2)
    
    async def start(self) -> None:
        """Start monitoring loop (async)"""
        self.is_running = True
        logger.info("ClosingMonitor started")
        
        while self.is_running:
            try:
                self.check_closed_positions()
                await asyncio.sleep(self.interval_seconds)
            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}")
                await asyncio.sleep(self.interval_seconds)
    
    async def stop(self) -> None:
        """Stop monitoring loop"""
        self.is_running = False
        logger.info("ClosingMonitor stopped")
