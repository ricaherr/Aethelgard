"""
Admin Router: User Management CRUD endpoints.

Arquitectura: Clean Architecture con Inyección de Dependencias obligatoria.
- Router → Depends(AdminService) → Depends(AuthService) → AuthRepository

Endpoints:
  GET  /api/admin/users              → List all users
  GET  /api/admin/users/{user_id}    → Get user details
  POST /api/admin/users              → Create new user
  PUT  /api/admin/users/{user_id}    → Update user (role/status/tier)
  DELETE /api/admin/users/{user_id}  → Soft delete user

Seguridad:
  - All endpoints require token with role='admin' (via @require_admin dependency)
  - Cannot modify own role to non-admin (lock-out protection)
  - Soft delete only (never hard delete)
  - All changes logged in sys_audit_logs
  
Gobernanza:
  - Type hints: 100%
  - Trace_ID: Obligatorio en todas las operaciones
  - Enums: UserRole, UserTier, UserStatus (SSOT)
  - DI: AdminService inyectado, no instanciado
"""
import logging
import uuid
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from core_brain.services.admin_service import AdminService
from core_brain.services.auth_service import AuthService
from core_brain.api.dependencies.auth import get_auth_service
from core_brain.api.dependencies.rbac import require_admin
from core_brain.api.schemas import user_to_response
from data_vault.auth_repo import AuthRepository
from models.auth import TokenPayload
from models.user_enums import UserRole, UserTier, UserStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["Admin"])


# ── Dependency Injection ───────────────────────────────────────────────────────

def _get_auth_repo() -> AuthRepository:
    """Lazy-load AuthRepository singleton."""
    return AuthRepository()


def get_admin_service(auth_repo: AuthRepository = Depends(_get_auth_repo)) -> AdminService:
    """Inyectar AdminService con AuthRepository.
    
    Patrón: Service Layer depende de Repository, nunca lo instancia internamente.
    """
    return AdminService(auth_repo=auth_repo)


# ── Pydantic Models ────────────────────────────────────────────────────────────

class UserCreateRequest(BaseModel):
    """Request body para crear usuario."""
    email: EmailStr
    password: str
    role: str  # Debe ser uno de UserRole.*
    tier: str = "BASIC"  # Debe ser uno de UserTier.*


class UserUpdateRequest(BaseModel):
    """Request body para actualizar usuario."""
    role: Optional[str] = None  # Debe ser uno de UserRole.* si se proporciona
    status: Optional[str] = None  # Debe ser active|suspended (NO deleted via API)
    tier: Optional[str] = None  # Debe ser uno de UserTier.* si se proporciona


class UserResponse(BaseModel):
    """Response model para usuario (sin password)."""
    id: str
    email: str
    role: str
    status: str
    tier: str
    created_at: str
    updated_at: str


# ── GET /api/admin/users ───────────────────────────────────────────────────────

@router.get("/users", response_model=List[UserResponse])
async def list_users(
    token: TokenPayload = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
) -> List[Dict[str, Any]]:
    """
    List all users (admin/trader).
    
    Requires: admin role
    """
    try:
        users = admin_service.list_all_users(include_deleted=False)
        logger.info(f"[AdminRouter] Usuarios listados por {token.sub}: {len(users)} usuarios")
        return users
    except Exception as e:
        logger.error(f"[AdminRouter] Error listing users: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list users"
        )


# ── GET /api/admin/users/{user_id} ──────────────────────────────────────────

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    token: TokenPayload = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
) -> Dict[str, Any]:
    """
    Get user details by ID.
    
    Requires: admin role
    """
    try:
        user = admin_service.get_user_by_id(user_id)
        
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        return user_to_response(user)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AdminRouter] Error getting user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get user"
        )


# ── POST /api/admin/users ───────────────────────────────────────────────────

