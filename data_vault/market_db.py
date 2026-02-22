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
                    metadata = json_set(COALESCE(metadata, '{}'), '$.exit_reason', 'REJECTED')
                WHERE symbol = ? 
                AND status = 'EXECUTED'
                AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
            """, (symbol,))
            conn.commit()
        except Exception as e:
            logger.error(f"Error clearing ghost position for {symbol}: {e}")
        finally:
            self._close_conn(conn)

    def get_latest_heatmap_state(self) -> List[Dict]:
        """
        Obtiene el último estado conocido (`JSON`) de cada símbolo/timeframe
        de forma eficiente para reconstruir la matriz de calor.
        Recupera datos de las últimas 24 horas para asegurar frescura.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Query robusta usando CTE y ROW_NUMBER para obtener el ÚLTIMO registro real de cada par
            cursor.execute("""
                WITH LatestStates AS (
                    SELECT 
                        symbol, 
                        data, 
                        timestamp,
                        ROW_NUMBER() OVER (
                            PARTITION BY symbol, json_extract(data, '$.timeframe') 
                            ORDER BY timestamp DESC
                        ) as rn
                    FROM market_state
                    WHERE timestamp > datetime('now', '-24 hours', 'utc')
                )
                SELECT symbol, data, timestamp
                FROM LatestStates
                WHERE rn = 1
                ORDER BY timestamp DESC
            """)
            rows = cursor.fetchall()
            results = []
            for row in rows:
                try:
                    state = json.loads(row['data'])
                    results.append(state)
                except Exception:
                    continue
            return results
        except Exception as e:
            logger.error(f"Error recuperando estado de heatmap: {e}")
            return []
        finally:
            self._close_conn(conn)

    def get_all_market_states(self) -> Dict[str, Dict]:
        """
        Obtiene el último estado de mercado para cada símbolo.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Usar ROW_NUMBER para obtener el más reciente por símbolo
            cursor.execute("""
                SELECT symbol, data, timestamp
                FROM (
                    SELECT symbol, data, timestamp,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY timestamp DESC) as rn
                    FROM market_state
                )
                WHERE rn = 1
            """)
            rows = cursor.fetchall()
            states = {}
            for row in rows:
                try:
                    states[row['symbol']] = {
                        "data": json.loads(row['data']),
                        "timestamp": row['timestamp']
                    }
                except:
                    continue
            return states
        finally:
            self._close_conn(conn)

    def get_asset_profile(self, symbol: str, trace_id: Optional[str] = None) -> Optional[Dict]:
        """
        Get asset profile for a symbol.
        SSOT: Unified instrument normalization.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM asset_profiles WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row:
                profile = dict(row)
                if trace_id:
                    logger.info(f"[{trace_id}] Profile retrieved for {symbol}")
                return profile
            return None
        finally:
            self._close_conn(conn)

    def seed_initial_assets(self) -> None:
        """Seed initial asset profiles if table is empty."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM asset_profiles")
            if cursor.fetchone()[0] > 0:
                return

            initial_assets = [
                ('EURUSD', 'FOREX', 0.00001, 0.01, 100000, 'USD', '08:00', '17:00'),
                ('GBPUSD', 'FOREX', 0.00001, 0.01, 100000, 'USD', '08:00', '16:00'),
                ('USDJPY', 'FOREX', 0.001, 0.01, 100000, 'JPY', '00:00', '09:00'),
                ('GOLD',   'METAL', 0.01, 0.01, 100,    'USD', '08:00', '17:00'),
                ('BTCUSD', 'CRYPTO', 0.01, 0.0001, 1,    'USD', '00:00', '23:59')
            ]
            
            cursor.executemany("""
                INSERT INTO asset_profiles 
                (symbol, asset_class, tick_size, lot_step, contract_size, currency, golden_hour_start, golden_hour_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, initial_assets)
            
            conn.commit()
            logger.info("Initial asset profiles seeded.")
        finally:
            self._close_conn(conn)
