"""
Toggle Modules - Quick Script
==============================

Script rápido para habilitar/deshabilitar módulos del sistema sin editar código.

Uso:
    # Deshabilitar scanner y executor (solo gestionar posiciones)
    python scripts/toggle_modules.py --disable scanner executor

    # Habilitar todos los módulos
    python scripts/toggle_modules.py --enable-all

    # Ver estado actual
    python scripts/toggle_modules.py --status

    # Resetear a defaults (todos habilitados)
    python scripts/toggle_modules.py --reset
"""
import sys
import argparse
from pathlib import Path

# Add project root to path
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from data_vault.storage import StorageManager


def print_status(storage: StorageManager):
    """Imprime el estado actual de los módulos"""
    modules = storage.get_global_modules_enabled()
    
    print("\n" + "=" * 60)
    print("ESTADO ACTUAL DE MÓDULOS (GLOBAL)")
    print("=" * 60)
    
    for module, enabled in modules.items():
        status_icon = "✅" if enabled else "❌"
        status_text = "HABILITADO" if enabled else "DESHABILITADO"
        print(f"{status_icon} {module:<20} {status_text}")
    
    print("=" * 60 + "\n")


def disable_modules(storage: StorageManager, modules: list):
    """Deshabilita los módulos especificados"""
    updates = {module: False for module in modules}
    storage.set_global_modules_enabled(updates)
    print(f"\n✅ Módulos deshabilitados: {', '.join(modules)}")
    print_status(storage)


def enable_modules(storage: StorageManager, modules: list):
    """Habilita los módulos especificados"""
    updates = {module: True for module in modules}
    storage.set_global_modules_enabled(updates)
    print(f"\n✅ Módulos habilitados: {', '.join(modules)}")
    print_status(storage)


def enable_all(storage: StorageManager):
    """Habilita todos los módulos"""
    all_modules = ["scanner", "executor", "position_manager", 
                   "risk_manager", "monitor", "notificator"]
    updates = {module: True for module in all_modules}
    storage.set_global_modules_enabled(updates)
    print("\n✅ TODOS los módulos habilitados")
    print_status(storage)


def reset_defaults(storage: StorageManager):
    """Resetea a configuración por defecto (todos habilitados)"""
    default_modules = {
        "scanner": True,
        "executor": True,
        "position_manager": True,
        "risk_manager": True,
        "monitor": True,
        "notificator": True
    }
    storage.set_global_modules_enabled(default_modules)
    print("\n✅ Configuración reseteada a defaults")
    print_status(storage)


def main():
    parser = argparse.ArgumentParser(
        description="Toggle de módulos del sistema Aethelgard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:

  # Ver estado actual
  python scripts/toggle_modules.py --status

  # Modo "Solo gestión de posiciones" (testing)
  python scripts/toggle_modules.py --disable scanner executor

  # Modo "Solo monitoreo" (sin trading)
  python scripts/toggle_modules.py --disable scanner executor position_manager

  # Reactivar todos los módulos
  python scripts/toggle_modules.py --enable-all

  # Habilitar módulos específicos
  python scripts/toggle_modules.py --enable scanner executor

  # Resetear a defaults
  python scripts/toggle_modules.py --reset
        """
    )
    
    parser.add_argument(
        '--disable',
        nargs='+',
        metavar='MODULE',
        choices=['scanner', 'executor', 'position_manager', 'risk_manager', 'monitor', 'notificator'],
        help='Deshabilitar módulos específicos'
    )
    
    parser.add_argument(
        '--enable',
        nargs='+',
        metavar='MODULE',
        choices=['scanner', 'executor', 'position_manager', 'risk_manager', 'monitor', 'notificator'],
        help='Habilitar módulos específicos'
    )
    
    parser.add_argument(
        '--enable-all',
        action='store_true',
        help='Habilitar TODOS los módulos'
    )
    
    parser.add_argument(
        '--status',
        action='store_true',
        help='Mostrar estado actual de los módulos'
    )
    
    parser.add_argument(
        '--reset',
        action='store_true',
        help='Resetear a configuración por defecto (todos habilitados)'
    )
    
    args = parser.parse_args()
    
    # Initialize storage
    storage = StorageManager()
    
    # Execute command
    if args.status:
        print_status(storage)
    elif args.enable_all:
        enable_all(storage)
    elif args.reset:
        reset_defaults(storage)
    elif args.disable:
        disable_modules(storage, args.disable)
    elif args.enable:
        enable_modules(storage, args.enable)
    else:
        # No arguments provided, show status
        print_status(storage)
        print("\nUSO: python scripts/toggle_modules.py --help")


if __name__ == "__main__":
    main()
