"""
Strategy Ranker - Darwinismo Algorítmico (Shadow Ranking System)
Manages strategy evolution: SHADOW -> LIVE -> QUARANTINE and recovery cycles.
Includes regime-aware metric weighting for dynamic EDGE selection.
"""
import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from decimal import Decimal

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
    
    Weighted Scoring by Regime:
    - Introduced: Dynamic metric weighting based on market regime (TREND, RANGE, VOLATILE)
    - Enables EDGE selection: High DD + High Sharpe strategies are rewarded in VOLATILE regimes
    - Math: Score = Σ (Metric_n × Weight_n) where metrics normalized to [0, 1]
    - Weights sourced from regime_configs table (SSOT principle)
    
    Example Weighting:
    - TREND: WR=25%, Sharpe=35%, PF=30%, DD=10% → favors consistent wins
    - RANGE: WR=40%, Sharpe=25%, PF=25%, DD=10% → prioritizes consistency
    - VOLATILE: WR=20%, Sharpe=50%, PF=20%, DD=10% → rewards risk-adjusted returns
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
    
    def calculate_weighted_score(self, strategy_id: str, current_regime: str) -> Decimal:
        """
        Calculate weighted score for a strategy based on current market regime.
        
        Formula: Score = Σ (Metric_n × Weight_n)
        
        where:
        - Metrics are normalized to [0, 1] range
        - Weights vary by regime (from regime_configs table)
        - Drawdown is inverted (higher is worse, so we use 1 - normalized_dd)
        
        Args:
            strategy_id: Strategy identifier
            current_regime: Market regime (TREND, RANGE, VOLATILE)
            
        Returns:
            Decimal score (0-1 range, 4+ decimal places precision)
        """
        # Fetch strategy ranking metrics
        ranking = self.storage.get_strategy_ranking(strategy_id)
        if not ranking:
            logger.warning(f"Strategy {strategy_id} not found for weighted ranking")
            return Decimal('0.0')
        
        try:
            # Get regime weights from DB
            weights_dict = self.storage.get_regime_weights(current_regime)
            if not weights_dict:
                logger.warning(f"No regime weights found for regime: {current_regime}")
                return Decimal('0.0')
            
            # Convert weights to Decimal
            weights = {k: Decimal(str(v)) for k, v in weights_dict.items()}
            
            # Normalize metrics
            normalized = self._normalize_metrics(ranking)
            
            # Calculate weighted sum: Σ (Metric_n × Weight_n)
            score = Decimal('0.0')
            for metric_name, weight in weights.items():
                metric_value = normalized.get(metric_name, Decimal('0.0'))
                contribution = metric_value * weight
                score += contribution
                logger.debug(
                    f"Metric {metric_name}: {metric_value:.4f} × {weight:.4f} = {contribution:.4f}"
                )
            
            # Ensure score is in [0, 1] range
            score = max(Decimal('0.0'), min(score, Decimal('1.0')))
            
            logger.info(
                f"Strategy {strategy_id} weighted score in {current_regime}: {score:.4f}"
            )
            return score
            
        except Exception as e:
            logger.error(f"Error calculating weighted score for {strategy_id}: {e}")
            return Decimal('0.0')
    
    def _normalize_metrics(self, ranking: Dict[str, Any]) -> Dict[str, Decimal]:
        """
        Normalize metric values to [0, 1] range for scoring.
        
        Normalization rules:
        - win_rate: Already [0, 1], just ensure bounds
        - profit_factor: Normalize by dividing by max expected (~3.0) and capping at 1.0
        - sharpe_ratio: Normalize by dividing by max expected (5.0, rarely exceeded) and capping at 1.0
        - drawdown_max: Invert (1 - dd/100) to penalize higher drawdown
        
        Args:
            ranking: Dictionary of raw metrics from DB
            
        Returns:
            Dictionary of normalized metrics [0, 1]
        """
        normalized = {}
        
        # Win Rate: already 0-1
        win_rate = Decimal(str(ranking.get('win_rate', 0.0)))
        normalized['win_rate'] = max(Decimal('0.0'), min(win_rate, Decimal('1.0')))
        
        # Profit Factor: normalize by typical max (3.0)
        pf = Decimal(str(ranking.get('profit_factor', 0.0)))
        pf_max = Decimal('3.0')
        normalized['profit_factor'] = min(pf / pf_max, Decimal('1.0'))
        
        # Sharpe Ratio: normalize by reasonable max (5.0)
        # Rationale: Sharpe > 5.0 is extremely rare; treat as outlier
        sharpe = Decimal(str(ranking.get('sharpe_ratio', 0.0)))
        sharpe_max = Decimal('5.0')
        normalized['sharpe_ratio'] = min(sharpe / sharpe_max, Decimal('1.0'))
        
        # Drawdown: invert (higher DD is worse, so 1 - normalized_DD)
        dd = Decimal(str(ranking.get('drawdown_max', 0.0)))
        dd_normalized = Decimal('1.0') - (dd / Decimal('100.0'))
        normalized['drawdown_max'] = max(Decimal('0.0'), dd_normalized)
        
        logger.debug(f"Normalized metrics: {normalized}")
        return normalized
    
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
