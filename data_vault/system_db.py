import json
import logging
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

class SystemMixin(BaseRepository):
    """Mixin for System State, Stats, Data Providers and Learning operations."""

    def update_system_state(self, new_state: dict) -> None:
        """Update system state in database"""
        def _update(conn: sqlite3.Connection, new_state: dict) -> None:
            cursor = conn.cursor()
            for key, value in new_state.items():
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO system_state (key, value, updated_at)
                        VALUES (?, ?, ?)
                    """, (key, json.dumps(value), datetime.now()))
                except sqlite3.OperationalError:
                    cursor.execute("""
                        INSERT OR REPLACE INTO system_state (key, value)
                        VALUES (?, ?)
                    """, (key, json.dumps(value)))
            conn.commit()
        
        try:
            self._execute_serialized(_update, new_state)
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    def get_system_state(self) -> Dict[str, Any]:
        """Get current system state from database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM system_state")
            rows = cursor.fetchall()
            state = {}
            for row in rows:
                try:
                    state[row['key']] = json.loads(row['value'])
                except json.JSONDecodeError:
                    state[row['key']] = row['value']
            return state
        finally:
            self._close_conn(conn)

    def get_active_timeframes(self) -> List[str]:
        """Get list of active timeframes from system state"""
        state = self.get_system_state()
        tfs = state.get('active_timeframes', [])
        if isinstance(tfs, str):
            try:
                return json.loads(tfs)
            except json.JSONDecodeError:
                return [t for t in tfs.split(',') if t.strip()]
        if isinstance(tfs, list):
            return tfs
        return ['M1', 'M5', 'M15'] # Default fallback

    def save_tuning_adjustment(self, adjustment: Dict) -> None:
        """Save tuning adjustment to database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tuning_adjustments (adjustment_data)
                VALUES (?)
            """, (json.dumps(adjustment),))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_tuning_history(self, limit: int = 50) -> List[Dict]:
        """Get tuning adjustment history"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tuning_adjustments 
                ORDER BY timestamp DESC 
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            history = []
            for row in rows:
                adjustment = dict(row)
                adjustment['adjustment_data'] = json.loads(adjustment['adjustment_data'])
                history.append(adjustment)
            return history
        finally:
            self._close_conn(conn)

    def save_edge_learning(self, detection: str, action_taken: str, learning: str, details: Optional[str] = None) -> None:
        """Save an EDGE learning event for observability."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO edge_learning (detection, action_taken, learning, details)
                VALUES (?, ?, ?, ?)
            """, (detection, action_taken, learning, details))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_modules_config(self) -> Dict[str, Any]:
        """Get active modules configuration from system state (SSOT)."""
        state = self.get_system_state()
        config = state.get('modules_config', {})
        if isinstance(config, str):
            try:
                return json.loads(config)
            except json.JSONDecodeError:
                logger.error("Failed to decode modules_config from DB")
                return {}
        return config if isinstance(config, dict) else {}

    def save_modules_config(self, config: Dict[str, Any]) -> None:
        """Save modules configuration to system state (SSOT)."""
        self.update_system_state({'modules_config': config})

    def get_edge_learning_history(self, limit: int = 20) -> List[Dict]:
        """Get EDGE learning history"""
        query = "SELECT * FROM edge_learning ORDER BY timestamp DESC LIMIT ?"
        return self.execute_query(query, (limit,))

    def save_data_provider(self, name: str, enabled: bool = True, priority: int = 50, 
                          requires_auth: bool = False, api_key: Optional[str] = None, 
                          api_secret: Optional[str] = None, additional_config: Optional[Dict] = None,
                          is_system: bool = False, provider_type: str = "generic") -> None:
        """Save data provider configuration"""
        if additional_config is None:
            additional_config = {}
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO data_providers 
                (name, type, enabled, priority, requires_auth, api_key, api_secret, additional_config, is_system)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                name, provider_type, enabled, priority, requires_auth, 
                api_key, api_secret, json.dumps(additional_config), is_system
            ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_data_providers(self) -> List[Dict]:
        """Get all data providers"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM data_providers")
            rows = cursor.fetchall()
            column_names = [description[0] for description in cursor.description]
            providers = []
            for row in rows:
                provider = dict(zip(column_names, row))
                if 'config' in provider and provider['config']:
                    try:
                        config_data = json.loads(provider['config'])
                        provider.update(config_data)
                    except (json.JSONDecodeError, TypeError):
                        pass
                
                if 'additional_config' in provider and provider['additional_config']:
                    try:
                        if isinstance(provider['additional_config'], str):
                            provider['additional_config'] = json.loads(provider['additional_config'])
                    except (json.JSONDecodeError, TypeError):
                        provider['additional_config'] = {}
                else:
                    provider['additional_config'] = {}
                
                provider['config'] = {
                    'priority': provider.get('priority', 50),
                    'requires_auth': provider.get('requires_auth', False),
                    'api_key': provider.get('api_key'),
                    'api_secret': provider.get('api_secret'),
                    'additional_config': provider.get('additional_config', {}),
                    'is_system': provider.get('is_system', False)
                }
                if 'id' not in provider or not provider['id']:
                    provider['id'] = provider.get('name')
                providers.append(provider)
            return providers
        finally:
            self._close_conn(conn)

    def update_provider_enabled(self, provider_id: str, enabled: bool) -> None:
        """Update data provider enabled status"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE data_providers SET enabled = ? WHERE name = ?", (enabled, provider_id))
            conn.commit()
        finally:
            self._close_conn(conn)

    def update_module_heartbeat(self, module_name: str) -> None:
        """Update last activity timestamp for a module"""
        self.update_system_state({f"heartbeat_{module_name}": datetime.now().isoformat()})

    def get_module_heartbeats(self) -> Dict[str, str]:
        """Get last activity timestamps for all modules"""
        system_state = self.get_system_state()
        heartbeats = {}
        for key, value in system_state.items():
            if key.startswith("heartbeat_"):
                module_name = key.replace("heartbeat_", "")
                heartbeats[module_name] = value
        return heartbeats

    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics for dashboard"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM signals")
            total_signals = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM signals WHERE status = 'executed'")
            executed_signals_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM trade_results WHERE profit > 0")
            wins = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM trade_results WHERE profit < 0")
            losses = cursor.fetchone()[0]
            total_trades = wins + losses
            win_rate = (wins / total_trades) if total_trades > 0 else 0
            cursor.execute("SELECT AVG(profit) FROM trade_results")
            avg_pnl_result = cursor.fetchone()[0]
            avg_pnl = float(avg_pnl_result) if avg_pnl_result else 0.0
            
            return {
                'total_signals': total_signals,
                'executed_signals': {
                    'total': executed_signals_count,
                    'avg_pnl': avg_pnl,
                    'winning_trades': wins,
                    'win_rate': win_rate
                },
                'total_trades': total_trades,
                'wins': wins,
                'losses': losses,
                'win_rate': win_rate
            }
        finally:
            self._close_conn(conn)
    
    # ========== MODULE TOGGLES (GLOBAL) ==========
    
    def get_global_modules_enabled(self) -> Dict[str, bool]:
        """
        Get global module enable/disable settings.
        These settings affect ALL accounts system-wide.
        
        Returns:
            Dict with module names as keys, enabled status as values.
            Defaults to all enabled if not set.
        """
        system_state = self.get_system_state()
        default_modules = {
            "scanner": True,
            "executor": True,
            "position_manager": True,
            "risk_manager": True,
            "monitor": True,
            "notificator": True
        }
        return system_state.get("modules_enabled", default_modules)
    
    def set_global_module_enabled(self, module_name: str, enabled: bool) -> None:
        """
        Enable or disable a module globally (affects all accounts).
        
        Args:
            module_name: Name of the module (scanner, executor, etc.)
            enabled: True to enable, False to disable
        """
        modules = self.get_global_modules_enabled()
        modules[module_name] = enabled
        self.update_system_state({"modules_enabled": modules})
        logger.info(f"[GLOBAL] Module '{module_name}' set to {'ENABLED' if enabled else 'DISABLED'}")
    
    def set_global_modules_enabled(self, modules_dict: Dict[str, bool]) -> None:
        """
        Set multiple global module states at once.
        
        Args:
            modules_dict: Dictionary of {module_name: enabled_status}
        """
        current_modules = self.get_global_modules_enabled()
        current_modules.update(modules_dict)
        self.update_system_state({"modules_enabled": current_modules})
        logger.info(f"[GLOBAL] Updated module states: {modules_dict}")

    # ========== NOTIFICATION SETTINGS (Multi-channel) ==========
    
    def get_notification_settings(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene la configuración de un proveedor de notificaciones.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM notification_settings WHERE provider = ?", (provider,))
            row = cursor.fetchone()
            if not row:
                return None
            
            res = dict(row)
            if res.get('config'):
                try:
                    res['config'] = json.loads(res['config'])
                except:
                    pass
            return res
        finally:
            self._close_conn(conn)

    def update_notification_settings(self, provider: str, enabled: bool, config: Dict[str, Any]) -> bool:
        """
        Actualiza o crea la configuración de un proveedor de notificaciones.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO notification_settings (provider, enabled, config, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (provider, 1 if enabled else 0, json.dumps(config)))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating notification settings for {provider}: {e}")
            return False
        finally:
            self._close_conn(conn)

    def get_all_notification_settings(self) -> List[Dict[str, Any]]:
        """
        Obtiene la configuración de todos los proveedores.
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT provider, enabled, config_json FROM notification_settings")
            results = cursor.fetchall()
            conn.close()
            
            settings = []
            for row in results:
                settings.append({
                    "provider": row[0],
                    "enabled": bool(row[1]),
                    "config": json.loads(row[2])
                })
            return settings
        except Exception as e:
            logger.error(f"Error getting all notification settings: {e}")
            return []

    # =========================================================================
    # CONFIGURATION SSOT (Regla 14)
    # =========================================================================
    
    def get_risk_settings(self) -> Dict[str, Any]:
        """
        Obtiene la configuración de riesgo desde el estado del sistema.
        Si no existe, retorna un diccionario vacío para que el manager use defaults.
        """
        state = self.get_system_state()
        return state.get("risk_settings", {})

    def update_risk_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Actualiza la configuración de riesgo en el estado del sistema.
        """
        state = self.get_system_state()
        state["risk_settings"] = settings
        return self.update_system_state(state)

    def get_dynamic_params(self) -> Dict[str, Any]:
        """
        Obtiene los parámetros dinámicos (Auto-tune) desde el estado del sistema.
        """
        state = self.get_system_state()
        return state.get("dynamic_params", {})

    def update_dynamic_params(self, params: Dict[str, Any]) -> bool:
        """
        Actualiza los parámetros dinámicos en el estado del sistema.
        """
        state = self.get_system_state()
        state["dynamic_params"] = params
        return self.update_system_state(state)
