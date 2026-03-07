"""
MT5 Connection Diagnostic Tool
Helps identify authentication issues
"""
import sys
from pathlib import Path
from typing import Any, Optional, cast
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager

print("=" * 70)
print("🔍 DIAGNÓSTICO DE CONEXIÓN MT5")
print("=" * 70)

storage = StorageManager()

# Step 1: Check database accounts
print("\n📊 PASO 1: Verificar cuentas en base de datos")
print("-" * 70)
all_accounts = storage.get_sys_broker_accounts()
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
        account_id: Optional[str] = acc.get('account_id')
        if not account_id:
            print("   Contraseña: ❌ account_id inválido")
        else:
            try:
                credentials = storage.get_credentials(account_id)
                if credentials.get('password'):
                    print(f"   Contraseña: ✅ Guardada (longitud: {len(credentials['password'])} caracteres)")
                else:
                    print(f"   Contraseña: ❌ NO guardada")
            except Exception as e:
                print(f"   Contraseña: ❌ Error al leer: {e}")

# Step 2: Validate DB configuration state
print("\n\n📁 PASO 2: Verificar configuración en base de datos")
print("-" * 70)

enabled_mt5 = [acc for acc in mt5_accounts if str(acc.get('account_type', '')).lower() == 'demo' and acc.get('enabled', 1)]

if enabled_mt5:
    print(f"✅ Cuentas DEMO habilitadas: {len(enabled_mt5)}")
    for acc in enabled_mt5:
        print(f"   - {acc.get('account_name', 'Sin nombre')} | {acc.get('account_number')} | {acc.get('server')}")
else:
    print("⚠️  No hay cuentas DEMO habilitadas en DB")

# Step 3: Test MT5 connection
print("\n\n🔌 PASO 3: Probar conexión a MT5")
print("-" * 70)

try:
    from connectors.mt5_wrapper import MT5 as mt5
    mt5 = cast(Any, mt5)
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
            
            # Compare with DB
            if enabled_mt5:
                actual_login = str(account_info.login)
                actual_server = account_info.server.strip()
                
                print("\n🔍 Comparación contra DB (cuentas DEMO habilitadas):")
                matches = [
                    acc for acc in enabled_mt5
                    if str(acc.get('account_number')) == actual_login
                    and str(acc.get('server', '')).strip() == actual_server
                ]
                
                if matches:
                    print("   ✅ MT5 coincide con la cuenta DEMO en DB")
                else:
                    print("   ❌ MT5 NO coincide con ninguna cuenta DEMO habilitada en DB")
                    print("   💡 Corrija login/servidor en la base de datos")
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
