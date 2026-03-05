"""
Strategy Monitor Service
Provides real-time monitoring of strategy metrics and status.

Metrics tracked:
- Status: LIVE, QUARANTINE, SHADOW, UNKNOWN
- DD% (Drawdown %): Current drawdown percentage
- CL (Consecutive Losses): Loss streak
- WR (Win Rate): Percentage of winning trades
- PF (Profit Factor): Gross profit / Gross loss ratio
"""

import logging
from typing import Dict, List, Optional, Any
from datetime import datetime

from data_vault.storage import StorageManager
from core_brain.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class StrategyMonitorService:
    """
    Real-time strategy monitoring service.
    
    Provides current metrics for all strategies including:
    - Execution mode (LIVE, SHADOW, QUARANTINE)
    - Performance metrics (DD%, CL, WR, PF)
    - Trading authorization status
    
    Architecture: Service Layer (per DEVELOPMENT_GUIDELINES § 1.6)
    """
    
    def __init__(
        self,
        storage: StorageManager,
        circuit_breaker: CircuitBreaker
    ):
        """
        Initialize monitor with dependencies.
        
        Args:
            storage: StorageManager for strategy data retrieval
            circuit_breaker: CircuitBreaker for status determination
        """
        self.storage = storage
        self.circuit_breaker = circuit_breaker
        logger.debug("[STRATEGY_MONITOR] Service initialized")
    
    def get_strategy_metrics(self, strategy_id: str) -> Dict[str, Any]:
        """
        Get current metrics for a single strategy.
        
        Args:
            strategy_id: The strategy identifier
        
        Returns:
            Dict with keys:
            - strategy_id: str
            - status: LIVE | QUARANTINE | SHADOW | UNKNOWN
            - dd_pct: float (0-100) drawdown percentage
            - consecutive_losses: int ≥ 0
            - win_rate: float (0.0-1.0)
            - profit_factor: float > 0
            - blocked_for_trading: bool
            - updated_at: ISO8601 timestamp
        """
        try:
            # Get strategy data from storage
            strategy_data = self.storage.get_strategy_ranking(strategy_id)
            
            if strategy_data is None:
                logger.warning(f"[STRATEGY_MONITOR] Strategy not found: {strategy_id}")
                return {
                    'strategy_id': strategy_id,
                    'status': 'UNKNOWN',
                    'dd_pct': 0.0,
                    'consecutive_losses': 0,
                    'win_rate': 0.0,
                    'profit_factor': 1.0,
                    'blocked_for_trading': False,
                    'updated_at': datetime.now().isoformat(),
                    'error': 'Strategy not found'
                }
            
            # Get execution status from circuit breaker
            cb_status = self.circuit_breaker.get_strategy_status(strategy_id)
            is_blocked = self.circuit_breaker.is_strategy_blocked_for_trading(strategy_id)
            
            # Map CB status to UI status
            status = self._map_cb_status_to_ui_status(cb_status)
            
            # Extract metrics from strategy data
            dd_pct = float(strategy_data.get('dd_pct', 0.0))
            consecutive_losses = int(strategy_data.get('consecutive_losses', 0))
            win_rate = float(strategy_data.get('win_rate', 0.0))
            profit_factor = float(strategy_data.get('profit_factor', 1.0))
            
            # Determine if recently updated (online status)
            updated_at = strategy_data.get('updated_at')
            if isinstance(updated_at, str):
                updated_dt = datetime.fromisoformat(updated_at)
            else:
                updated_dt = datetime.now()
            
            return {
                'strategy_id': strategy_id,
                'status': status,
                'dd_pct': dd_pct,
                'consecutive_losses': consecutive_losses,
                'win_rate': win_rate,
                'profit_factor': profit_factor,
                'blocked_for_trading': is_blocked,
                'updated_at': updated_dt.isoformat(),
                'trades_count': strategy_data.get('trades_count', 0)
            }
        
        except Exception as exc:
            # RULE 4.3: Fail-safe exception handling
            logger.error(
                f"[STRATEGY_MONITOR] Error getting metrics for {strategy_id}: {exc}",
                exc_info=True
            )
            return {
                'strategy_id': strategy_id,
                'status': 'UNKNOWN',
                'dd_pct': 0.0,
                'consecutive_losses': 0,
                'win_rate': 0.0,
                'profit_factor': 1.0,
                'blocked_for_trading': False,
                'updated_at': datetime.now().isoformat(),
                'error': str(exc)
            }
    
    def get_all_strategies_metrics(self) -> List[Dict[str, Any]]:
        """
        Get metrics for all monitored strategies.
        
        Results are sorted by priority:
        1. LIVE (actively trading)
        2. SHADOW (shadow trading, learning mode)
        3. QUARANTINE (degraded, not trading)
        4. UNKNOWN (not configured)
        
        Returns:
            List of strategy metric dicts, sorted by status priority
        """
        try:
            # Get all strategies from storage
            all_strategies = self.storage.get_all_strategies()
            
            if not all_strategies:
                logger.warning("[STRATEGY_MONITOR] No strategies found in storage")
                return []
            
            # Get metrics for each
            metrics_list = []
            for strategy_summary in all_strategies:
                strategy_id = strategy_summary.get('strategy_id')
                if strategy_id:
                    metrics = self.get_strategy_metrics(strategy_id)
                    metrics_list.append(metrics)
            
            # Sort by status priority
            status_priority = {'LIVE': 0, 'SHADOW': 1, 'QUARANTINE': 2, 'UNKNOWN': 3}
            metrics_list.sort(
                key=lambda m: status_priority.get(m['status'], 999)
            )
            
            logger.debug(
                f"[STRATEGY_MONITOR] Retrieved metrics for {len(metrics_list)} strategies"
            )
            return metrics_list
        
        except Exception as exc:
            # RULE 4.3: Fail-safe
            logger.error(
                f"[STRATEGY_MONITOR] Error getting all metrics: {exc}",
                exc_info=True
            )
            return []
    
    @staticmethod
    def _map_cb_status_to_ui_status(cb_status: Optional[str]) -> str:
        """
        Map internal CircuitBreaker status to UI status.
        
        Internal statuses: LIVE, SHADOW, QUARANTINE, UNKNOWN
        UI statuses: LIVE, SHADOW, QUARANTINE, UNKNOWN (same mapping)
        
        Args:
            cb_status: CircuitBreaker status
        
        Returns:
            UI-friendly status string
        """
        if cb_status is None:
            return 'UNKNOWN'
        
        status_map = {
            'LIVE': 'LIVE',
            'SHADOW': 'SHADOW',
            'QUARANTINE': 'QUARANTINE',
            'CLOSED': 'QUARANTINE',  # Alternative term for blocked
        }
        
        return status_map.get(str(cb_status).upper(), 'UNKNOWN')
