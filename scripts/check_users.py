#!/usr/bin/env python3
"""
Script para crear usuario de prueba en la base de datos
"""

import sys
import os
sys.path.insert(0, os.getcwd())

from data_vault.storage import StorageManager
from passlib.context import CryptContext

def main():
    try:
        storage = StorageManager()
        
        # Crear contexto para hash de passwords
        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        
        print("=" * 80)
        print("SETUP DE USUARIO PARA TESTING")
        print("=" * 80)
        
        # Email de prueba
        test_email = "test@system.ai"
        test_password = "Test@12345"
        test_user_id = "default"  # Refactored from test_tenant
        
        # Verificar si el usuario ya existe
        existing = storage.auth_repo.get_user_by_email(test_email)
        
        if existing:
            print(f"\n✅ Usuario ya existe:")
            print(f"   Email: {existing.get('email')}")
            print(f"   ID: {existing.get('id')}")
            print(f"   User ID: {existing.get('tenant_id')}")
            print(f"\n📝 Usa estas credenciales para testing:")
            print(f"   Email: {test_email}")
            print(f"   Password: {test_password}")
        else:
            print(f"\n🔐 Creando usuario de prueba...")
            
            # Hash del password
            hashed_pw = pwd_context.hash(test_password)
            
            # Crear usuario
            user_id = storage.auth_repo.create_user(
                email=test_email,
                password_hash=hashed_pw,
                user_id=test_user_id,
                role="admin"
            )
            
            print(f"\n✅ Usuario creado exitosamente!")
            print(f"=" * 80)
            print(f"Email:    {test_email}")
            print(f"Password: {test_password}")
            print(f"User ID:  {test_user_id}")
            print(f"ID:       {user_id}")
            print(f"=" * 80)
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
