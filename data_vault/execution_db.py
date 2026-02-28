import json
import logging
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, Dict, List, Any

from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

class ExecutionMixin(BaseRepository):
    """
    Mixin para operaciones de base de datos relacionadas con la ejecución de alta fidelidad.
    Implementa el Shadow Reporting y monitoreo de slippage.
    """

    def log_execution_shadow(
        self,
        signal_id: str,
        symbol: str,
        theoretical_price: Decimal,
        real_price: Decimal,
        slippage_pips: Decimal,
        latency_ms: float,
        status: str,
        tenant_id: str,
        trace_id: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Registra un 'Shadow Log' para comparar el precio teórico vs real.
        Cumple con la norma de fidelidad F-001 del Manifiesto.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Convertimos Decimal a float o str para SQLite
            # Usamos float para precios para permitir comparaciones, 
            # pero Decimal en la lógica para evitar errores IEEE 754.
            
            cursor.execute("""
                INSERT INTO execution_shadow_logs (
                    signal_id, symbol, theoretical_price, real_price, 
                    slippage_pips, latency_ms, status, tenant_id, 
                    trace_id, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                signal_id, 
                symbol, 
                float(theoretical_price), 
                float(real_price), 
                float(slippage_pips), 
                latency_ms, 
                status, 
                tenant_id, 
                trace_id, 
                json.dumps(metadata) if metadata else None
            ))
            
            conn.commit()
            logger.info(
                f"[SHADOW-LOG] Registrada ejecución para {symbol}. "
                f"Slippage: {slippage_pips} pips. Trace: {trace_id}"
            )
            return True
        except Exception as e:
            logger.error(f"Error al registrar Shadow Log: {e}")
            return False
        finally:
            self._close_conn(conn)

    def get_execution_shadow_logs(self, limit: int = 100, tenant_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Recupera los logs de ejecución recientes."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM execution_shadow_logs"
            params = []
            
            if tenant_id:
                query += " WHERE tenant_id = ?"
                params.append(tenant_id)
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, params)
            rows = cursor.fetchall()
            
            logs = []
            for row in rows:
                log = dict(row)
                if log.get('metadata'):
                    try:
                        log['metadata'] = json.loads(log['metadata'])
                    except:
                        log['metadata'] = {}
                logs.append(log)
            return logs
        finally:
            self._close_conn(conn)
