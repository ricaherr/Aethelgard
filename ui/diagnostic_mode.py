"""
DIAGNOSTIC MODE UI - Trazabilidad Real
=======================================
Modo diagnóstico del Dashboard que reemplaza visualizaciones estéticas
por tabla de trazabilidad real: TIMESTAMP | TRACE_ID | MÓDULO | ACCIÓN | RESULTADO SQL

CRITICAL: Esta UI muestra SOLO lo que realmente está pasando en el sistema.
No "pensamientos", no animaciones, solo logs reales de operación.

Usage:
    streamlit run ui/diagnostic_mode.py
"""

import streamlit as st
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict
import pandas as pd

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_vault.storage import StorageManager

st.set_page_config(
    page_title="Aethelgard - Modo Diagnóstico",
    page_icon="🔍",
    layout="wide"
)

# CSS for diagnostic mode (clean, minimal)
st.markdown("""
<style>
    .diagnostic-header {
        background-color: #1a1a1a;
        color: #00ff00;
        padding: 20px;
        border-radius: 5px;
        font-family: 'Courier New', monospace;
        font-size: 24px;
        text-align: center;
        margin-bottom: 20px;
    }
    .critical-status {
        background-color: #ff0000;
        color: #ffffff;
        padding: 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .ok-status {
        background-color: #00ff00;
        color: #000000;
        padding: 10px;
        border-radius: 5px;
        font-weight: bold;
    }
    .trace-table {
        font-family: 'Courier New', monospace;
        font-size: 12px;
    }
</style>
""", unsafe_allow_html=True)

def get_database_path() -> str:
    """Find main database."""
    data_vault_dir = project_root / "data_vault"
    
    for name in ["aethelgard.db", "trading.db", "main.db"]:
        db_path = data_vault_dir / name
        if db_path.exists():
            return str(db_path)
    
    db_files = list(data_vault_dir.glob("*.db"))
    if db_files:
        return str(db_files[0])
    
    return ""


