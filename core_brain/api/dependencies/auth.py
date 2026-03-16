import os
from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status, Request, Cookie, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core_brain.services.auth_service import AuthService
from models.auth import TokenPayload
from typing import Optional

security = HTTPBearer()

def get_auth_service() -> AuthService:
    return AuthService()

async def get_current_active_user(
    request: Request,
    a_token: Optional[str] = Cookie(None),
    auth_service: AuthService = Depends(get_auth_service)
) -> TokenPayload:
    """
    El Guardia de Puerta (Auth Gateway).
    Valida el JWT desde HttpOnly cookie.
    Extrae el token de la cookie 'a_token' (access token).
    Rechaza inmediatamente con HTTP_401_UNAUTHORIZED si no es válido o expirado.
    """
    
    # 1. Leer token de cookie HttpOnly
    token = a_token
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # 2. Validar y decodificar JWT
    try:
        token_data = auth_service.decode_token(token)
        
        if token_data is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # 3. Inyectar tenant_id en el contexto HTTP (Protocolo de Aislamiento)
        # Use 'sub' (user_id) as tenant_id for isolation
        request.state.tenant_id = token_data.sub
        request.state.user_id = token_data.sub
        
        return token_data
    
    except HTTPException:
        raise
    except Exception as e:
        # Catch any token decoding errors
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_ws_user(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    auth_service: AuthService = Depends(get_auth_service),
) -> TokenPayload:
    """
    WebSocket Auth Gateway — single dependency for all WS endpoints.

    Sources checked in order of preference:
      1. HttpOnly cookie 'a_token'  (browser sends automatically, same-origin)
      2. Authorization: Bearer header
      3. Query param ?token=         (development / non-browser clients)

    Raises WebSocketException(1008) — never a fallback, never a demo token.
    1008 = Policy Violation (RFC 6455): closes the socket with the correct WS code.
    """
    token_str: Optional[str] = None

    # 1. Cookie (preferred — set by /api/auth/login via HttpOnly)
    token_str = websocket.cookies.get("a_token")

    # 2. Authorization header
    if not token_str:
        auth_header = websocket.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            token_str = auth_header[7:]

    # 3. Query param (fallback for dev/non-browser clients)
    if not token_str:
        token_str = token or None

    if not token_str:
        raise WebSocketException(code=1008, reason="Not authenticated")

    token_data = auth_service.decode_token(token_str)
    if not token_data:
        raise WebSocketException(code=1008, reason="Invalid or expired token")

    return token_data
