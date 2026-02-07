import uuid
import logging
import sqlite3
from typing import Dict, List, Optional
from datetime import date
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

class TradesMixin(BaseRepository):
    """Mixin for Trade-related database operations."""

    def save_trade_result(self, trade_data: Dict) -> None:
        """Save trade result to database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Accept both 'profit' and 'profit_loss' for compatibility
            profit = trade_data.get('profit') or trade_data.get('profit_loss')
            # Use provided ID (ticket from broker) or generate UUID as fallback
            trade_id = trade_data.get('id') or str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO trade_results (
                    id, signal_id, symbol, entry_price, exit_price, 
                    profit, exit_reason, close_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                trade_data.get('signal_id'),
                trade_data.get('symbol'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                profit,
                trade_data.get('exit_reason'),
                trade_data.get('close_time')
            ))
            conn.commit()
        finally:
            self._close_conn(conn)
    
    def trade_exists(self, ticket_id: str) -> bool:
        """Check if a trade with given ticket_id already exists in database."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM trade_results WHERE id = ? LIMIT 1",
                (ticket_id,)
            )
            result = cursor.fetchone()
            return result is not None
        finally:
            self._close_conn(conn)

    def get_trade_results(self, limit: int = 100) -> List[Dict]:
        """Get trade results from database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                ORDER BY close_time DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def has_open_position(self, symbol: str) -> bool:
        """Check if there's an open position for the given symbol"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM signals 
                WHERE symbol = ? 
                AND UPPER(status) = 'EXECUTED'
                AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
            """, (symbol,))
            count = cursor.fetchone()[0]
            return count > 0
        finally:
            self._close_conn(conn)

    def get_recent_trades(self, limit: int = 10) -> List[Dict]:
        """Get recent trades"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                WHERE profit IS NOT NULL
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            trades = []
            for row in rows:
                profit = row[5]
                if profit is not None:
                    trade = {
                        'id': row[0],
                        'signal_id': row[1],
                        'symbol': row[2],
                        'entry_price': row[3],
                        'exit_price': row[4],
                        'profit_loss': profit, 
                        'profit': profit,       
                        'exit_reason': row[6],
                        'close_time': row[7],
                        'created_at': row[8],
                        'is_win': profit > 0,
                        'pips': abs(profit) * 100  
                    }
                    trades.append(trade)
            return trades
        finally:
            self._close_conn(conn)

    def get_total_profit(self, days: int = 30) -> float:
        """Get total profit for the last N days"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(profit), 0) 
                FROM trade_results 
                WHERE created_at >= datetime('now', '-{} days')
            """.format(days))
            result = cursor.fetchone()[0]
            return float(result) if result else 0.0
        finally:
            self._close_conn(conn)

    def get_win_rate(self, days: int = 30) -> float:
        """Get win rate for the last N days"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 
                    COUNT(CASE WHEN profit > 0 THEN 1 END) as wins,
                    COUNT(CASE WHEN profit < 0 THEN 1 END) as losses
                FROM trade_results 
                WHERE created_at >= datetime('now', '-{} days')
            """.format(days))
            row = row = cursor.fetchone()
            wins = row[0] if row[0] else 0
            losses = row[1] if row[1] else 0
            total_trades = wins + losses
            return (wins / total_trades) if total_trades > 0 else 0.0
        finally:
            self._close_conn(conn)

    def get_profit_by_symbol(self, days: int = 30) -> Dict[str, float]:
        """Get total profit grouped by symbol for the last N days"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, SUM(profit) as total_profit
                FROM trade_results 
                WHERE created_at >= datetime('now', '-{} days')
                GROUP BY symbol
                ORDER BY total_profit DESC
            """.format(days))
            rows = cursor.fetchall()
            return {row[0]: float(row[1]) for row in rows}
        finally:
            self._close_conn(conn)

    def get_all_trades(self, limit: int = 1000) -> List[Dict]:
        """Get all trade results with optional limit"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM trade_results 
                ORDER BY created_at DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)
