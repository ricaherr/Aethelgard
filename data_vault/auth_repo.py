import sqlite3
import os
import uuid
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from contextlib import contextmanager

logger = logging.getLogger(__name__)

class AuthRepository:
    """
    Gestor de la base de datos GLOBAL de autenticación.
    Cumple con el principio de Muro de Cristal: Las credenciales NUNCA entran a los silos de tenants.
    """
    def __init__(self, db_path: str = "data_vault/global/auth.db"):
        self.db_path = db_path
        self._ensure_global_directory()
        self._initialize_schema()

    def _ensure_global_directory(self) -> None:
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

    def _initialize_schema(self) -> None:
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # Tabla de Usuarios
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    role TEXT NOT NULL DEFAULT 'user',
                    status TEXT NOT NULL DEFAULT 'active',
                    created_at TEXT NOT NULL
                )
                ''')
                # Índice para optimizar login
                cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)')
                
                # Tabla de Configuración (Single Source of Truth) para el JWT Secret
                cursor.execute('''
                CREATE TABLE IF NOT EXISTS config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                ''')
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"[AuthRepo] Error inicializando schema: {e}")

    @contextmanager
    def _get_connection(self) -> Any:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    # --- Users ---

    def create_user(self, email: str, password_hash: str, tenant_id: str, role: str = "user") -> str:
        with self._get_connection() as conn:
            user_id = str(uuid.uuid4())
            now = datetime.now().isoformat()
            conn.execute(
                "INSERT INTO users (id, email, password_hash, tenant_id, role, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, email, password_hash, tenant_id, role, now)
            )
            conn.commit()
            return user_id

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    # --- Config ---

    def get_jwt_secret(self) -> Optional[str]:
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT value FROM config WHERE key = 'jwt_secret'")
            row = cursor.fetchone()
            return row["value"] if row else None

    def set_jwt_secret(self, secret: str) -> None:
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute(
                "INSERT OR REPLACE INTO config (key, value, updated_at) VALUES (?, ?, ?)",
                ('jwt_secret', secret, now)
            )
            conn.commit()

