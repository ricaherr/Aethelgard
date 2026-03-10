"""
RBAC Dependencies: Role-Based Access Control decorators.

Proporciona decoradores y funciones para validación de roles en endpoints FastAPI.

Uso:
  @router.get('/api/admin/...')
  async def endpoint(..., token: TokenPayload = Depends(require_admin_role)):
      # El endpoint solo se ejecuta si token.role == 'admin'
      ...

  O directamente como middleware en Depends():
  async def endpoint(..., _: None = Depends(require_role('admin'))):
      ...

Governance:
  - Enums: UserRole (SSOT)
"""
import logging
from typing import Callable, Optional
from functools import wraps
from fastapi import HTTPException, status, Depends

from models.auth import TokenPayload
from models.user_enums import UserRole
from core_brain.api.dependencies.auth import get_current_active_user

logger = logging.getLogger(__name__)


def require_role(*allowed_roles: str) -> Callable:
    """
    Dependency factory: Retorna una función que valida roles.
    
    Uso:
      @router.post('/admin/config')
      async def set_config(_: None = Depends(require_role('admin'))):
          pass
    
    Args:
        *allowed_roles: Roles permitidos (ej: 'admin', 'trader', 'super_admin')
    
    Retorna:
        Función de dependencia que valida el token de usuario
    """
    async def validate_role(token: TokenPayload = Depends(get_current_active_user)) -> TokenPayload:
        if token.role not in allowed_roles:
            logger.warning(
                f"[RBAC] Unauthorized access attempt: user {token.sub} (role={token.role}) "
                f"tried to access endpoint requiring roles: {allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {', '.join(allowed_roles)}. Your role: {token.role}"
            )
        return token
    
    return validate_role


# ── Aliases for common role validations with auto-dependency injection ──────────

def require_admin(token: TokenPayload = Depends(get_current_active_user)) -> TokenPayload:
    """Dependency: Validate that user is ADMIN."""
    if token.role != UserRole.ADMIN.value:
        logger.warning(f"[RBAC] Unauthorized: user {token.sub} (role={token.role}) tried to access admin resource")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Admin role required (you have: {token.role})"
        )
    return token


def require_trader(token: TokenPayload = Depends(get_current_active_user)) -> TokenPayload:
    """Dependency: Validate that user is TRADER."""
    if token.role != UserRole.TRADER.value:
        logger.warning(f"[RBAC] Unauthorized: user {token.sub} (role={token.role}) tried to access trader resource")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Trader role required (you have: {token.role})"
        )
    return token


def require_any_role(*allowed_roles: str) -> Callable:
    """Dependency: Validate that user has ANY of the allowed roles."""
    async def validate(token: TokenPayload = Depends(get_current_active_user)) -> TokenPayload:
        if token.role not in allowed_roles:
            logger.warning(
                f"[RBAC] Unauthorized: user {token.sub} (role={token.role}) "
                f"tried to access endpoint requiring one of: {allowed_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required one of: {', '.join(allowed_roles)}"
            )
        return token
    return validate


def require_all_roles(*required_roles: str) -> Callable:
    """
    Dependency: Validate that user has ALL required roles (advanced use case).
    
    Nota: En sistemas más simples, típicamente un usuario tiene UN rol, no múltiples.
    Esta función es para futuros sistemas multi-role (ej: admin+auditor).
    """
    async def validate(token: TokenPayload = Depends(get_current_active_user)) -> TokenPayload:
        # Asumiendo token.role puede ser list o tuple en futuros sistemas
        user_roles = token.role if isinstance(token.role, (list, tuple)) else [token.role]
        
        missing_roles = [r for r in required_roles if r not in user_roles]
        if missing_roles:
            logger.warning(
                f"[RBAC] Unauthorized: user {token.sub} missing roles: {missing_roles}"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing required roles: {', '.join(missing_roles)}"
            )
        return token
    return validate


# ── Backward Compatibility ─────────────────────────────────────────────────────

# Alias para código existente
requires_admin = require_admin
requires_trader = require_trader

