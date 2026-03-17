import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, List, Optional
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

class MarketMixin(BaseRepository):
    """Mixin for Market State and Coherence database operations."""

    def log_sys_market_pulse(self, state_data: Dict) -> None:
        """Log market state data"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sys_market_pulse (symbol, data)
                VALUES (?, ?)
            """, (state_data.get('symbol'), json.dumps(state_data)))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_sys_market_pulse_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get market state history for a symbol"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sys_market_pulse 
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
                INSERT INTO usr_coherence_events 
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
                UPDATE sys_signals 
                SET status = 'CLOSED', 
                    metadata = json_set(COALESCE(metadata, '{}'), '$.exit_reason', 'REJECTED')
                WHERE symbol = ? 
                AND status = 'EXECUTED'
                AND id NOT IN (SELECT signal_id FROM usr_trades WHERE signal_id IS NOT NULL)
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
                    FROM sys_market_pulse
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

    def get_all_sys_market_pulses(self) -> Dict[str, Dict]:
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
                    FROM sys_market_pulse
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
            cursor.execute("SELECT * FROM usr_assets_cfg WHERE symbol = ?", (symbol,))
            row = cursor.fetchone()
            if row:
                profile = dict(row)
                if trace_id:
                    logger.info(f"[{trace_id}] Profile retrieved for {symbol}")
                return profile
            return None
        finally:
            self._close_conn(conn)

    def get_all_usr_assets_cfg(self) -> List[Dict]:
        """
        Get all asset configurations (enabled and disabled).
        FASE 4: Used for signal filtering to only generate signals for enabled assets.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usr_assets_cfg")
            rows = cursor.fetchall()
            if rows:
                return [dict(row) for row in rows]
            return []
        finally:
            self._close_conn(conn)

    def log_market_cache(self, symbol: str, data: Optional[List[Dict]] = None, 
                         limit_records: int = 100, metadata: Optional[Dict] = None) -> None:
        """
        Persist market data cache (agnóstico - Rule #15 SSOT).
        
        Used by: DXYService, other data services for cache persistence.
        
        Args:
            symbol: Market symbol (e.g., "DXY", "EURUSD")
            data: Market OHLCV data to cache (optional for cleanup)
            limit_records: Keep only latest N records per symbol
            metadata: Additional metadata (ttl_seconds, provider, etc.)
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            timestamp_str = datetime.now(timezone.utc).isoformat()
            
            # Prepare cache entry with metadata
            cache_entry = {
                "timestamp": timestamp_str,
                "symbol": symbol,
                "record_count": len(data) if data else 0,
                "metadata": metadata or {}
            }
            if data:
                cache_entry["records"] = data
            
            # Insert cache entry
            cursor.execute("""
                INSERT INTO sys_market_pulse (symbol, data)
                VALUES (?, ?)
            """, (symbol, json.dumps(cache_entry)))
            
            # Cleanup: Keep only latest N per symbol
            cursor.execute("""
                DELETE FROM sys_market_pulse 
                WHERE symbol = ? AND id NOT IN (
                    SELECT id FROM sys_market_pulse 
                    WHERE symbol = ? 
                    ORDER BY timestamp DESC 
                    LIMIT ?
                )
            """, (symbol, symbol, limit_records))
            
            conn.commit()
            logger.debug(f"[CACHE] Logged {len(data) if data else 0} records for {symbol}")
        except Exception as e:
            logger.warning(f"[CACHE] log_market_cache failed: {e}")
        finally:
            self._close_conn(conn)
    
    def get_market_cache(self, symbol: str, count: int = 100) -> Optional[List[Dict]]:
        """
        Retrieve market data cache (SSOT persistence - Rule #15).
        
        Returns: List of OHLCV records or None if not found.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT data FROM sys_market_pulse 
                WHERE symbol = ? 
                ORDER BY timestamp DESC 
                LIMIT 1
            """, (symbol,))
            
            row = cursor.fetchone()
            if not row:
                logger.debug(f"[CACHE] No cache found for {symbol}")
                return None
            
            try:
                cache_data = json.loads(row['data'])
                records = cache_data.get('records', [])
                
                # Return only requested count
                result = records[-count:] if records else None
                logger.debug(f"[CACHE] Retrieved {len(result) if result else 0} records for {symbol}")
                return result
            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"[CACHE] Malformed cache data for {symbol}: {e}")
                return None
                
        except Exception as e:
            logger.warning(f"[CACHE] get_market_cache failed: {e}")
            return None
        finally:
            self._close_conn(conn)

    def seed_initial_assets(self) -> None:
        """Seed initial asset profiles if table is empty."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM usr_assets_cfg")
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
                INSERT INTO usr_assets_cfg 
                (symbol, asset_class, tick_size, lot_step, contract_size, currency, golden_hour_start, golden_hour_end)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, initial_assets)
            
            conn.commit()
            logger.info("Initial asset profiles seeded.")
        finally:
            self._close_conn(conn)