@router.post("/users", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreateRequest,
    token: TokenPayload = Depends(require_admin),
    auth_service: AuthService = Depends(get_auth_service),
    admin_service: AdminService = Depends(get_admin_service)
) -> Dict[str, Any]:
    """
    Create new user (admin/trader).
    
    Requires: admin role
    
    Validations:
    - Email must be unique
    - Role must be admin|trader
    - Tier must be BASIC|PREMIUM|INSTITUTIONAL
    """
    try:
        # Validar que email no exista
        if admin_service.user_exists(request.email):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email {request.email} already exists"
            )
        
        # Validar role
        if not UserRole.is_valid(request.role):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Role must be one of: {', '.join(UserRole.valid_roles())}"
            )
        
        # Validar tier
        if not UserTier.is_valid(request.tier):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tier must be one of: {', '.join(UserTier.valid_tiers())}"
            )
        
        # Hash password
        password_hash = auth_service.get_password_hash(request.password)
        
        # Create user
        trace_id = str(uuid.uuid4())
        user_id = admin_service.create_user(
            email=request.email,
            password_hash=password_hash,
            role=request.role,
            tier=request.tier,
            created_by=token.sub,
            trace_id=trace_id
        )
        
        logger.info(f"[AdminRouter] User created: {request.email} (role={request.role}) by {token.sub}, trace_id={trace_id}")
        
        # Return created user
        user = admin_service.get_user_by_id(user_id)
        return user_to_response(user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AdminRouter] Error creating user: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create user"
        )


# ── PUT /api/admin/users/{user_id} ──────────────────────────────────────────

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    request: UserUpdateRequest,
    token: TokenPayload = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
) -> Dict[str, Any]:
    """
    Update user (role/status/tier).
    
    Requires: admin role
    
    Protections:
    - Cannot change own role to non-admin (lock-out prevention)
    - Cannot change own status to suspended|deleted
    """
    try:
        # Get user
        user = admin_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # Protection: No self-destruction
        if user_id == token.sub:
            if request.role and request.role != user["role"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change your own role (lock-out prevention)"
                )
            if request.status and request.status != user["status"]:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot change your own status"
                )
        
        # Update role
        trace_id = str(uuid.uuid4())
        if request.role and request.role != user["role"]:
            if not UserRole.is_valid(request.role):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Role must be one of: {', '.join(UserRole.valid_roles())}"
                )
            admin_service.update_user_role(
                user_id=user_id,
                new_role=request.role,
                updated_by=token.sub,
                trace_id=trace_id
            )
        
        # Update status
        if request.status and request.status != user["status"]:
            if not UserStatus.is_valid(request.status) or request.status == UserStatus.DELETED.value:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Status must be one of: {', '.join(UserStatus.active_statuses())}"
                )
            admin_service.update_user_status(
                user_id=user_id,
                new_status=request.status,
                updated_by=token.sub,
                trace_id=trace_id
            )
        
        # Update tier
        if request.tier and request.tier != user["tier"]:
            if not UserTier.is_valid(request.tier):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Tier must be one of: {', '.join(UserTier.valid_tiers())}"
                )
            admin_service.update_user_tier(
                user_id=user_id,
                new_tier=request.tier,
                updated_by=token.sub,
                trace_id=trace_id
            )
        
        logger.info(f"[AdminRouter] User updated: {user_id} by {token.sub} (trace_id={trace_id})")
        
        # Return updated user
        updated_user = admin_service.get_user_by_id(user_id)
        return user_to_response(updated_user)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AdminRouter] Error updating user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update user"
        )


# ── DELETE /api/admin/users/{user_id} ────────────────────────────────────────

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    token: TokenPayload = Depends(require_admin),
    admin_service: AdminService = Depends(get_admin_service)
) -> Dict[str, str]:
    """
    Soft delete user (status='deleted').
    
    Requires: admin role
    
    Policy: NUNCA borrar registros - audit trail preservation
    """
    try:
        # Get user
        user = admin_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {user_id} not found"
            )
        
        # Protection: No self-deletion
        if user_id == token.sub:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot delete your own account"
            )
        
        # Soft delete
        trace_id = str(uuid.uuid4())
        admin_service.soft_delete_user(
            user_id=user_id,
            updated_by=token.sub,
            trace_id=trace_id
        )
        
        logger.info(f"[AdminRouter] User deleted: {user_id} by {token.sub} (trace_id={trace_id})")
        
        return {"status": "success", "message": f"User {user_id} soft-deleted"}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AdminRouter] Error deleting user {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user"
        )
