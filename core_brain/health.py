"""
Aethelgard Health Core - Diagnostic and Monitoring System
Rules:
1. Pure Python (Agnostic logic).
2. Validates DB, Config, and Connectors.
"""
import json
import logging
import os
from sqlite3 import Connection
from sqlite3 import Cursor
import sys
import psutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional

# Path configuration
BASE_DIR: Path = Path(__file__).parent.parent
CONFIG_DIR: Path = BASE_DIR / "config"
DATA_DIR: Path = BASE_DIR / "data_vault"

logger: logging.Logger = logging.getLogger("HEALTH_CORE")

class HealthManager:
    def __init__(self) -> None:
        self.db_path: Path = DATA_DIR / "aethelgard.db"
    
    def check_config_integrity(self) -> Dict[str, Any]:
        """Checks if critical JSON config files are present and valid."""
        results = {"status": "GREEN", "details": []}
        critical_files: List[str] = ["modules.json", "dynamic_params.json"]
        
        for cf in critical_files:
            file_path: Path = CONFIG_DIR / cf
            if not file_path.exists():
                results["status"] = "RED"
                results["details"].append(f"CRITICAL: {cf} is missing.")
                continue
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    json.load(f)
                results["details"].append(f"SUCCESS: {cf} is valid JSON.")
            except Exception as e:
                results["status"] = "RED"
                results["details"].append(f"CRITICAL: {cf} has invalid JSON format: {e}")
        
        return results

    def check_db_integrity(self) -> Dict[str, Any]:
        """Checks SQLite database health and table presence."""
        results = {"status": "GREEN", "details": []}
        
        if not self.db_path.exists():
            results["status"] = "RED"
            results["details"].append("CRITICAL: aethelgard.db is missing.")
            return results
            
        try:
            import sqlite3
            conn: Connection = sqlite3.connect(self.db_path)
            cursor: Cursor = conn.cursor()
            # Simple check of critical tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables: List[Any] = [r[0] for r in cursor.fetchall()]
            
            # Correct tables based on StorageManager schema
            needed_tables: List[str] = ['system_state', 'signals', 'trades', 'market_states']
            for t in needed_tables:
                if t not in tables:
                    results["status"] = "YELLOW"
                    results["details"].append(f"WARNING: Table {t} missing.")
                else:
                    results["details"].append(f"SUCCESS: Table {t} found.")
            
            conn.close()
        except Exception as e:
            results["status"] = "RED"
            results["details"].append(f"CRITICAL: DB Connection Error: {e}")
            
        return results
    
    def auto_correct_lockdown(
        self, 
        storage_manager: 'StorageManager', 
        risk_manager: 'RiskManager'
    ) -> Dict[str, Any]:
        """
        EDGE Auto-Correction: Verifica si lockdown está activo sin justificación
        y lo corrige automáticamente.
        
        Criterio: Lockdown solo debe estar activo si hay 3+ pérdidas consecutivas
        en el historial de trades cerrados.
        
        Args:
            storage_manager: Para acceder a historial de trades
            risk_manager: Para leer/modificar estado de lockdown directamente
        
        Returns:
            Dict con resultado de la corrección
        """
        results = {"action_taken": None, "reason": None, "lockdown_before": None, "lockdown_after": None}
        
        try:
            # 1. Verificar estado  actual DIRECTAMENTE del RiskManager (no de DB)
            lockdown_active = risk_manager.is_lockdown_active()
            results["lockdown_before"] = lockdown_active
            
            if not lockdown_active:
                results["action_taken"] = "NO_ACTION"
                results["reason"] = "Lockdown already inactive"
                results["lockdown_after"] = False
                return results
            
            # 2. Verificar historial de trades (últimos 10)
            conn = storage_manager._get_conn()
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT profit FROM trade_results
                ORDER BY close_time DESC
                LIMIT 10
            """)
            trade_history = cursor.fetchall()
            storage_manager._close_conn(conn)
            
            # 3. Contar pérdidas consecutivas
            consecutive_losses = 0
            for trade in trade_history:
                if trade[0] <= 0:  # profit <= 0 = pérdida
                    consecutive_losses += 1
                else:
                    break  # Primera ganancia rompe la racha
            
            # 4. Determinar si lockdown está justificado
            max_consecutive_losses = system_state.get('config_risk', {}).get('max_consecutive_losses', 3)
            
            if consecutive_losses < max_consecutive_losses:
                # LOCKDOWN NO JUSTIFICADO - Auto-corregir
                logger.warning(
                    f"EDGE AUTO-CORRECTION: Lockdown activo sin justificación. "
                    f"Pérdidas consecutivas: {consecutive_losses} < {max_consecutive_losses} (umbral)"
                )
                
                # Desactivar usando el RiskManager recibido para afectar instancia en uso
                risk_manager._deactivate_lockdown()
                
                results["action_taken"] = "LOCKDOWN_DEACTIVATED"
                results["reason"] = f"Consecutive losses ({consecutive_losses}) < threshold ({max_consecutive_losses}). No justification for lockdown."
                results["lockdown_after"] = False
                
                logger.info(f"✅ EDGE: Lockdown auto-corregido a INACTIVE")
            else:
                results["action_taken"] = "NO_ACTION"
                results["reason"] = f"Lockdown justified: {consecutive_losses} consecutive losses >= {max_consecutive_losses} threshold"
                results["lockdown_after"] = True
            
        except Exception as e:
            logger.error(f"Error in auto_correct_lockdown: {e}", exc_info=True)
            results["action_taken"] = "ERROR"
            results["reason"] = str(e)
        
        return results

    def get_resource_usage(self) -> Dict[str, Any]:
        """Gets CPU and Memory usage of the current process group."""
        try:
            process = psutil.Process(os.getpid())
            mem_info = process.memory_info()
            return {
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "memory_mb": mem_info.rss / (1024 * 1024),
                "threads": process.num_threads(),
                "status": "GREEN"
            }
        except Exception as e:
            return {"status": "YELLOW", "error": str(e)}

    def check_mt5_connection(self) -> Dict[str, Any]:
        """
        Check MT5 installation, connection status and account information.
        
        Returns:
            Dict with MT5 status, account info, and open positions
        """
        results = {
            "status": "RED",
            "installed": False,
            "connected": False,
            "account_type": None,
            "account_info": {},
            "open_positions": [],
            "details": []
        }
        
        try:
            # Check if MT5 library is available
            try:
                from connectors.mt5_wrapper import MT5 as mt5
                results["installed"] = True
                results["details"].append("✅ Librería MetaTrader5 instalada correctamente")
            except ImportError:
                results["details"].append("❌ La librería de MetaTrader5 no está instalada.")
                results["details"].append("")
                results["details"].append("📋 PASOS PARA SOLUCIONAR:")
                results["details"].append("1. Abra PowerShell o Terminal")
                results["details"].append("2. Ejecute: .\\venv\\Scripts\\python.exe -m pip install MetaTrader5")
                results["details"].append("3. Reinicie el Dashboard")
                results["details"].append("")
                results["details"].append("❓ ¿Necesita ayuda? Contacte al soporte técnico")
                return results
            
            # Check if MT5 accounts exist in database
            from data_vault.storage import StorageManager
            storage = StorageManager()
            all_accounts = storage.get_broker_accounts()
            mt5_accounts = [acc for acc in all_accounts if acc.get('platform_id') == 'mt5' and acc.get('enabled', True)]
            
            if not mt5_accounts:
                results["status"] = "YELLOW"
                results["details"].append("⚠️ No hay cuentas MT5 configuradas en el sistema")
                results["details"].append("")
                results["details"].append("📋 PASOS PARA CONFIGURAR:")
                results["details"].append("1. Vaya a la pestaña '🔌 Configuración de Brokers'")
                results["details"].append("2. Expanda la sección 'XM' (u otro broker)")
                results["details"].append("3. Haga clic en '➕ Crear Nueva Cuenta'")
                results["details"].append("4. Complete: Nombre, Login, Servidor, Contraseña")
                results["details"].append("5. Seleccione tipo 'DEMO' (recomendado)")
                results["details"].append("6. Guarde la cuenta")
                results["details"].append("")
                results["details"].append("💡 DATO: Puede obtener cuenta DEMO gratuita en:")
                results["details"].append("   • XM: https://www.xm.com/demo-account")
                results["details"].append("   • IC Markets: https://www.icmarkets.com/demo-trading-account")
                results["details"].append("")
                results["details"].append("❓ ¿Necesita ayuda? Contacte al soporte técnico")
                results["needs_config"] = True
                return results
            
            # Check if accounts have credentials
            account_with_creds = None
            for acc in mt5_accounts:
                creds: Optional[Dict[str, str]] = storage.get_credentials(acc['account_id'])
                if creds and creds.get('password'):
                    account_with_creds = acc
                    break
            
            if not account_with_creds:
                results["status"] = "YELLOW"
                results["details"].append("⚠️ Cuentas MT5 encontradas pero sin contraseñas guardadas")
                results["details"].append("")
                results["details"].append("📋 PASOS PARA SOLUCIONAR:")
                results["details"].append("1. Vaya a '🔌 Configuración de Brokers'")
                results["details"].append("2. Busque su cuenta MT5 en la lista")
                results["details"].append("3. Haga clic en 'Expandir' para ver detalles")
                results["details"].append("4. Ingrese la contraseña en el campo mostrado")
                results["details"].append("5. Haga clic en 'Guardar contraseña'")
                results["details"].append("")
                results["details"].append("❓ ¿Necesita ayuda? Contacte al soporte técnico")
                results["needs_config"] = True
                return results
            
            # Try to load MT5 connector
            try:
                from connectors.mt5_connector import MT5Connector
                
                connector = MT5Connector()
                
                # Attempt connection
                if connector.connect():
                    results["connected"] = True
                    results["status"] = "GREEN"
                    
                    # Get account info
                    account_info = mt5.account_info()  # type: ignore
                    if account_info:
                        results["account_type"] = "DEMO" if connector.is_demo else "REAL"
                        results["account_info"] = {
                            "login": account_info.login,
                            "server": account_info.server,
                            "balance": account_info.balance,
                            "equity": account_info.equity,
                            "profit": account_info.profit,
                            "margin": account_info.margin,
                            "margin_free": account_info.margin_free,
                            "currency": account_info.currency,
                            "leverage": account_info.leverage
                        }
                        
                        results["details"].append(
                            f"✅ Conectado a cuenta {results['account_type']} de MT5 #{account_info.login}"
                        )
                        results["details"].append(
                            f"💰 Balance: {account_info.balance:,.2f} {account_info.currency} | Servidor: {account_info.server}"
                        )
                    
                    # Check AutoTrading status
                    terminal_info = mt5.terminal_info()  # type: ignore
                    if terminal_info:
                        if terminal_info.trade_allowed:
                            results["details"].append("✅ AutoTrading habilitado en MT5")
                        else:
                            results["status"] = "YELLOW"
                            results["details"].append("⚠️ AutoTrading DESHABILITADO en MT5")
                            results["details"].append("")
                            results["details"].append("📋 PASOS PARA HABILITAR AUTOTRADING:")
                            results["details"].append("1. Abra MetaTrader 5")
                            results["details"].append("2. En la barra superior, busque el botón 'AutoTrading' (icono 🤖)")
                            results["details"].append("3. Haga clic en el botón para activarlo (debe ponerse VERDE)")
                            results["details"].append("")
                            results["details"].append("ALTERNATIVA:")
                            results["details"].append("• Menú → Herramientas → Opciones → Expert Advisors")
                            results["details"].append("• ✅ Marcar: 'Permitir AutoTrading'")
                            results["details"].append("")
                            results["details"].append("⚠️ SIN AUTOTRADING NO SE PUEDEN EJECUTAR OPERACIONES AUTOMÁTICAS")
                    
                    # Get open positions
                    open_positions = connector.get_open_positions()
                    results["open_positions"] = open_positions
                    if len(open_positions) > 0:
                        results["details"].append(f"📊 {len(open_positions)} posición(es) abierta(s)")
                    else:
                        results["details"].append(f"✅ Conexión activa - Sin posiciones abiertas")
                    
                    # Disconnect
                    connector.disconnect()
                    
                else:
                    results["status"] = "YELLOW"
                    results["details"].append("❌ No se pudo conectar a MetaTrader 5")
                    results["details"].append("")
                    results["details"].append("📋 PASOS PARA SOLUCIONAR:")
                    results["details"].append("1. Abra MetaTrader 5 en su computadora")
                    results["details"].append("2. Asegúrese de estar conectado a Internet")
                    results["details"].append("3. Verifique que sus credenciales sean correctas:")
                    results["details"].append(f"   • Cuenta configurada: {account_with_creds.get('account_name')}")
                    results["details"].append(f"   • Login: {account_with_creds.get('login') or account_with_creds.get('account_number')}")
                    results["details"].append(f"   • Servidor: {account_with_creds.get('server')}")
                    results["details"].append("4. Pruebe conectar manualmente en MT5 primero")
                    results["details"].append("5. Si conecta OK en MT5, reintente desde el Dashboard")
                    results["details"].append("")
                    results["details"].append("💡 POSIBLES CAUSAS:")
                    results["details"].append("   • MT5 no está abierto")
                    results["details"].append("   • Contraseña incorrecta")
                    results["details"].append("   • Servidor incorrecto")
                    results["details"].append("   • Cuenta expirada/deshabilitada")
                    results["details"].append("")
                    results["details"].append("❓ ¿Necesita ayuda? Contacte al soporte técnico")
                    results["needs_config"] = True
                    
            except FileNotFoundError as e:
                results["status"] = "YELLOW"
                results["details"].append(f"⚠️ Error de configuración: {e}")
                results["details"].append("")
                results["details"].append("📋 PASOS PARA SOLUCIONAR:")
                results["details"].append("1. Vaya a '🔌 Configuración de Brokers'")
                results["details"].append("2. Verifique que su cuenta MT5 tenga:")
                results["details"].append("   • Login completo (sin truncar)")
                results["details"].append("   • Servidor correcto")
                results["details"].append("   • Contraseña guardada")
                results["details"].append("3. Si falta algo, edite la cuenta y complete los datos")
                results["details"].append("")
                results["details"].append("❓ ¿Necesita ayuda? Contacte al soporte técnico")
                results["needs_config"] = True
            except Exception as e:
                results["details"].append(f"❌ Error de conexión: {str(e)}")
                results["details"].append("")
                results["details"].append("📋 PASOS PARA DIAGNOSTICAR:")
                results["details"].append("1. Ejecute script de diagnóstico:")
                results["details"].append("   python scripts/utilities/diagnose_mt5_connection.py")
                results["details"].append("2. Revise los logs del sistema en: logs/")
                results["details"].append("3. Capture el error completo y envíelo al soporte")
                results["details"].append("")
                results["details"].append("❓ Contacte al soporte técnico con el mensaje de error")
                results["details"].append("💡 Asegúrese de que MetaTrader 5 esté instalado y en ejecución")
                
        except Exception as e:
            results["details"].append(f"CRITICAL: Unexpected error checking MT5: {e}")
            logger.error(f"Error in check_mt5_connection: {e}", exc_info=True)
        
        return results

    def run_full_diagnostic(self) -> Dict[str, Any]:
        """Runs all checks and returns a summary."""
        config: Dict[str, Any] = self.check_config_integrity()
        db: Dict[str, Any] = self.check_db_integrity()
        resources: Dict[str, Any] = self.get_resource_usage()
        mt5: Dict[str, Any] = self.check_mt5_connection()
        
        # Overall status logic
        status = "GREEN"
        if config["status"] == "RED" or db["status"] == "RED":
            status = "RED"
        elif config["status"] == "YELLOW" or db["status"] == "YELLOW" or mt5["status"] == "YELLOW":
            status = "YELLOW"
            
        return {
            "timestamp": datetime.now().isoformat(),
            "overall_status": status,
            "config": config,
            "db": db,
            "resources": resources,
            "mt5": mt5
        }

if __name__ == "__main__":
    # Quick CLI test
    hm = HealthManager()
    summary: Dict[str, Any] = hm.run_full_diagnostic()
    print(json.dumps(summary, indent=2))
