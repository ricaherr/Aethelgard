from pydantic import BaseModel, EmailStr
from typing import Optional

class UserAuth(BaseModel):
    email: EmailStr
    password: str

class TokenPayload(BaseModel):
    sub: str        # User ID
    tid: str        # Tenant ID
    exp: float      # Expiration
    role: str       # User role

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserInDB(BaseModel):
    id: str
    email: EmailStr
    password_hash: str
    tenant_id: str
    role: str
    status: str
    created_at: str
