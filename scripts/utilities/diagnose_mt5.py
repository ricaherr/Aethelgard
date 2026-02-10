"""Diagnóstico completo MT5 Connector"""
from data_vault.storage import StorageManager
from connectors.mt5_connector import MT5Connector

# 1. Verificar cuentas en DB
print("=" * 60)
print("1. CUENTAS MT5 EN BASE DE DATOS:")
print("=" * 60)
sm = StorageManager()
accounts = sm.get_broker_accounts()
mt5_accounts = [a for a in accounts if a.get('platform_id') == 'mt5']
print(f"Total MT5 accounts: {len(mt5_accounts)}\n")

for acc in mt5_accounts:
    print(f"Account: {acc.get('account_name')}")
    print(f"  - Enabled: {acc.get('enabled')}")
    print(f"  - Login: {acc.get('login')}")
    print(f"  - Server: {acc.get('server')}")
    print(f"  - Account ID: {acc.get('account_id')}")
    print()

# 2. Intentar cargar MT5Connector
print("=" * 60)
print("2. CARGAR MT5CONNECTOR:")
print("=" * 60)
try:
    connector = MT5Connector()
    print(f"✅ MT5Connector creado")
    print(f"  - Config enabled: {connector.config.get('enabled')}")
    print(f"  - Account ID: {connector.account_id}")
    print(f"  - Login: {connector.config.get('login')}")
    print(f"  - Server: {connector.config.get('server')}")
    print()
    
    # 3. Intentar conectar
    print("=" * 60)
    print("3. INTENTAR CONEXIÓN MT5:")
    print("=" * 60)
    result = connector.connect(timeout_seconds=15)
    print(f"Conexión result: {result}")
    print(f"Connection state: {connector.connection_state}")
    print(f"Is connected: {connector.is_connected}")
    print(f"Available symbols: {len(connector.available_symbols)}")
    if len(connector.available_symbols) > 0:
        print(f"Sample symbols: {sorted(list(connector.available_symbols))[:10]}")
    
except Exception as e:
    print(f"❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
