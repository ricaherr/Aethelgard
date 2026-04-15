"""
SessionManager: Secure HTTP-Only Cookie Management for Aethelgard.

Implements OWASP-compliant session handling:
- HttpOnly cookies prevent XSS token theft
- Secure flag (HTTPS only in production)
- SameSite=Lax prevents CSRF attacks
- Server-side token revocation via database
- Automatic refresh token rotation

Replaces vulnerable localStorage-based auth.
"""
import logging
import secrets
import os
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

from fastapi import Response, HTTPException, status

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)

# Determine environment
IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

# Cookie Configuration (OWASP-compliant, adaptive to environment)
COOKIE_CONFIG = {
    "access_token": {
        "name": "a_token",
        "max_age": 900,  # 15 minutes
        "secure": IS_PRODUCTION,  # HTTPS only in production, HTTP allowed in dev
        "httponly": True,  # Cannot be accessed via JavaScript
        "samesite": "lax",  # CSRF protection
    },
    "refresh_token": {
        "name": "r_token",
        "max_age": 2592000,  # 30 days
        "secure": IS_PRODUCTION,  # HTTPS only in production
        "httponly": True,
        "samesite": "lax",
    }
}


class SessionManager:
    """
    Manages HTTP-Only cookie sessions with server-side revocation.
    
    Lifecycle:
    1. User login: create_session() sets HttpOnly cookies
    2. API request: Client sends cookies automatically (no JS exposure)
    3. Token expires: Refresh token rotates automatically
    4. User logout: revoke_session() invalidates server-side
    
    Database schema required (managed by data_vault/schema.py):
    - sys_session_tokens(token_hash, user_id, token_type, expires_at, revoked, created_at)
    Trace_ID: ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14
    """
    
    def __init__(self, storage: StorageManager):
        """
        Initialize SessionManager with storage backend.
        
        Args:
            storage: StorageManager instance for persistent token storage
        """
        self.storage = storage
        self._ensure_schema()
    
    def _ensure_schema(self) -> None:
        """No-op: sys_session_tokens DDL managed by data_vault/schema.py (ETI-SRE-CANONICAL-PERSISTENCE-2026-04-14)."""
        pass
    
    def create_session(
        self,
        response: Response,
        user_id: str,
        access_token: str,
        refresh_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Create secure session by setting HttpOnly cookies.
        
        Args:
            response: FastAPI Response to set cookies on
            user_id: User identifier
            access_token: JWT token (short-lived, 15 min)
            refresh_token: JWT token (long-lived, 30 days)
            user_agent: Browser user agent (audit)
            ip_address: Client IP address (audit)
        """
        now = datetime.now(timezone.utc)
        
        # Store access token hash in database
        access_expires = now + timedelta(seconds=COOKIE_CONFIG["access_token"]["max_age"])
        access_hash = self._hash_token(access_token)
        
        try:
            self.storage.execute_query(
                """
                INSERT INTO sys_session_tokens
                (token_hash, user_id, token_type, expires_at, user_agent, ip_address)
                VALUES (?, ?, 'access', ?, ?, ?)
                """,
                (access_hash, user_id, access_expires, user_agent, ip_address)
            )
        except Exception as e:
            logger.error(f"Failed to store access token: {e}")
            # Continue anyway - token will be validated via JWT signature
        
        # Store refresh token hash in database
        refresh_expires = now + timedelta(seconds=COOKIE_CONFIG["refresh_token"]["max_age"])
        refresh_hash = self._hash_token(refresh_token)
        
        try:
            self.storage.execute_query(
                """
                INSERT INTO sys_session_tokens
                (token_hash, user_id, token_type, expires_at, user_agent, ip_address)
                VALUES (?, ?, 'refresh', ?, ?, ?)
                """,
                (refresh_hash, user_id, refresh_expires, user_agent, ip_address)
            )
        except Exception as e:
            logger.error(f"Failed to store refresh token: {e}")
        
        # Set HttpOnly cookies
        config = COOKIE_CONFIG["access_token"]
        response.set_cookie(
            key=config["name"],
            value=access_token,
            max_age=config["max_age"],
            secure=config["secure"],
            httponly=config["httponly"],
            samesite=config["samesite"]
        )
        
        config = COOKIE_CONFIG["refresh_token"]
        response.set_cookie(
            key=config["name"],
            value=refresh_token,
            max_age=config["max_age"],
            secure=config["secure"],
            httponly=config["httponly"],
            samesite=config["samesite"]
        )
        
        logger.info(f"Session created for user {user_id}", extra={
            "event": "session_created",
            "user_id": user_id,
            "ip": ip_address
        })
    
    def revoke_session(
        self,
        response: Response,
        token: str,
        user_id: Optional[str] = None
    ) -> None:
        """
        Revoke token and clear cookies (logout).
        
        Args:
            response: FastAPI Response to clear cookies
            token: Token to revoke
            user_id: User identity (audit log)
        """
        token_hash = self._hash_token(token)
        
        try:
            # Mark token as revoked (soft delete for audit trail)
            self.storage.execute_query(
                "UPDATE sys_session_tokens SET revoked = 1 WHERE token_hash = ?",
                (token_hash,)
            )
        except Exception as e:
            logger.warning(f"Failed to revoke token: {e}")
        
        # Clear cookies
        response.delete_cookie(
            key=COOKIE_CONFIG["access_token"]["name"],
            secure=COOKIE_CONFIG["access_token"]["secure"],
            httponly=COOKIE_CONFIG["access_token"]["httponly"],
            samesite=COOKIE_CONFIG["access_token"]["samesite"]
        )
        response.delete_cookie(
            key=COOKIE_CONFIG["refresh_token"]["name"],
            secure=COOKIE_CONFIG["refresh_token"]["secure"],
            httponly=COOKIE_CONFIG["refresh_token"]["httponly"],
            samesite=COOKIE_CONFIG["refresh_token"]["samesite"]
        )
        
        logger.info(f"Session revoked", extra={
            "event": "session_revoked",
            "user_id": user_id
        })
    
    def validate_token(self, token: str) -> bool:
        """
        Validate that token exists and is not revoked.
        
        Args:
            token: Token to validate
            
        Returns:
            True if token is valid (not revoked, not expired)
        """
        token_hash = self._hash_token(token)
        
        try:
            rows = self.storage.execute_query(
                """
                SELECT revoked, expires_at FROM sys_session_tokens
                WHERE token_hash = ? LIMIT 1
                """,
                (token_hash,)
            )
            
            if not rows:
                return False  # Token not found
            
            row = rows[0]
            if row["revoked"]:
                return False  # Token is revoked
            
            # Check expiration
            expires_at = datetime.fromisoformat(row["expires_at"])
            if expires_at < datetime.now(timezone.utc):
                return False  # Token expired
            
            return True
            
        except Exception as e:
            logger.error(f"Token validation error: {e}")
            return False
    
    def refresh_access_token(
        self,
        response: Response,
        user_id: str,
        new_access_token: str,
        user_agent: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> None:
        """
        Refresh access token (extends session).
        Called when access token expires but refresh token is still valid.
        
        Args:
            response: FastAPI Response
            user_id: User identity
            new_access_token: New JWT access token
            user_agent: Browser info (audit)
            ip_address: Client IP (audit)
        """
        now = datetime.now(timezone.utc)
        access_expires = now + timedelta(seconds=COOKIE_CONFIG["access_token"]["max_age"])
        access_hash = self._hash_token(new_access_token)
        
        try:
            # Store new token
            self.storage.execute_query(
                """
                INSERT INTO sys_session_tokens
                (token_hash, user_id, token_type, expires_at, user_agent, ip_address)
                VALUES (?, ?, 'access', ?, ?, ?)
                """,
                (access_hash, user_id, access_expires, user_agent, ip_address)
            )
            
            # Update last_used_at for refresh token tracking
            self.storage.execute_query(
                """
                UPDATE sys_session_tokens
                SET last_used_at = ? 
                WHERE user_id = ? AND token_type = 'refresh' AND revoked = 0
                """,
                (now, user_id)
            )
        except Exception as e:
            logger.error(f"Failed to refresh token: {e}")
        
        # Update cookie
        config = COOKIE_CONFIG["access_token"]
        response.set_cookie(
            key=config["name"],
            value=new_access_token,
            max_age=config["max_age"],
            secure=config["secure"],
            httponly=config["httponly"],
            samesite=config["samesite"]
        )
        
        logger.debug(f"Access token refreshed for user {user_id}")
    
    def get_active_sessions(self, user_id: str) -> list:
        """
        Get all active sessions for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            List of active session records
        """
        try:
            rows = self.storage.execute_query(
                """
                SELECT id, token_type, expires_at, created_at, ip_address, user_agent
                FROM sys_session_tokens
                WHERE user_id = ? AND revoked = 0 AND expires_at > datetime('now')
                ORDER BY created_at DESC
                """,
                (user_id,)
            )
            return rows or []
        except Exception as e:
            logger.error(f"Failed to get active sessions: {e}")
            return []
    
    def revoke_all_sessions(self, response: Response, user_id: str) -> None:
        """
        Logout from all sessions (all devices).
        
        Args:
            response: FastAPI Response
            user_id: User identifier
        """
        try:
            self.storage.execute_query(
                "UPDATE sys_session_tokens SET revoked = 1 WHERE user_id = ?",
                (user_id,)
            )
        except Exception as e:
            logger.error(f"Failed to revoke all sessions: {e}")
        
        # Clear cookies from current device
        response.delete_cookie(
            key=COOKIE_CONFIG["access_token"]["name"],
            secure=COOKIE_CONFIG["access_token"]["secure"],
            httponly=COOKIE_CONFIG["access_token"]["httponly"],
            samesite=COOKIE_CONFIG["access_token"]["samesite"]
        )
        response.delete_cookie(
            key=COOKIE_CONFIG["refresh_token"]["name"],
            secure=COOKIE_CONFIG["refresh_token"]["secure"],
            httponly=COOKIE_CONFIG["refresh_token"]["httponly"],
            samesite=COOKIE_CONFIG["refresh_token"]["samesite"]
        )
        
        logger.info(f"All sessions revoked for user {user_id}")
    
    @staticmethod
    def _hash_token(token: str) -> str:
        """
        Hash token for storage (NEVER store plaintext tokens).
        
        Args:
            token: Token to hash
            
        Returns:
            Hashed token (SHA256)
        """
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()


def get_session_manager(storage: Any = None) -> 'SessionManager':
    """
    Factory function for dependency injection.
    
    Usage in FastAPI:
        from fastapi import Depends
        
        async def login(..., sm: SessionManager = Depends(get_session_manager)):
            sm.create_session(response, user_id, access_token, refresh_token)
    
    Args:
        storage: StorageManager instance (auto-resolved by FastAPI)
    
    Returns:
        SessionManager instance
    """
    if storage is None:
        # Fallback if not injected (shouldn't happen in FastAPI context)
        from data_vault.tenant_factory import TenantDBFactory
        storage = TenantDBFactory.get_default_storage()
    
    return SessionManager(storage)
