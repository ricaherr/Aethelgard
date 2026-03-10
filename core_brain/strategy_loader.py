"""
Dynamic Strategy Loader - Universal Strategy Engine v2.0

TRACE_ID: LOADER-DYNAMIC-STRATEGIES-2026

Carga dinámicamente estrategias desde tabla strategy_registries en data_vault/aethelgard.db.
Integra con MainOrchestrator para inyección de dependencias.

SINGLE SOURCE OF TRUTH: data_vault/aethelgard.db (tabla strategy_registries)
MÁS INFORMACIÓN: scripts/migrate_strategy_registries.py
"""

import sqlite3
import json
import logging
from typing import Dict, List, Optional, Any
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


@dataclass
class StrategySpec:
    """Especificación de estrategia cargada desde registry."""
    strategy_id: str
    class_id: str
    mnemonic: str
    type: str  # "JSON_SCHEMA" | "PYTHON_CLASS"
    affinity_scores: Dict[str, float]
    regime_requirements: List[str]
    membership_tier: str
    required_sensors: List[str]
    status: str  # "OPERATIVE" | "SHADOW" | "QUARANTINE"
    schema_version: str


class StrategyRegistry:
    """
    SSOT para estrategias operativas.
    Lee desde tabla strategy_registries en aethelgard.db.
    
    Mantiene compatibilidad hacia atrás con el código existente.
    """

    def __init__(self, registry_path: Optional[str] = None, db_path: Optional[str] = None):
        """
        Inicializa registry.
        
        Args:
            registry_path: DEPRECATED (ignorado, para compatibilidad hacia atrás)
            db_path: Ruta a aethelgard.db (default: data_vault/aethelgard.db - SSOT)
        """
        if db_path is None:
            # Por defecto, buscar en data_vault (SSOT obligatorio per .ai_rules.md)
            root = Path(__file__).parent.parent
            db_path = str(root / "data_vault" / "aethelgard.db")
        
        self.db_path = db_path
        self.usr_strategies: Dict[str, StrategySpec] = {}
        self.version = "2.0"  # Actualizado a DB-backed
        self._load_registry()

    def _load_registry(self) -> None:
        """Carga usr_strategies desde DB."""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Verificar que la tabla existe
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name='strategy_registries'
            """)
            if not cursor.fetchone():
                logger.warning(f"[REGISTRY] Table strategy_registries not found in {self.db_path}")
                logger.warning(f"[REGISTRY] Run: python scripts/migrate_strategy_registries.py")
                conn.close()
                return
            
            # Cargar todas las estrategias
            cursor.execute("SELECT * FROM strategy_registries ORDER BY strategy_id")
            rows = cursor.fetchall()
            
            for row in rows:
                strategy_id = row["strategy_id"]
                
                # Deserializar campos JSON
                try:
                    affinity_scores = json.loads(row["affinity_scores"] or "{}")
                except:
                    affinity_scores = {}
                
                try:
                    regime_requirements = json.loads(row["regime_requirements"] or "[]")
                except:
                    regime_requirements = []
                
                try:
                    required_sensors = json.loads(row["required_sensors"] or "[]")
                except:
                    required_sensors = []
                
                spec = StrategySpec(
                    strategy_id=strategy_id,
                    class_id=strategy_id,  # En DB-backed, class_id = strategy_id
                    mnemonic=row["mnemonic"],
                    type=row["type"],
                    affinity_scores=affinity_scores,
                    regime_requirements=regime_requirements,
                    membership_tier=row["membership_tier"] or "FREE",
                    required_sensors=required_sensors,
                    status=row["status"] or "SHADOW",
                    schema_version=row["version"] or "1.0"
                )
                self.usr_strategies[strategy_id] = spec
            
            conn.close()
            
            logger.info(f"[REGISTRY] Loaded {len(self.usr_strategies)} usr_strategies from DB ({self.db_path})")
        
        except sqlite3.OperationalError as e:
            logger.error(f"[REGISTRY] DB error loading registry: {e}")
            self.usr_strategies = {}
        except Exception as e:
            logger.error(f"[REGISTRY] Unexpected error loading registry: {e}")
            self.usr_strategies = {}

    def get_all_sys_strategies(self) -> List[StrategySpec]:
        """Retorna todas las estrategias registradas."""
        return list(self.usr_strategies.values())

    def get_active_usr_strategies(self) -> List[StrategySpec]:
        """Retorna solo estrategias OPERATIVE (no SHADOW/QUARANTINE)."""
        return [s for s in self.usr_strategies.values() if s.status == "OPERATIVE"]

    def get_by_class_id(self, class_id: str) -> Optional[StrategySpec]:
        """Obtiene una estrategia por class_id (fallback a strategy_id)."""
        # Buscar primero por class_id directo
        spec = self.usr_strategies.get(class_id)
        if spec:
            return spec
        # Fallback: buscar en all usr_strategies por strategy_id
        for spec in self.usr_strategies.values():
            if spec.class_id == class_id or spec.strategy_id == class_id:
                return spec
        return None

    def get_by_membership(self, membership_tier: str) -> List[StrategySpec]:
        """Obtiene estrategias permitidas para un nivel de membresía."""
        tier_hierarchy = {"Free": 0, "Standard": 1, "Premium": 2, "Institutional": 3}
        user_level = tier_hierarchy.get(membership_tier, 0)
        
        return [
            s for s in self.usr_strategies.values()
            if tier_hierarchy.get(s.membership_tier, 0) <= user_level
        ]

    def is_available_for_tier(self, class_id: str, membership_tier: str) -> bool:
        """¿Está disponible esta estrategia para el tier?"""
        spec = self.get_by_class_id(class_id)
        if not spec:
            return False
        
        tier_hierarchy = {"Free": 0, "Standard": 1, "Premium": 2, "Institutional": 3}
        user_level = tier_hierarchy.get(membership_tier, 0)
        required_level = tier_hierarchy.get(spec.membership_tier, 0)
        
        return user_level >= required_level

    def __repr__(self) -> str:
        return f"StrategyRegistry(v{self.version}, usr_strategies={len(self.usr_strategies)})"


class StrategyLoaderService:
    """
    Servicio que carga estrategias dinámicamente.
    Integración con MainOrchestrator.
    """

    def __init__(self, registry: Optional[StrategyRegistry] = None):
        """
        Inicializa servicio de carga.
        
        Args:
            registry: StrategyRegistry instance (crea uno si no se proporciona)
        """
        self.registry = registry or StrategyRegistry()
        logger.info(f"[LOADER] StrategyLoaderService initialized with {len(self.registry.usr_strategies)} usr_strategies")

    def get_usr_strategies_for_execution(
        self,
        user_membership: str = "Premium",
        filter_status: str = "OPERATIVE"
    ) -> List[StrategySpec]:
        """
        Obtiene lista de estrategias a ejecutar.
        
        Args:
            user_membership: Nivel de membresía del usuario
            filter_status: "OPERATIVE" | "SHADOW" | None (todas)
        
        Returns:
            List de estrategias disponibles
        """
        specs = self.registry.get_by_membership(user_membership)
        
        if filter_status:
            specs = [s for s in specs if s.status == filter_status]
        
        logger.info(f"[LOADER] Loaded {len(specs)} usr_strategies for {user_membership} (filter={filter_status})")
        return specs

    def load_strategy_class(self, class_id: str) -> Optional[type]:
        """
        Carga dinámicamente la clase de estrategia.
        
        Args:
            class_id: Identificador de clase (ej. "MOM_BIAS_0001")
        
        Returns:
            Clase de estrategia o None si no existe
        """
        spec = self.registry.get_by_class_id(class_id)
        if not spec:
            logger.error(f"[LOADER] Strategy {class_id} not found in registry")
            return None
        
        try:
            # Mapeo de classes conocidas
            strategy_class_map = {
                "BRK_OPEN_0001": "core_brain.usr_strategies.brk_open_0001",
                "institutional_footprint": "core_brain.strategies.institutional_footprint",
                "MOM_BIAS_0001": "core_brain.strategies.mom_bias_0001",
                "LIQ_SWEEP_0001": "core_brain.strategies.liq_sweep_0001",
                "SESS_EXT_0001": "core_brain.strategies.sess_ext_0001",
                "STRUC_SHIFT_0001": "core_brain.strategies.struc_shift_0001",
            }
            
            module_path = strategy_class_map.get(class_id)
            if not module_path:
                logger.warning(f"[LOADER] No mapping for {class_id}, trying default heuristic")
                # Heurística: convert class_id to module path
                module_name = class_id.lower()
                module_path = f"core_brain.usr_strategies.{module_name}"
            
            # Importar dinámicamente
            import importlib
            module = importlib.import_module(module_path)
            
            # Buscar clase con nombre similar
            class_name_candidates = [
                class_id,
                ''.join(word.capitalize() for word in class_id.split('_')),
                class_id.split('_')[0].capitalize() + ''.join(w.capitalize() for w in class_id.split('_')[1:])
            ]
            
            for candidate in class_name_candidates:
                if hasattr(module, candidate):
                    strategy_class = getattr(module, candidate)
                    logger.info(f"[LOADER] Loaded class {candidate} from {module_path}")
                    return strategy_class
            
            logger.error(f"[LOADER] Could not find strategy class in {module_path}")
            return None
        
        except ImportError as e:
            logger.error(f"[LOADER] Failed to import {class_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"[LOADER] Unexpected error loading {class_id}: {e}")
            return None

    def instantiate_strategy(
        self,
        class_id: str,
        dependency_config: Dict[str, Any]
    ) -> Optional[Any]:
        """
        Instancia una estrategia con inyección de dependencias.
        
        Args:
            class_id: Identificador de clase
            dependency_config: Dict con dependencias inyectadas (storage, regime_classifier, etc.)
        
        Returns:
            Instancia de estrategia o None
        """
        strategy_class = self.load_strategy_class(class_id)
        if not strategy_class:
            return None
        
        try:
            # Inyección de dependencias
            instance = strategy_class(**dependency_config)
            logger.info(f"[LOADER] Instantiated {class_id} with DI")
            return instance
        except Exception as e:
            logger.error(f"[LOADER] Failed to instantiate {class_id}: {e}")
            return None


# Exportar para uso externo
__all__ = ["StrategyRegistry", "StrategyLoaderService", "StrategySpec"]
