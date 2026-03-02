"""
Script para crear un usuario demo automáticamente.
Útil para testing y demostración del sistema.
"""

import sys
import os
import logging

# Configurar path para importar módulos desde el directorio raíz del proyecto
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from data_vault.auth_repo import AuthRepository
from core_brain.services.auth_service import AuthService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_USER_EMAIL = "demo@aethelgard.local"
DEMO_USER_PASSWORD = "demo123"
DEMO_TENANT_ID = "default"


def create_demo_user():
    """Crea un usuario de demostración si no existe."""
    try:
        auth_repo = AuthRepository()
        
        # Verificar si el usuario ya existe
        existing_user = auth_repo.get_user_by_email(DEMO_USER_EMAIL)
        if existing_user:
            logger.info(f"✓ Usuario demo ya existe: {DEMO_USER_EMAIL}")
            return existing_user
        
        # Crear el usuario
        auth_service = AuthService(auth_repo)
        hashed_password = auth_service.get_password_hash(DEMO_USER_PASSWORD)
        
        user_id = auth_repo.create_user(
            email=DEMO_USER_EMAIL,
            password_hash=hashed_password,
            tenant_id=DEMO_TENANT_ID,
            role="admin"
        )
        
        logger.info(f"✓ Usuario demo creado exitosamente")
        logger.info(f"  - Email: {DEMO_USER_EMAIL}")
        logger.info(f"  - Password: {DEMO_USER_PASSWORD}")
        logger.info(f"  - Tenant ID: {DEMO_TENANT_ID}")
        logger.info(f"  - User ID: {user_id}")
        
        return {"id": user_id, "email": DEMO_USER_EMAIL, "tenant_id": DEMO_TENANT_ID}
    
    except Exception as e:
        logger.error(f"✗ Error creando usuario demo: {e}")
        raise


def generate_demo_token():
    """Genera un token JWT para el usuario de demostración."""
    try:
        auth_repo = AuthRepository()
        user = auth_repo.get_user_by_email(DEMO_USER_EMAIL)
        
        if not user:
            logger.error("Usuario demo no existe. Crear primero con create_demo_user()")
            return None
        
        auth_service = AuthService(auth_repo)
        token = auth_service.create_access_token(
            subject=user["id"],
            tenant_id=user["tenant_id"],
            role=user["role"]
        )
        
        logger.info(f"✓ Token JWT generado para {DEMO_USER_EMAIL}")
        logger.info(f"  - Token: {token[:50]}...")
        
        return token
    
    except Exception as e:
        logger.error(f"✗ Error generando token: {e}")
        raise


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Manage demo user for Aethelgard")
    parser.add_argument(
        "--action",
        choices=["create", "token", "both"],
        default="both",
        help="Acción a ejecutar"
    )
    
    args = parser.parse_args()
    
    try:
        if args.action in ["create", "both"]:
            create_demo_user()
        
        if args.action in ["token", "both"]:
            token = generate_demo_token()
            if token:
                print(f"\n🔐 Credentials para usar en la UI:")
                print(f"Email: {DEMO_USER_EMAIL}")
                print(f"Password: {DEMO_USER_PASSWORD}")
                print(f"\n📋 JWT Token (copiar a localStorage):")
                print(f"Token: {token}")
    
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)
