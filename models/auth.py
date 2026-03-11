from pydantic import BaseModel, EmailStr
from typing import Optional

class UserAuth(BaseModel):
    email: EmailStr
    password: str

class TokenPayload(BaseModel):
    sub: str                              # User ID (primary identifier for multitenancy)
    exp: float                            # Expiration
    role: str                             # User role
    tid: Optional[str] = None             # Tenant ID (optional for backward compatibility)
    token_type: Optional[str] = "access"  # 'access' or 'refresh' (Phase 3 security upgrade)

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserInDB(BaseModel):
    id: str
    email: EmailStr
    password_hash: str
    user_id: Optional[str] = None           # User identifier for isolation
    role: str
    status: str
    created_at: str
