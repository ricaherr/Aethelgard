import json
import logging
import sqlite3
from typing import Dict, List, Optional
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

class MarketMixin(BaseRepository):
    """Mixin for Market State and Coherence database operations."""

    def log_market_state(self, state_data: Dict) -> None:
        """Log market state data"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO market_state (symbol, data)
                VALUES (?, ?)
            """, (state_data.get('symbol'), json.dumps(state_data)))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_market_state_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get market state history for a symbol"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM market_state 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (symbol, limit))
            rows = cursor.fetchall()
            history = []
            for row in rows:
                state = dict(row)
                state['data'] = json.loads(state['data'])
                history.append(state)
            return history
        finally:
            self._close_conn(conn)

    def log_coherence_event(self, signal_id: Optional[str], symbol: str, timeframe: Optional[str],
                           strategy: Optional[str], stage: str, status: str, incoherence_type: Optional[str],
                           reason: str, details: Optional[str], connector_type: Optional[str]) -> None:
        """Log coherence monitoring event"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO coherence_events 
                (signal_id, symbol, timeframe, strategy, stage, status, incoherence_type, reason, details, connector_type)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (signal_id, symbol, timeframe, strategy, stage, status, incoherence_type, reason, details, connector_type))
            conn.commit()
        finally:
            self._close_conn(conn)

    def _clear_ghost_position_inline(self, symbol: str) -> None:
        """
        Clear ghost position inline (fused logic, no separate function).
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE signals 
                SET status = 'CLOSED', 
                    metadata = json_set(COALESCE(metadata, '{}'), '$.exit_reason', 'GHOST_CLEARED')
                WHERE symbol = ? 
                AND status = 'EXECUTED'
                AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
            """, (symbol,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error clearing ghost position for {symbol}: {e}")
        finally:
            self._close_conn(conn)
