"""
Script de Prueba Rápida - Sistema MT5
======================================

Valida la integración completa del sistema con MT5:
1. Verifica instalación de MT5
2. Valida configuración existente
3. Ejecuta una señal de prueba
4. Confirma que aparezca en MT5
5. Cierra la posición de prueba

Uso: python scripts/test_mt5_system.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import logging
from datetime import datetime

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def print_header(text: str):
    """Imprime un encabezado formateado"""
    print("\n" + "=" * 70)
    print(f"  {text}")
    print("=" * 70)

def check_mt5_installation():
    """Verifica que MT5 esté instalado"""
    print_header("1. Verificando Instalación de MT5")
    
    try:
        import MetaTrader5 as mt5
        
        if not mt5.initialize():
            error = mt5.last_error()
            logger.error(f"No se pudo inicializar MT5: {error}")
            print("\n❌ MT5 no está instalado o no se puede acceder")
            print("   Descarga desde: https://www.metatrader5.com/en/download")
            return False
        
        version = mt5.version()
        print(f"✅ MT5 instalado - Versión: {version[0]}.{version[1]}.{version[2]}")
        mt5.shutdown()
        return True
        
    except ImportError:
        logger.error("Librería MetaTrader5 no instalada")
        print("\n❌ Librería MetaTrader5 no instalada")
        print("   Instalar con: pip install MetaTrader5")
        return False

def check_configuration():
    """Verifica que exista configuración MT5"""
    print_header("2. Verificando Configuración")
    
    config_path = Path('config/mt5_config.json')
    env_path = Path('config/mt5.env')
    
    if not config_path.exists():
        print("\n❌ No se encontró config/mt5_config.json")
        print("   Ejecuta: python scripts/setup_mt5_demo.py")
        return False
    
    if not env_path.exists():
        print("\n❌ No se encontró config/mt5.env")
        print("   Ejecuta: python scripts/setup_mt5_demo.py")
        return False
    
    print("✅ Archivos de configuración encontrados")
    return True

def test_connector():
    """Prueba el conector MT5"""
    print_header("3. Probando Conector MT5")
    
    try:
        from connectors.mt5_connector import MT5Connector
        
        print("📡 Creando instancia de MT5Connector...")
        connector = MT5Connector()
        
        print("🔌 Intentando conectar...")
        if not connector.connect():
            print("\n❌ Fallo al conectar con MT5")
            print("   Verifica que:")
            print("   - MT5 esté cerrado")
            print("   - Las credenciales sean correctas")
            print("   - La cuenta demo no haya expirado")
            return None
        
        print("✅ Conexión exitosa!")
        return connector
        
    except Exception as e:
        logger.error(f"Error al probar conector: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return None

def execute_test_trade(connector):
    """Ejecuta un trade de prueba"""
    print_header("4. Ejecutando Trade de Prueba")
    
    try:
        from models.signal import Signal, ConnectorType
        
        # Crear señal de prueba para EURUSD
        test_signal = Signal(
            symbol="EURUSD",
            signal_type="BUY",
            confidence=0.95,
            connector_type=ConnectorType.METATRADER5,
            entry_price=0.0,  # Se usará precio de mercado
            stop_loss=0.0,    # Se calculará automáticamente
            take_profit=0.0,  # Se calculará automáticamente
            volume=0.01,      # Micro lote
            timestamp=datetime.now(),
            metadata={
                "test": True,
                "description": "Trade de prueba del sistema"
            }
        )
        
        print(f"📊 Señal de prueba: {test_signal.symbol} {test_signal.signal_type}")
        print(f"   Volumen: {test_signal.volume} lotes")
        
        print("\n🚀 Ejecutando orden...")
        result = connector.execute_signal(test_signal)
        
        if result.get('success'):
            ticket = result.get('ticket')
            price = result.get('price')
            print(f"\n✅ Orden ejecutada exitosamente!")
            print(f"   Ticket: {ticket}")
            print(f"   Precio: {price}")
            print(f"\n💡 Abre MT5 Terminal y verifica que aparezca la posición")
            print(f"   (Magic Number: 234000)")
            
            return ticket
        else:
            error = result.get('error', 'Unknown error')
            print(f"\n❌ Fallo al ejecutar orden: {error}")
            return None
            
    except Exception as e:
        logger.error(f"Error ejecutando trade de prueba: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return None

def close_test_trade(connector, ticket):
    """Cierra el trade de prueba"""
    print_header("5. Cerrando Trade de Prueba")
    
    try:
        print(f"🔄 Cerrando posición {ticket}...")
        
        if connector.close_position(ticket):
            print(f"✅ Posición {ticket} cerrada exitosamente")
            print("\n💡 Verifica en MT5 Terminal → History que aparezca el trade cerrado")
            return True
        else:
            print(f"❌ No se pudo cerrar la posición {ticket}")
            print("   Ciérrala manualmente en MT5")
            return False
            
    except Exception as e:
        logger.error(f"Error cerrando trade: {e}", exc_info=True)
        print(f"\n❌ Error: {e}")
        return False

def main():
    """Flujo principal de prueba"""
    print_header("🧪 PRUEBA RÁPIDA DEL SISTEMA MT5")
    
    # Paso 1: Verificar instalación
    if not check_mt5_installation():
        return False
    
    # Paso 2: Verificar configuración
    if not check_configuration():
        return False
    
    # Paso 3: Probar conector
    connector = test_connector()
    if not connector:
        return False
    
    # Paso 4: Ejecutar trade de prueba
    print("\n⚠️  IMPORTANTE: Este script ejecutará un trade REAL en tu cuenta DEMO")
    response = input("¿Continuar? [y/N]: ").strip().lower()
    
    if response != 'y':
        print("\n⏭️  Prueba cancelada por el usuario")
        connector.disconnect()
        return True
    
    ticket = execute_test_trade(connector)
    
    if not ticket:
        connector.disconnect()
        return False
    
    # Esperar confirmación del usuario
    input("\n⏸️  Presiona ENTER para cerrar el trade de prueba...")
    
    # Paso 5: Cerrar trade
    close_test_trade(connector, ticket)
    
    # Desconectar
    connector.disconnect()
    
    # Resumen final
    print_header("✅ PRUEBA COMPLETADA")
    print("\nPróximos pasos:")
    print("   1. Verifica en MT5 que el trade aparezca en History")
    print("   2. Ejecuta el sistema completo: python start.py")
    print("   3. Abre el dashboard: http://localhost:8503")
    print()
    
    return True

if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Prueba interrumpida por el usuario")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error inesperado: {e}", exc_info=True)
        print(f"\n❌ Error inesperado: {e}")
        sys.exit(1)
