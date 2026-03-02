"""
Authentication Router: Secure Session Management with HttpOnly Cookies.

Phase 3 Implementation (Architectural Refactor):
- Replaces localStorage token storage (XSS-vulnerable)
- Uses HttpOnly cookies (JS-inaccessible, server-managed)
- Implements refresh token rotation (30-day lifecycle)
- Client-side: credentials: 'include' auto-attaches cookies

Security Standards:
- OWASP Top 10 (Session management, Auth)
- JWT token validation still required
- Server-side token revocation possible
- CSRF protection via SameSite=Lax
"""
import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr

from core_brain.services.auth_service import AuthService
from core_brain.api.dependencies.auth import get_auth_service, get_current_active_user
from core_brain.api.dependencies.session_manager import (
    SessionManager,
    get_session_manager,
    COOKIE_CONFIG
)
from data_vault.storage import StorageManager
from models.auth import TokenPayload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


class UserRegister(BaseModel):
    email: EmailStr
    password: str
    tenant_id: str
    role: str = "user"


class LoginResponse(BaseModel):
    """
    Login response (NO TOKEN IN BODY).
    Token is sent via HttpOnly cookie automatically by browser.
    """
    user_id: str
    email: str
    tenant_id: str
    role: str
    message: str = "Logged in successfully"


class RefreshResponse(BaseModel):
    """Refresh token response (new token in HttpOnly cookie)."""
    status: str = "token_refreshed"
    message: str = "Access token refreshed"


# ============ DEPENDENCY INJECTION ============
def _get_storage() -> Any:
    """Lazy-load StorageManager."""
    from core_brain.server import _get_storage as get_storage_from_server
    return get_storage_from_server()


# ============ REGISTER ============
@router.post("/register", response_model=Dict[str, Any])
async def register(
    user_data: UserRegister,
    auth_service: AuthService = Depends(get_auth_service)
) -> Dict[str, Any]:
    """
    Register new user (email + password).
    Does NOT create session (user must login separately).
    
    Returns:
        user_id and confirmation message
    """
    try:
        # Check if user already exists
        existing_user = auth_service.repo.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        
        # Hash password and create user
        hashed_password = auth_service.get_password_hash(user_data.password)
        user_id = auth_service.repo.create_user(
            email=user_data.email,
            password_hash=hashed_password,
            tenant_id=user_data.tenant_id,
            role=user_data.role
        )
        
        logger.info(f"User registered: {user_id} ({user_data.email})")
        
        return {
            "status": "success",
            "user_id": user_id,
            "message": "User registered successfully. Please login."
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Registration error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Registration failed"
        )


