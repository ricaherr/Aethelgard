from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from core_brain.services.auth_service import AuthService
from core_brain.api.dependencies.auth import get_auth_service
from pydantic import BaseModel, EmailStr
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    tenant_id: str
    role: str = "user"

@router.post("/register")
async def register(
    user_data: UserRegister,
    auth_service: AuthService = Depends(get_auth_service)
) -> dict:
    try:
        # Verificar si ya existe
        existing_user = auth_service.repo.get_user_by_email(user_data.email)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        # Hashear y crear
        hashed_password = auth_service.get_password_hash(user_data.password)
        user_id = auth_service.repo.create_user(
            email=user_data.email,
            password_hash=hashed_password,
            tenant_id=user_data.tenant_id,
            role=user_data.role
        )
        
        return {"status": "success", "user_id": user_id, "message": "Operative registered successfully"}
    except Exception as e:
        logger.error(f"[AuthRouter] Error during registration: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    auth_service: AuthService = Depends(get_auth_service)
) -> dict:
    try:
        user = auth_service.repo.get_user_by_email(form_data.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        if not auth_service.verify_password(form_data.password, user["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        
        # Generar Token
        access_token = auth_service.create_access_token(
            subject=user["id"],
            tenant_id=user["tenant_id"],
            role=user["role"]
        )
        
        return {"access_token": access_token, "token_type": "bearer"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[AuthRouter] Error during login: {e}")
        raise HTTPException(status_code=500, detail=str(e))
