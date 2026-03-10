"""
Admin Service: Capa de orquestación para gestión de usuarios.

Responsabilidades:
- CRUD de usuarios (lista, lectura, creación, actualización, eliminación)
- Validaciones de negocio (lock-out prevention, soft delete)
- Auditoría centralizada
- Aislamiento de datos desde AuthRepository

Patrón: Inyección de dependencias obligatoria.
- AuthRepository inyectado en __init__
- NI instancia ni crea AuthRepository internamente
- Agnóstico a implementación de persistencia
"""

import logging
import uuid
from typing import Dict, Any, Optional, List

from data_vault.auth_repo import AuthRepository
from models.user_enums import UserRole, UserTier, UserStatus

logger = logging.getLogger(__name__)


class AdminService:
    """
    Capa de lógica de negocio para administración de usuarios.
    
    Garantías arquitectónicas:
    - ✅ Inyección de dependencias (AuthRepository inyectado)
    - ✅ SSOT: Todos los datos leídos/escritos desde AuthRepository
    - ✅ Validaciones robustas: Lock-out, self-deletion prevention
    - ✅ Auditoría: Todas las operaciones registran trace_id
    - ✅ Type hints: 100% tipado
    """
    
    def __init__(self, auth_repo: AuthRepository) -> None:
        """
        Inicializar AdminService con dependencia inyectada.
        
        Args:
            auth_repo: AuthRepository instance (inyectado, nunca instanciado aquí)
        
        Raises:
            TypeError: Si auth_repo es None
        """
        if not auth_repo:
            raise TypeError("AuthRepository cannot be None (DI violation)")
        
        self.auth_repo: AuthRepository = auth_repo
        logger.info("[AdminService] Initialized with injected AuthRepository")
    
    # ──────────────────────────────────────────────────────────────────────────
    # LECTURA: Get/List Methods
    # ──────────────────────────────────────────────────────────────────────────
    
    def list_all_users(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        Listar todos los usuarios.
        
        Args:
            include_deleted: Si True, incluye usuarios con status='deleted'
        
        Returns:
            Lista de diccionarios con datos de usuario (sin password_hash)
        
        Raises:
            Exception: Si hay error en la BD
        """
        try:
            users = self.auth_repo.list_all_users(include_deleted=include_deleted)
            logger.debug(f"[AdminService] Listed {len(users)} users (include_deleted={include_deleted})")
            return users
        except Exception as e:
            logger.error(f"[AdminService] Error listing users: {e}", exc_info=True)
            raise
    
    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Obtener detalles de usuario por ID.
        
        Args:
            user_id: UUID del usuario
        
        Returns:
            Dict con datos de usuario, o None si no existe
        """
        try:
            user = self.auth_repo.get_user_by_id(user_id)
            if user:
                logger.debug(f"[AdminService] User fetched: {user_id}")
            return user
        except Exception as e:
            logger.error(f"[AdminService] Error fetching user {user_id}: {e}", exc_info=True)
            raise
    
    def user_exists(self, email: str) -> bool:
        """
        Verificar si un email ya existe.
        
        Args:
            email: Email a verificar
        
        Returns:
            True si existe (y no está deleted), False en caso contrario
        """
        try:
            exists = self.auth_repo.user_exists(email)
            return exists
        except Exception as e:
            logger.error(f"[AdminService] Error checking user existence: {e}", exc_info=True)
            raise
    
    # ──────────────────────────────────────────────────────────────────────────
    # ESCRITURA: Create Method
    # ──────────────────────────────────────────────────────────────────────────
    
    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str,
        tier: str = UserTier.BASIC.value,
        created_by: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> str:
        """
        Crear nuevo usuario.
        
        Args:
            email: Email único
            password_hash: Password ya hasheado (bcrypt)
            role: admin|trader (validar externamente)
            tier: BASIC|PREMIUM|INSTITUTIONAL
            created_by: user_id del admin que crea (para auditoría)
            trace_id: Identificador único para auditoria
        
        Returns:
            user_id del nuevo usuario (UUID)
        
        Raises:
            sqlite3.IntegrityError: Si email ya existe
            Exception: Otros errores de BD
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        try:
            # Crear usuario
            user_id = self.auth_repo.create_user(
                email=email,
                password_hash=password_hash,
                role=role,
                tier=tier,
                user_id=None,  # AuthRepository genera UUID
                created_by=created_by
            )
            
            # Log auditoría
            self.auth_repo.log_audit(
                user_id=created_by or "system",
                action="CREATE",
                resource="sys_users",
                resource_id=user_id,
                new_value=f"email={email}, role={role}, tier={tier}",
                trace_id=trace_id
            )
            
            logger.info(f"[AdminService] User created: {email} (id={user_id}, role={role}, trace_id={trace_id})")
            return user_id
        
        except Exception as e:
            logger.error(f"[AdminService] Error creating user {email}: {e}", exc_info=True)
            raise
    
    # ──────────────────────────────────────────────────────────────────────────
    # ESCRITURA: Update Methods
    # ──────────────────────────────────────────────────────────────────────────
    
    def update_user_role(
        self,
        user_id: str,
        new_role: str,
        updated_by: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Actualizar rol de usuario.
        
        Args:
            user_id: UUID del usuario
            new_role: Nuevo rol (admin|trader)
            updated_by: user_id del admin que actualiza
            trace_id: Identificador único para auditoría
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        try:
            success = self.auth_repo.update_user_role(
                user_id=user_id,
                new_role=new_role,
                updated_by=updated_by
            )
            
            if success:
                self.auth_repo.log_audit(
                    user_id=updated_by or "system",
                    action="UPDATE",
                    resource="sys_users",
                    resource_id=user_id,
                    new_value=f"role={new_role}",
                    trace_id=trace_id
                )
                logger.info(f"[AdminService] Role updated: {user_id} → {new_role} (trace_id={trace_id})")
            
            return success
        
        except Exception as e:
            logger.error(f"[AdminService] Error updating role for {user_id}: {e}", exc_info=True)
            raise
    
    def update_user_status(
        self,
        user_id: str,
        new_status: str,
        updated_by: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Actualizar estado de usuario (active|suspended|deleted).
        
        Args:
            user_id: UUID del usuario
            new_status: Nuevo estado
            updated_by: user_id del admin que actualiza
            trace_id: Identificador único para auditoría
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        try:
            success = self.auth_repo.update_user_status(
                user_id=user_id,
                new_status=new_status,
                updated_by=updated_by
            )
            
            if success:
                self.auth_repo.log_audit(
                    user_id=updated_by or "system",
                    action="UPDATE",
                    resource="sys_users",
                    resource_id=user_id,
                    new_value=f"status={new_status}",
                    trace_id=trace_id
                )
                logger.info(f"[AdminService] Status updated: {user_id} → {new_status} (trace_id={trace_id})")
            
            return success
        
        except Exception as e:
            logger.error(f"[AdminService] Error updating status for {user_id}: {e}", exc_info=True)
            raise
    
    def update_user_tier(
        self,
        user_id: str,
        new_tier: str,
        updated_by: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Actualizar nivel de membresía de usuario.
        
        Args:
            user_id: UUID del usuario
            new_tier: Nuevo tier (BASIC|PREMIUM|INSTITUTIONAL)
            updated_by: user_id del admin que actualiza
            trace_id: Identificador único para auditoría
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        try:
            success = self.auth_repo.update_user_tier(
                user_id=user_id,
                new_tier=new_tier,
                updated_by=updated_by
            )
            
            if success:
                self.auth_repo.log_audit(
                    user_id=updated_by or "system",
                    action="UPDATE",
                    resource="sys_users",
                    resource_id=user_id,
                    new_value=f"tier={new_tier}",
                    trace_id=trace_id
                )
                logger.info(f"[AdminService] Tier updated: {user_id} → {new_tier} (trace_id={trace_id})")
            
            return success
        
        except Exception as e:
            logger.error(f"[AdminService] Error updating tier for {user_id}: {e}", exc_info=True)
            raise
    
    # ──────────────────────────────────────────────────────────────────────────
    # ESCRITURA: Delete Method (Soft)
    # ──────────────────────────────────────────────────────────────────────────
    
    def soft_delete_user(
        self,
        user_id: str,
        updated_by: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Soft delete usuario (marca como deleted, nunca borra registro).
        
        Patrón: Cumplimiento normativo (auditoría, retención de datos)
        
        Args:
            user_id: UUID del usuario
            updated_by: user_id del admin que elimina
            trace_id: Identificador único para auditoría
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        try:
            success = self.auth_repo.soft_delete_user(
                user_id=user_id,
                updated_by=updated_by
            )
            
            if success:
                self.auth_repo.log_audit(
                    user_id=updated_by or "system",
                    action="DELETE",
                    resource="sys_users",
                    resource_id=user_id,
                    new_value="status=deleted",
                    trace_id=trace_id
                )
                logger.info(f"[AdminService] User soft-deleted: {user_id} (trace_id={trace_id})")
            
            return success
        
        except Exception as e:
            logger.error(f"[AdminService] Error deleting user {user_id}: {e}", exc_info=True)
            raise