# ============ LOGIN (HttpOnly Cookie) ============
@router.post("/login", response_model=LoginResponse)
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service),
    request: Request = None
) -> LoginResponse:
    """
    Login endpoint with HttpOnly cookie session creation.
    
    Security:
    1. Verify password
    2. Create JWT tokens (access + refresh)
    3. Store token hashes in DB for revocation
    4. Set HttpOnly cookies (auto-managed by browser)
    5. Return user info ONLY (NO TOKEN in response body)
    
    Client Usage:
        const res = await fetch('/auth/login', {
            method: 'POST',
            credentials: 'include',  // IMPORTANT: auto-attach cookies
            ...
        });
        // Token already in HttpOnly cookie, nothing to store in localStorage
    """
    try:
        # Initialize session manager with storage
        storage = _get_storage()
        session_manager = SessionManager(storage)
        
        # 1. Authenticate user
        user = auth_service.repo.get_user_by_email(form_data.username)
        if not user:
            logger.warning(f"Login failed: user not found ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        if not auth_service.verify_password(form_data.password, user["password_hash"]):
            logger.warning(f"Login failed: invalid password ({form_data.username})")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials"
            )
        
        # 2. Create tokens
        access_token = auth_service.create_access_token(
            subject=user["id"],
            tenant_id=user["tenant_id"],
            role=user["role"]
        )
        
        refresh_token = auth_service.create_refresh_token(
            subject=user["id"],
            tenant_id=user["tenant_id"]
        )
        
        # 3. Create session (store token hashes, set cookies)
        user_agent = request.headers.get("user-agent") if request else None
        client_ip = (
            request.client.host if request and request.client else None
        )
        
        session_manager.create_session(
            response=response,
            user_id=user["id"],
            access_token=access_token,
            refresh_token=refresh_token,
            user_agent=user_agent,
            ip_address=client_ip
        )
        
        logger.info(f"User logged in: {user['id']} ({user['email']})")
        
        # 4. Return user info only (token is in HttpOnly cookie)
        return LoginResponse(
            user_id=user["id"],
            email=user["email"],
            tenant_id=user["tenant_id"],
            role=user["role"]
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Login error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


# ============ REFRESH TOKEN ============
@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    request: Request = None
) -> RefreshResponse:
    """
    Refresh access token using refresh token from HttpOnly cookie.
    
    Called when:
    - Access token expires (client gets 401)
    - Or proactively before expiration
    
    Process:
    1. Extract refresh_token from HttpOnly cookie (auto-sent by browser)
    2. Validate JWT signature
    3. Check revocation status in DB
    4. Create new access_token
    5. Update HttpOnly cookie
    
    Security:
    - Refresh token never exposed to JavaScript
    - Rotation: old token hashed in DB, new token issued
    - Client doesn't need to handle token storage
    """
    try:
        # Initialize session manager with storage
        storage = _get_storage()
        session_manager = SessionManager(storage)
        
        # Get refresh token from cookie
        refresh_token_cookie = request.cookies.get(COOKIE_CONFIG["refresh_token"]["name"])
        if not refresh_token_cookie:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token missing"
            )
        
        # Validate refresh token
        token_payload = auth_service.verify_token(refresh_token_cookie)
        if not token_payload or token_payload.token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token"
            )
        
        # Check revocation
        is_valid = session_manager.validate_token(refresh_token_cookie)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token revoked"
            )
        
        # Create new access token
        new_access_token = auth_service.create_access_token(
            subject=token_payload.sub,
            tenant_id=token_payload.tid,
            role=token_payload.role
        )
        
        # Update session
        user_agent = request.headers.get("user-agent") if request else None
        client_ip = (
            request.client.host if request and request.client else None
        )
        
        session_manager.refresh_access_token(
            response=response,
            user_id=token_payload.sub,
            new_access_token=new_access_token,
            user_agent=user_agent,
            ip_address=client_ip
        )
        
        logger.debug(f"Token refreshed for user {token_payload.sub}")
        
        return RefreshResponse()
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Token refresh error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token refresh failed"
        )


# ============ LOGOUT ============
@router.post("/logout", response_model=Dict[str, str])
async def logout(
    response: Response,
    auth_service: AuthService = Depends(get_auth_service),
    request: Request = None
) -> Dict[str, str]:
    """
    Logout: Revoke tokens and clear cookies.
    
    Process:
    1. Extract access_token from cookie
    2. Mark token as revoked in DB
    3. Delete HttpOnly cookies
    4. Return confirmation
    
    After logout:
    - Cookies automatically deleted from browser
    - Token hashes marked as revoked (cannot be refreshed)
    - Next API request will be 401 (no valid token)
    """
    try:
        # Initialize session manager with storage
        storage = _get_storage()
        session_manager = SessionManager(storage)
        
        # Get access token from cookie
        access_token = request.cookies.get(COOKIE_CONFIG["access_token"]["name"])
        
        if access_token:
            # Validate token to get user_id for audit
            token_payload = auth_service.verify_token(access_token)
            user_id = token_payload.sub if token_payload else "unknown"
            
            # Revoke token
            session_manager.revoke_session(
                response=response,
                token=access_token,
                user_id=user_id
            )
            
            logger.info(f"User logged out: {user_id}")
        else:
            # Cookie already deleted, just clear anyway
            session_manager.revoke_session(
                response=response,
                token="",
                user_id="unknown"
            )
        
        return {"status": "success", "message": "Logged out successfully"}
        
    except Exception as e:
        logger.error(f"Logout error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Logout failed"
        )


# ============ GET CURRENT USER (HttpOnly Cookie Auth) ============
@router.get("/me", response_model=Dict[str, Any])
async def get_current_user(
    token: TokenPayload = Depends(get_current_active_user)
) -> Dict[str, Any]:
    """
    Get current authenticated user info from HttpOnly cookie.
    
    Endpoint called by frontend on app load to verify session validity.
    Token is extracted from HttpOnly cookie automatically via FastAPI dependency.
    
    Returns:
        User metadata (user_id, email, tenant_id, role) from JWT token
        
    Security:
    - Token validated via JWT signature (done in dependency)
    - No additional database query needed - token is already verified
    - No token exposed in response body
    - Cookie is auto-managed by browser
    """
    try:
        # Return user data from the validated JWT token
        # Token is already verified in get_current_active_user dependency
        # so we know it's valid and the data is trustworthy
        return {
            "user_id": token.sub,
            "tenant_id": token.tid,
            "role": token.role
        }
        
    except Exception as e:
        logger.error(f"Get current user error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve user"
        )
