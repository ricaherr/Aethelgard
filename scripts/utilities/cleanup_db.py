import os
import sqlite3
import shutil
import logging
from pathlib import Path

# Configuración de logging profesional
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent
DATA_VAULT = PROJECT_ROOT / "data_vault"
OFFICIAL_DB = DATA_VAULT / "aethelgard.db"

ORPHAN_DBS = [
    DATA_VAULT / "aethelgard_ssot.db",
    DATA_VAULT / "trading.db",
    DATA_VAULT / "system_db.sqlite",
    DATA_VAULT / "trades_db.sqlite"
]

def migrate_table(src_conn, dst_conn, table_name):
    """Migra datos de una tabla si existe en el origen y destino."""
    try:
        cursor_src = src_conn.execute(f"SELECT name FROM sqlite_master WHERE type='table' AND name='{table_name}'")
        if not cursor_src.fetchone():
            return

        logger.info(f"Migrando tabla {table_name}...")
        
        # Obtener columnas del destino para evitar fallos por esquemas diferentes
        cursor_dst = dst_conn.execute(f"PRAGMA table_info({table_name})")
        columns = [row[1] for row in cursor_dst.fetchall()]
        col_list = ", ".join(columns)
        
        # Migrar datos (INSERT OR IGNORE para evitar duplicados en PKs)
        cursor_src = src_conn.execute(f"SELECT {col_list} FROM {table_name}")
        rows = cursor_src.fetchall()
        
        if rows:
            placeholders = ", ".join(["?" for _ in columns])
            dst_conn.executemany(f"INSERT OR IGNORE INTO {table_name} ({col_list}) VALUES ({placeholders})", rows)
            logger.info(f"Se migraron {len(rows)} registros de la tabla {table_name}.")
        
    except Exception as e:
        logger.error(f"Error migrando tabla {table_name}: {e}")

def cleanup():
    logger.info("--- INICIANDO UNIFICACIÓN DE DB (Milestone 5.8) ---")
    
    if not OFFICIAL_DB.exists():
        logger.error(f"Base de datos oficial no encontrada en {OFFICIAL_DB}")
        return

    # Conectar a la base de datos oficial
    dst_conn = sqlite3.connect(OFFICIAL_DB)
    
    try:
        for db_path in ORPHAN_DBS:
            if db_path.exists() and db_path != OFFICIAL_DB:
                # Si el archivo tiene tamaño 0, simplemente lo borramos
                if db_path.stat().st_size == 0:
                    logger.info(f"Eliminando DB huérfana vacía: {db_path.name}")
                    db_path.unlink()
                    continue
                
                logger.info(f"Analizando DB huérfana: {db_path.name}")
                src_conn = sqlite3.connect(db_path)
                
                # Tablas críticas a migrar
                tables_to_migrate = [
                    'asset_profiles', 
                    'strategy_ranking', 
                    'signals', 
                    'trade_results', 
                    'broker_accounts',
                    'regime_configs'
                ]
                
                for table in tables_to_migrate:
                    migrate_table(src_conn, dst_conn, table)
                
                src_conn.close()
                dst_conn.commit()
                
                # Eliminar archivo después de migrar
                logger.info(f"Eliminando DB migrada: {db_path.name}")
                db_path.unlink()
        
        logger.info("--- UNIFICACIÓN COMPLETADA EXITOSAMENTE ---")
        
    except Exception as e:
        logger.error(f"Fallo crítico durante la limpieza: {e}")
    finally:
        dst_conn.close()

if __name__ == "__main__":
    cleanup()
