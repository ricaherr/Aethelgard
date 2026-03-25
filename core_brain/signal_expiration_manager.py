"""
SignalExpirationManager - Gestión centralizada expiración señales

Marca señales PENDING como EXPIRED cuando exceden ventana de validez.
Diseñado para ejecutarse en MainOrchestrator cada ciclo.

Arquitectura:
- Regla: Señal expira después de 4 velas completas del timeframe origen
- Solo afecta señales PENDING (ejecutadas/rechazadas no se tocan)
- Ventanas dinámicas por timeframe
- Metadata incluye razón y timestamp expiración

Uso:
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_usr_signals()
    # stats = {'total_expired': 5, 'by_timeframe': {'M5': 3, 'H1': 2}}
"""
from datetime import datetime, timedelta
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Dynamic expiration windows (in minutes) - 4 candle rule.
# A signal stays PENDING for exactly 4 complete candles of its timeframe,
# then is marked EXPIRED so it stops blocking new signals.
# This is intentionally aligned with calculate_deduplication_window() in signals_db.
#   M5  -> 4 × 5  =   20 min
#   M15 -> 4 × 15 =   60 min
#   M30 -> 4 × 30 =  120 min
#   H1  -> 4 × 60 =  240 min
#   H4  -> 4 × 240 = 960 min
#   D1  -> 4 × 1440 = 5760 min (4 trading days)
EXPIRATION_WINDOWS = {
    'M1':  4,
    'M3':  12,
    'M5':  20,
    'M10': 40,
    'M15': 60,
    'M30': 120,
    'H1':  240,
    'H2':  480,
    'H4':  960,
    'H6':  1440,
    'H8':  1920,
    'D1':  5760,
    'W1':  40320,
}


class SignalExpirationManager:
    """Manages automatic signal expiration based on timeframe"""
    
    def __init__(self, storage):
        """
        Initialize SignalExpirationManager.
        
        Args:
            storage: StorageManager instance (dependency injection)
        """
        self.storage = storage
    
    def expire_old_sys_signals(self) -> Dict[str, int]:
        """
        Mark PENDING sys_signals as EXPIRED if they exceeded timeframe window.
        
        Process:
        1. Get all PENDING sys_signals
        2. Calculate age for each signal
        3. Compare age vs timeframe window
        4. Mark as EXPIRED if age > window
        5. Update metadata with expiration details
        
        Returns:
            Dict with expiration stats:
            {
                'total_expired': 5,
                'by_timeframe': {
                    'M5': 3,
                    'H1': 2
                }
            }
        """
        stats = {'total_expired': 0, 'total_checked': 0, 'by_timeframe': {}}
        
        # Get all PENDING sys_signals (only these can be expired)
        pending_sys_signals = self.storage.get_sys_signals(status='PENDING')
        stats['total_checked'] = len(pending_sys_signals)
        
        if not pending_sys_signals:
            return stats
        
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        for signal in pending_sys_signals:
            timeframe = signal.get('timeframe', 'H1')  # Default H1 if missing
            window_minutes = EXPIRATION_WINDOWS.get(timeframe, 60)  # Default 1h if unknown TF
            
            # Parse signal timestamp
            timestamp_str = signal.get('timestamp')
            if not timestamp_str:
                logger.warning(f"Signal {signal.get('id')} missing timestamp, skipping")
                continue
            
            try:
                from datetime import timezone
                if isinstance(timestamp_str, datetime):
                    signal_time = timestamp_str
                else:
                    ts = str(timestamp_str).replace("Z", "+00:00")
                    signal_time = datetime.fromisoformat(ts)

                # Legacy naive timestamps: interpret as local timezone before UTC conversion
                if signal_time.tzinfo is None:
                    local_tz = datetime.now().astimezone().tzinfo or timezone.utc
                    signal_time = signal_time.replace(tzinfo=local_tz)

                signal_time = signal_time.astimezone(timezone.utc)
            except (ValueError, TypeError) as e:
                logger.warning(f"Failed to parse timestamp {timestamp_str}: {e}")
                continue
            
            # Calculate age in minutes
            age_minutes = (now - signal_time).total_seconds() / 60
            
            # Check if expired
            if age_minutes > window_minutes:
                signal_id = signal['id']
                
                # Update signal status to EXPIRED with metadata
                self.storage.update_signal_status(signal_id, 'EXPIRED', {
                    'expired_at': now.isoformat(),
                    'reason': f'Signal expired after {age_minutes:.1f}min (window: {window_minutes}min)',
                    'timeframe_window': window_minutes,
                    'signal_age_minutes': age_minutes
                })
                
                # Update stats
                stats['total_expired'] += 1
                stats['by_timeframe'][timeframe] = stats['by_timeframe'].get(timeframe, 0) + 1
                
                logger.info(
                    f"[EXPIRED] {signal.get('symbol', 'UNKNOWN')} "
                    f"{signal.get('signal_type', 'UNKNOWN')} [{timeframe}] "
                    f"(age: {age_minutes:.1f}min > window: {window_minutes}min)"
                )
        
        # Log summary if any usr_signals expired
        if stats['total_expired'] > 0:
            logger.info(
                f"[EXPIRATION CYCLE] Expired {stats['total_expired']} usr_signals: "
                f"{stats['by_timeframe']}"
            )
        
        return stats
