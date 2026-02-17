"""
MultiTimeframeLimiter - EDGE protection for multi-timeframe operations

Validates exposure limits per symbol:
- Max positions simultaneous
- Max total volume
- Hedge alerts
- Opposite signal blocks (configurable)

Usage:
    limiter = MultiTimeframeLimiter(storage, config)
    is_valid, reason = limiter.validate_new_signal(signal)
    if not is_valid:
        reject_signal(reason)
"""
from typing import Dict, Tuple, List, Any
import logging

from models.signal import Signal
from connectors.mt5_connector import MT5Connector

logger = logging.getLogger(__name__)


class MultiTimeframeLimiter:
    """Validates multi-timeframe exposure limits per symbol"""
    
    def __init__(self, storage, config: Dict):
        """
        Initialize MultiTimeframeLimiter.
        
        Args:
            storage: StorageManager instance (dependency injection)
            config: Full config dict with 'multi_timeframe_limits' section
        """
        self.storage = storage
        self.config = config.get('multi_timeframe_limits', {})
        self.enabled = self.config.get('enabled', True)
        self.max_positions = self.config.get('max_positions_per_symbol', 3)
        self.max_volume = self.config.get('max_total_volume_per_symbol', 5.0)
        self.hedge_threshold = self.config.get('alert_hedge_threshold', 0.2)
        self.allow_opposite = self.config.get('allow_opposite_signals', True)
    
    def validate_new_signal(self, signal: Signal) -> Tuple[bool, str]:
        """
        Validate if new signal respects multi-timeframe limits.
        
        Process:
        1. Check if limiter enabled
        2. Check max positions per symbol
        3. Check max volume per symbol
        4. Check opposite signals (if disabled)
        5. Check hedge risk (alert only, not blocking)
        
        Args:
            signal: Signal instance to validate
        
        Returns:
            Tuple[bool, str]: (is_valid, reason)
            - (True, "OK") if signal allowed
            - (False, "REASON") if signal blocked
        """
        if not self.enabled:
            return True, "Multi-timeframe limits disabled"
        
        symbol = signal.symbol
        
        # Get current open positions for this symbol
        open_positions = self._get_open_positions_by_symbol(symbol)
        
        # 1. Check max positions limit
        if len(open_positions) >= self.max_positions:
            return False, f"MAX_POSITIONS_EXCEEDED: {len(open_positions)}/{self.max_positions} for {symbol}"
        
        # 2. Check max volume limit
        current_volume = sum(self._get_lot_size(p) for p in open_positions)
        new_total_volume = current_volume + signal.volume
        
        if new_total_volume > self.max_volume:
            return False, f"MAX_VOLUME_EXCEEDED: {new_total_volume:.2f}/{self.max_volume} lots for {symbol}"
        
        # 3. Check opposite signals (if not allowed)
        if not self.allow_opposite and open_positions:
            existing_types = {self._get_signal_type(p) for p in open_positions}
            
            if signal.signal_type.value in ['BUY', 'SELL']:
                opposite = 'SELL' if signal.signal_type.value == 'BUY' else 'BUY'
                
                if opposite in existing_types:
                    return False, f"OPPOSITE_SIGNAL_BLOCKED: {symbol} already has {opposite} position"
        
        # 4. Check hedge risk (alert only, NOT blocking)
        if open_positions and self.allow_opposite:
            self._check_hedge_alert(symbol, open_positions, signal)
        
        return True, "OK"
    
    
    def _get_open_positions_by_symbol(self, symbol: str) -> list:
        """
        Get all ACTUALLY OPEN positions for symbol from MT5.
        
        CRITICAL FIX: Don't rely on DB status='EXECUTED' alone.
        Positions may be closed in MT5 but still marked EXECUTED in DB.
        
        Returns only positions that are confirmed open in MT5.
        """
        try:
            # Import connector to check actual MT5 positions
            
            mt5 = MT5Connector()
            if not mt5.connect():
                logger.warning(
                    f"Could not connect to MT5 to verify positions for {symbol}. "
                    "Falling back to DB-only check (may be inaccurate)."
                )
                return self._get_open_positions_from_db_only(symbol)
            
            # Get actual open positions from MT5
            mt5_positions = mt5.get_open_positions()
            
            # Filter by symbol
            open_for_symbol = [
                pos for pos in mt5_positions 
                if pos.get('symbol') == symbol
            ]
            
            logger.info(
                f"[MultiTimeframeLimiter] {symbol}: {len(open_for_symbol)} positions "
                f"actually open in MT5"
            )
            
            return open_for_symbol
            
        except Exception as e:
            logger.error(
                f"Error checking MT5 positions for {symbol}: {e}. "
                "Falling back to DB-only check."
            )
            return self._get_open_positions_from_db_only(symbol)
    
    def _get_open_positions_from_db_only(self, symbol: str) -> list:
        """
        Fallback: Get EXECUTED signals from DB (may include closed positions).
        
        WARNING: This method is INACCURATE if positions were closed in MT5
        but not updated in DB. Use only as fallback.
        """
        all_executed = self.storage.get_signals(status='EXECUTED', limit=1000)
        
        # Filter by symbol and confirmed orders (have order_id/ticket)
        open_positions = [
            sig for sig in all_executed
            if sig.get('symbol') == symbol and sig.get('order_id')
        ]
        
        logger.warning(
            f"[MultiTimeframeLimiter] Using DB-only check for {symbol}: "
            f"{len(open_positions)} EXECUTED signals found (may include closed positions)"
        )
        
        return open_positions
    
    def _get_lot_size(self, position: dict) -> float:
        """Extract lot_size from position metadata, fallback to volume"""
        # Try metadata first (set by executor)
        metadata = position.get('metadata', {})
        lot_size = metadata.get('lot_size')
        
        if lot_size is not None:
            return float(lot_size)
        
        # Fallback to volume field
        return float(position.get('volume', 0))
    
    def _get_signal_type(self, position: dict) -> str:
        """Extract signal_type from position"""
        signal_type = position.get('signal_type')
        
        # Handle both string and SignalType enum
        if hasattr(signal_type, 'value'):
            return signal_type.value
        
        return str(signal_type)
    
    def _check_hedge_alert(self, symbol: str, open_positions: List[Dict[str, Any]], new_signal: Signal) -> None:
        """
        Check for hedge risk and log warning (does NOT block signal).
        
        Hedge detected when net exposure < threshold (e.g. 20%).
        Example: BUY 2.0 + SELL 1.8 = net 0.2/3.8 = 5.3% < 20% → ALERT
        """
        # Calculate current BUY/SELL volumes
        buy_volume = 0.0
        sell_volume = 0.0
        
        for pos in open_positions:
            sig_type = self._get_signal_type(pos)
            lot_size = self._get_lot_size(pos)
            
            if sig_type == 'BUY':
                buy_volume += lot_size
            elif sig_type == 'SELL':
                sell_volume += lot_size
        
        # Add new signal volume
        if new_signal.signal_type.value == 'BUY':
            buy_volume += new_signal.volume
        elif new_signal.signal_type.value == 'SELL':
            sell_volume += new_signal.volume
        
        # Calculate net exposure
        total_volume = buy_volume + sell_volume
        
        if total_volume == 0:
            return
        
        net_exposure = abs(buy_volume - sell_volume) / total_volume
        
        # Alert if net exposure too low (possible hedge)
        if net_exposure < self.hedge_threshold:
            logger.warning(
                f"⚠️  HEDGE ALERT: {symbol} net exposure {net_exposure:.1%} < {self.hedge_threshold:.1%} "
                f"(BUY: {buy_volume:.2f} lots, SELL: {sell_volume:.2f} lots)"
            )
            # NOTE: This is ALERT ONLY, signal still allowed
            # User may intentionally want hedging strategy
