"""
MT5 Connection Diagnostic Tool
Helps identify authentication issues
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import json
from data_vault.storage import StorageManager

print("=" * 70)
print("🔍 DIAGNÓSTICO DE CONEXIÓN MT5")
print("=" * 70)

storage = StorageManager()

# Step 1: Check database accounts
print("\n📊 PASO 1: Verificar cuentas en base de datos")
print("-" * 70)
all_accounts = storage.get_broker_accounts()
mt5_accounts = [acc for acc in all_accounts if acc.get('platform_id') == 'mt5']

if not mt5_accounts:
    print("❌ No se encontraron cuentas MT5 en la base de datos")
else:
    for acc in mt5_accounts:
        print(f"\n✅ Cuenta encontrada:")
        print(f"   Nombre: {acc.get('account_name')}")
        print(f"   Número: {acc.get('account_number')}")
        print(f"   Servidor: {acc.get('server')}")
        print(f"   Tipo: {acc.get('account_type')}")
        
        # Check credentials
        account_id = acc.get('account_id')
        try:
            credentials = storage.get_credentials(account_id)
            if credentials.get('password'):
                print(f"   Contraseña: ✅ Guardada (longitud: {len(credentials['password'])} caracteres)")
            else:
                print(f"   Contraseña: ❌ NO guardada")
        except Exception as e:
            print(f"   Contraseña: ❌ Error al leer: {e}")

# Step 2: Check config files
print("\n\n📁 PASO 2: Verificar archivos de configuración")
print("-" * 70)

config_path = Path("config/mt5_config.json")
env_path = Path("config/mt5.env")

if config_path.exists():
    print(f"✅ {config_path} existe")
    try:
        with open(config_path, 'r') as f:
            config = json.load(f)
        print(f"   Login configurado: {config.get('login')}")
        print(f"   Servidor configurado: {config.get('server')}")
        print(f"   Habilitado: {config.get('enabled')}")
    except Exception as e:
        print(f"   ❌ Error al leer: {e}")
else:
    print(f"❌ {config_path} NO existe")

if env_path.exists():
    print(f"✅ {env_path} existe")
    try:
        with open(env_path, 'r') as f:
            content = f.read()
        if 'MT5_PASSWORD=' in content:
            pwd_line = [line for line in content.split('\n') if 'MT5_PASSWORD=' in line][0]
            pwd_value = pwd_line.split('=', 1)[1].strip()
            print(f"   Contraseña configurada: {'*' * len(pwd_value)} (longitud: {len(pwd_value)})")
        else:
            print(f"   ❌ No se encontró MT5_PASSWORD en el archivo")
    except Exception as e:
        print(f"   ❌ Error al leer: {e}")
else:
    print(f"❌ {env_path} NO existe")

# Step 3: Test MT5 connection
print("\n\n🔌 PASO 3: Probar conexión a MT5")
print("-" * 70)

try:
    import MetaTrader5 as mt5
    print("✅ Librería MetaTrader5 instalada")
    
    # Initialize
    if not mt5.initialize():
        error = mt5.last_error()
        print(f"❌ No se pudo inicializar MT5: {error}")
    else:
        print("✅ MT5 inicializado correctamente")
        
        # Try to get terminal info
        terminal_info = mt5.terminal_info()
        if terminal_info:
            print(f"\n📱 Información de Terminal:")
            print(f"   Path: {terminal_info.path}")
            print(f"   Data Path: {terminal_info.data_path}")
            print(f"   Build: {terminal_info.build}")
            print(f"   Conectado: {terminal_info.connected}")
        
        # Check current account
        account_info = mt5.account_info()
        if account_info:
            print(f"\n👤 Cuenta actualmente conectada en MT5:")
            print(f"   Login: {account_info.login}")
            print(f"   Servidor: {account_info.server}")
            print(f"   Nombre: {account_info.name}")
            print(f"   Compañía: {account_info.company}")
            print(f"   Tipo: {'DEMO' if account_info.trade_mode == 0 else 'REAL'}")
            
            # Compare with config
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                
                config_login = str(config.get('login'))
                actual_login = str(account_info.login)
                
                print(f"\n🔍 Comparación:")
                print(f"   Login en config: '{config_login}' (longitud: {len(config_login)})")
                print(f"   Login en MT5:    '{actual_login}' (longitud: {len(actual_login)})")
                
                if config_login == actual_login:
                    print(f"   ✅ Los números coinciden")
                else:
                    print(f"   ❌ LOS NÚMEROS NO COINCIDEN!")
                    print(f"   💡 Corrija el número en la base de datos")
                
                config_server = config.get('server', '').strip()
                actual_server = account_info.server.strip()
                
                print(f"\n   Servidor en config: '{config_server}'")
                print(f"   Servidor en MT5:    '{actual_server}'")
                
                if config_server == actual_server:
                    print(f"   ✅ Los servidores coinciden")
                else:
                    print(f"   ❌ LOS SERVIDORES NO COINCIDEN!")
                    print(f"   💡 Corrija el servidor en la base de datos")
        else:
            print("❌ No hay cuenta conectada en MT5")
            print("💡 Asegúrese de conectarse manualmente primero en MT5")
        
        mt5.shutdown()
        
except ImportError:
    print("❌ Librería MetaTrader5 no instalada")
    print("💡 Instale con: pip install MetaTrader5")
except Exception as e:
    print(f"❌ Error al probar conexión: {e}")

print("\n" + "=" * 70)
print("💡 RECOMENDACIONES:")
print("=" * 70)
print("""
1. Abra MetaTrader 5 manualmente
2. Conéctese con su cuenta DEMO
3. Verifique el número de cuenta EXACTO (File > Login to Trade Account)
4. Verifique el nombre del servidor EXACTO
5. Actualice la base de datos con los valores correctos
6. Pruebe nuevamente la conexión desde el Dashboard
""")
print("=" * 70)