def get_real_trace_log(db_path: str, limit: int = 50) -> List[Dict]:
    """
    Query real execution trace from audit log.
    
    Returns:
        List of trace entries with TIMESTAMP | TRACE_ID | MODULE | ACTION | SQL_RESULT
    """
    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        
        # Check if audit_log table exists
        cursor = conn.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='audit_log'
        """)
        
        if not cursor.fetchone():
            return []
        
        # Query audit log
        cursor = conn.execute("""
            SELECT 
                timestamp,
                trace_id,
                module,
                action,
                details,
                success
            FROM audit_log
            ORDER BY timestamp DESC
            LIMIT ?
        """, (limit,))
        
        traces = []
        for row in cursor.fetchall():
            traces.append({
                'timestamp': row['timestamp'],
                'trace_id': row['trace_id'],
                'module': row['module'],
                'action': row['action'],
                'sql_result': '✅ SUCCESS' if row['success'] else '❌ FAILED',
                'details': row['details']
            })
        
        conn.close()
        return traces
        
    except Exception as e:
        st.error(f"Error querying audit log: {e}")
        return []


def get_heartbeats(storage: StorageManager) -> Dict[str, str]:
    """Get module heartbeats."""
    try:
        heartbeats = storage.get_module_heartbeats()
        
        now = datetime.now()
        status = {}
        
        for module, timestamp_str in heartbeats.items():
            try:
                last_beat = datetime.fromisoformat(timestamp_str)
                elapsed = (now - last_beat).total_seconds()
                
                if elapsed < 30:
                    status[module] = f"✅ OK ({int(elapsed)}s ago)"
                elif elapsed < 60:
                    status[module] = f"⚠️ WARNING ({int(elapsed)}s ago)"
                else:
                    status[module] = f"❌ FROZEN ({int(elapsed)}s ago)"
            except:
                status[module] = "❌ INVALID"
        
        return status
        
    except Exception as e:
        return {"error": str(e)}


def get_current_counts(storage: StorageManager) -> Dict:
    """Get real counts from database."""
    try:
        db_path = storage.db_path
        conn = sqlite3.connect(db_path)
        
        # Count signals
        cursor = conn.execute("SELECT COUNT(*) FROM signals")
        signals_total = cursor.fetchone()[0]
        
        cursor = conn.execute("SELECT COUNT(*) FROM signals WHERE status = 'executed'")
        signals_executed = cursor.fetchone()[0]
        
        # Count trades
        cursor = conn.execute("SELECT COUNT(*) FROM trades WHERE status IN ('PENDING', 'EXECUTED')")
        trades_active = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'signals_total': signals_total,
            'signals_executed': signals_executed,
            'trades_active': trades_active
        }
        
    except Exception as e:
        return {'error': str(e)}


def main() -> None:
    """Main UI."""
    
    # Header
    st.markdown('<div class="diagnostic-header">🔍 AETHELGARD - MODO DIAGNÓSTICO</div>', unsafe_allow_html=True)
    
    st.warning("⚠️ **MODO DIAGNÓSTICO ACTIVO**: Esta interfaz muestra SOLO datos reales del sistema. No hay visualizaciones estéticas.")
    
    # Auto-refresh
    if st.checkbox("Auto-refresh cada 5 segundos", value=False):
        st.rerun()
        import time
        time.sleep(5)
    
    # Refresh button
    if st.button("🔄 Refrescar Datos"):
        st.rerun()
    
    st.markdown("---")
    
    # Section 1: System Status
    st.header("📊 Estado del Sistema")
    
    storage = StorageManager()
    counts = get_current_counts(storage)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Señales Totales (DB)", counts.get('signals_total', 'N/A'))
    
    with col2:
        st.metric("Señales Ejecutadas (DB)", counts.get('signals_executed', 'N/A'))
    
    with col3:
        st.metric("Trades Activos (DB)", counts.get('trades_active', 'N/A'))
    
    # Critical Warning if data > 0
    if counts.get('signals_executed', 0) > 0 or counts.get('trades_active', 0) > 0:
        st.markdown("""
        <div class="critical-status">
        🚨 ADVERTENCIA: La base de datos contiene datos. 
        Si MT5 muestra 0 posiciones, ejecutar: python scripts/purge_database.py
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="ok-status">
        ✅ BASE DE DATOS LIMPIA: 0 señales ejecutadas, 0 trades activos
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Section 2: Module Heartbeats
    st.header("💓 Heartbeats de Módulos")
    
    heartbeats = get_heartbeats(storage)
    
    if heartbeats:
        for module, status in heartbeats.items():
            st.text(f"{module:20} → {status}")
    else:
        st.info("No hay heartbeats registrados")
    
    st.markdown("---")
    
    # Section 3: Real Trace Log (Audit Trail)
    st.header("📜 Trazabilidad Real (Audit Log)")
    
    db_path = get_database_path()
    
    if not db_path:
        st.error("❌ No se encontró base de datos")
        return
    
    traces = get_real_trace_log(db_path, limit=100)
    
    if not traces:
        st.info("ℹ️ No hay registros en audit_log. El sistema aún no ha ejecutado acciones trazables.")
        st.caption("Esto es normal si el sistema nunca se ha iniciado o no tiene tabla audit_log.")
    else:
        # Convert to DataFrame
        df = pd.DataFrame(traces)
        
        # Display as table
        st.dataframe(
            df[['timestamp', 'trace_id', 'module', 'action', 'sql_result']],
            use_container_width=True,
            hide_index=True
        )
        
        # Expandable details
        with st.expander("Ver detalles completos"):
            for trace in traces[:20]:  # Show first 20 with details
                st.text(f"""
{trace['timestamp']} | {trace['trace_id'][:8]} | {trace['module']}
Action: {trace['action']}
Result: {trace['sql_result']}
Details: {trace.get('details', 'N/A')}
{'─' * 70}
                """)
    
    st.markdown("---")
    
    # Section 4: Quick Actions
    st.header("⚡ Acciones Rápidas")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("🔍 Ejecutar check_integrity.py"):
            st.info("Ejecutar en terminal: python scripts/check_integrity.py")
    
    with col2:
        if st.button("🗑️ Ejecutar purge_database.py"):
            st.warning("Ejecutar en terminal: python scripts/purge_database.py")
            st.caption("⚠️ Esto eliminará TODOS los datos de prueba")
    
    with col3:
        if st.button("🧵 Ejecutar diagnose_threads.py"):
            st.info("Ejecutar en terminal: python scripts/diagnose_threads.py")
    
    st.markdown("---")
    
    # Footer
    st.caption(f"Última actualización: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.caption("Modo Diagnóstico - Aethelgard Integrity Restoration Protocol")


if __name__ == "__main__":
    main()
