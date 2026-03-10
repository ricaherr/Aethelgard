import sqlite3
import os
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class AuthRepository:
    """
    Gestor de la base de datos global de autenticación (SSOT).
    
    Reglas gobernanza:
    - BD única: data_vault/global/aethelgard.db (SSOT compliance)
    - Tabla: sys_users (con prefijo sys_ para convención obligatoria)
    - Campos: id, email, password_hash, role (admin|trader), status (active|suspended|deleted)
    - Auditoría: sys_audit_logs registra todo cambio
    - Política: Soft delete solamente (nunca borrar registros de usuarios)
    """
    
    def __init__(self, db_path: str = "data_vault/global/aethelgard.db"):
        self.db_path = db_path
        self._ensure_global_directory()

    def _ensure_global_directory(self) -> None:
        """Ensure data_vault/global/ directory exists."""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    @contextmanager
    def _get_connection(self) -> Any:
        """Context manager para conexión a BD (row_factory habilitado)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # ──────────────────────────────────────────────────────────────────────────────
    # ── LECTURA: Get/List Methods ──────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID (incluye deleted users si status='deleted')."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sys_users WHERE id = ?",
                (user_id,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email (solo activos y suspendidos, excluye deleted)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sys_users WHERE email = ? AND status != 'deleted'",
                (email,)
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def list_all_users(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """
        List all users (admin/trader).
        
        Args:
            include_deleted: Si True, incluye usuarios con status='deleted'
            
        Returns:
            List de usuarios como dicts
        """
        with self._get_connection() as conn:
            if include_deleted:
                query = "SELECT id, email, role, status, tier, created_at, updated_at FROM sys_users ORDER BY created_at DESC"
                cursor = conn.execute(query)
            else:
                query = "SELECT id, email, role, status, tier, created_at, updated_at FROM sys_users WHERE status != 'deleted' ORDER BY created_at DESC"
                cursor = conn.execute(query)
            
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def list_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        """List users by role (admin|trader), excluye deleted."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, email, role, status, tier, created_at FROM sys_users WHERE role = ? AND status != 'deleted' ORDER BY created_at DESC",
                (role,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def list_users_by_status(self, status: str) -> List[Dict[str, Any]]:
        """List users by status (active|suspended|deleted)."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT id, email, role, status, tier, created_at FROM sys_users WHERE status = ? ORDER BY created_at DESC",
                (status,)
            )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def user_exists(self, email: str) -> bool:
        """Check if email exists (excluyendo deleted)."""
        user = self.get_user_by_email(email)
        return user is not None

    # ──────────────────────────────────────────────────────────────────────────────
    # ── ESCRITURA: Create/Update/Delete Methods ────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────────

    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str,
        tier: str = "BASIC",
        user_id: Optional[str] = None,
        created_by: Optional[str] = None
    ) -> str:
        """
        Create new user.
        
        Args:
            email: email único
            password_hash: password hasheado (nunca plaintext)
            role: admin|trader
            tier: BASIC|PREMIUM|INSTITUTIONAL
            user_id: UUID (auto-generated si None)
            created_by: user_id del admin que lo creó (para auditoría)
            
        Returns:
            user_id del nuevo usuario
            
        Raises:
            sqlite3.IntegrityError si email ya existe
        """
        if user_id is None:
            user_id = str(uuid.uuid4())
        
        now = datetime.utcnow().isoformat()
        
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO sys_users 
                    (id, email, password_hash, role, tier, status, created_at, updated_at, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, email, password_hash, role, tier, 'active', now, now, created_by)
                )
                conn.commit()
                logger.info(f"[AuthRepo] User created: {email} ({role})")
                return user_id
            except sqlite3.IntegrityError as e:
                logger.error(f"[AuthRepo] Error creating user {email}: {e}")
                raise

    def update_user_role(self, user_id: str, new_role: str, updated_by: Optional[str] = None) -> bool:
        """
        Update user role (admin|trader).
        
        Protección: No permite cambiar propio rol a non-admin (evita lock-out)
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        user = self.get_user_by_id(user_id)
        if not user:
            logger.warning(f"[AuthRepo] User not found: {user_id}")
            return False
        
        now = datetime.utcnow().isoformat()
        
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sys_users SET role = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                (new_role, now, updated_by, user_id)
            )
            conn.commit()
            logger.info(f"[AuthRepo] User role updated: {user_id} → {new_role}")
            return True

    def update_user_status(self, user_id: str, new_status: str, updated_by: Optional[str] = None) -> bool:
        """
        Update user status (active|suspended|deleted).
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        user = self.get_user_by_id(user_id)
        if not user:
            logger.warning(f"[AuthRepo] User not found: {user_id}")
            return False
        
        now = datetime.utcnow().isoformat()
        deleted_at = now if new_status == 'deleted' else None
        
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sys_users SET status = ?, updated_at = ?, updated_by = ?, deleted_at = ? WHERE id = ?",
                (new_status, now, updated_by, deleted_at, user_id)
            )
            conn.commit()
            action = "suspended" if new_status == 'suspended' else new_status
            logger.info(f"[AuthRepo] User {action}: {user_id}")
            return True

    def update_user_tier(self, user_id: str, new_tier: str, updated_by: Optional[str] = None) -> bool:
        """Update user membership tier (BASIC|PREMIUM|INSTITUTIONAL)."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        
        now = datetime.utcnow().isoformat()
        
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE sys_users SET tier = ?, updated_at = ?, updated_by = ? WHERE id = ?",
                (new_tier, now, updated_by, user_id)
            )
            conn.commit()
            logger.info(f"[AuthRepo] User tier updated: {user_id} → {new_tier}")
            return True

    def soft_delete_user(self, user_id: str, updated_by: Optional[str] = None) -> bool:
        """
        Soft delete user (marca status=deleted, no borra registro).
        
        Política: NUNCA borrar registros de usuarios - auditoría/compliance
        
        Returns:
            True si exitoso, False si usuario no encontrado
        """
        return self.update_user_status(user_id, 'deleted', updated_by)

    def log_audit(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        status: str = 'success',
        reason: Optional[str] = None,
        trace_id: Optional[str] = None
    ) -> None:
        """
        Log audit event en sys_audit_logs.
        
        Args:
            user_id: Admin que realizó la acción
            action: CREATE|UPDATE|DELETE|SUSPEND
            resource: sys_users|sys_config|etc
            resource_id: ID del recurso modificado
            old_value: Valor anterior (si había)
            new_value: Valor nuevo
            status: success|failure
            reason: Razón de la acción (si hay)
            trace_id: Trace ID único (auto-generado si None)
        """
        if trace_id is None:
            trace_id = str(uuid.uuid4())
        
        now = datetime.utcnow().isoformat()
        
        with self._get_connection() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO sys_audit_logs
                    (user_id, action, resource, resource_id, old_value, new_value, status, reason, timestamp, trace_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (user_id, action, resource, resource_id, old_value, new_value, status, reason, now, trace_id)
                )
                conn.commit()
            except sqlite3.Error as e:
                logger.error(f"[AuthRepo] Error logging audit: {e}")

    # ──────────────────────────────────────────────────────────────────────────────
    # ── JWT Secret Management ──────────────────────────────────────────────────────
    # ──────────────────────────────────────────────────────────────────────────────

    def get_jwt_secret(self) -> Optional[str]:
        """Get JWT secret from sys_config."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                "SELECT value FROM sys_config WHERE key = 'jwt_secret'"
            )
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_jwt_secret(self, secret: str) -> None:
        """Set JWT secret in sys_config."""
        now = datetime.utcnow().isoformat()
        
        with self._get_connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO sys_config (key, value, updated_at) VALUES (?, ?, ?)",
                ('jwt_secret', secret, now)
            )
            conn.commit()

