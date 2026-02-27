import jwt
import bcrypt
from datetime import datetime, timedelta, timezone
from typing import Optional
from models.auth import TokenPayload
from data_vault.auth_repo import AuthRepository
import secrets

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 day for standard operational sessions

class AuthService:
    """
    Motor de Confianza: Maneja JWT y Hashing de contraseñas de manera aislada (Agnóstico al motor trading).
    """
    def __init__(self, auth_repo: AuthRepository = None):
        self.repo = auth_repo or AuthRepository()
        self.secret_key = self._get_or_create_secret()

    def _get_or_create_secret(self) -> str:
        secret = self.repo.get_jwt_secret()
        if not secret:
            secret = secrets.token_urlsafe(32)
            self.repo.set_jwt_secret(secret)
        return secret

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False

    def get_password_hash(self, password: str) -> str:
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def create_access_token(self, subject: str, tenant_id: str, role: str = "user", expires_delta: Optional[timedelta] = None) -> str:
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
            
        payload = TokenPayload(
            sub=subject,
            tid=tenant_id,
            exp=expire.timestamp(),
            role=role
        )
        
        encoded_jwt = jwt.encode(payload.model_dump(), self.secret_key, algorithm=ALGORITHM)
        return encoded_jwt

    def decode_token(self, token: str) -> Optional[TokenPayload]:
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[ALGORITHM])
            return TokenPayload(**payload)
        except jwt.PyJWTError:
            return None
        except Exception:
            return None
