"""
strategies_db.py — Strategy Metadata and Affinity Score Management

Responsibility: CRUD operations for:
  - strategies table (class_id, mnemonic, affinity_scores JSON, market_whitelist)
  - strategy_performance_logs table (learning logs for asset efficiency)

Dependency Injection: StorageManager (no direct DB connections)
Single Source of Truth: All affinity_scores stored in DB (SSOT)

TRACE_ID: EXEC-EFFICIENCY-SCORE-001
"""
import json
import logging
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class StrategiesMixin(BaseRepository):
    """Mixin for strategy metadata and affinity score database operations."""

    # ── Strategy Registry (CRUD) ──────────────────────────────────────────────

    def create_strategy(
        self,
        class_id: str,
        mnemonic: str,
        version: str = "1.0",
        affinity_scores: Optional[Dict[str, float]] = None,
        market_whitelist: Optional[List[str]] = None,
        description: Optional[str] = None
    ) -> bool:
        """
        Create a new strategy record in the database.
        
        Args:
            class_id: Unique strategy identifier (e.g., 'BRK_OPEN_0001')
            mnemonic: Human-readable name (e.g., 'BRK_OPEN_NY_STRIKE')
            version: Version string (default '1.0')
            affinity_scores: Dict mapping assets to efficiency scores (0-1)
            market_whitelist: List of allowed assets for this strategy
            description: Optional description
            
        Returns:
            True if successful, raises exception on conflict
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            affinity_json = json.dumps(affinity_scores or {})
            whitelist_json = json.dumps(market_whitelist or [])
            
            cursor.execute("""
                INSERT INTO strategies (
                    class_id, mnemonic, version, affinity_scores,
                    market_whitelist, description
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                class_id,
                mnemonic,
                version,
                affinity_json,
                whitelist_json,
                description
            ))
            conn.commit()
            logger.info(f"Strategy created: {class_id} ({mnemonic})")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Strategy {class_id} already exists: {e}")
            raise
        except Exception as e:
            logger.error(f"Error creating strategy: {e}")
            raise
        finally:
            self._close_conn(conn)

    def get_strategy(self, class_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve strategy metadata by class_id.
        
        Returns:
            Dict with strategy data, or None if not found
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategies WHERE class_id = ?
            """, (class_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            result = dict(row)
            # Parse JSON fields
            result['affinity_scores'] = json.loads(result.get('affinity_scores', '{}'))
            result['market_whitelist'] = json.loads(result.get('market_whitelist', '[]'))
            return result
        finally:
            self._close_conn(conn)

    def get_all_strategies(self) -> List[Dict[str, Any]]:
        """Retrieve all strategies with parsed JSON fields."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM strategies ORDER BY created_at DESC")
            rows = cursor.fetchall()
            
            results = []
            for row in rows:
                result = dict(row)
                result['affinity_scores'] = json.loads(result.get('affinity_scores', '{}'))
                result['market_whitelist'] = json.loads(result.get('market_whitelist', '[]'))
                results.append(result)
            return results
        finally:
            self._close_conn(conn)

    def update_strategy_affinity_scores(
        self,
        class_id: str,
        affinity_scores: Dict[str, float]
    ) -> bool:
        """
        Update affinity_scores for a strategy.
        Called by learning system after strategy_performance_logs aggregation.
        
        Args:
            class_id: Strategy identifier
            affinity_scores: Dict mapping assets to scores (0-1)
            
        Returns:
            True if successful
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            affinity_json = json.dumps(affinity_scores)
            
            cursor.execute("""
                UPDATE strategies
                SET affinity_scores = ?, updated_at = CURRENT_TIMESTAMP
                WHERE class_id = ?
            """, (affinity_json, class_id))
            
            conn.commit()
            logger.info(f"Affinity scores updated for {class_id}: {affinity_scores}")
            return True
        except Exception as e:
            logger.error(f"Error updating affinity scores: {e}")
            return False
        finally:
            self._close_conn(conn)

    def update_strategy_market_whitelist(
        self,
        class_id: str,
        market_whitelist: List[str]
    ) -> bool:
        """
        Update market_whitelist for a strategy.
        
        Args:
            class_id: Strategy identifier
            market_whitelist: List of allowed assets
            
        Returns:
            True if successful
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            whitelist_json = json.dumps(market_whitelist)
            
            cursor.execute("""
                UPDATE strategies
                SET market_whitelist = ?, updated_at = CURRENT_TIMESTAMP
                WHERE class_id = ?
            """, (whitelist_json, class_id))
            
            conn.commit()
            logger.info(f"Market whitelist updated for {class_id}: {market_whitelist}")
            return True
        except Exception as e:
            logger.error(f"Error updating market whitelist: {e}")
            return False
        finally:
            self._close_conn(conn)

    # ── Affinity Score Queries (for StrategyGatekeeper) ──────────────────────

    def get_strategy_affinity_scores(self, class_id: Optional[str] = None) -> Dict[str, float]:
        """
        Retrieve affinity scores for a strategy (or all strategies).
        Used by StrategyGatekeeper to load in-memory cache.
        
        Args:
            class_id: If provided, return scores for that strategy only.
                     If None, aggregate scores across all strategies.
                     
        Returns:
            Dict mapping assets to average efficiency scores
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            if class_id:
                cursor.execute("""
                    SELECT affinity_scores FROM strategies WHERE class_id = ?
                """, (class_id,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0] or '{}')
                return {}
            else:
                # Aggregate: average affinity scores across all strategies
                cursor.execute("SELECT affinity_scores FROM strategies")
                rows = cursor.fetchall()
                
                aggregated = {}
                total_count = 0
                for row in rows:
                    scores = json.loads(row[0] or '{}')
                    total_count += 1
                    for asset, score in scores.items():
                        if asset not in aggregated:
                            aggregated[asset] = []
                        aggregated[asset].append(score)
                
                # Calculate average
                result = {}
                for asset, scores in aggregated.items():
                    result[asset] = sum(scores) / len(scores) if scores else 0.0
                return result
        finally:
            self._close_conn(conn)

    def get_market_whitelist(self, class_id: str) -> List[str]:
        """Retrieve market_whitelist for a strategy."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT market_whitelist FROM strategies WHERE class_id = ?
            """, (class_id,))
            row = cursor.fetchone()
            if row:
                return json.loads(row[0] or '[]')
            return []
        finally:
            self._close_conn(conn)

    # ── Performance Logging (for Learning) ────────────────────────────────────

    def save_strategy_performance_log(
        self,
        strategy_id: str,
        asset: str,
        pnl: float,
        trades_count: int,
        win_rate: float,
        profit_factor: float,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Log strategy performance for a specific asset.
        Called after each trade or batch of trades.
        
        Args:
            strategy_id: Strategy class_id
            asset: Asset symbol (e.g., 'EUR/USD')
            pnl: Profit/Loss amount
            trades_count: Number of trades in this log
            win_rate: Win rate (0-1)
            profit_factor: Profit Factor (P&L wins / |P&L losses|)
            trace_id: Optional trace ID for auditing
            
        Returns:
            True if successful
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO strategy_performance_logs (
                    strategy_id, asset, pnl, trades_count,
                    win_rate, profit_factor, trace_id, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """, (
                strategy_id,
                asset,
                pnl,
                trades_count,
                win_rate,
                profit_factor,
                trace_id
            ))
            conn.commit()
            logger.debug(f"Performance logged: {strategy_id}@{asset} | PnL: {pnl}, WR: {win_rate:.2%}")
            return True
        except Exception as e:
            logger.error(f"Error saving performance log: {e}")
            return False
        finally:
            self._close_conn(conn)

    def get_asset_performance_history(
        self,
        strategy_id: str,
        asset: str,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Retrieve performance history for a strategy-asset pair.
        Used for calculating affinity scores dynamically.
        
        Args:
            strategy_id: Strategy class_id
            asset: Asset symbol
            limit: Max records to return
            
        Returns:
            List of performance logs sorted by timestamp DESC
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM strategy_performance_logs
                WHERE strategy_id = ? AND asset = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (strategy_id, asset, limit))
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def calculate_asset_affinity_score(
        self,
        strategy_id: str,
        asset: str,
        lookback_trades: int = 50
    ) -> float:
        """
        Calculate affinity score for an asset based on recent performance.
        
        Algorithm:
            - Retrieve last N trades for this strategy-asset combination
            - Weight by: (win_rate * 0.5) + (profit_factor / 2.0 * 0.3) + (recent_momentum * 0.2)
            - Scale to 0-1 range
            
        Returns:
            Score between 0.0 and 1.0
        """
        logs = self.get_asset_performance_history(
            strategy_id=strategy_id,
            asset=asset,
            limit=lookback_trades
        )
        
        if not logs:
            return 0.5  # Neutral score for unknown assets
        
        # Aggregate metrics
        total_trades = sum(log['trades_count'] for log in logs)
        if total_trades == 0:
            return 0.5
        
        # Weighted average of win rates
        avg_win_rate = sum(log['win_rate'] * log['trades_count'] for log in logs) / total_trades
        
        # Weighted average of profit factors
        avg_profit_factor = sum(log['profit_factor'] * log['trades_count'] for log in logs) / total_trades
        
        # Normalize profit_factor to 0-1 (cap at 2.0 = 1.0 score)
        pf_score = min(avg_profit_factor / 2.0, 1.0)
        
        # Calculate momentum (recent > old)
        if len(logs) > 1:
            recent = logs[0]['profit_factor']
            older = logs[-1]['profit_factor']
            momentum = (recent - older) / max(abs(older), 0.1) if older != 0 else 0
            momentum = min(max(momentum, -1.0), 1.0) / 2.0 + 0.5  # Scale to 0-1
        else:
            momentum = 0.5
        
        # Composite score: win_rate weight, profit_factor weight, momentum weight
        affinity_score = (avg_win_rate * 0.5) + (pf_score * 0.3) + (momentum * 0.2)
        
        logger.debug(
            f"Affinity score calculated for {strategy_id}@{asset}: {affinity_score:.2f} "
            f"(WR: {avg_win_rate:.2%}, PF: {avg_profit_factor:.2f}, Momentum: {momentum:.2f})"
        )
        
        return affinity_score

    def get_performance_summary(
        self,
        strategy_id: str,
        lookback_days: int = 30
    ) -> Dict[str, Any]:
        """
        Get aggregated performance summary for a strategy across all assets.
        
        Returns:
            Dict with asset-level metrics and overall stats
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Query recent logs
            cursor.execute("""
                SELECT asset, SUM(pnl) as total_pnl,
                       SUM(trades_count) as total_trades,
                       AVG(win_rate) as avg_win_rate,
                       AVG(profit_factor) as avg_profit_factor
                FROM strategy_performance_logs
                WHERE strategy_id = ? AND timestamp > datetime('now', '-' || ? || ' days')
                GROUP BY asset
                ORDER BY total_pnl DESC
            """, (strategy_id, lookback_days))
            
            rows = cursor.fetchall()
            summary = {
                'strategy_id': strategy_id,
                'period_days': lookback_days,
                'assets': {},
                'total_pnl': 0.0,
                'total_trades': 0
            }
            
            for row in rows:
                asset_data = dict(row)
                summary['assets'][asset_data['asset']] = asset_data
                summary['total_pnl'] += asset_data['total_pnl'] or 0
                summary['total_trades'] += asset_data['total_trades'] or 0
            
            return summary
        finally:
            self._close_conn(conn)
