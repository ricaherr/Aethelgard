"""
Gestor de Módulos Activos para Aethelgard
Verifica qué estrategias tienen permiso para ejecutarse según configuración centralizada en StorageManager (SSOT)
"""
import json
import logging
from typing import Dict, List, Optional, Set
from pathlib import Path
from enum import Enum

logger = logging.getLogger(__name__)


class MembershipLevel(str, Enum):
    """Niveles de membresía"""
    BASIC = "basic"
    PREMIUM = "premium"


class ModuleManager:
    """
    Gestiona qué módulos/estrategias están activos y tienen permiso para ejecutarse
    """
    
    def __init__(self, storage):
        """
        Inicializa el gestor de módulos usando StorageManager como SSOT
        Args:
            storage: StorageManager instance
        """
        self.storage = storage
        self.config: Dict = self.storage.get_modules_config()
    
    def reload_config(self) -> None:
        """Recarga la configuración desde StorageManager (SSOT)"""
        self.config = self.storage.get_modules_config()
        logger.info("Configuración de módulos recargada desde StorageManager (SSOT)")
    
    def _create_default_config(self) -> None:
        """Crea una configuración por defecto si no existe el archivo"""
        self.config = {
            "active_modules": {
                "oliver_velez": {
                    "enabled": True,
                    "description": "Estrategias de Oliver Vélez",
                    "required_regime": ["TREND", "RANGE"],
                    "membership_required": "basic"
                },
                "risk_manager": {
                    "enabled": True,
                    "description": "Gestión de riesgo",
                    "required_regime": ["TREND", "RANGE"],
                    "membership_required": "basic"
                }
            },
            "membership_levels": {
                "basic": {
                    "modules_allowed": ["oliver_velez", "risk_manager"],
                    "description": "Membresía básica"
                },
                "premium": {
                    "modules_allowed": ["oliver_velez", "risk_manager"],
                    "description": "Membresía premium"
                }
            },
            "default_membership": "basic"
        }
    
    def is_module_enabled(self, module_name: str) -> bool:
        """
        Verifica si un módulo está habilitado
        
        Args:
            module_name: Nombre del módulo
        
        Returns:
            True si el módulo está habilitado, False en caso contrario
        """
        module = self.config.get("active_modules", {}).get(module_name)
        if not module:
            return False
        return module.get("enabled", False)
    
    def can_execute_module(self, 
                          module_name: str, 
                          membership: MembershipLevel = MembershipLevel.BASIC) -> bool:
        """
        Verifica si un módulo puede ejecutarse según la membresía
        
        Args:
            module_name: Nombre del módulo
            membership: Nivel de membresía del usuario
        
        Returns:
            True si el módulo puede ejecutarse, False en caso contrario
        """
        # Verificar si el módulo está habilitado
        if not self.is_module_enabled(module_name):
            return False
        
        module = self.config.get("active_modules", {}).get(module_name)
        if not module:
            return False
        
        # Verificar membresía requerida
        required_membership = module.get("membership_required", "basic")
        
        # Premium tiene acceso a todo, básico solo a módulos básicos
        if required_membership == "premium" and membership == MembershipLevel.BASIC:
            return False
        
        # Verificar si el módulo está en la lista de módulos permitidos para esta membresía
        membership_config = self.config.get("membership_levels", {}).get(membership.value, {})
        allowed_modules = membership_config.get("modules_allowed", [])
        
        return module_name in allowed_modules
    
    def get_active_modules(self, 
                          membership: MembershipLevel = MembershipLevel.BASIC) -> List[str]:
        """
        Obtiene la lista de módulos activos para un nivel de membresía
        
        Args:
            membership: Nivel de membresía
        
        Returns:
            Lista de nombres de módulos activos
        """
        active_modules = []
        
        for module_name, module_config in self.config.get("active_modules", {}).items():
            if self.can_execute_module(module_name, membership):
                active_modules.append(module_name)
        
        return active_modules
    
    def get_modules_for_regime(self, 
                              regime: str,
                              membership: MembershipLevel = MembershipLevel.BASIC) -> List[str]:
        """
        Obtiene los módulos que pueden ejecutarse para un régimen específico
        
        Args:
            regime: Régimen de mercado (TREND, RANGE, CRASH, NEUTRAL)
            membership: Nivel de membresía
        
        Returns:
            Lista de nombres de módulos que pueden ejecutarse
        """
        available_modules = []
        
        for module_name, module_config in self.config.get("active_modules", {}).items():
            if not self.can_execute_module(module_name, membership):
                continue
            
            required_regimes = module_config.get("required_regime", [])
            if regime in required_regimes:
                available_modules.append(module_name)
        
        return available_modules
    
    def enable_module(self, module_name: str) -> None:
        """Habilita un módulo"""
        if "active_modules" not in self.config:
            self.config["active_modules"] = {}
        
        if module_name not in self.config["active_modules"]:
            logger.warning(f"Intento de habilitar módulo inexistente: {module_name}")
            return
        
        self.config["active_modules"][module_name]["enabled"] = True
        self._save_config()
        logger.info(f"Módulo {module_name} habilitado")
    
    def disable_module(self, module_name: str) -> None:
        """Deshabilita un módulo"""
        if "active_modules" not in self.config:
            return
        
        if module_name not in self.config["active_modules"]:
            logger.warning(f"Intento de deshabilitar módulo inexistente: {module_name}")
            return
        
        self.config["active_modules"][module_name]["enabled"] = False
        self._save_config()
        logger.info(f"Módulo {module_name} deshabilitado")
    
    def save_config(self) -> None:
        """Guarda la configuración en StorageManager (SSOT)"""
        self.storage.save_modules_config(self.config)
        logger.debug("Configuración de módulos guardada en StorageManager (SSOT)")
    
    
    def get_module_info(self, module_name: str) -> Optional[Dict]:
        """Obtiene información sobre un módulo específico"""
        return self.config.get("active_modules", {}).get(module_name)
    
    def get_all_modules_info(self) -> Dict:
        """Obtiene información sobre todos los módulos"""
        return self.config.get("active_modules", {})


# Instancia global del gestor de módulos
_module_manager_instance: Optional[ModuleManager] = None


def get_module_manager() -> ModuleManager:
    """Obtiene la instancia global del gestor de módulos"""
    global _module_manager_instance
    if _module_manager_instance is None:
        _module_manager_instance = ModuleManager()
    return _module_manager_instance
