import os
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from core_brain.services.auth_service import AuthService
from models.auth import TokenPayload

security = HTTPBearer()

def get_auth_service() -> AuthService:
    return AuthService()

async def get_current_active_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service)
) -> TokenPayload:
    """
    El Guardia de Puerta (Auth Gateway).
    Valida el JWT e inyecta el token (con el tenant_id) en el flujo de la petición.
    Rechaza inmediatamente con HTTP_401_UNAUTHORIZED si no es válido o expirado.
    """
    token = credentials.credentials
    token_data = auth_service.decode_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Inyectar tenant_id en el contexto HTTP para que StorageManager u otros puedan leerlo (Protocolo de Aislamiento)
    request.state.tenant_id = token_data.tid
    request.state.user_id = token_data.sub
    
    return token_data
