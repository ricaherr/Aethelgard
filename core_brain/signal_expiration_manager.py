"""
SignalExpirationManager - Gestión centralizada expiración señales

Marca señales PENDING como EXPIRED cuando exceden ventana de validez.
Diseñado para ejecutarse en MainOrchestrator cada ciclo.

Arquitectura:
- Regla: Señal expira después de 1 vela completa del timeframe origen
- Solo afecta señales PENDING (ejecutadas/rechazadas no se tocan)
- Ventanas dinámicas por timeframe
- Metadata incluye razón y timestamp expiración

Uso:
    manager = SignalExpirationManager(storage)
    stats = manager.expire_old_signals()
    # stats = {'total_expired': 5, 'by_timeframe': {'M5': 3, 'H1': 2}}
"""
from datetime import datetime, timedelta
from typing import Dict
import logging

logger = logging.getLogger(__name__)

# Dynamic expiration windows (in minutes) - 1 candle rule
# M5  -> 5 minutes (1 candle)
# M15 -> 15 minutes (1 candle)
# H1  -> 60 minutes (1 candle)
# H4  -> 240 minutes (1 candle)
# D1  -> 1440 minutes (1 candle = 24 hours)
EXPIRATION_WINDOWS = {
    'M5': 5,
    'M15': 15,
    'M30': 30,
    'H1': 60,
    'H4': 240,
    'D1': 1440
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
    
    def expire_old_signals(self) -> Dict[str, int]:
        """
        Mark PENDING signals as EXPIRED if they exceeded timeframe window.
        
        Process:
        1. Get all PENDING signals
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
        
        # Get all PENDING signals (only these can be expired)
        pending_signals = self.storage.get_signals(status='PENDING')
        stats['total_checked'] = len(pending_signals)
        
        if not pending_signals:
            return stats
        
        from datetime import timezone
        now = datetime.now(timezone.utc)
        
        for signal in pending_signals:
            timeframe = signal.get('timeframe', 'H1')  # Default H1 if missing
            window_minutes = EXPIRATION_WINDOWS.get(timeframe, 60)  # Default 1h if unknown TF
            
            # Parse signal timestamp
            timestamp_str = signal.get('timestamp')
            if not timestamp_str:
                logger.warning(f"Signal {signal.get('id')} missing timestamp, skipping")
                continue
            
            try:
                # Normalizar a UTC
                from core_brain.market_utils import to_utc
                from datetime import timezone
                if 'T' in timestamp_str or '.' in timestamp_str:
                    # ISO 8601 extendido
                    signal_time = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                    if signal_time.tzinfo is None:
                        signal_time = signal_time.replace(tzinfo=timezone.utc)
                    else:
                        signal_time = signal_time.astimezone(timezone.utc)
                else:
                    signal_time = datetime.strptime(timestamp_str, '%Y-%m-%d %H:%M:%S')
                    signal_time = signal_time.replace(tzinfo=timezone.utc)
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
        
        # Log summary if any signals expired
        if stats['total_expired'] > 0:
            logger.info(
                f"[EXPIRATION CYCLE] Expired {stats['total_expired']} signals: "
                f"{stats['by_timeframe']}"
            )
        
        return stats
