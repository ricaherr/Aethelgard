#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Script: Crear usuarios demo en sys_users después de migración.

Crea usuarios de demostración para que el sistema tenga datos de prueba listos.
Ejecutar DESPUÉS de que el schema.py haya creado la tabla sys_users.

Usuarios creados:
  - admin@aethelgard.com (ADMIN) / Aethelgard2026!
  - demo@aethelgard.com (TRADER) / demo123
  - alice@aethelgard.com (TRADER) / alice123
  - bob@aethelgard.com (TRADER) / bob123
"""

import sys
import os
import logging

# Configurar path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from data_vault.auth_repo import AuthRepository
from core_brain.services.auth_service import AuthService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


DEMO_USERS = [
    {
        "email": "admin@aethelgard.com",
        "password": "Aethelgard2026!",
        "role": "admin",
        "tier": "INSTITUTIONAL"
    },
    {
        "email": "demo@aethelgard.com",
        "password": "demo123",
        "role": "trader",
        "tier": "BASIC"
    },
    {
        "email": "alice@aethelgard.com",
        "password": "alice123",
        "role": "trader",
        "tier": "PREMIUM"
    },
    {
        "email": "bob@aethelgard.com",
        "password": "bob123",
        "role": "trader",
        "tier": "BASIC"
    }
]


def create_demo_users():
    """Crea usuarios de demostración en sys_users."""
    try:
        logger.info("="*80)
        logger.info("[START] Creando usuarios demo en sys_users")
        logger.info("="*80)
        
        # Inicializar repositorios
        auth_repo = AuthRepository()
        auth_service = AuthService()
        
        created = 0
        skipped = 0
        
        for user_data in DEMO_USERS:
            email = user_data["email"]
            
            # Verificar si usuario ya existe
            if auth_repo.user_exists(email):
                logger.warning(f"  ⚠️  Usuario ya existe: {email} (skipping)")
                skipped += 1
                continue
            
            # Hash password
            password_hash = auth_service.get_password_hash(user_data["password"])
            
            # Crear usuario
            user_id = auth_repo.create_user(
                email=email,
                password_hash=password_hash,
                role=user_data["role"],
                tier=user_data["tier"],
                created_by="system"
            )
            
            # Log en sys_audit_logs
            auth_repo.log_audit(
                user_id="system",
                action="CREATE",
                resource="sys_users",
                resource_id=user_id,
                new_value=f"email={email}, role={user_data['role']}, tier={user_data['tier']}",
                status="success"
            )
            
            logger.info(f"  ✅ Creado: {email} (role={user_data['role']}, tier={user_data['tier']})")
            created += 1
        
        # Summary
        logger.info("")
        logger.info("="*80)
        logger.info(f"[SUMMARY] Usuarios demo creados: {created}")
        logger.info(f"[SUMMARY] Usuarios ya existentes: {skipped}")
        logger.info("="*80)
        logger.info("")
        logger.info("Credenciales de prueba:")
        logger.info("  admin@aethelgard.com / Aethelgard2026! (ADMIN)")
        logger.info("  demo@aethelgard.com / demo123 (TRADER)")
        logger.info("  alice@aethelgard.com / alice123 (TRADER)")
        logger.info("  bob@aethelgard.com / bob123 (TRADER)")
        logger.info("")
        logger.info("Prueba en frontend: http://localhost:8000")
        
        return 0 if created > 0 or skipped > 0 else 1
        
    except Exception as e:
        logger.error(f"[ERROR] Error creando usuarios demo: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    exit_code = create_demo_users()
    sys.exit(exit_code)
