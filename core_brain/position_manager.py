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
        
        # Track orphan positions (without metadata) to avoid log spam
        self._synced_orphans = set()  # Set of ticket numbers already synced
        
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
            return {"monitored": 0, "actions": []}
        
        actions = []
        
        for position in open_positions:
            ticket = position.get('ticket')
            symbol = position.get('symbol')
            
            try:
                # 0. Sync metadata for orphan positions (opened outside Aethelgard)
                self._sync_orphan_position(position)
                
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
                
                # 3. Check for breakeven opportunity (FASE 3)
                metadata = self.storage.get_position_metadata(ticket)
                if metadata:
                    should_move, reason = self._should_move_to_breakeven(position, metadata)
                    logger.debug(
                        f"Breakeven check for {ticket}: should_move={should_move}, reason={reason}"
                    )
                    if should_move:
                        breakeven_price = self._calculate_breakeven_real(position, metadata)
                        if breakeven_price:
                            # Keep current TP, only modify SL to breakeven
                            current_tp = position.get('tp', 0)
                            
                            logger.info(
                                f"Position {ticket} ({symbol}) moving SL to breakeven - "
                                f"New SL: {breakeven_price}"
                            )
                            
                            # Modify position directly via connector with informative comment
                            result = self.connector.modify_position(ticket, breakeven_price, current_tp, reason="BREAKEVEN")
                            if result and result.get('success', False):
                                actions.append({
                                    'ticket': ticket,
                                    'action': 'BREAKEVEN_REAL',
                                    'new_sl': breakeven_price,
                                    'reason': 'BREAKEVEN_PROTECTION'
                                })
                            else:
                                logger.warning(
                                    f"Failed to move position {ticket} to breakeven: "
                                    f"{result.get('error') if result else 'No result'}"
                                )
                else:
                    logger.debug(f"No metadata found for position {ticket} - Skipping breakeven check")
                
                # 4. Check for trailing stop opportunity (FASE 4)
                if metadata:
                    should_apply, reason = self._should_apply_trailing_stop(position, metadata)
                    logger.debug(
                        f"Trailing stop check for {ticket}: should_apply={should_apply}, reason={reason}"
                    )
                    if should_apply:
                        trailing_sl = self._calculate_trailing_stop_atr(position, metadata)
                        if trailing_sl:
                            # Keep current TP, only modify SL to trailing
                            current_tp = position.get('tp', 0)
                            
                            logger.info(
                                f"Position {ticket} ({symbol}) applying trailing stop - "
                                f"New SL: {trailing_sl}"
                            )
                            
                            # Modify position directly via connector with informative comment
                            result = self.connector.modify_position(ticket, trailing_sl, current_tp, reason="TRAILING_STOP")
                            if result and result.get('success', False):
                                actions.append({
                                    'ticket': ticket,
                                    'action': 'TRAILING_STOP_ATR',
                                    'new_sl': trailing_sl,
                                    'reason': 'TRAILING_PROTECTION'
                                })
                            else:
                                logger.warning(
                                    f"Failed to apply trailing stop to position {ticket}: "
                                    f"{result.get('error') if result else 'No result'}"
                                )
                
                # 5. Check for regime change requiring adjustment
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
            'monitored': len(open_positions),
            'actions': actions,
            'timestamp': datetime.now().isoformat()
        }
        
        logger.info(
            f"Position monitoring completed - "
            f"{len(open_positions)} positions, "
            f"{len(actions)} actions taken"
        )
        
        return summary
    
    def _sync_orphan_position(self, position: Dict[str, Any]) -> None:
        """
        Auto-sync metadata for positions without it (orphan positions).
        
        Orphan positions are those opened:
        - Before metadata system was implemented
        - Directly from MT5/broker (manual trades)
        - From other systems/EAs
        
        Creates minimal metadata to enable monitoring. Initial risk is estimated
        based on current SL-Entry distance.
        
        Args:
            position: Position dict from connector
        """
        ticket = position.get('ticket')
        
        # Skip if already has metadata
        if self.storage.get_position_metadata(ticket):
            return
        
        # Skip if already synced this session (avoid repeated work)
        if ticket in self._synced_orphans:
            return
        
        # Log once per position
        logger.info(
            f"Syncing orphan position {ticket} ({position.get('symbol')}) - "
            f"Creating metadata from broker data"
        )
        
        # Extract position data
        symbol = position.get('symbol')
        entry_price = position.get('price', position.get('price_open', 0))  # Entry price
        current_sl = position.get('sl', 0)
        current_tp = position.get('tp', 0)
        volume = position.get('volume', 0)
        open_time = position.get('time')
        position_type = position.get('type')
        
        # Estimate initial risk (distance from entry to SL)
        initial_risk_usd = 0.0
        if current_sl and current_sl > 0 and entry_price > 0 and volume > 0:
            # Determine point size based on instrument
            if 'JPY' in symbol:
                point = 0.001  # Japanese Yen pairs (3 decimal places)
            elif any(metal in symbol for metal in ['XAU', 'XAG', 'GOLD', 'SILVER']):
                point = 0.01  # Metals (2 decimal places)
            else:
                point = 0.00001  # Standard forex (5 decimal places)
            
            # Calculate risk in points
            sl_distance = abs(entry_price - current_sl)
            sl_distance_points = sl_distance / point
            
            # Estimate USD risk per lot (simplified)
            # Standard forex: ~$10 per pip per standard lot
            # This is a rough estimate for monitoring purposes
            # For accurate calculation, we'd need account currency, conversion rates, etc.
            usd_per_pip = 10.0  # Approximate for major pairs
            initial_risk_usd = sl_distance * volume * usd_per_pip
            
            logger.debug(
                f"Orphan position {ticket} risk calculation: "
                f"SL distance={sl_distance:.5f}, volume={volume}, "
                f"estimated_risk=${initial_risk_usd:.2f}"
            )
        else:
            logger.debug(
                f"Orphan position {ticket} has no SL or invalid data - "
                f"initial_risk_usd will be 0 (sl={current_sl}, entry={entry_price}, vol={volume})"
            )
        
        # Determine direction from MT5 position type
        # MT5 constants: POSITION_TYPE_BUY=0, POSITION_TYPE_SELL=1
        direction = 'BUY' if position_type == 0 else 'SELL' if position_type == 1 else 'UNKNOWN'
        
        # Format entry time
        if open_time:
            if isinstance(open_time, (int, float)):
                entry_time_str = datetime.fromtimestamp(open_time).isoformat()
            else:
                entry_time_str = open_time
        else:
            entry_time_str = datetime.now().isoformat()
        
        # Get current regime (fallback to NEUTRAL if unavailable)
        current_regime = self._get_current_regime_with_fallback(symbol)
        regime_str = current_regime.value if hasattr(current_regime, 'value') else 'NEUTRAL'
        
        # Create basic metadata
        metadata = {
            'ticket': ticket,
            'symbol': symbol,
            'entry_price': entry_price,
            'entry_time': entry_time_str,
            'direction': direction,
            'sl': current_sl,
            'tp': current_tp,
            'volume': volume,
            'initial_risk_usd': initial_risk_usd,
            'entry_regime': regime_str,
            'timeframe': position.get('timeframe', 'UNKNOWN'),
            'strategy': 'ORPHAN_SYNC',  # Mark as auto-synced
        }
        
        # Save to database
        success = self.storage.update_position_metadata(ticket, metadata)
        
        if success:
            # Mark as synced to avoid repeating this process
            self._synced_orphans.add(ticket)
            logger.info(
                f"Orphan position {ticket} synced successfully - "
                f"Estimated risk: ${initial_risk_usd:.2f}"
            )
        else:
            logger.error(
                f"Failed to sync orphan position {ticket}"
            )
    
    def _get_current_regime_with_fallback(self, symbol: str) -> 'MarketRegime':
        """
        Get current market regime for symbol with fallback to NEUTRAL.
        
        RegimeClassifier may not have enough data or may fail to classify
        when scanner is disabled. This method provides safe fallback.
        
        Args:
            symbol: Symbol to classify
            
        Returns:
            MarketRegime: Classified regime or NEUTRAL if classification fails
        """
        from models.signal import MarketRegime
        
        try:
            # RegimeClassifier.classify() returns MarketRegime directly
            # without needing OHLC data if it has historical data loaded
            regime = self.regime_classifier.classify()
            
            # Map "NORMAL" value (no mapping needed, return as-is)
            if hasattr(regime, 'value') and regime.value == 'NORMAL':
                return MarketRegime.NORMAL
            
            return regime
        except (AttributeError, Exception) as e:
            logger.debug(
                f"Could not classify regime for {symbol}: {e}. "
                f"Defaulting to NORMAL"
            )
            return MarketRegime.NORMAL
    
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
            # Log only once per position to avoid spam
            if ticket not in self._synced_orphans:
                logger.debug(
                    f"No metadata found for position {ticket} - "
                    f"Cannot validate max drawdown (will auto-sync)"
                )
            return False
        
        initial_risk_usd = metadata.get('initial_risk_usd', 0)
        if initial_risk_usd <= 0:
            # DEBUG: Position without SL or orphan without risk calculation
            # This is expected for manual positions or positions without SL
            logger.debug(
                f"Position {ticket} has no initial_risk_usd (value: {initial_risk_usd}) - "
                f"Cannot validate max drawdown. This is normal for positions without SL."
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
            # Log only once per position to avoid spam
            if ticket not in self._synced_orphans:
                logger.debug(
                    f"No metadata for position {ticket} - Cannot check staleness (will auto-sync)"
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
        
        # Get current regime for symbol (with fallback to NEUTRAL)
        current_regime = self._get_current_regime_with_fallback(symbol)
        
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
        
        # Get current regime (with fallback to NEUTRAL)
        current_regime = self._get_current_regime_with_fallback(symbol)
        
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
        
        # Get current regime (with fallback to NEUTRAL)
        current_regime = self._get_current_regime_with_fallback(symbol)
        
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
        
        # FALLBACK: Get direction from MT5 position if not in metadata
        # (for manual positions or positions opened before direction tracking)
        if not direction:
            type_value = position.get('type')
            if type_value is not None:
                # Convert MT5 position type to string direction
                # MT5 constants: POSITION_TYPE_BUY=0, POSITION_TYPE_SELL=1
                direction = 'BUY' if type_value == 0 else 'SELL' if type_value == 1 else ''
                if direction:
                    logger.info(
                        f"Direction missing from metadata for {ticket}, "
                        f"using MT5 type {type_value} → {direction}"
                    )
        
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
                f"Invalid direction for position {ticket}: '{direction}' "
                f"(metadata: {metadata.get('direction')}, MT5 type: {position.get('type')})"
            )
            return False
        
        # Validate and modify position
        # MT5 comment limit: 31 chars total
        regime_short = current_regime.value[:3].upper()  # NORMAL → NOR, TREND → TRE
        return self._modify_with_validation(
            ticket=ticket,
            symbol=symbol,
            new_sl=new_sl,
            new_tp=new_tp,
            reason=f"RGM_{regime_short}"
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
        
        # 3. Execute modification via connector with reason in comment
        try:
            # Get old SL/TP for logging
            old_sl = old_metadata.get('sl') if old_metadata else None
            old_tp = old_metadata.get('tp') if old_metadata else None
            
            result = self.connector.modify_position(ticket, new_sl, new_tp, reason=reason)
            
            if result.get('success'):
                logger.info(
                    f"Position {ticket} ({symbol}) modified - SL: {new_sl}, TP: {new_tp}, "
                    f"Reason: {reason}"
                )
                
                # Log successful modification to history
                self.storage.log_position_event(
                    ticket=ticket,
                    symbol=symbol,
                    event_type=self._get_event_type_from_reason(reason),
                    old_sl=old_sl,
                    new_sl=new_sl,
                    old_tp=old_tp,
                    new_tp=new_tp,
                    reason=reason,
                    success=True
                )
                
                return True
            else:
                # Modification failed - rollback metadata
                error_msg = result.get('error', 'Unknown')
                
                # Log failed modification to history
                self.storage.log_position_event(
                    ticket=ticket,
                    symbol=symbol,
                    event_type='MODIFICATION_FAILED',
                    old_sl=old_sl,
                    new_sl=new_sl,
                    old_tp=old_tp,
                    new_tp=new_tp,
                    reason=reason,
                    success=False,
                    error_message=error_msg
                )
                
                # Expected broker responses (No changes / Invalid stops) - log as DEBUG
                if error_msg in ['No changes', 'Invalid stops']:
                    logger.debug(
                        f"MT5 rejected modification for {ticket}: {error_msg} - "
                        f"Rolling back metadata"
                    )
                else:
                    logger.error(
                        f"Failed to modify position {ticket}: {error_msg} - "
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
            
            # Log exception to history
            self.storage.log_position_event(
                ticket=ticket,
                symbol=symbol,
                event_type='MODIFICATION_FAILED',
                old_sl=old_metadata.get('sl') if old_metadata else None,
                new_sl=new_sl,
                old_tp=old_metadata.get('tp') if old_metadata else None,
                new_tp=new_tp,
                reason=reason,
                success=False,
                error_message=str(e)
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
        freeze_level = getattr(symbol_info, 'trade_stops_level', 0)
        point = getattr(symbol_info, 'point', 0.00001)
        
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
    
    def _get_event_type_from_reason(self, reason: str) -> str:
        """
        Map modification reason to position_history event_type.
        
        Args:
            reason: Modification reason string
            
        Returns:
            Event type string for position_history table
        """
        reason_upper = reason.upper()
        
        # Map common reasons to event types
        if 'BREAKEVEN' in reason_upper:
            return 'BREAKEVEN'
        elif 'TRAIL' in reason_upper:
            return 'TRAILING_STOP'
        elif any(regime in reason_upper for regime in ['RGM_', 'REGIME']):
            return 'REGIME_CHANGE'
        elif 'SYNC' in reason_upper or 'RECONCIL' in reason_upper:
            return 'SYNC'
        elif 'DRAWDOWN' in reason_upper:
            return 'MAX_DRAWDOWN'
        elif 'TP' in reason_upper and 'SL' not in reason_upper:
            return 'TP_MODIFIED'
        elif 'SL' in reason_upper and 'TP' not in reason_upper:
            return 'SL_MODIFIED'
        else:
            # Default: generic modification
            return 'SL_TP_MODIFIED'
    
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
        # Try to get ATR from regime classifier (if scanner is running)
        try:
            # RegimeClassifier doesn't have get_regime_data() - use get_metrics() instead
            if hasattr(self.regime_classifier, 'get_metrics'):
                metrics = self.regime_classifier.get_metrics()
                atr = metrics.get('atr')
                if atr and atr > 0:
                    return float(atr)
        except Exception as e:
            logger.debug(
                f"Could not get ATR from regime classifier for {symbol}: {e}"
            )
        
        # Fallback: Estimate ATR from MT5 symbol info (use typical ATR = 0.1% of price)
        try:
            symbol_info = self.connector.get_symbol_info(symbol)
            if symbol_info:
                # Use current price to estimate conservative ATR
                price = getattr(symbol_info, 'ask', 0)
                if price > 0:
                    # Estimate ATR as 0.1% of current price (conservative for major pairs)
                    estimated_atr = price * 0.001
                    logger.debug(
                        f"Using estimated ATR for {symbol}: {estimated_atr:.5f} "
                        f"(0.1% of price {price:.5f})"
                    )
                    return estimated_atr
        except Exception as e:
            logger.warning(f"Could not estimate ATR for {symbol}: {e}")
        
        # Last resort: return None
        logger.warning(
            f"ATR not available for {symbol} - Trailing stops disabled"
        )
        return None
    
    def _calculate_breakeven_real(
        self,
        position: Dict,
        metadata: Dict
    ) -> Optional[float]:
        """
        Calculate TRUE breakeven price including all broker costs.
        
        FASE 3: Breakeven Real Formula
        ================================
        breakeven_real = entry_price + (total_costs / position_value)
        
        Where total_costs includes:
        - Commission: Round-trip commission (open + close)
        - Swap: Accumulated overnight financing costs
        - Spread: Bid-Ask spread cost at entry
        
        Args:
            position: Position dict from connector
            metadata: Position metadata from database
            
        Returns:
            float: Breakeven price or None if calculation fails
        """
        try:
            entry_price = float(metadata.get('entry_price', 0))
            volume = float(position.get('volume', 0))
            symbol = position.get('symbol')
            
            if entry_price <= 0 or volume <= 0:
                # This indicates corrupted metadata - force re-sync
                ticket = position.get('ticket')
                logger.warning(
                    f"Position {ticket} has corrupted metadata - "
                    f"entry_price: {entry_price}, volume: {volume}. "
                    f"Deleting and forcing re-sync..."
                )
                # Delete corrupted metadata from database
                try:
                    conn = self.storage._get_conn()
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM position_metadata WHERE ticket = ?", (ticket,))
                    conn.commit()
                    self.storage._close_conn(conn)
                    logger.info(f"Deleted corrupted metadata for position {ticket}")
                except Exception as e:
                    logger.error(f"Failed to delete corrupted metadata for {ticket}: {e}")
                
                # Remove from synced orphans to force re-sync
                if ticket in self._synced_orphans:
                    self._synced_orphans.remove(ticket)
                
                # Trigger re-sync in next cycle
                return None
            
            # Get breakeven config
            breakeven_config = self.config.get('breakeven', {})
            if not breakeven_config.get('enabled', False):
                return None
            
            # 1. Commission cost (round-trip)
            commission_total = 0.0
            if breakeven_config.get('include_commission', True):
                commission_total = abs(float(metadata.get('commission_total', 0)))
            
            # 2. Swap cost (accumulated)
            swap_cost = 0.0
            if breakeven_config.get('include_swap', True):
                # Swap can be positive (credit) or negative (debit)
                # If negative, it's a cost we must recover
                swap = float(position.get('swap', 0))
                if swap < 0:
                    swap_cost = abs(swap)
            
            # 3. Spread cost at entry
            spread_cost = 0.0
            if breakeven_config.get('include_spread', True):
                symbol_info = self.connector.get_symbol_info(symbol)
                if symbol_info:
                    ask = float(getattr(symbol_info, 'ask', 0))
                    bid = float(getattr(symbol_info, 'bid', 0))
                    point = float(getattr(symbol_info, 'point', 0.00001))
                    
                    if ask > 0 and bid > 0:
                        spread_points = (ask - bid) / point
                        # Convert spread to USD cost
                        # For Forex: pip_value = (volume * contract_size * pip_size)
                        # Simplified: volume * 10 * point (for standard lots)
                        spread_cost = spread_points * volume * point * 100000
            
            # Total cost to recover
            total_cost = commission_total + swap_cost + spread_cost
            
            if total_cost <= 0:
                # No costs to recover = entry price is breakeven
                return entry_price
            
            # Calculate breakeven in pips
            # For Forex pairs: 1 pip = $10 per lot (standard)
            # For volume 0.10 lots: 1 pip = $1
            # Cost in pips = total_cost / (volume * pip_value)
            pip_value = volume * 10  # $10 per pip per lot
            if pip_value <= 0:
                logger.warning(f"Invalid pip value calculation: {pip_value}")
                return None
            
            cost_in_pips = total_cost / pip_value
            
            # Get pip size (0.0001 for EURUSD, 0.01 for USDJPY)
            pip_size = 0.0001  # Default for most pairs
            symbol_info = self.connector.get_symbol_info(symbol)
            if symbol_info:
                digits = getattr(symbol_info, 'digits', 5)
                pip_size = 0.0001 if digits == 5 else 0.01
            
            # Breakeven price = entry + cost in pips
            # BUY: SL sube desde abajo hacia entry (entry - cost → entry)
            # SELL: SL baja desde arriba hacia entry (entry + cost → entry)
            position_type = position.get('type')
            # Normalize type: MT5 returns int (0=BUY, 1=SELL per POSITION_TYPE_BUY/SELL)
            # Metadata stores string ('BUY', 'SELL'). Support both formats.
            is_buy = position_type in [0, 'BUY']
            is_sell = position_type in [1, 'SELL']
            
            if is_buy:
                breakeven_price = entry_price + (cost_in_pips * pip_size)
            elif is_sell:
                breakeven_price = entry_price + (cost_in_pips * pip_size)  # SL baja desde arriba hacia entry
            else:
                logger.warning(f"Unknown position type: {position_type}")
                return None
            
            logger.debug(
                f"Breakeven calculation - "
                f"Entry: {entry_price}, Commission: ${commission_total}, "
                f"Swap: ${swap_cost}, Spread: ${spread_cost}, "
                f"Total: ${total_cost}, Breakeven: {breakeven_price}"
            )
            
            return breakeven_price
            
        except Exception as e:
            logger.error(
                f"Error calculating breakeven: {e}",
                exc_info=True
            )
            return None
    
    def _should_move_to_breakeven(
        self,
        position: Dict,
        metadata: Dict
    ) -> tuple[bool, str]:
        """
        Determine if SL should be moved to breakeven.
        
        Validation checks:
        1. Minimum time elapsed (15 minutes default)
        2. Minimum profit distance (5 pips default)
        3. Current price > breakeven_real + min_distance
        4. Current SL < breakeven_real (not already at breakeven)
        5. Freeze level validation (safety margin)
        
        Args:
            position: Position dict from connector
            metadata: Position metadata from database
            
        Returns:
            tuple: (should_move: bool, reason: str)
        """
        try:
            ticket = position.get('ticket')
            symbol = position.get('symbol')
            
            # Get breakeven config
            breakeven_config = self.config.get('breakeven', {})
            if not breakeven_config.get('enabled', False):
                return False, "Breakeven disabled in config"
            
            # 1. Check minimum time elapsed
            min_time_minutes = breakeven_config.get('min_time_minutes', 15)
            entry_time_str = metadata.get('entry_time')
            if entry_time_str:
                entry_time = datetime.fromisoformat(entry_time_str)
                elapsed_minutes = (datetime.now() - entry_time).total_seconds() / 60
                if elapsed_minutes < min_time_minutes:
                    return False, f"Insufficient time elapsed: {elapsed_minutes:.1f} min"
            
            # 2. Calculate breakeven real
            breakeven_real = self._calculate_breakeven_real(position, metadata)
            if breakeven_real is None:
                return False, "Could not calculate breakeven price"
            
            # 3. Check current price vs breakeven (must be in profit)
            current_price = float(position.get('current_price', 0))
            position_type = position.get('type')
            entry_price = float(metadata.get('entry_price', 0))
            
            # Calculate current profit in USD (explicit validation)
            current_profit_usd = float(position.get('profit', 0))
            if current_profit_usd <= 0:
                return False, f"Position in loss (${current_profit_usd:.2f}) - breakeven only applies to winning trades"
            
            # Get minimum distance - DYNAMIC based on ATR
            symbol_info = self.connector.get_symbol_info(symbol)
            pip_size = 0.0001  # Default
            if symbol_info:
                digits = getattr(symbol_info, 'digits', 5)
                pip_size = 0.0001 if digits == 5 else 0.01
            
            # Try to get dynamic distance from ATR (like trailing stops)
            atr = self.get_current_atr(symbol)
            if atr and atr > 0:
                # Use 0.5x ATR as minimum distance (more conservative than trailing's 2-3x)
                min_distance_price = atr * 0.5
                min_distance_pips = min_distance_price / pip_size
                logger.debug(f"Using dynamic distance: {min_distance_pips:.1f} pips (0.5x ATR)")
            else:
                # Fallback to config value if ATR not available
                min_distance_pips = breakeven_config.get('min_profit_distance_pips', 5)
                min_distance_price = min_distance_pips * pip_size
                logger.debug(f"Using static distance: {min_distance_pips} pips (ATR unavailable)")
            
            # Check distance based on position type
            if position_type == 'BUY':
                required_price = breakeven_real + min_distance_price
                if current_price < required_price:
                    distance = (current_price - breakeven_real) / pip_size
                    return False, f"Insufficient distance: {distance:.1f} pips (min {min_distance_pips})"
            elif position_type == 'SELL':
                required_price = breakeven_real - min_distance_price
                if current_price > required_price:
                    distance = (breakeven_real - current_price) / pip_size
                    return False, f"Insufficient distance: {distance:.1f} pips (min {min_distance_pips})"
            
            # 4. Check if SL is already at or above breakeven
            current_sl = float(position.get('sl', 0))
            if position_type == 'BUY':
                if current_sl >= breakeven_real:
                    return False, "SL already at or above breakeven"
            elif position_type == 'SELL':
                if 0 < current_sl <= breakeven_real:
                    return False, "SL already at or below breakeven"
            
            # 5. Validate freeze level (safety margin)
            if not self._validate_freeze_level(symbol, current_price, breakeven_real):
                return False, "Freeze level validation failed"
            
            # All checks passed
            return True, "Ready to move to breakeven"
            
        except Exception as e:
            logger.error(
                f"Error validating breakeven conditions: {e}",
                exc_info=True
            )
            return False, f"Error: {e}"
    
    def _calculate_trailing_stop_atr(
        self,
        position: Dict,
        metadata: Dict
    ) -> Optional[float]:
        """
        Calculate trailing stop price based on ATR (Average True Range).
        
        FASE 4: ATR-Based Trailing Stop
        =================================
        Formula:
        - BUY: trailing_sl = current_price - (ATR * multiplier)
        - SELL: trailing_sl = current_price + (ATR * multiplier)
        
        Args:
            position: Position dict from connector
            metadata: Position metadata from database
            
        Returns:
            float: Trailing stop price or None if calculation fails
        """
        try:
            symbol = position.get('symbol')
            position_type = position.get('type')
            current_price = float(position.get('current_price', 0))
            
            if current_price <= 0:
                # DEBUG: Transitorio, MT5 aún no ha devuelto precio actual
                logger.debug(
                    f"Position {position.get('ticket')} current_price not available yet "
                    f"(value: {current_price}) - Skipping trailing stop calculation"
                )
                return None
            
            # Get trailing stop config
            trailing_config = self.config.get('trailing_stop', {})
            if not trailing_config.get('enabled', False):
                return None
            
            # Get ATR from regime classifier
            atr = self.get_current_atr(symbol)
            if not atr or atr <= 0:
                logger.debug(f"ATR not available for {symbol} - Cannot calculate trailing stop")
                return None
            
            # Get regime-specific multiplier (FASE 4B: Dynamic by regime)
            current_regime = self._get_current_regime_with_fallback(symbol)
            regime_name = current_regime.value if hasattr(current_regime, 'value') else str(current_regime)
            
            atr_multipliers_by_regime = trailing_config.get('atr_multipliers_by_regime', {})
            
            # Priority: regime-specific > fallback 2.0
            if atr_multipliers_by_regime and regime_name in atr_multipliers_by_regime:
                atr_multiplier = atr_multipliers_by_regime[regime_name]
            else:
                # Fallback: Try legacy 'atr_multiplier' or default 2.0
                atr_multiplier = trailing_config.get('atr_multiplier', 2.0)
            
            # Calculate trailing stop distance
            trailing_distance = atr * atr_multiplier
            
            # Calculate new SL based on position type
            # Normalize type: MT5 returns int (0=BUY, 1=SELL per POSITION_TYPE_BUY/SELL)
            # Metadata stores string ('BUY', 'SELL'). Support both formats.
            is_buy = position_type in [0, 'BUY']
            is_sell = position_type in [1, 'SELL']
            
            if is_buy:
                # BUY: SL debajo del precio actual
                trailing_sl = current_price - trailing_distance
            elif is_sell:
                # SELL: SL arriba del precio actual
                trailing_sl = current_price + trailing_distance
            else:
                logger.warning(f"Unknown position type: {position_type}")
                return None
            
            logger.debug(
                f"Trailing stop calculation - "
                f"Price: {current_price}, ATR: {atr}, Multiplier: {atr_multiplier}, "
                f"Distance: {trailing_distance}, Trailing SL: {trailing_sl}"
            )
            
            return trailing_sl
            
        except Exception as e:
            logger.error(
                f"Error calculating trailing stop: {e}",
                exc_info=True
            )
            return None
    
    def _should_apply_trailing_stop(
        self,
        position: Dict,
        metadata: Dict
    ) -> tuple[bool, str]:
        """
        Determine if trailing stop should be applied.
        
        Validation checks:
        1. Minimum profit requirement (10 pips default)
        2. New SL improves current SL (BUY: higher, SELL: lower)
        3. Cooldown elapsed since last modification
        4. Daily limit not exceeded
        5. Freeze level validation
        
        Args:
            position: Position dict from connector
            metadata: Position metadata from database
            
        Returns:
            tuple: (should_apply: bool, reason: str)
        """
        try:
            ticket = position.get('ticket')
            symbol = position.get('symbol')
            position_type = position.get('type')
            current_sl = float(position.get('sl', 0))
            entry_price = float(metadata.get('entry_price', 0))
            current_price = float(position.get('current_price', 0))
            
            # Get trailing stop config
            trailing_config = self.config.get('trailing_stop', {})
            if not trailing_config.get('enabled', False):
                return False, "Trailing stop disabled in config"
            
            # 1. Check minimum profit requirement (FASE 4B: Dynamic with ATR)
            # Get pip size
            symbol_info = self.connector.get_symbol_info(symbol)
            pip_size = 0.0001  # Default
            if symbol_info:
                # SymbolInfo is a namedtuple, not a dict - use attribute access
                digits = getattr(symbol_info, 'digits', 5)
                pip_size = 0.0001 if digits == 5 else 0.01
            
            # Calculate current profit in pips
            # Normalize type: MT5 returns int (0=BUY, 1=SELL per POSITION_TYPE_BUY/SELL)
            # Metadata stores string ('BUY', 'SELL'). Support both formats.
            is_buy = position_type in [0, 'BUY']
            is_sell = position_type in [1, 'SELL']
            
            if is_buy:
                profit_pips = (current_price - entry_price) / pip_size
            elif is_sell:
                profit_pips = (entry_price - current_price) / pip_size
            else:
                return False, f"Unknown position type: {position_type}"
            
            # Calculate dynamic profit threshold with ATR
            min_profit_atr_multiplier = trailing_config.get('min_profit_atr_multiplier')
            
            if min_profit_atr_multiplier is not None:
                # FASE 4B: Dynamic threshold (1x ATR)
                atr = self.get_current_atr(symbol)
                if not atr or atr <= 0:
                    return False, "ATR not available for dynamic profit threshold"
                
                profit_threshold_price = atr * min_profit_atr_multiplier
                profit_threshold_pips = profit_threshold_price / pip_size
            else:
                # Fallback: Legacy fixed pips (FASE 4 compatibility)
                profit_threshold_pips = trailing_config.get('min_profit_pips', 10)
            
            if profit_pips < profit_threshold_pips:
                return False, f"Insufficient profit: {profit_pips:.1f} pips (min {profit_threshold_pips:.1f})"
            
            # 2. Calculate new trailing SL
            new_trailing_sl = self._calculate_trailing_stop_atr(position, metadata)
            if new_trailing_sl is None:
                return False, "Could not calculate trailing stop"
            
            # 3. Validate that new SL improves current SL
            if position_type == 'BUY':
                # BUY: new SL must be HIGHER than current (mejora = más cerca del precio)
                if new_trailing_sl <= current_sl:
                    return False, f"New SL ({new_trailing_sl:.5f}) does not improve current SL ({current_sl:.5f})"
            elif position_type == 'SELL':
                # SELL: new SL must be LOWER than current (mejora = más cerca del precio)
                if current_sl > 0 and new_trailing_sl >= current_sl:
                    return False, f"New SL ({new_trailing_sl:.5f}) does not improve current SL ({current_sl:.5f})"
            
            # 4. Check cooldown
            last_mod_timestamp = metadata.get('last_modification_timestamp')
            if last_mod_timestamp:
                last_mod_time = datetime.fromisoformat(last_mod_timestamp)
                elapsed_seconds = (datetime.now() - last_mod_time).total_seconds()
                if elapsed_seconds < self.cooldown_seconds:
                    return False, f"Cooldown active: {elapsed_seconds:.0f}s elapsed (need {self.cooldown_seconds}s)"
            
            # 5. Check daily modification limit
            modifications_today = metadata.get('sl_modifications_count', 0)
            if modifications_today >= self.max_modifications_per_day:
                return False, f"Daily limit reached: {modifications_today}/{self.max_modifications_per_day}"
            
            # 6. Validate freeze level
            if not self._validate_freeze_level(symbol, current_price, new_trailing_sl):
                return False, "Freeze level validation failed"
            
            # All checks passed
            return True, f"Ready to apply trailing stop: {new_trailing_sl:.5f}"
            
        except Exception as e:
            logger.error(
                f"Error validating trailing stop conditions: {e}",
                exc_info=True
            )
            return False, f"Error: {e}"
