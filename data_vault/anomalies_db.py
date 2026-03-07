"""
AnomaloDDB Mixin for Aethelgard Storage Manager
Handles persistence and retrieval of anomaly events (HU 4.6).
"""

import json
import logging
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)


class AnomaliesMixin(BaseRepository):
    """Mixin for Anomaly Event database operations."""

    async def persist_anomaly_event(
        self,
        symbol: str,
        anomaly_type: str,
        z_score: float,
        confidence: float,
        timestamp: datetime,
        trace_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Persiste un evento de anomalía en la base de datos.
        
        Args:
            symbol: Instrumento afectado (ej. EURUSD)
            anomaly_type: Tipo de anomalía (extreme_volatility, flash_crash, etc)
            z_score: Puntuación Z (si aplica)
            confidence: Confianza de la detección (0-1)
            timestamp: Momento de detección
            trace_id: ID único para trazabilidad
            details: Detalles adicionales en JSON
            
        Returns:
            True si se persistió correctamente
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            details_json = json.dumps(details or {})
            
            cursor.execute("""
                INSERT INTO usr_anomaly_events (
                    symbol,
                    anomaly_type,
                    z_score,
                    confidence,
                    timestamp,
                    trace_id,
                    details
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol,
                anomaly_type,
                z_score,
                confidence,
                timestamp.isoformat() if isinstance(timestamp, datetime) else timestamp,
                trace_id,
                details_json
            ))
            
            conn.commit()
            logger.debug(
                f"[ANOMALY_DB] Event persisted: {symbol} {anomaly_type} Z={z_score:.2f} "
                f"Trace_ID={trace_id}"
            )
            return True
            
        except sqlite3.IntegrityError as e:
            logger.warning(f"[ANOMALY_DB] Duplicate trace_id {trace_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"[ANOMALY_DB] Error persisting anomaly event: {e}")
            return False
        finally:
            self._close_conn(conn)

    async def get_anomaly_history(
        self,
        symbol: Optional[str] = None,
        anomaly_type: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        Recupera el historial de eventos de anomalía.
        
        Args:
            symbol: Filtrar por símbolo (opcional)
            anomaly_type: Filtrar por tipo de anomalía (opcional)
            limit: Número máximo de resultados
            
        Returns:
            Lista de eventos de anomalía
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            query = "SELECT * FROM usr_anomaly_events WHERE 1=1"
            params: List[Any] = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if anomaly_type:
                query += " AND anomaly_type = ?"
                params.append(anomaly_type)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            results: List[Dict[str, Any]] = []
            for row in rows:
                record = dict(row)
                # Parse JSON details
                if record.get('details'):
                    try:
                        record['details'] = json.loads(record['details'])
                    except json.JSONDecodeError:
                        record['details'] = {}
                results.append(record)
            
            return results
            
        except Exception as e:
            logger.error(f"[ANOMALY_DB] Error retrieving anomaly history: {e}")
            return []
        finally:
            self._close_conn(conn)

    async def get_recent_anomalies(
        self,
        symbol: str,
        hours: int = 1,
    ) -> List[Dict[str, Any]]:
        """
        Recupera anomalías recientes para un símbolo en las últimas N horas.
        
        Args:
            symbol: Instrumento
            hours: Ventana de tiempo (horas)
            
        Returns:
            Lista de anomalías recientes
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM usr_anomaly_events
                WHERE symbol = ?
                  AND timestamp > datetime('now', '-' || ? || ' hours')
                ORDER BY timestamp DESC
            """, (symbol, hours))
            
            rows = cursor.fetchall()
            
            results: List[Dict[str, Any]] = []
            for row in rows:
                record = dict(row)
                if record.get('details'):
                    try:
                        record['details'] = json.loads(record['details'])
                    except json.JSONDecodeError:
                        record['details'] = {}
                results.append(record)
            
            return results
            
        except Exception as e:
            logger.error(f"[ANOMALY_DB] Error retrieving recent anomalies: {e}")
            return []
        finally:
            self._close_conn(conn)

    async def get_critical_anomalies(
        self,
        min_confidence: float = 0.85,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Recupera anomalías críticas (alta confianza).
        
        Args:
            min_confidence: Confianza mínima
            limit: Número máximo de resultados
            
        Returns:
            Lista de anomalías críticas
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM usr_anomaly_events
                WHERE confidence >= ?
                  AND anomaly_type IN ('flash_crash', 'liquidation_cascade')
                ORDER BY confidence DESC, timestamp DESC
                LIMIT ?
            """, (min_confidence, limit))
            
            rows = cursor.fetchall()
            
            results: List[Dict[str, Any]] = []
            for row in rows:
                record = dict(row)
                if record.get('details'):
                    try:
                        record['details'] = json.loads(record['details'])
                    except json.JSONDecodeError:
                        record['details'] = {}
                results.append(record)
            
            return results
            
        except Exception as e:
            logger.error(f"[ANOMALY_DB] Error retrieving critical anomalies: {e}")
            return []
        finally:
            self._close_conn(conn)

    async def get_anomaly_count(
        self,
        symbol: Optional[str] = None,
        hours: Optional[int] = None,
    ) -> int:
        """
        Cuenta el número de anomalías para un símbolo en un período.
        
        Args:
            symbol: Símbolo (opcional)
            hours: Ventana de tiempo en horas (opcional)
            
        Returns:
            Número de anomalías
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            query = "SELECT COUNT(*) FROM usr_anomaly_events WHERE 1=1"
            params: List[Any] = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if hours:
                query += " AND timestamp > datetime('now', '-' || ? || ' hours')"
                params.append(hours)
            
            cursor.execute(query, params)
            result = cursor.fetchone()
            
            return result[0] if result else 0
            
        except Exception as e:
            logger.error(f"[ANOMALY_DB] Error counting anomalies: {e}")
            return 0
        finally:
            self._close_conn(conn)

    def get_anomaly_stats(self) -> Dict[str, Any]:
        """
        Obtiene estadísticas generales de anomalías detectadas.
        
        Returns:
            Dict con estadísticas de anomalías
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Total de anomalías por tipo
            cursor.execute("""
                SELECT anomaly_type, COUNT(*) as count
                FROM usr_anomaly_events
                GROUP BY anomaly_type
            """)
            by_type = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Total de anomalías por símbolo
            cursor.execute("""
                SELECT symbol, COUNT(*) as count
                FROM usr_anomaly_events
                GROUP BY symbol
                ORDER BY count DESC
                LIMIT 10
            """)
            by_symbol = {row[0]: row[1] for row in cursor.fetchall()}
            
            # Confianza promedio
            cursor.execute("SELECT AVG(confidence), MIN(confidence), MAX(confidence) FROM usr_anomaly_events")
            conf_row = cursor.fetchone()
            avg_confidence, min_confidence, max_confidence = conf_row if conf_row else (0, 0, 0)
            
            # Se z_score promedio
            cursor.execute("SELECT AVG(z_score), MAX(z_score) FROM usr_anomaly_events WHERE z_score IS NOT NULL")
            zscore_row = cursor.fetchone()
            avg_zscore, max_zscore = zscore_row if zscore_row else (0, 0)
            
            return {
                "total_anomalies": sum(by_type.values()),
                "by_type": by_type,
                "by_symbol": by_symbol,
                "confidence_stats": {
                    "average": round(float(avg_confidence) if avg_confidence else 0, 3),
                    "min": float(min_confidence) if min_confidence else 0,
                    "max": float(max_confidence) if max_confidence else 0,
                },
                "zscore_stats": {
                    "average": round(float(avg_zscore) if avg_zscore else 0, 3),
                    "max": float(max_zscore) if max_zscore else 0,
                },
            }
            
        except Exception as e:
            logger.error(f"[ANOMALY_DB] Error getting anomaly stats: {e}")
            return {"error": str(e)}
        finally:
            self._close_conn(conn)

    def register_coherence_event(
        self,
        symbol: str,
        strategy_id: Optional[str],
        status: str,
        coherence_score: float,
        performance_degradation: float,
        trace_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Register a coherence monitoring event (HU 6.3).
        
        Args:
            symbol: Trading symbol
            strategy_id: Strategy ID (optional)
            status: Coherence status (COHERENT, INCOHERENT, MONITORING, etc)
            coherence_score: Calculated coherence (0-1)
            performance_degradation: Performance degradation ratio (0-1)
            trace_id: Trace ID for audit trail
            details: Additional metadata
        
        Returns:
            True if successfully registered
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            details_json = json.dumps(details or {})
            reason = (
                f"Coherence={coherence_score*100:.1f}%, Degradation={performance_degradation*100:.1f}%"
            )
            
            cursor.execute("""
                INSERT INTO usr_coherence_events
                (signal_id, symbol, timeframe, strategy, stage, status, incoherence_type, reason, details, connector_type, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace_id,
                symbol,
                "multi",  # Multi-timeframe detection
                strategy_id or "SYSTEM",
                "DRIFT" if status == "INCOHERENT" else "MONITORING",
                status,
                f"SHA_DEGRADATION_{int(performance_degradation*100)}PCT" if status == "INCOHERENT" else None,
                reason,
                details_json,
                "AGGREGATED",
                datetime.now().isoformat(),
            ))
            
            conn.commit()
            logger.debug(
                f"[COHERENCE_DB] Event registered: {symbol} {status} "
                f"Score={coherence_score*100:.1f}% Trace_ID={trace_id}"
            )
            return True
            
        except Exception as e:
            logger.error(f"[COHERENCE_DB] Error registering coherence event: {e}")
            return False
        finally:
            self._close_conn(conn)
