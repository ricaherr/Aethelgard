"""
Position Manager - Dynamic Position Management System
FASE 1: Regime Management + Max Drawdown + Freeze Level Validation

Manages open positions with:
- Emergency close on max drawdown
- SL/TP adjustments based on regime changes
- Time-based exits for stale positions
- Freeze level validation
- Cooldown and daily limits
- Metadata persistence and rollback
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from decimal import Decimal

from models.signal import MarketRegime

logger = logging.getLogger(__name__)


class PositionManager:
    """
    Manages open positions with regime-aware adjustments and risk protection.
    
    Key Features (FASE 1):
    - Emergency close on max drawdown (2x initial risk)
    - SL/TP adjustment on regime change
    - Time-based exits (TREND 72h, RANGE 4h, VOLATILE 2h, CRASH 1h)
    - Freeze level validation (10% safety margin)
    - Cooldown (5 min) and daily limits (10 modifications)
    - Idempotent metadata persistence
    """
    
    def __init__(
        self,
        storage,
        connector,
        regime_classifier,
        config: Dict[str, Any]
    ):
        """
        Initialize PositionManager with injected dependencies.
        
        Args:
            storage: StorageManager instance
            connector: Broker connector (MT5Connector, PaperConnector, etc.)
            regime_classifier: RegimeClassifier instance
            config: Configuration dict from dynamic_params.json['position_management']
        """
        self.storage = storage
        self.connector = connector
        self.regime_classifier = regime_classifier
        self.config = config
        
        # Extract configuration
        self.max_drawdown_multiplier = config.get('max_drawdown_multiplier', 2.0)
        self.cooldown_seconds = config.get('cooldown_seconds', 300)  # 5 min
        self.max_modifications_per_day = config.get('max_modifications_per_day', 10)
        self.regime_adjustments = config.get('regime_adjustments', {})
        self.stale_thresholds = config.get('stale_thresholds_hours', {})
        
        logger.info(
            f"PositionManager initialized - "
            f"Max Drawdown: {self.max_drawdown_multiplier}x, "
            f"Cooldown: {self.cooldown_seconds}s, "
            f"Daily Limit: {self.max_modifications_per_day}"
        )
    
    def monitor_positions(self) -> Dict[str, Any]:
        """
        Main monitoring loop - checks all open positions and applies necessary adjustments.
        
        Returns:
            dict: Summary of actions taken
        """
        logger.debug("Starting position monitoring cycle")
        
        # Get all open positions from connector
        open_positions = self.connector.get_open_positions()
        
        if not open_positions:
            logger.debug("No open positions to monitor")
            return {"total_positions": 0, "actions": []}
        
        actions = []
        
        for position in open_positions:
            ticket = position.get('ticket')
            symbol = position.get('symbol')
            
            try:
                # 1. Check for emergency close (max drawdown exceeded)
                if self._exceeds_max_drawdown(position):
                    logger.warning(
                        f"Position {ticket} ({symbol}) exceeds max drawdown - "
                        f"Emergency close triggered"
                    )
                    self._emergency_close(position, "MAX_DRAWDOWN")
                    actions.append({
                        'ticket': ticket,
                        'action': 'EMERGENCY_CLOSE',
                        'reason': 'MAX_DRAWDOWN'
                    })
                    continue
                
                # 2. Check for stale position (time-based exit)
                if self._is_stale_position(position):
                    logger.info(
                        f"Position {ticket} ({symbol}) is stale - Closing"
                    )
                    self._close_stale_position(position)
                    actions.append({
                        'ticket': ticket,
                        'action': 'TIME_EXIT',
                        'reason': 'STALE_POSITION'
                    })
                    continue
                
                # 3. Check for regime change requiring adjustment
                if self._regime_changed(position):
                    logger.info(
                        f"Position {ticket} ({symbol}) regime changed - "
                        f"Adjusting SL/TP"
                    )
                    if self._adjust_for_regime_change(position):
                        actions.append({
                            'ticket': ticket,
                            'action': 'REGIME_ADJUSTMENT',
                            'reason': 'REGIME_CHANGE'
                        })
                
            except Exception as e:
                logger.error(
                    f"Error monitoring position {ticket}: {e}",
                    exc_info=True
                )
                continue
        
        summary = {
            'total_positions': len(open_positions),
            'actions': actions,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(
            f"Position monitoring completed - "
            f"{len(open_positions)} positions, "
            f"{len(actions)} actions taken"
        )
        
        return summary
    
    def _exceeds_max_drawdown(self, position: Dict) -> bool:
        """
        Check if position exceeds maximum allowed drawdown.
        
        Max drawdown = initial_risk_usd * max_drawdown_multiplier (default 2.0)
        
        Args:
            position: Position dict from connector
            
        Returns:
            bool: True if drawdown exceeded
        """
        ticket = position.get('ticket')
        
        # Get position metadata from database
        metadata = self.storage.get_position_metadata(ticket)
        if not metadata:
            logger.warning(
                f"No metadata found for position {ticket} - "
                f"Cannot validate max drawdown"
            )
            return False
        
        initial_risk_usd = metadata.get('initial_risk_usd', 0)
        if initial_risk_usd <= 0:
            logger.warning(
                f"Invalid initial_risk_usd for position {ticket}: {initial_risk_usd}"
            )
            return False
        
        # Calculate current profit/loss
        current_profit = position.get('profit', 0)
        
        # Check if loss exceeds threshold
        max_allowed_loss = -abs(initial_risk_usd * self.max_drawdown_multiplier)
        
        if current_profit <= max_allowed_loss:
            logger.warning(
                f"Position {ticket} drawdown exceeded - "
                f"Current: ${current_profit:.2f}, "
                f"Max allowed: ${max_allowed_loss:.2f}"
            )
            return True
        
        return False
    
    def _is_stale_position(self, position: Dict) -> bool:
        """
        Check if position has been open too long based on regime.
        
        Thresholds:
        - TREND: 72 hours
        - RANGE: 4 hours
        - VOLATILE: 2 hours
        - CRASH: 1 hour
        - NEUTRAL: 24 hours (default)
        
        Args:
            position: Position dict from connector
            
        Returns:
            bool: True if position is stale
        """
        ticket = position.get('ticket')
        symbol = position.get('symbol')
        
        # Get position metadata
        metadata = self.storage.get_position_metadata(ticket)
        if not metadata:
            logger.warning(
                f"No metadata for position {ticket} - Cannot check staleness"
            )
            return False
        
        entry_time_str = metadata.get('entry_time')
        if not entry_time_str:
            logger.warning(
                f"No entry_time in metadata for position {ticket}"
            )
            return False
        
        # Parse entry time
        try:
            entry_time = datetime.fromisoformat(entry_time_str)
        except (ValueError, TypeError) as e:
            logger.error(
                f"Invalid entry_time format for position {ticket}: {entry_time_str} - {e}"
            )
            return False
        
        # Get current regime for symbol
        current_regime = self.regime_classifier.classify_regime(symbol)
        
        # Get threshold for this regime
        threshold_hours = self.stale_thresholds.get(
            current_regime.value,
            self.stale_thresholds.get('NEUTRAL', 24)
        )
        
        # Check if position is stale
        age = datetime.now() - entry_time
        max_age = timedelta(hours=threshold_hours)
        
        if age > max_age:
            logger.info(
                f"Position {ticket} ({symbol}) is stale - "
                f"Age: {age}, Max: {max_age}, Regime: {current_regime.value}"
            )
            return True
        
        return False
    
    def _regime_changed(self, position: Dict) -> bool:
        """
        Check if market regime has changed since position entry.
        
        Args:
            position: Position dict from connector
            
        Returns:
            bool: True if regime changed
        """
        ticket = position.get('ticket')
        symbol = position.get('symbol')
        
        # Get position metadata
        metadata = self.storage.get_position_metadata(ticket)
        if not metadata:
            logger.debug(
                f"No metadata for position {ticket} - Assuming no regime change"
            )
            return False
        
        entry_regime = metadata.get('entry_regime')
        if not entry_regime:
            logger.debug(
                f"No entry_regime in metadata for position {ticket}"
            )
            return False
        
        # Get current regime
        current_regime = self.regime_classifier.classify_regime(symbol)
        
        # Check if changed
        if current_regime.value != entry_regime:
            logger.info(
                f"Regime changed for position {ticket} ({symbol}) - "
                f"{entry_regime} → {current_regime.value}"
            )
            return True
        
        return False
    
    def _adjust_for_regime_change(self, position: Dict) -> bool:
        """
        Adjust SL/TP based on regime change.
        
        Args:
            position: Position dict from connector
            
        Returns:
            bool: True if adjustment successful
        """
        ticket = position.get('ticket')
        symbol = position.get('symbol')
        
        # Get current regime
        current_regime = self.regime_classifier.classify_regime(symbol)
        
        # Get regime adjustment configuration
        regime_config = self.regime_adjustments.get(current_regime.value, {})
        if not regime_config:
            logger.warning(
                f"No configuration for regime {current_regime.value} - Skipping adjustment"
            )
            return False
        
        # Get position metadata
        metadata = self.storage.get_position_metadata(ticket)
        if not metadata:
            logger.warning(
                f"No metadata for position {ticket} - Cannot adjust"
            )
            return False
        
        # Check if can modify (cooldown + daily limits)
        if not self._can_modify(metadata):
            logger.info(
                f"Cannot modify position {ticket} - Cooldown or daily limit reached"
            )
            return False
        
        # Get current ATR for symbol
        current_atr = self.get_current_atr(symbol)
        if not current_atr or current_atr <= 0:
            logger.warning(
                f"Invalid ATR for {symbol}: {current_atr} - Cannot adjust"
            )
            return False
        
        # Calculate new SL/TP based on regime
        entry_price = metadata.get('entry_price', 0)
        direction = metadata.get('direction', '')
        
        sl_atr_multiplier = regime_config.get('sl_atr_multiplier', 1.5)
        tp_atr_multiplier = regime_config.get('tp_atr_multiplier', 2.0)
        
        sl_distance = current_atr * sl_atr_multiplier
        tp_distance = current_atr * tp_atr_multiplier
        
        if direction == 'BUY':
            new_sl = entry_price - sl_distance
            new_tp = entry_price + tp_distance
        elif direction == 'SELL':
            new_sl = entry_price + sl_distance
            new_tp = entry_price - tp_distance
        else:
            logger.error(
                f"Invalid direction for position {ticket}: {direction}"
            )
            return False
        
        # Validate and modify position
        return self._modify_with_validation(
            ticket=ticket,
            symbol=symbol,
            new_sl=new_sl,
            new_tp=new_tp,
            reason=f"REGIME_CHANGE_TO_{current_regime.value}"
        )
    
    def _emergency_close(self, position: Dict, reason: str) -> bool:
        """
        Emergency close position (max drawdown exceeded).
        
        Args:
            position: Position dict from connector
            reason: Reason for emergency close
            
        Returns:
            bool: True if closed successfully
        """
        ticket = position.get('ticket')
        symbol = position.get('symbol')
        
        try:
            # Close position via connector
            result = self.connector.close_position(ticket, reason)
            
            if result.get('success'):
                logger.warning(
                    f"EMERGENCY CLOSE: Position {ticket} ({symbol}) - Reason: {reason}"
                )
                
                # Update metadata
                self.storage.update_position_metadata(ticket, {
                    'emergency_close': True,
                    'emergency_reason': reason,
                    'closed_at': datetime.now().isoformat()
                })
                
                return True
            else:
                logger.error(
                    f"Failed to emergency close position {ticket}: {result.get('error')}"
                )
                return False
                
        except Exception as e:
            logger.error(
                f"Exception during emergency close of position {ticket}: {e}",
                exc_info=True
            )
            return False
    
    def _close_stale_position(self, position: Dict) -> bool:
        """
        Close stale position (time-based exit).
        
        Args:
            position: Position dict from connector
            
        Returns:
            bool: True if closed successfully
        """
        ticket = position.get('ticket')
        symbol = position.get('symbol')
        
        try:
            # Close position via connector
            result = self.connector.close_position(ticket, "STALE_POSITION")
            
            if result.get('success'):
                logger.info(
                    f"Stale position closed: {ticket} ({symbol})"
                )
                
                # Update metadata
                self.storage.update_position_metadata(ticket, {
                    'stale_exit': True,
                    'closed_at': datetime.now().isoformat()
                })
                
                return True
            else:
                logger.error(
                    f"Failed to close stale position {ticket}: {result.get('error')}"
                )
                return False
                
        except Exception as e:
            logger.error(
                f"Exception closing stale position {ticket}: {e}",
                exc_info=True
            )
            return False
    
    def _modify_with_validation(
        self,
        ticket: int,
        symbol: str,
        new_sl: float,
        new_tp: Optional[float] = None,
        reason: str = ""
    ) -> bool:
        """
        Modify position with freeze level validation and rollback on failure.
        
        Args:
            ticket: Position ticket
            symbol: Symbol name
            new_sl: New stop loss price
            new_tp: New take profit price (optional)
            reason: Reason for modification
            
        Returns:
            bool: True if modification successful
        """
        # 1. Validate freeze level
        if not self._validate_freeze_level(symbol, new_sl, new_tp):
            logger.warning(
                f"Freeze level validation failed for position {ticket} ({symbol})"
            )
            return False
        
        # 2. Persist metadata BEFORE modification (idempotence)
        old_metadata = self.storage.get_position_metadata(ticket)
        
        new_metadata = {
            'last_modification_timestamp': datetime.now().isoformat(),
            'sl_modifications_count': old_metadata.get('sl_modifications_count', 0) + 1,
            'modification_reason': reason,
            'new_sl': new_sl,
            'new_tp': new_tp
        }
        
        # Update metadata
        if not self.storage.update_position_metadata(ticket, new_metadata):
            logger.error(
                f"Failed to update metadata for position {ticket} - Aborting modification"
            )
            return False
        
        # 3. Execute modification via connector
        try:
            result = self.connector.modify_position(ticket, new_sl, new_tp)
            
            if result.get('success'):
                logger.info(
                    f"Position {ticket} ({symbol}) modified - SL: {new_sl}, TP: {new_tp}, "
                    f"Reason: {reason}"
                )
                return True
            else:
                # Modification failed - rollback metadata
                logger.error(
                    f"Failed to modify position {ticket}: {result.get('error')} - "
                    f"Rolling back metadata"
                )
                self.storage.rollback_position_modification(ticket)
                return False
                
        except Exception as e:
            # Exception during modification - rollback metadata
            logger.error(
                f"Exception modifying position {ticket}: {e} - Rolling back metadata",
                exc_info=True
            )
            self.storage.rollback_position_modification(ticket)
            return False
    
    def _validate_freeze_level(
        self,
        symbol: str,
        new_sl: float,
        new_tp: Optional[float] = None
    ) -> bool:
        """
        Validate that new SL/TP respect broker's freeze level (minimum distance).
        
        Applies 10% safety margin to avoid rejections.
        
        Args:
            symbol: Symbol name
            new_sl: New stop loss price
            new_tp: New take profit price (optional)
            
        Returns:
            bool: True if valid
        """
        # Get symbol info from connector
        symbol_info = self.connector.get_symbol_info(symbol)
        if not symbol_info:
            logger.error(
                f"Could not get symbol info for {symbol} - Cannot validate freeze level"
            )
            return False
        
        # Get freeze level (minimum distance in points)
        freeze_level = symbol_info.get('trade_stops_level', 0)
        point = symbol_info.get('point', 0.00001)
        
        if freeze_level <= 0:
            logger.debug(
                f"No freeze level for {symbol} - Validation passed"
            )
            return True
        
        # Apply 10% safety margin
        safe_freeze_level = freeze_level * 1.1
        
        # Get current price
        current_price = self.connector.get_current_price(symbol)
        if not current_price or current_price <= 0:
            logger.error(
                f"Could not get current price for {symbol}"
            )
            return False
        
        # Validate SL distance
        if new_sl:
            sl_distance_points = abs(current_price - new_sl) / point
            
            if sl_distance_points < safe_freeze_level:
                logger.warning(
                    f"SL too close to price for {symbol} - "
                    f"Distance: {sl_distance_points:.1f} points, "
                    f"Minimum: {safe_freeze_level:.1f} points (10% margin)"
                )
                return False
        
        # Validate TP distance
        if new_tp:
            tp_distance_points = abs(current_price - new_tp) / point
            
            if tp_distance_points < safe_freeze_level:
                logger.warning(
                    f"TP too close to price for {symbol} - "
                    f"Distance: {tp_distance_points:.1f} points, "
                    f"Minimum: {safe_freeze_level:.1f} points (10% margin)"
                )
                return False
        
        logger.debug(
            f"Freeze level validation passed for {symbol} - "
            f"SL distance: {sl_distance_points:.1f} points, "
            f"Minimum: {safe_freeze_level:.1f} points"
        )
        
        return True
    
    def _can_modify(self, metadata: Dict) -> bool:
        """
        Check if position can be modified (cooldown + daily limits).
        
        Args:
            metadata: Position metadata from DB
            
        Returns:
            bool: True if can modify
        """
        # Check cooldown
        last_mod_str = metadata.get('last_modification_timestamp')
        if last_mod_str:
            try:
                last_mod = datetime.fromisoformat(last_mod_str)
                time_since_last = (datetime.now() - last_mod).total_seconds()
                
                if time_since_last < self.cooldown_seconds:
                    logger.debug(
                        f"Cooldown active - {time_since_last:.1f}s since last modification, "
                        f"minimum: {self.cooldown_seconds}s"
                    )
                    return False
            except (ValueError, TypeError) as e:
                logger.warning(
                    f"Invalid last_modification_timestamp: {last_mod_str} - {e}"
                )
        
        # Check daily limit
        modifications_count = metadata.get('sl_modifications_count', 0)
        if modifications_count >= self.max_modifications_per_day:
            logger.warning(
                f"Daily modification limit reached - "
                f"{modifications_count}/{self.max_modifications_per_day}"
            )
            return False
        
        return True
    
    def get_current_atr(self, symbol: str) -> Optional[float]:
        """
        Get current ATR for symbol.
        
        Args:
            symbol: Symbol name
            
        Returns:
            float: ATR value or None if not available
        """
        # Try to get ATR from regime classifier
        try:
            regime_data = self.regime_classifier.get_regime_data(symbol)
            if regime_data:
                atr = regime_data.get('atr')
                if atr and atr > 0:
                    return float(atr)
        except Exception as e:
            logger.warning(
                f"Could not get ATR from regime classifier for {symbol}: {e}"
            )
        
        # Fallback: Calculate ATR from connector
        # This would require implementing ATR calculation from OHLC data
        # For now, return None and log warning
        logger.warning(
            f"ATR not available for {symbol} - Cannot proceed with adjustment"
        )
        return None
