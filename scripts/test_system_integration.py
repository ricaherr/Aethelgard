"""
Test de verificación completa del sistema
Valida: DB, credenciales encriptadas, auto-provisioning
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from data_vault.storage import StorageManager
import asyncio
from connectors.auto_provisioning import BrokerProvisioner

def test_database_structure():
    """Verificar estructura de DB"""
    print("\n" + "="*60)
    print("TEST 1: Estructura de Base de Datos")
    print("="*60)
    
    storage = StorageManager()
    
    # Verificar brokers
    brokers = storage.get_brokers()
    print(f"\n✅ Brokers en DB: {len(brokers)}")
    for b in brokers[:3]:
        print(f"   - {b['name']} ({b['broker_id']}) | Auto-provision: {b['auto_provision_available']}")
    
    # Verificar platforms
    platforms = storage.get_platforms()
    print(f"\n✅ Plataformas en DB: {len(platforms)}")
    for p in platforms[:3]:
        print(f"   - {p['name']} ({p['platform_id']}) | Vendor: {p['vendor']}")
    
    # Verificar accounts
    accounts = storage.get_broker_accounts()
    print(f"\n✅ Cuentas configuradas: {len(accounts)}")
    for a in accounts:
        print(f"   - {a['account_name']} | Broker: {a['broker_id']} | Tipo: {a['account_type']}")
    
    return len(brokers) > 0 and len(platforms) > 0


def test_encrypted_credentials():
    """Verificar credenciales encriptadas"""
    print("\n" + "="*60)
    print("TEST 2: Credenciales Encriptadas")
    print("="*60)
    
    storage = StorageManager()
    
    # Obtener cuentas demo
    demo_accounts = storage.get_broker_accounts(account_type='demo')
    
    if not demo_accounts:
        print("⚠️  No hay cuentas demo para verificar")
        return False
    
    for account in demo_accounts:
        print(f"\n📋 Cuenta: {account['account_name']}")
        print(f"   Account ID: {account['account_id']}")
        
        # Leer credenciales (desencriptadas automáticamente)
        credentials = storage.get_credentials(account['account_id'])
        
        if credentials:
            print(f"   ✅ Credenciales: {len(credentials)} encontradas")
            for key in credentials.keys():
                # No mostrar valores completos por seguridad
                value = credentials[key]
                masked = value[:4] + '***' if len(value) > 4 else '***'
                print(f"      - {key}: {masked}")
        else:
            print(f"   ❌ No se encontraron credenciales")
            return False
    
    return True


async def test_auto_provisioning():
    """Verificar auto-provisioning"""
    print("\n" + "="*60)
    print("TEST 3: Auto-Provisioning")
    print("="*60)
    
    provisioner = BrokerProvisioner()
    
    # Verificar brokers con auto-provision
    storage = StorageManager()
    brokers = storage.get_brokers()
    
    auto_brokers = [b for b in brokers if b.get('auto_provision_available')]
    manual_brokers = [b for b in brokers if not b.get('auto_provision_available')]
    
    print(f"\n✅ Brokers con auto-provision: {len(auto_brokers)}")
    for b in auto_brokers:
        print(f"   - {b['name']}")
    
    print(f"\n⚠️  Brokers con setup manual: {len(manual_brokers)}")
    for b in manual_brokers[:3]:
        print(f"   - {b['name']}")
    
    # Verificar cuentas existentes
    for broker_id in ['binance', 'tradovate']:
        has_account = provisioner.has_demo_account(broker_id)
        print(f"\n{'✅' if has_account else '❌'} {broker_id}: {'Cuenta existente' if has_account else 'Sin cuenta'}")
    
    return len(auto_brokers) > 0


def test_system_state():
    """Verificar estado del sistema"""
    print("\n" + "="*60)
    print("TEST 4: Estado del Sistema")
    print("="*60)
    
    storage = StorageManager()
    state = storage.get_system_state()
    
    print(f"\n✅ Variables de estado: {len(state)}")
    for key in list(state.keys())[:5]:
        print(f"   - {key}")
    
    return True


async def main():
    """Ejecutar todos los tests"""
    print("\n🔍 PRUEBA COMPLETA DEL SISTEMA AETHELGARD")
    print("Verificando integración de cambios...")
    
    results = []
    
    # Test 1: Database Structure
    results.append(("Base de Datos", test_database_structure()))
    
    # Test 2: Encrypted Credentials
    results.append(("Credenciales Encriptadas", test_encrypted_credentials()))
    
    # Test 3: Auto-Provisioning
    results.append(("Auto-Provisioning", await test_auto_provisioning()))
    
    # Test 4: System State
    results.append(("Estado del Sistema", test_system_state()))
    
    # Resumen
    print("\n" + "="*60)
    print("RESUMEN DE PRUEBAS")
    print("="*60)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status} - {name}")
    
    print(f"\n{'='*60}")
    print(f"Resultado: {passed}/{total} pruebas exitosas")
    
    if passed == total:
        print("✅ SISTEMA COMPLETAMENTE FUNCIONAL")
    else:
        print("⚠️  Algunas pruebas fallaron - revisar configuración")
    
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
