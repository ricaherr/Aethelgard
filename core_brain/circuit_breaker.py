"""
Circuit Breaker - Real-time LIVE Strategy Monitoring & Auto-Degradation
TRACE_ID: CIRCUIT-BREAKER-REALTIME-2026

Monitors all LIVE strategies for risk metric violations and automatically
degrades them to QUARANTINE when thresholds are exceeded.

Thresholds (from MANIFESTO § 7.4 - Single Source of Truth):
- Drawdown >= 3%
- Consecutive Losses >= 5

Operates every cycle in MainOrchestrator.run_single_cycle() via TradeClosureListener
integration for real-time metric updates.

All threshold values MUST match those in strategy_ranker.py for consistency.

Integration: When strategies degrade, DegradationAlertService sends alerts
to NotificationService (Telegram, Email, etc.) for immediate user notification.
"""

import logging
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# ===== CIRCUIT BREAKER THRESHOLDS (SSOT: MANIFESTO § 7.4) =====
# These values MUST match StrategyRanker thresholds (degradation criteria)
# Source: docs/AETHELGARD_MANIFESTO.md § 7.4
CB_DRAWDOWN_THRESHOLD = 3.0      # Percentage (%): Auto-degrade LIVE→QUARANTINE if DD ≥ 3%
CB_CONSECUTIVE_LOSSES_THRESHOLD = 5  # Count: Auto-degrade LIVE→QUARANTINE if CL ≥ 5


def _resolve_storage(storage: Optional[StorageManager]) -> StorageManager:
    """
    Resolve storage dependency with legacy fallback.
    Main path should inject StorageManager from composition root.
    """
    if storage is not None:
        return storage
    logger.warning("CircuitBreaker initialized without explicit storage! Falling back to default storage.")
    return StorageManager()


