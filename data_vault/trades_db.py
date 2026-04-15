import uuid
import logging
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import date
from .base_repo import BaseRepository
from models.execution_mode import ExecutionMode, Provider, AccountType

logger = logging.getLogger(__name__)

class TradesMixin(BaseRepository):
    """Mixin for Trade-related database operations.

    Key Design Patterns:
    - All query methods (get_*_profit, get_win_rate, etc.) default to execution_mode='LIVE'
      to maintain backward compatibility and avoid contaminating metrics with paper usr_trades.
    - StrategyRanker must explicitly call get_usr_trades(execution_mode='SHADOW') to analyze SHADOW usr_trades.
    - save_trade_result() accepts execution_mode, provider, account_type for full audit trail.
    """

    def save_trade_result(self, trade_data: Dict[str, Any]) -> None:
        """Save trade result to the appropriate table based on execution_mode.

        Routing (SPRINT 22 — sys_trades migration):
        - LIVE             → usr_trades  (Capa 1, trader-owned performance)
        - SHADOW/BACKTEST  → sys_trades  (Capa 0, system-managed paper trades)

        This transparent routing maintains backward compatibility for callers
        that pass execution_mode='SHADOW' via this method.

        Args:
            trade_data: Dict with trade details including execution_mode, provider, account_type
        """
        mode = trade_data.get('execution_mode', ExecutionMode.default())
        if mode in (ExecutionMode.SHADOW.value, 'BACKTEST'):
            # Route paper trades to sys_trades (Capa 0) to keep usr_trades LIVE-only.
            self.save_sys_trade(trade_data)
            return

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Accept both 'profit' and 'profit_loss' for compatibility
            profit = trade_data.get('profit') or trade_data.get('profit_loss')
            # Use provided ID (ticket from broker) or generate UUID as fallback
            trade_id = trade_data.get('id') or str(uuid.uuid4())
            cursor.execute("""
                INSERT INTO usr_trades (
                    id, signal_id, symbol, entry_price, exit_price,
                    profit, exit_reason, close_time, execution_mode, provider, account_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                trade_data.get('signal_id'),
                trade_data.get('symbol'),
                trade_data.get('entry_price'),
                trade_data.get('exit_price'),
                profit,
                trade_data.get('exit_reason'),
                trade_data.get('close_time'),
                mode,
                trade_data.get('provider', Provider.default()),
                trade_data.get('account_type', AccountType.default())
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
                "SELECT 1 FROM usr_trades WHERE id = ? LIMIT 1",
                (ticket_id,)
            )
            result = cursor.fetchone()
            return result is not None
        finally:
            self._close_conn(conn)

    def get_trade_results(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get trade results from database (default: LIVE usr_trades only for backward compatibility)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM usr_trades
                WHERE execution_mode = ?
                ORDER BY close_time DESC
                LIMIT ?
            """, (ExecutionMode.LIVE.value, limit,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def get_trade_result_by_signal_id(self, signal_id: str) -> Optional[Dict[str, Any]]:
        """Get a trade result by its signal ID (returns first match, any execution_mode)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usr_trades WHERE signal_id = ? LIMIT 1", (signal_id,))
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
            timeframe: Optional timeframe filter. If provided, only checks usr_positions on that specific timeframe.
                      This allows independent usr_positions on different timeframes for the same symbol.

        Returns:
            True if open position exists, False otherwise
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if timeframe:
                # Filter by both symbol AND timeframe (allows multi-timeframe positions)
                cursor.execute("""
                    SELECT COUNT(*) FROM sys_signals
                    WHERE symbol = ?
                    AND timeframe = ?
                    AND UPPER(status) = 'EXECUTED'
                    AND id NOT IN (SELECT signal_id FROM usr_trades WHERE signal_id IS NOT NULL)
                """, (symbol, timeframe))
            else:
                # Legacy behavior: check any timeframe (for backward compatibility)
                cursor.execute("""
                    SELECT COUNT(*) FROM sys_signals
                    WHERE symbol = ?
                    AND UPPER(status) = 'EXECUTED'
                    AND id NOT IN (SELECT signal_id FROM usr_trades WHERE signal_id IS NOT NULL)
                """, (symbol,))
            result = cursor.fetchone()
            count: int = result[0] if result else 0
            # print(f"DEBUG DB: has_open_position({symbol}, {timeframe}) -> {count}")
            if count > 0:
                logger.info(f"DEBUG DB: has_open_position({symbol}, {timeframe}) -> TRUE (Count: {count})")
            return count > 0
        finally:
            self._close_conn(conn)

    def get_recent_usr_trades(self, limit: int = 10, execution_mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get recent usr_trades, optionally filtered by execution_mode (default: LIVE for backward compat)

        Args:
            limit: Number of recent usr_trades to retrieve
            execution_mode: Optional filter ('LIVE', 'SHADOW'). If None, defaults to 'LIVE'.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if execution_mode is None:
                execution_mode = ExecutionMode.LIVE.value
            cursor.execute("""
                SELECT * FROM usr_trades 
                WHERE profit IS NOT NULL
                AND execution_mode = ?
                ORDER BY created_at DESC 
                LIMIT ?
            """, (execution_mode, limit))
            rows = cursor.fetchall()
            usr_trades = []
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
                    usr_trades.append(trade)
            return usr_trades
        finally:
            self._close_conn(conn)

    def get_total_profit(self, days: int = 30, execution_mode: Optional[str] = None) -> float:
        """Get total profit for the last N days, optionally filtered by execution_mode (default: LIVE).

        Routing (SPRINT 22): SHADOW/BACKTEST queries transparently read from sys_trades.

        Args:
            days: Number of days lookback (default: 30)
            execution_mode: Optional filter ('LIVE', 'SHADOW'). If None, defaults to 'LIVE'.
        """
        if execution_mode is None:
            execution_mode = ExecutionMode.LIVE.value
        # SHADOW/BACKTEST trades live in sys_trades (Capa 0), not usr_trades
        if execution_mode in (ExecutionMode.SHADOW.value, 'BACKTEST'):
            trades = self.get_sys_trades(execution_mode=execution_mode)
            return float(sum(t['profit'] or 0.0 for t in trades if t.get('profit') is not None))
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COALESCE(SUM(profit), 0)
                FROM usr_trades
                WHERE created_at >= datetime('now', '-{} days', 'utc')
                AND execution_mode = ?
            """.format(days), (execution_mode,))
            result = cursor.fetchone()[0]
            return float(result) if result else 0.0
        finally:
            self._close_conn(conn)

    def get_win_rate(self, days: int = 30, execution_mode: Optional[str] = None) -> float:
        """Get win rate for the last N days, optionally filtered by execution_mode (default: LIVE).

        Routing (SPRINT 22): SHADOW/BACKTEST queries transparently read from sys_trades.

        Args:
            days: Number of days lookback (default: 30)
            execution_mode: Optional filter ('LIVE', 'SHADOW'). If None, defaults to 'LIVE'.
        """
        if execution_mode is None:
            execution_mode = ExecutionMode.LIVE.value
        # SHADOW/BACKTEST trades live in sys_trades (Capa 0), not usr_trades
        if execution_mode in (ExecutionMode.SHADOW.value, 'BACKTEST'):
            trades = self.get_sys_trades(execution_mode=execution_mode)
            profits = [t['profit'] for t in trades if t.get('profit') is not None]
            total = len(profits)
            wins = sum(1 for p in profits if p > 0)
            return wins / total if total > 0 else 0.0
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(CASE WHEN profit > 0 THEN 1 END) as wins,
                    COUNT(CASE WHEN profit < 0 THEN 1 END) as losses
                FROM usr_trades
                WHERE created_at >= datetime('now', '-{} days', 'utc')
                AND execution_mode = ?
            """.format(days), (execution_mode,))
            row = cursor.fetchone()
            wins = row[0] if row[0] else 0
            losses = row[1] if row[1] else 0
            total_usr_trades = wins + losses
            return (wins / total_usr_trades) if total_usr_trades > 0 else 0.0
        finally:
            self._close_conn(conn)

    def get_profit_by_symbol(self, days: int = 30, execution_mode: Optional[str] = None) -> Dict[str, float]:
        """Get total profit grouped by symbol for the last N days, optionally filtered by execution_mode (default: LIVE).
        
        Args:
            days: Number of days lookback (default: 30)
            execution_mode: Optional filter ('LIVE', 'SHADOW'). If None, defaults to 'LIVE'.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if execution_mode is None:
                execution_mode = ExecutionMode.LIVE.value
            cursor.execute("""
                SELECT symbol, SUM(profit) as total_profit
                FROM usr_trades 
                WHERE created_at >= datetime('now', '-{} days', 'utc')
                AND execution_mode = ?
                GROUP BY symbol
                ORDER BY total_profit DESC
            """.format(days), (execution_mode,))
            rows = cursor.fetchall()
            return {row[0]: float(row[1]) for row in rows}
        finally:
            self._close_conn(conn)

    def get_all_usr_trades(self, limit: int = 1000, execution_mode: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get all trade results with optional limit, optionally filtered by execution_mode (default: LIVE).

        Args:
            limit: Maximum number of usr_trades to retrieve (default: 1000)
            execution_mode: Optional filter ('LIVE', 'SHADOW'). If None, defaults to 'LIVE'.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if execution_mode is None:
                execution_mode = ExecutionMode.LIVE.value
            cursor.execute("""
                SELECT * FROM usr_trades 
                WHERE execution_mode = ?
                ORDER BY created_at DESC 
                LIMIT ?
            """, (execution_mode, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    # ── sys_trades (Capa 0) — SHADOW and BACKTEST only ───────────────────────

    def save_sys_trade(self, trade_data: Dict[str, Any]) -> None:
        """Save a SHADOW or BACKTEST trade to sys_trades (Capa 0 — system-managed).

        NEVER call this for LIVE trades — use save_trade_result() instead.
        sys_trades is the source of truth for 3 Pilares evaluation and backtest auditing.

        Args:
            trade_data: Dict with execution_mode ('SHADOW' or 'BACKTEST'), instance_id,
                        account_id, symbol, entry_price, exit_price, profit, etc.
        Raises:
            ValueError: if execution_mode is 'LIVE' (application-layer protection).
        """
        mode = trade_data.get('execution_mode', '')
        if mode == ExecutionMode.LIVE.value:
            raise ValueError(
                "LIVE trades must use save_trade_result() → usr_trades, not save_sys_trade()"
            )
        trade_id = trade_data.get('id') or str(uuid.uuid4())
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sys_trades (
                    id, signal_id, instance_id, account_id, symbol, direction,
                    entry_price, exit_price, profit, exit_reason,
                    open_time, close_time, execution_mode, strategy_id, order_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    trade_id,
                    trade_data.get('signal_id'),
                    trade_data.get('instance_id'),
                    trade_data.get('account_id'),
                    trade_data.get('symbol'),
                    trade_data.get('direction'),
                    trade_data.get('entry_price'),
                    trade_data.get('exit_price'),
                    trade_data.get('profit') or trade_data.get('profit_loss'),
                    trade_data.get('exit_reason'),
                    trade_data.get('open_time'),
                    trade_data.get('close_time'),
                    mode,
                    trade_data.get('strategy_id'),
                    trade_data.get('order_id'),
                ),
            )
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_sys_trades(
        self,
        execution_mode: Optional[str] = None,
        instance_id: Optional[str] = None,
        strategy_id: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        """Query sys_trades with optional filters.

        Used by ShadowManager for 3 Pilares evaluation and by backtest auditing.

        Args:
            execution_mode: Optional filter ('SHADOW' or 'BACKTEST').
            instance_id: Optional filter by shadow instance ID.
            strategy_id: Optional filter by strategy ID.
            limit: Maximum number of records to return (default: 1000).

        Returns:
            List of trade records as dicts, ordered newest first.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM sys_trades WHERE 1=1"
            params: list[Any] = []
            if execution_mode is not None:
                query += " AND execution_mode = ?"
                params.append(execution_mode)
            if instance_id is not None:
                query += " AND instance_id = ?"
                params.append(instance_id)
            if strategy_id is not None:
                query += " AND strategy_id = ?"
                params.append(strategy_id)
            query += " ORDER BY created_at DESC LIMIT ?"
            params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def calculate_sys_trades_metrics(self, instance_id: str) -> Dict[str, Any]:
        """Calculate 3 Pilares metrics for a SHADOW instance from sys_trades.

        Returns dict with: total_trades, win_rate, profit_factor, max_drawdown_pct,
        consecutive_losses_max, equity_curve_cv.

        Args:
            instance_id: Shadow instance identifier to evaluate.
        """
        import statistics as _stats

        trades = self.get_sys_trades(
            execution_mode=ExecutionMode.SHADOW.value,
            instance_id=instance_id,
        )
        if not trades:
            return {
                'total_trades': 0,
                'win_rate': 0.0,
                'profit_factor': 0.0,
                'consecutive_losses_max': 0,
                'equity_curve_cv': 0.0,
            }

        profits = [t['profit'] for t in trades if t.get('profit') is not None]
        total = len(profits)
        wins = [p for p in profits if p > 0]
        losses = [abs(p) for p in profits if p < 0]

        win_rate = len(wins) / total if total > 0 else 0.0
        profit_factor = (
            sum(wins) / sum(losses) if losses else (1.5 if wins else 0.0)
        )

        cumulative = []
        running = 0.0
        for p in profits:
            running += p
            cumulative.append(running)
        mean_equity = _stats.mean(cumulative) if cumulative else 0.0
        equity_cv = (
            (_stats.stdev(cumulative) / abs(mean_equity))
            if len(cumulative) > 1 and mean_equity != 0
            else 0.0
        )

        max_consec = 0
        current_consec = 0
        for p in profits:
            if p < 0:
                current_consec += 1
                max_consec = max(max_consec, current_consec)
            else:
                current_consec = 0

        return {
            'total_trades': total,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'consecutive_losses_max': max_consec,
            'equity_curve_cv': equity_cv,
        }

    # ── Unified Trades Query API ─────────────────────────────────────────────

    def get_usr_trades(self, execution_mode: Optional[str] = None, limit: int = 1000) -> List[Dict[str, Any]]:
        """Unified method to query trades with optional execution_mode filter.

        Routing (SPRINT 22):
        - LIVE (default) → queries usr_trades (Capa 1, trader-owned)
        - SHADOW/BACKTEST → transparently queries sys_trades (Capa 0, system-managed)

        This maintains backward compatibility for callers that use SHADOW mode.

        Args:
            execution_mode: Optional filter ('LIVE', 'SHADOW', or None for 'LIVE').
            limit: Maximum number of trades to retrieve.

        Returns:
            List of trade records as dicts.
        """
        if execution_mode is None:
            execution_mode = ExecutionMode.LIVE.value
        # SHADOW/BACKTEST trades live in sys_trades (Capa 0), not usr_trades
        if execution_mode in (ExecutionMode.SHADOW.value, 'BACKTEST'):
            return self.get_sys_trades(execution_mode=execution_mode, limit=limit)
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM usr_trades
                WHERE execution_mode = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (execution_mode, limit))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    # ── Position Metadata ─────────────────────────────────────────────────────

    def get_position_metadata(self, ticket: int) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific position/trade by ticket. Returns None if not found.

        Reads from sys_position_metadata (canonical). Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='sys_position_metadata'"
            )
            if not cursor.fetchone():
                return None
            cursor.execute("SELECT * FROM sys_position_metadata WHERE ticket = ?", (ticket,))
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

    def update_position_metadata(self, ticket: int, metadata: Dict[str, Any]) -> bool:
        """Save or update position metadata for monitoring. Merges with existing data.

        Writes to sys_position_metadata (canonical). Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
        """
        import json as _json

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            existing = self.get_position_metadata(ticket)
            merged = {**(existing or {}), **metadata, "ticket": ticket}

            cursor.execute("""
                REPLACE INTO sys_position_metadata
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
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Log position management event (SL/TP change, breakeven, trailing, etc.)."""
        import json as _json

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO usr_position_history
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
    ) -> List[Dict[str, Any]]:
        """Get position history events, newest first."""
        import json as _json

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM usr_position_history WHERE 1=1"
            params: list[Any] = []
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
        Remove 'EXECUTED' status from sys_signals for a symbol that has no real open position.
        This fixes the 'ghost position' issue where DB thinks a trade is open but MT5 doesn't.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # logger.warning(f"🧹 Clearing ghost positions for {symbol} (Marking as REJECTED)")
            
            # Using basic UPDATE first, json_patch might be sqlite extension dependent
            # If json_patch is not available, just update status
            cursor.execute("""
                UPDATE sys_signals 
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
    def get_account_usr_trades(self, account_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Get recent usr_trades for a specific account (for Equity Curve analysis).
        
        Args:
            account_id: Account ID to retrieve usr_trades for
            limit: Maximum number of usr_trades to return
        
        Returns:
            List of trade dicts with normalized fields (is_win, pnl, etc.)
        
        Note: Currently returns recent usr_trades since trade_results doesn't have account_id.
              In future multi-tenant refactoring, this will filter by account_id.
        """
        # For now, use get_recent_usr_trades as base
        # TODO: Update when trade_results schema adds account_id column
        usr_trades = self.get_recent_usr_trades(limit=limit)
        return usr_trades
    
    def log_threshold_adjustment(
        self,
        account_id: str,
        old_threshold: float,
        new_threshold: float,
        reason: str,
        governance_note: str = "",
        win_rate: float = 0.0,
        consecutive_losses: int = 0,
        trace_id: str = ""
    ) -> None:
        """
        Log a confidence threshold adjustment for auditability.
        
        Args:
            account_id: Account that was adjusted
            old_threshold: Previous threshold value
            new_threshold: New threshold value
            reason: Reason for adjustment (e.g., "LOSS_STREAK(4)")
            governance_note: Safety Governor notes if applicable
            win_rate: Win rate at time of adjustment
            consecutive_losses: Consecutive loss count at time of adjustment
            trace_id: Trace ID for observability (ADAPTIVE-THRESHOLD-2026-001)
        """
        import json
        from datetime import datetime, timezone
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            adjustment_data = {
                "account_id": account_id,
                "old_threshold": old_threshold,
                "new_threshold": new_threshold,
                "delta": new_threshold - old_threshold,
                "reason": reason,
                "governance_note": governance_note,
                "win_rate": win_rate,
                "consecutive_losses": consecutive_losses,
                "trace_id": trace_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            
            cursor.execute("""
                INSERT INTO usr_tuning_adjustments (adjustment_data)
                VALUES (?)
            """, (json.dumps(adjustment_data),))
            
            conn.commit()
            logger.debug(f"[THRESHOLD_ADJUSTMENT_LOG] Trade {trace_id}: {new_threshold - old_threshold:+.4f}")
        except Exception as e:
            logger.error(f"Error logging threshold adjustment: {e}")
        finally:
            self._close_conn(conn)