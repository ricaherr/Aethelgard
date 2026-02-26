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

    def get_trade_result_by_signal_id(self, signal_id: str) -> Optional[Dict]:
        """Get a trade result by its signal ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM trade_results WHERE signal_id = ? LIMIT 1", (signal_id,))
            row = cursor.fetchone()
            if row:
                res = dict(row)
                # Normalize profit field
                if 'profit' in res:
                    res['profit_loss'] = res['profit']
                return res
            return None
        finally:
            self._close_conn(conn)

    def has_open_position(self, symbol: str, timeframe: Optional[str] = None) -> bool:
        """
        Check if there's an open position for the given symbol.
        
        Args:
            symbol: Trading symbol to check
            timeframe: Optional timeframe filter. If provided, only checks positions on that specific timeframe.
                      This allows independent positions on different timeframes for the same symbol.
        
        Returns:
            True if open position exists, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if timeframe:
                # Filter by both symbol AND timeframe (allows multi-timeframe positions)
                cursor.execute("""
                    SELECT COUNT(*) FROM signals 
                    WHERE symbol = ? 
                    AND timeframe = ?
                    AND UPPER(status) = 'EXECUTED'
                    AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
                """, (symbol, timeframe))
            else:
                # Legacy behavior: check any timeframe (for backward compatibility)
                cursor.execute("""
                    SELECT COUNT(*) FROM signals 
                    WHERE symbol = ? 
                    AND UPPER(status) = 'EXECUTED'
                    AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
                """, (symbol,))
            count = cursor.fetchone()[0]
            # print(f"DEBUG DB: has_open_position({symbol}, {timeframe}) -> {count}")
            if count > 0:
                logger.info(f"DEBUG DB: has_open_position({symbol}, {timeframe}) -> TRUE (Count: {count})")
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
                WHERE created_at >= datetime('now', '-{} days', 'utc')
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
                WHERE created_at >= datetime('now', '-{} days', 'utc')
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
                WHERE created_at >= datetime('now', '-{} days', 'utc')
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

    # ── Position Metadata ─────────────────────────────────────────────────────

    def get_position_metadata(self, ticket: int) -> Optional[Dict]:
        """Get metadata for a specific position/trade by ticket. Returns None if not found."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='position_metadata'"
            )
            if not cursor.fetchone():
                return None
            cursor.execute("SELECT * FROM position_metadata WHERE ticket = ?", (ticket,))
            row = cursor.fetchone()
            if not row:
                return None
            metadata = dict(row)
            if metadata.get("data"):
                try:
                    import json as _json
                    metadata["data"] = _json.loads(metadata["data"])
                except (ValueError, TypeError):
                    pass
            return metadata
        finally:
            self._close_conn(conn)

    def update_position_metadata(self, ticket: int, metadata: Dict) -> bool:
        """Save or update position metadata for monitoring. Merges with existing data."""
        import json as _json

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            existing = self.get_position_metadata(ticket)
            merged = {**(existing or {}), **metadata, "ticket": ticket}

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS position_metadata (
                    ticket INTEGER PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    entry_time TEXT NOT NULL,
                    direction TEXT,
                    sl REAL,
                    tp REAL,
                    volume REAL NOT NULL,
                    initial_risk_usd REAL,
                    entry_regime TEXT,
                    timeframe TEXT,
                    strategy TEXT,
                    data TEXT
                )
            """)

            # AUTO-MIGRATION: ensure optional columns exist
            for col in ("direction", "strategy"):
                try:
                    cursor.execute(f"SELECT {col} FROM position_metadata LIMIT 1")
                except Exception:
                    cursor.execute(f"ALTER TABLE position_metadata ADD COLUMN {col} TEXT")
                    conn.commit()

            cursor.execute("""
                REPLACE INTO position_metadata
                (ticket, symbol, entry_price, entry_time, direction, sl, tp, volume,
                 initial_risk_usd, entry_regime, timeframe, strategy, data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket,
                merged.get("symbol"), merged.get("entry_price"), merged.get("entry_time"),
                merged.get("direction"), merged.get("sl"), merged.get("tp"), merged.get("volume"),
                merged.get("initial_risk_usd"), merged.get("entry_regime"),
                merged.get("timeframe"), merged.get("strategy"),
                _json.dumps({k: v for k, v in merged.items() if k not in {
                    "ticket", "symbol", "entry_price", "entry_time", "direction",
                    "sl", "tp", "volume", "initial_risk_usd", "entry_regime", "timeframe", "strategy"
                }}) or None,
            ))
            conn.commit()
            return True
        except Exception as exc:
            logger.error("Failed to save position metadata for ticket %s: %s", ticket, exc, exc_info=True)
            return False
        finally:
            self._close_conn(conn)

    def rollback_position_modification(self, ticket: int) -> bool:
        """No-op: metadata is preserved even if MT5 modification fails."""
        logger.debug("[ROLLBACK] Position %s — metadata preserved (no-op)", ticket)
        return True

    def log_position_event(
        self,
        ticket: int,
        symbol: str,
        event_type: str,
        old_sl: Optional[float] = None,
        new_sl: Optional[float] = None,
        old_tp: Optional[float] = None,
        new_tp: Optional[float] = None,
        reason: Optional[str] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> bool:
        """Log position management event (SL/TP change, breakeven, trailing, etc.)."""
        import json as _json

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO position_history
                (ticket, symbol, event_type, old_sl, new_sl, old_tp, new_tp,
                 reason, success, error_message, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                ticket, symbol, event_type, old_sl, new_sl, old_tp, new_tp,
                reason, success, error_message,
                _json.dumps(metadata) if metadata else None,
            ))
            conn.commit()
            logger.debug("[HISTORY] %s for %s (%s) SL:%s→%s TP:%s→%s",
                         event_type, ticket, symbol, old_sl, new_sl, old_tp, new_tp)
            return True
        except Exception as exc:
            logger.error("[HISTORY] Failed to log event for %s: %s", ticket, exc)
            return False
        finally:
            self._close_conn(conn)

    def get_position_history(
        self,
        ticket: Optional[int] = None,
        symbol: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get position history events, newest first."""
        import json as _json

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM position_history WHERE 1=1"
            params: list = []
            if ticket:
                query += " AND ticket = ?"
                params.append(ticket)
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            events = []
            for row in cursor.fetchall():
                evt = dict(row)
                if evt.get("metadata"):
                    try:
                        evt["metadata"] = _json.loads(evt["metadata"])
                    except Exception:
                        pass
                events.append(evt)
            return events
        finally:
            self._close_conn(conn)

    def clear_ghost_position(self, symbol: str) -> None:
        """
        Remove 'EXECUTED' status from signals for a symbol that has no real open position.
        This fixes the 'ghost position' issue where DB thinks a trade is open but MT5 doesn't.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # logger.warning(f"🧹 Clearing ghost positions for {symbol} (Marking as REJECTED)")
            
            # Using basic UPDATE first, json_patch might be sqlite extension dependent
            # If json_patch is not available, just update status
            cursor.execute("""
                UPDATE signals 
                SET status = 'REJECTED'
                WHERE symbol = ? 
                AND status = 'EXECUTED'
                AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
            """, (symbol,))
            
            if cursor.rowcount > 0:
                logger.info(f"🧹 Cleared {cursor.rowcount} ghost positions for {symbol}")
                conn.commit()
        except Exception as e:
            logger.error(f"Error clearing ghost positions: {e}")
        finally:
            self._close_conn(conn)
