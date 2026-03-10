from pydantic import BaseModel, EmailStr
from typing import Optional

class UserAuth(BaseModel):
    email: EmailStr
    password: str

class TokenPayload(BaseModel):
    sub: str                              # User ID
    tid: Optional[str] = None             # Tenant ID (legacy, now optional - new arch uses user_id only)
    exp: float                            # Expiration
    role: str                             # User role
    token_type: Optional[str] = "access"  # 'access' or 'refresh' (Phase 3 security upgrade)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserInDB(BaseModel):
    id: str
    email: EmailStr
    password_hash: str
    tenant_id: Optional[str] = None           # Legacy (now uses user_id-based architecture)
    role: str
    status: str
    created_at: str
