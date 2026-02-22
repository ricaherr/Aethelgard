"""
Strategy Ranker - Darwinismo Algorítmico (Shadow Ranking System)
Manages strategy evolution: SHADOW -> LIVE -> QUARANTINE and recovery cycles.
"""
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


def _resolve_storage(storage: Optional[StorageManager]) -> StorageManager:
    """
    Resolve storage dependency with legacy fallback.
    Main path should inject StorageManager from composition root.
    """
    if storage is not None:
        return storage
    logger.warning("StrategyRanker initialized without explicit storage! Falling back to default storage.")
    return StorageManager()


class StrategyRanker:
    """
    Evaluates strategy performance and manages execution mode transitions.
    
    Modes:
    - SHADOW: Forward-testing phase, tracking metrics without real orders
    - LIVE: Strategy approved for real trading
    - QUARANTINE: Suspended due to risk threshold violations
    
    Promotion Logic (SHADOW -> LIVE):
    - Profit Factor > 1.5 AND Win Rate > 50% in last 50 trades
    
    Degradation Logic (LIVE -> QUARANTINE):
    - Drawdown >= 3% OR Consecutive Losses >= 5
    
    Recovery Logic (QUARANTINE -> SHADOW):
    - All degradation triggers must clear for re-evaluation
    """
    
    # Thresholds for transitions
    PROFIT_FACTOR_THRESHOLD = 1.5
    WIN_RATE_THRESHOLD = 0.50
    MIN_TRADES_FOR_PROMOTION = 50
    DRAWDOWN_THRESHOLD = 3.0  # percentage
    CONSECUTIVE_LOSSES_THRESHOLD = 5
    
    def __init__(self, storage: Optional[StorageManager] = None):
        """
        Initialize StrategyRanker with dependency injection.
        
        Args:
            storage: StorageManager instance for persistence
        """
        self.storage = _resolve_storage(storage)
        logger.info("StrategyRanker initialized with SHADOW->LIVE->QUARANTINE evolution engine")
    
    def evaluate_and_rank(self, strategy_id: str) -> Dict[str, Any]:
        """
        Evaluate strategy metrics and determine if mode transition is warranted.
        
        Args:
            strategy_id: Identifier of the strategy to evaluate
            
        Returns:
            Dictionary with action, metrics, and trace_id if applicable
        """
        # Fetch current strategy data
        ranking = self.storage.get_strategy_ranking(strategy_id)
        if not ranking:
            logger.warning(f"Strategy {strategy_id} not found in ranking table")
            return {'action': 'not_found', 'strategy_id': strategy_id}
        
        current_mode = ranking['execution_mode']
        
        # Route to appropriate evaluation logic
        if current_mode == 'SHADOW':
            return self._evaluate_shadow(strategy_id, ranking)
        elif current_mode == 'LIVE':
            return self._evaluate_live(strategy_id, ranking)
        elif current_mode == 'QUARANTINE':
            return self._evaluate_quarantine(strategy_id, ranking)
        else:
            logger.error(f"Unknown execution mode: {current_mode}")
            return {'action': 'error', 'reason': 'unknown_mode'}
    
    def _evaluate_shadow(self, strategy_id: str, ranking: Dict) -> Dict[str, Any]:
        """
        Evaluate SHADOW strategy for promotion to LIVE.
        
        Promotion criteria:
        - Profit Factor > 1.5
        - Win Rate > 50%
        - At least 50 completed trades in evaluation window
        """
        profit_factor = ranking.get('profit_factor', 0.0)
        win_rate = ranking.get('win_rate', 0.0)
        completed_last_50 = ranking.get('completed_last_50', 0)
        
        # Check promotion conditions
        meets_profit_factor = profit_factor > self.PROFIT_FACTOR_THRESHOLD
        meets_win_rate = win_rate > self.WIN_RATE_THRESHOLD
        meets_trade_count = completed_last_50 >= self.MIN_TRADES_FOR_PROMOTION
        
        if not meets_trade_count:
            logger.info(
                f"Strategy {strategy_id}: Insufficient trades for promotion "
                f"({completed_last_50}/{self.MIN_TRADES_FOR_PROMOTION})"
            )
            return {
                'action': 'insufficient_trades',
                'current_mode': 'SHADOW',
                'profit_factor': profit_factor,
                'win_rate': win_rate,
                'completed_trades': completed_last_50,
                'min_required': self.MIN_TRADES_FOR_PROMOTION
            }
        
        if meets_profit_factor and meets_win_rate:
            # PROMOTION to LIVE
            trace_id = self._promote_strategy(strategy_id, ranking)
            return {
                'action': 'promoted',
                'from_mode': 'SHADOW',
                'to_mode': 'LIVE',
                'reason': 'optimal_metrics',
                'trace_id': trace_id,
                'profit_factor': profit_factor,
                'win_rate': win_rate,
                'completed_trades': completed_last_50
            }
        else:
            # No change
            missing_criteria = []
            if not meets_profit_factor:
                missing_criteria.append(f"PF {profit_factor:.2f} < {self.PROFIT_FACTOR_THRESHOLD}")
            if not meets_win_rate:
                missing_criteria.append(f"WR {win_rate:.1%} < {self.WIN_RATE_THRESHOLD:.0%}")
            
            logger.debug(f"Strategy {strategy_id} remains in SHADOW: {', '.join(missing_criteria)}")
            return {
                'action': 'no_change',
                'current_mode': 'SHADOW',
                'reason': 'insufficient_metrics',
                'missing_criteria': missing_criteria,
                'profit_factor': profit_factor,
                'win_rate': win_rate
            }
    
    def _evaluate_live(self, strategy_id: str, ranking: Dict) -> Dict[str, Any]:
        """
        Evaluate LIVE strategy for degradation to QUARANTINE.
        
        Degradation triggers:
        - Drawdown >= 3% OR
        - Consecutive Losses >= 5
        """
        drawdown_max = ranking.get('drawdown_max', 0.0)
        consecutive_losses = ranking.get('consecutive_losses', 0)
        
        # Check degradation conditions
        drawdown_exceeded = drawdown_max >= self.DRAWDOWN_THRESHOLD
        losses_exceeded = consecutive_losses >= self.CONSECUTIVE_LOSSES_THRESHOLD
        
        if drawdown_exceeded or losses_exceeded:
            # DEGRADATION to QUARANTINE
            reason = 'drawdown_exceeded' if drawdown_exceeded else 'consecutive_losses_exceeded'
            trace_id = self._degrade_strategy(strategy_id, ranking, reason)
            
            logger.critical(
                f"[TRACE_ID: {trace_id}] Strategy {strategy_id} degraded to QUARANTINE. "
                f"Reason: {reason} (DD={drawdown_max:.2f}%, CL={consecutive_losses})"
            )
            
            return {
                'action': 'degraded',
                'from_mode': 'LIVE',
                'to_mode': 'QUARANTINE',
                'reason': reason,
                'trace_id': trace_id,
                'drawdown_max': drawdown_max,
                'consecutive_losses': consecutive_losses
            }
        else:
            # Healthy LIVE strategy - no change
            logger.debug(f"Strategy {strategy_id} healthy in LIVE mode (DD={drawdown_max:.2f}%, CL={consecutive_losses})")
            return {
                'action': 'no_change',
                'current_mode': 'LIVE',
                'drawdown_max': drawdown_max,
                'consecutive_losses': consecutive_losses
            }
    
    def _evaluate_quarantine(self, strategy_id: str, ranking: Dict) -> Dict[str, Any]:
        """
        Evaluate QUARANTINE strategy for recovery to SHADOW.
        
        Recovery conditions:
        - Drawdown < 3% AND
        - Consecutive Losses < 5
        - At least 50 trades completed
        """
        drawdown_max = ranking.get('drawdown_max', 0.0)
        consecutive_losses = ranking.get('consecutive_losses', 0)
        completed_last_50 = ranking.get('completed_last_50', 0)
        profit_factor = ranking.get('profit_factor', 0.0)
        
        # Check recovery conditions
        drawdown_recovered = drawdown_max < self.DRAWDOWN_THRESHOLD
        losses_recovered = consecutive_losses < self.CONSECUTIVE_LOSSES_THRESHOLD
        has_enough_trades = completed_last_50 >= self.MIN_TRADES_FOR_PROMOTION
        
        if drawdown_recovered and losses_recovered and has_enough_trades:
            # RECOVERY to SHADOW
            trace_id = self._recover_strategy(strategy_id, ranking)
            logger.critical(
                f"[TRACE_ID: {trace_id}] Strategy {strategy_id} recovered to SHADOW for re-evaluation. "
                f"DD={drawdown_max:.2f}%, CL={consecutive_losses}"
            )
            
            return {
                'action': 'recovered',
                'from_mode': 'QUARANTINE',
                'to_mode': 'SHADOW',
                'reason': 'risk_metrics_normalized',
                'trace_id': trace_id,
                'drawdown_max': drawdown_max,
                'consecutive_losses': consecutive_losses
            }
        else:
            # Still in quarantine
            failing_checks = []
            if not drawdown_recovered:
                failing_checks.append(f"DD {drawdown_max:.2f}% >= {self.DRAWDOWN_THRESHOLD}%")
            if not losses_recovered:
                failing_checks.append(f"CL {consecutive_losses} >= {self.CONSECUTIVE_LOSSES_THRESHOLD}")
            if not has_enough_trades:
                failing_checks.append(f"Trades {completed_last_50} < {self.MIN_TRADES_FOR_PROMOTION}")
            
            logger.debug(f"Strategy {strategy_id} remains QUARANTINE: {', '.join(failing_checks)}")
            return {
                'action': 'no_change',
                'current_mode': 'QUARANTINE',
                'failing_checks': failing_checks,
                'drawdown_max': drawdown_max,
                'consecutive_losses': consecutive_losses
            }
    
    def _promote_strategy(self, strategy_id: str, ranking: Dict) -> str:
        """
        Execute promotion from SHADOW to LIVE.
        
        Returns:
            trace_id for audit trail
        """
        trace_id = self.storage.update_strategy_execution_mode(
            strategy_id, 'LIVE', trace_id=None
        )
        
        # Log state change for audit
        self.storage.log_strategy_state_change(
            strategy_id=strategy_id,
            old_mode='SHADOW',
            new_mode='LIVE',
            trace_id=trace_id,
            reason='promotion_criteria_met',
            metrics={
                'profit_factor': ranking.get('profit_factor'),
                'win_rate': ranking.get('win_rate'),
                'total_trades': ranking.get('total_trades'),
                'completed_last_50': ranking.get('completed_last_50')
            }
        )
        
        logger.critical(
            f"✅ [TRACE_ID: {trace_id}] PROMOTION: {strategy_id} "
            f"SHADOW -> LIVE (PF={ranking.get('profit_factor', 0):.2f}, "
            f"WR={ranking.get('win_rate', 0):.1%})"
        )
        
        return trace_id
    
    def _degrade_strategy(self, strategy_id: str, ranking: Dict, reason: str) -> str:
        """
        Execute degradation from LIVE to QUARANTINE.
        
        Args:
            strategy_id: Strategy identifier
            ranking: Current ranking data
            reason: Reason code for degradation
            
        Returns:
            trace_id for audit trail
        """
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
                'drawdown_max': ranking.get('drawdown_max'),
                'consecutive_losses': ranking.get('consecutive_losses'),
                'total_trades': ranking.get('total_trades')
            }
        )
        
        return trace_id
    
    def _recover_strategy(self, strategy_id: str, ranking: Dict) -> str:
        """
        Execute recovery from QUARANTINE to SHADOW.
        
        Returns:
            trace_id for audit trail
        """
        trace_id = self.storage.update_strategy_execution_mode(
            strategy_id, 'SHADOW', trace_id=None
        )
        
        # Log state change
        self.storage.log_strategy_state_change(
            strategy_id=strategy_id,
            old_mode='QUARANTINE',
            new_mode='SHADOW',
            trace_id=trace_id,
            reason='risk_recovery_confirmed',
            metrics={
                'drawdown_max': ranking.get('drawdown_max'),
                'consecutive_losses': ranking.get('consecutive_losses'),
                'profit_factor': ranking.get('profit_factor')
            }
        )
        
        return trace_id
    
    def batch_evaluate(self, strategy_ids: list) -> Dict[str, Dict[str, Any]]:
        """
        Evaluate multiple strategies in batch.
        
        Args:
            strategy_ids: List of strategy identifiers
            
        Returns:
            Dictionary mapping strategy_id to evaluation result
        """
        results = {}
        for strategy_id in strategy_ids:
            try:
                results[strategy_id] = self.evaluate_and_rank(strategy_id)
            except Exception as e:
                logger.error(f"Error evaluating strategy {strategy_id}: {e}")
                results[strategy_id] = {'action': 'error', 'error': str(e)}
        
        return results
    
    def get_live_strategies(self) -> list:
        """Get all strategies currently in LIVE mode."""
        return self.storage.get_strategies_by_mode('LIVE')
    
    def get_shadow_strategies(self) -> list:
        """Get all strategies currently in SHADOW mode."""
        return self.storage.get_strategies_by_mode('SHADOW')
    
    def get_quarantine_strategies(self) -> list:
        """Get all strategies currently in QUARANTINE mode."""
        return self.storage.get_strategies_by_mode('QUARANTINE')
