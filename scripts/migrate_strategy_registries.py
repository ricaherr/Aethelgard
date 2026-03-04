#!/usr/bin/env python3
"""
Migration: Create strategy_registries table and migrate data from JSON

TRACE_ID: MIGRATION-STRATEGY-REGISTRIES-2026
"""
import sqlite3
import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_strategy_registries():
    """Crea tabla y migra datos del JSON a DB.
    
    NOTA: Este script es LEGACY. La migración automática se hace en:
    - StorageManager._bootstrap_from_json() → ejecuta UNA SOLA VEZ (idempotent)
    - Ubicación canonical: data_vault/seed/strategy_registry.json
    
    Este script es FALLBACK para casos manual debug.
    """
    
    # Rutas
    project_root = Path(__file__).parent.parent
    db_path = project_root / "data_vault" / "aethelgard.db"  # UBICACIÓN CORRECTA: data_vault/
    json_path = project_root / "data_vault" / "seed" / "strategy_registry.json"  # UBICACIÓN CORRECTA: seed/
    
    if not json_path.exists():
        logger.error(f"❌ {json_path} no existe")
        return False
    
    logger.info(f"📂 Leyendo {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        registry_data = json.load(f)
    
    # Conectar/crear DB
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    try:
        # Crear tabla si no existe
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS strategy_registries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_id TEXT UNIQUE NOT NULL,
            mnemonic TEXT NOT NULL,
            display_name TEXT NOT NULL,
            version TEXT NOT NULL,
            type TEXT NOT NULL,
            description TEXT,
            author TEXT,
            published_date TEXT,
            schema_file TEXT,
            status TEXT NOT NULL DEFAULT 'SHADOW',
            membership_tier TEXT,
            tags TEXT,
            affinity_scores TEXT,
            market_whitelist TEXT,
            regime_requirements TEXT,
            required_sensors TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        """)
        
        logger.info("✅ Tabla strategy_registries creada/verificada")
        
        # Migrar estrategias del JSON
        strategies = registry_data.get("strategies", [])
        inserted = 0
        updated = 0
        
        for strat in strategies:
            strategy_id = strat.get("strategy_id")
            
            # Serializar campos JSON
            affinity_scores = json.dumps(strat.get("affinity_scores", {}))
            market_whitelist = json.dumps(strat.get("market_whitelist", []))
            regime_requirements = json.dumps(strat.get("regime_requirements", []))
            required_sensors = json.dumps(strat.get("required_sensors", []))
            tags = json.dumps(strat.get("tags", []))
            
            try:
                cursor.execute("""
                INSERT OR REPLACE INTO strategy_registries (
                    strategy_id, mnemonic, display_name, version, type,
                    description, author, published_date, schema_file,
                    status, membership_tier, tags,
                    affinity_scores, market_whitelist,
                    regime_requirements, required_sensors
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    strategy_id,
                    strat.get("mnemonic"),
                    strat.get("display_name"),
                    strat.get("version"),
                    strat.get("type"),
                    strat.get("description"),
                    strat.get("author"),
                    strat.get("published_date"),
                    strat.get("schema_file"),
                    strat.get("status", "SHADOW"),
                    strat.get("membership_tier", "FREE"),
                    tags,
                    affinity_scores,
                    market_whitelist,
                    regime_requirements,
                    required_sensors
                ))
                print(f"  ✅ {strategy_id}")
                inserted += 1
            except Exception as e:
                logger.error(f"  ❌ Error migrating {strategy_id}: {e}")
        
        conn.commit()
        
        logger.info(f"\n{'='*70}")
        logger.info(f"✅ MIGRACIÓN COMPLETADA")
        logger.info(f"{'='*70}")
        logger.info(f"   Estrategias migradas: {inserted}")
        logger.info(f"   Base de datos: {db_path}")
        logger.info(f"   Tabla: strategy_registries")
        logger.info(f"\n📝 PRÓXIMO PASO: strategy_loader.py leerá desde DB")
        logger.info(f"{'='*70}\n")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Error en migración: {e}")
        conn.rollback()
        return False
    finally:
        conn.close()

if __name__ == "__main__":
    success = migrate_strategy_registries()
    exit(0 if success else 1)
