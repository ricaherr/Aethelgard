"""
AuthRepository — Authentication & User Management (SSOT)
=========================================================

SINGLE RESPONSIBILITY:
- CRUD operations on sys_users (global authentication table)
- Audit logging to sys_audit_logs
- Delegate all DB connections to DatabaseManager (ZERO direct sqlite3.connect calls)

GOVERNANCE:
- Base de datos única: data_vault/global/aethelgard.db (SSOT)
- Tabla: sys_users (convención sys_ = system table)
- Política: Soft delete only (nunca hard delete de usuarios)
- Auditoría: Todos los cambios automáticamente logged en sys_audit_logs

TRACE_ID: FIX-AUTH-REPO-DB-MANAGER-2026-04-01
"""

import os
import uuid
import logging
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone

from .base_repo import BaseRepository
from .database_manager import get_database_manager

logger = logging.getLogger(__name__)


class AuthRepository(BaseRepository):
    """Authentication and user management repository (uses DatabaseManager)."""

    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            db_path = os.path.join(
                os.path.dirname(__file__), "global", "aethelgard.db"
            )
        super().__init__(db_path)

    # ──────────────────────────────────────────────────────────────────────────────
    # LECTURA: Get/List Methods
    # ──────────────────────────────────────────────────────────────────────────────

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user by ID (incluye deleted users si status='deleted')."""
        results = self.db_manager.execute_query(
            self.db_path,
            "SELECT * FROM sys_users WHERE id = ?",
            (user_id,)
        )
        return results[0] if results else None

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Get user by email (solo activos y suspendidos, excluye deleted)."""
        results = self.db_manager.execute_query(
            self.db_path,
            "SELECT * FROM sys_users WHERE email = ? AND status != 'deleted'",
            (email,)
        )
        return results[0] if results else None

    def list_all_users(self, include_deleted: bool = False) -> List[Dict[str, Any]]:
        """List all users (admin/trader)."""
        if include_deleted:
            query = "SELECT id, email, role, status, tier, created_at, updated_at FROM sys_users ORDER BY created_at DESC"
        else:
            query = "SELECT id, email, role, status, tier, created_at, updated_at FROM sys_users WHERE status != 'deleted' ORDER BY created_at DESC"
        return self.db_manager.execute_query(self.db_path, query)

    def list_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        """List users by role (admin|trader), excluye deleted."""
        return self.db_manager.execute_query(
            self.db_path,
            "SELECT id, email, role, status, tier, created_at FROM sys_users WHERE role = ? AND status != 'deleted' ORDER BY created_at DESC",
            (role,)
        )

    def list_users_by_status(self, status: str) -> List[Dict[str, Any]]:
        """List users by status (active|suspended|deleted)."""
        return self.db_manager.execute_query(
            self.db_path,
            "SELECT id, email, role, status, tier, created_at FROM sys_users WHERE status = ? ORDER BY created_at DESC",
            (status,)
        )

    def user_exists(self, email: str) -> bool:
        """Check if email exists (excluyendo deleted)."""
        user = self.get_user_by_email(email)
        return user is not None

    # ──────────────────────────────────────────────────────────────────────────────
    # ESCRITURA: Create/Update/Delete Methods
    # ──────────────────────────────────────────────────────────────────────────────

    def create_user(
        self,
        email: str,
        password_hash: str,
        role: str,
        tier: str = "BASIC",
        user_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> str:
        """Create new user. Returns user_id."""
        if user_id is None:
            user_id = str(uuid.uuid4())

        now = datetime.now(timezone.utc).isoformat()

        try:
            self.db_manager.execute_update(
                self.db_path,
                """
                INSERT INTO sys_users
                (id, email, password_hash, role, tier, status, created_at, updated_at, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, email, password_hash, role, tier, "active", now, now, created_by),
            )
            logger.info(f"[AuthRepo] User created: {email} ({role})")
            return user_id
        except Exception as e:
            logger.error(f"[AuthRepo] Error creating user {email}: {e}")
            raise

    def update_user_role(self, user_id: str, new_role: str, updated_by: Optional[str] = None) -> bool:
        """Update user role (admin|trader). Returns True if successful."""
        user = self.get_user_by_id(user_id)
        if not user:
            logger.warning(f"[AuthRepo] User not found: {user_id}")
            return False

        now = datetime.now(timezone.utc).isoformat()
        self.db_manager.execute_update(
            self.db_path,
            "UPDATE sys_users SET role = ?, updated_at = ?, updated_by = ? WHERE id = ?",
            (new_role, now, updated_by, user_id),
        )
        logger.info(f"[AuthRepo] User role updated: {user_id} → {new_role}")
        return True

    def update_user_status(self, user_id: str, new_status: str, updated_by: Optional[str] = None) -> bool:
        """Update user status (active|suspended|deleted). Returns True if successful."""
        user = self.get_user_by_id(user_id)
        if not user:
            logger.warning(f"[AuthRepo] User not found: {user_id}")
            return False

        now = datetime.now(timezone.utc).isoformat()
        deleted_at = now if new_status == "deleted" else None

        self.db_manager.execute_update(
            self.db_path,
            "UPDATE sys_users SET status = ?, updated_at = ?, updated_by = ?, deleted_at = ? WHERE id = ?",
            (new_status, now, updated_by, deleted_at, user_id),
        )
        action = "suspended" if new_status == "suspended" else new_status
        logger.info(f"[AuthRepo] User {action}: {user_id}")
        return True

    def update_user_tier(self, user_id: str, new_tier: str, updated_by: Optional[str] = None) -> bool:
        """Update user membership tier (BASIC|PREMIUM|INSTITUTIONAL)."""
        user = self.get_user_by_id(user_id)
        if not user:
            return False

        now = datetime.now(timezone.utc).isoformat()
        self.db_manager.execute_update(
            self.db_path,
            "UPDATE sys_users SET tier = ?, updated_at = ?, updated_by = ? WHERE id = ?",
            (new_tier, now, updated_by, user_id),
        )
        logger.info(f"[AuthRepo] User tier updated: {user_id} → {new_tier}")
        return True

    def soft_delete_user(self, user_id: str, updated_by: Optional[str] = None) -> bool:
        """Soft delete user (marks status=deleted, no hard delete for compliance)."""
        return self.update_user_status(user_id, "deleted", updated_by)

    def log_audit(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        status: str = "success",
        reason: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> None:
        """Log audit event to sys_audit_logs."""
        if trace_id is None:
            trace_id = str(uuid.uuid4())

        now = datetime.now(timezone.utc).isoformat()

        try:
            self.db_manager.execute_update(
                self.db_path,
                """
                INSERT INTO sys_audit_logs
                (user_id, action, resource, resource_id, old_value, new_value, status, reason, timestamp, trace_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, action, resource, resource_id, old_value, new_value, status, reason, now, trace_id),
            )
        except Exception as e:
            logger.error(f"[AuthRepo] Error logging audit: {e}")

    # ──────────────────────────────────────────────────────────────────────────────
    # JWT Secret Management
    # ──────────────────────────────────────────────────────────────────────────────

    def get_jwt_secret(self) -> Optional[str]:
        """Get JWT secret from sys_config."""
        results = self.db_manager.execute_query(
            self.db_path,
            "SELECT value FROM sys_config WHERE key = 'jwt_secret'",
        )
        return results[0]["value"] if results else None

    def set_jwt_secret(self, secret: str) -> None:
        """Set JWT secret in sys_config."""
        now = datetime.now(timezone.utc).isoformat()
        self.db_manager.execute_update(
            self.db_path,
            "INSERT OR REPLACE INTO sys_config (key, value, updated_at) VALUES (?, ?, ?)",
            ("jwt_secret", secret, now),
        )