class CircuitBreaker:
    """
    Monitors all LIVE strategies in real-time and automatically degrades them
    to QUARANTINE when risk thresholds are violated.
    
    Architecture:
    - Called by TradeClosureListener when trade closes
    - Reads strategy metrics from strategy_ranking table (SSOT)
    - Checks DD and CL thresholds
    - Degrades to QUARANTINE if violated
    - Logs all transitions with trace_ids for audit trail
    
    Non-blocking: Errors in CB should not interrupt trading cycle.
    """
    
    def __init__(
        self,
        storage: Optional[StorageManager] = None,
        degradation_alert_service: Optional['DegradationAlertService'] = None
    ):
        """
        Initialize CircuitBreaker with dependency injection.
        
        Args:
            storage: StorageManager instance for persistence and query
            degradation_alert_service: DegradationAlertService for sending alerts
                (Optional for backward compatibility)
        """
        self.storage = _resolve_storage(storage)
        self.degradation_alert_service = degradation_alert_service
        logger.info(
            f"CircuitBreaker initialized with real-time monitoring. "
            f"Thresholds: DD>={CB_DRAWDOWN_THRESHOLD}%, CL>={CB_CONSECUTIVE_LOSSES_THRESHOLD}. "
            f"Alert service: {'enabled' if degradation_alert_service else 'disabled (legacy mode)'}"
        )
    
    def check_and_degrade_if_needed(self, strategy_id: str) -> Dict[str, Any]:
        """
        Check a single LIVE strategy for risk violations and degrade if needed.
        
        Args:
            strategy_id: Identifier of the strategy to check
            
        Returns:
            Dictionary with action, reason, and trace_id if applicable
            
        Actions:
            - 'degraded': Moved from LIVE to QUARANTINE
            - 'no_action': Healthy LIVE strategy
            - 'skipped': Not in LIVE mode
            - 'not_found': Strategy not in ranking table
            - 'error': Error during check (non-blocking)
        """
        try:
            # Get current strategy metrics
            ranking = self.storage.get_strategy_ranking(strategy_id)
            if not ranking:
                logger.warning(f"[CB] Strategy {strategy_id} not found in ranking table")
                return {'action': 'not_found', 'strategy_id': strategy_id}
            
            current_mode = ranking.get('execution_mode')
            
            # CircuitBreaker only monitors LIVE strategies
            if current_mode != 'LIVE':
                logger.debug(f"[CB] {strategy_id}: Skipping (mode={current_mode})")
                return {
                    'action': 'skipped',
                    'reason': 'not_live_mode',
                    'current_mode': current_mode,
                    'strategy_id': strategy_id
                }
            
            # Extract metrics
            drawdown_max = ranking.get('drawdown_max', 0.0)
            consecutive_losses = ranking.get('consecutive_losses', 0)
            
            # Check thresholds
            drawdown_violated = drawdown_max >= CB_DRAWDOWN_THRESHOLD
            losses_violated = consecutive_losses >= CB_CONSECUTIVE_LOSSES_THRESHOLD
            
            if not (drawdown_violated or losses_violated):
                # All good - no action needed
                logger.debug(
                    f"[CB] {strategy_id}: Healthy (DD={drawdown_max:.2f}%, CL={consecutive_losses})"
                )
                return {
                    'action': 'no_action',
                    'current_mode': 'LIVE',
                    'drawdown_max': drawdown_max,
                    'consecutive_losses': consecutive_losses,
                    'strategy_id': strategy_id
                }
            
            # Risk threshold violated - degrade to QUARANTINE
            reason = 'drawdown_exceeded' if drawdown_violated else 'consecutive_losses_exceeded'
            
            # Execute degradation
            trace_id = self.storage.update_strategy_execution_mode(
                strategy_id, 'QUARANTINE', trace_id=None
            )
            
            # Log state change
            self.storage.log_strategy_state_change(
                strategy_id=strategy_id,
                old_mode='LIVE',
                new_mode='QUARANTINE',
                trace_id=trace_id,
                reason=reason,
                metrics={
                    'drawdown_max': drawdown_max,
                    'consecutive_losses': consecutive_losses,
                    'total_trades': ranking.get('total_trades'),
                    'profit_factor': ranking.get('profit_factor')
                }
            )
            
            # Critical log for visibility
            logger.critical(
                f"[CB] 🔴 CIRCUIT BREAKER: {strategy_id} degraded LIVE→QUARANTINE "
                f"({reason}: DD={drawdown_max:.2f}%, CL={consecutive_losses}) "
                f"[Trace: {trace_id}]"
            )
            
            # RULE 4.3: Try/Except on alert service integration
            # Send degradation alert if service available
            if self.degradation_alert_service:
                try:
                    # Get tenant_id from storage context (if available)
                    tenant_id = getattr(self.storage, 'tenant_id', 'default')
                    
                    self.degradation_alert_service.handle_degradation({
                        'strategy_id': strategy_id,
                        'from_status': 'LIVE',
                        'to_status': 'QUARANTINE',
                        'reason': f"{reason}: DD={drawdown_max:.2f}%, CL={consecutive_losses}",
                        'dd_pct': drawdown_max,
                        'consecutive_losses': consecutive_losses,
                        'profit_factor': ranking.get('profit_factor'),
                        'win_rate': ranking.get('win_rate'),
                        'tenant_id': tenant_id
                    })
                    logger.info(f"[CB] {trace_id}: Degradation alert sent for {strategy_id}")
                
                except Exception as exc:
                    # RULE 4.3: Log error but don't crash circuit breaker
                    logger.error(
                        f"[CB] {trace_id}: Error sending degradation alert: {exc}",
                        exc_info=True
                    )
            
            return {
                'action': 'degraded',
                'from_mode': 'LIVE',
                'to_mode': 'QUARANTINE',
                'reason': reason,
                'trace_id': trace_id,
                'drawdown_max': drawdown_max,
                'consecutive_losses': consecutive_losses,
                'strategy_id': strategy_id
            }
            
        except Exception as e:
            logger.error(
                f"[CB] Error checking strategy {strategy_id}: {e}",
                exc_info=False
            )
            # Return error action instead of crashing
            return {
                'action': 'error',
                'strategy_id': strategy_id,
                'error': str(e)
            }
    
    def monitor_all_live_strategies(self) -> Dict[str, Dict[str, Any]]:
        """
        Monitor all LIVE strategies in batch.
        
        Called by MainOrchestrator or TradeClosureListener for continuous monitoring.
        
        Returns:
            Dictionary mapping strategy_id to check result
        """
        try:
            # Get all LIVE strategies
            live_strategies = self.storage.get_strategies_by_mode('LIVE')
            
            logger.info(f"[CB] Monitoring {len(live_strategies)} LIVE strategies...")
            
            results = {}
            for strategy_id in live_strategies:
                try:
                    result = self.check_and_degrade_if_needed(strategy_id)
                    results[strategy_id] = result
                except Exception as e:
                    logger.error(f"[CB] Error checking {strategy_id}: {e}", exc_info=False)
                    results[strategy_id] = {'action': 'error', 'error': str(e)}
            
            # Log summary
            degradations = sum(1 for r in results.values() if r.get('action') == 'degraded')
            if degradations > 0:
                logger.critical(f"[CB] Summary: {degradations} strategies degraded to QUARANTINE")
            else:
                logger.debug(f"[CB] All {len(live_strategies)} LIVE strategies healthy")
            
            return results
            
        except Exception as e:
            logger.error(f"[CB] Error in batch monitoring: {e}", exc_info=False)
            return {}
    
    def is_strategy_blocked_for_trading(self, strategy_id: str) -> bool:
        """
        Quick check: Is strategy blocked from sending orders?
        
        Used by Executor to prevent order placement.
        
        Returns True if in QUARANTINE or SHADOW mode.
        """
        try:
            ranking = self.storage.get_strategy_ranking(strategy_id)
            if not ranking:
                return True  # Unknown = blocked
            
            execution_mode = ranking.get('execution_mode')
            # Only LIVE -> send orders. SHADOW/QUARANTINE -> blocked
            return execution_mode != 'LIVE'
            
        except Exception:
            return True  # Error = block (safe default)
