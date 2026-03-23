import json
import logging
import sqlite3
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from utils.time_utils import to_utc
from .base_repo import BaseRepository

logger = logging.getLogger(__name__)

class SystemMixin(BaseRepository):
    """Mixin for System State, Stats, Data Providers and Learning operations."""

    def update_sys_config(self, new_state: dict) -> None:
        """Update system state in database"""
        def _update(conn: sqlite3.Connection, new_state: dict) -> None:
            cursor = conn.cursor()
            for key, value in new_state.items():
                try:
                    cursor.execute("""
                        INSERT OR REPLACE INTO sys_config (key, value, updated_at)
                        VALUES (?, ?, ?)
                    """, (key, json.dumps(value), datetime.now(timezone.utc)))
                except sqlite3.OperationalError:
                    cursor.execute("""
                        INSERT OR REPLACE INTO sys_config (key, value)
                        VALUES (?, ?)
                    """, (key, json.dumps(value)))
            conn.commit()
        
        try:
            self._execute_serialized(_update, new_state)
        except Exception as e:
            logger.error(f"Error updating system state: {e}")

    def get_sys_config(self) -> Dict[str, Any]:
        """Get current system state from database"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT key, value FROM sys_config")
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
        state = self.get_sys_config()
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
                INSERT INTO usr_tuning_adjustments (adjustment_data)
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
                SELECT * FROM usr_tuning_adjustments 
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
                INSERT INTO usr_edge_learning (detection, action_taken, learning, details)
                VALUES (?, ?, ?, ?)
            """, (detection, action_taken, learning, details))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_modules_config(self) -> Dict[str, Any]:
        """Get active modules configuration from system state (SSOT)."""
        state = self.get_sys_config()
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
        self.update_sys_config({'modules_config': config})

    def get_edge_learning_history(self, limit: int = 20) -> List[Dict]:
        """Get EDGE learning history"""
        query = "SELECT * FROM usr_edge_learning ORDER BY timestamp DESC LIMIT ?"
        return self.execute_query(query, (limit,))

    def save_data_provider(self, name: str, enabled: bool = True, priority: int = 50,
                          requires_auth: bool = False, api_key: Optional[str] = None,
                          api_secret: Optional[str] = None, additional_config: Optional[Dict] = None,
                          is_system: bool = False, provider_type: str = "generic",
                          connector_module: Optional[str] = None,
                          connector_class: Optional[str] = None) -> None:
        """Save data provider configuration.

        SSOT rule: On conflict (row already exists), the `enabled` column is NEVER
        overwritten by this UPSERT.  The `enabled` state is the single source of
        truth and may only be changed through `update_provider_enabled()` (called
        by `enable_provider()` / `disable_provider()`).  This prevents any code
        path that reconstructs in-memory state from accidentally corrupting the
        user-configured enabled/disabled state.

        COALESCE on connector_module/class preserves existing values when callers
        omit those arguments.
        """
        if additional_config is None:
            additional_config = {}

        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sys_data_providers
                (name, type, enabled, priority, requires_auth, api_key, api_secret,
                 additional_config, is_system, connector_module, connector_class)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    type=excluded.type,
                    enabled=COALESCE(sys_data_providers.enabled, excluded.enabled),
                    priority=excluded.priority,
                    requires_auth=excluded.requires_auth,
                    api_key=excluded.api_key,
                    api_secret=excluded.api_secret,
                    additional_config=excluded.additional_config,
                    is_system=excluded.is_system,
                    connector_module=COALESCE(excluded.connector_module, sys_data_providers.connector_module),
                    connector_class=COALESCE(excluded.connector_class, sys_data_providers.connector_class)
            """, (
                name, provider_type, enabled, priority, requires_auth,
                api_key, api_secret, json.dumps(additional_config), is_system,
                connector_module, connector_class
            ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_sys_data_providers(self) -> List[Dict]:
        """Get all data providers"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM sys_data_providers")
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
            cursor.execute("UPDATE sys_data_providers SET enabled = ? WHERE name = ?", (enabled, provider_id))
            conn.commit()
        finally:
            self._close_conn(conn)

    def set_connector_enabled(self, provider_id: str, enabled: bool) -> None:
        """Set manual enable/disable status for a connector (Satellite Link)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO usr_connector_settings (provider_id, enabled, last_manual_toggle)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """, (provider_id, 1 if enabled else 0))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_connector_settings(self) -> Dict[str, bool]:
        """Get all connector manual settings"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT provider_id, enabled FROM usr_connector_settings")
            rows = cursor.fetchall()
            return {row['provider_id']: bool(row['enabled']) for row in rows}
        finally:
            self._close_conn(conn)

    def update_module_heartbeat(self, module_name: str) -> None:
        """Update last activity timestamp for a module"""
        self.update_sys_config({f"heartbeat_{module_name}": datetime.now(timezone.utc).isoformat()})

    def get_module_heartbeats(self) -> Dict[str, str]:
        """Get last activity timestamps for all modules"""
        sys_config = self.get_sys_config()
        heartbeats = {}
        for key, value in sys_config.items():
            if key.startswith("heartbeat_"):
                module_name = key.replace("heartbeat_", "")
                heartbeats[module_name] = value
        return heartbeats

    def get_statistics(self) -> Dict[str, Any]:
        """Get system statistics for dashboard (LIVE trades only for backward compatibility)"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sys_signals")
            total_usr_signals = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sys_signals WHERE status = 'executed'")
            executed_usr_signals_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM usr_trades WHERE profit > 0 AND execution_mode = 'LIVE'")
            wins = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM usr_trades WHERE profit < 0 AND execution_mode = 'LIVE'")
            losses = cursor.fetchone()[0]
            total_usr_trades = wins + losses
            win_rate = (wins / total_usr_trades) if total_usr_trades > 0 else 0
            cursor.execute("SELECT AVG(profit) FROM usr_trades WHERE execution_mode = 'LIVE'")
            avg_pnl_result = cursor.fetchone()[0]
            avg_pnl = float(avg_pnl_result) if avg_pnl_result else 0.0
            
            return {
                'total_usr_signals': total_usr_signals,
                'executed_usr_signals': {
                    'total': executed_usr_signals_count,
                    'avg_pnl': avg_pnl,
                    'winning_usr_trades': wins,
                    'win_rate': win_rate
                },
                'total_usr_trades': total_usr_trades,
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
        sys_config = self.get_sys_config()
        default_modules = {
            "scanner": True,
            "executor": True,
            "position_manager": True,
            "risk_manager": True,
            "monitor": True,
            "notificator": True
        }
        return sys_config.get("modules_enabled", default_modules)
    
    def set_global_module_enabled(self, module_name: str, enabled: bool) -> None:
        """
        Enable or disable a module globally (affects all accounts).
        
        Args:
            module_name: Name of the module (scanner, executor, etc.)
            enabled: True to enable, False to disable
        """
        modules = self.get_global_modules_enabled()
        modules[module_name] = enabled
        self.update_sys_config({"modules_enabled": modules})
        logger.info(f"[GLOBAL] Module '{module_name}' set to {'ENABLED' if enabled else 'DISABLED'}")
    
    def set_global_modules_enabled(self, modules_dict: Dict[str, bool]) -> None:
        """
        Set multiple global module states at once.
        
        Args:
            modules_dict: Dictionary of {module_name: enabled_status}
        """
        current_modules = self.get_global_modules_enabled()
        current_modules.update(modules_dict)
        self.update_sys_config({"modules_enabled": current_modules})
        logger.info(f"[GLOBAL] Updated module states: {modules_dict}")

    # ========== NOTIFICATION SETTINGS (Multi-channel) ==========
    
    def get_usr_notification_settings(self, provider: str) -> Optional[Dict[str, Any]]:
        """
        Obtiene la configuración de un proveedor de notificaciones.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usr_notification_settings WHERE provider = ?", (provider,))
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

    def update_usr_notification_settings(self, provider: str, enabled: bool, config: Dict[str, Any]) -> bool:
        """
        Actualiza o crea la configuración de un proveedor de notificaciones.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO usr_notification_settings (provider, enabled, config, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """, (provider, 1 if enabled else 0, json.dumps(config)))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error updating notification settings for {provider}: {e}")
            return False
        finally:
            self._close_conn(conn)

    def get_all_usr_notification_settings(self) -> List[Dict[str, Any]]:
        """
        Obtiene la configuración de todos los proveedores.
        """
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT provider, enabled, config FROM usr_notification_settings")
            results = cursor.fetchall()
            conn.close()
            
            settings = []
            for row in results:
                settings.append({
                    "provider": row[0],
                    "enabled": bool(row[1]),
                    "config": json.loads(row[2]) if row[2] else {}
                })
            return settings
        except Exception as e:
            logger.error(f"Error getting all notification settings: {e}")
            return []

    # ========== INTERNAL NOTIFICATIONS (Persistent) ==========
    
    def save_notification(self, notification: Dict[str, Any]) -> bool:
        """
        Guarda una notificación en la base de datos.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO usr_notifications 
                (id, user_id, category, priority, title, message, details, actions, read, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                notification.get('id'),
                notification.get('user_id', 'default'),
                notification.get('category'),
                notification.get('priority', 'medium'),
                notification.get('title'),
                notification.get('message'),
                json.dumps(notification.get('details', {})),
                json.dumps(notification.get('actions', [])),
                1 if notification.get('read', False) else 0,
                notification.get('timestamp', datetime.now().isoformat())
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Error saving notification: {e}")
            return False
        finally:
            self._close_conn(conn)

    def get_user_notifications(self, user_id: str = 'default', unread_only: bool = False, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Recupera notificaciones de un usuario desde la base de datos.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM usr_notifications WHERE user_id = ?"
            params = [user_id]
            
            if unread_only:
                query += " AND read = 0"
            
            query += " ORDER BY timestamp DESC LIMIT ?"
            params.append(limit)
            
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
            
            notifications = []
            for row in rows:
                notif = dict(row)
                if notif.get('details'):
                    try: notif['details'] = json.loads(notif['details'])
                    except: pass
                if notif.get('actions'):
                    try: notif['actions'] = json.loads(notif['actions'])
                    except: pass
                notifications.append(notif)
            return notifications
        except Exception as e:
            logger.error(f"Error getting notifications for {user_id}: {e}")
            return []
        finally:
            self._close_conn(conn)

    def mark_notification_read(self, notification_id: str) -> bool:
        """
        Marca una notificación específica como leída.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE usr_notifications SET read = 1 WHERE id = ?", (notification_id,))
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            logger.error(f"Error marking notification {notification_id} as read: {e}")
            return False
        finally:
            self._close_conn(conn)

    def delete_old_notifications(self, hours: int = 48) -> int:
        """
        Elimina notificaciones más antiguas de N horas para mantener la DB limpia.
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                DELETE FROM usr_notifications 
                WHERE timestamp < datetime('now', '-' || ? || ' hours')
            """, (hours,))
            conn.commit()
            return cursor.rowcount
        except Exception as e:
            logger.error(f"Error deleting old notifications: {e}")
            return 0
        finally:
            self._close_conn(conn)

    # =========================================================================
    # CONFIGURATION SSOT (Regla 14)
    # =========================================================================
    
    def get_risk_settings(self) -> Dict[str, Any]:
        """
        Obtiene la configuración de riesgo desde el estado del sistema.
        Si no existe, retorna un diccionario vacío para que el manager use defaults.
        """
        state = self.get_sys_config()
        return state.get("risk_settings", {})

    def update_risk_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Actualiza la configuración de riesgo en el estado del sistema.
        """
        state = self.get_sys_config()
        state["risk_settings"] = settings
        return self.update_sys_config(state)

    def get_dynamic_params(self) -> Dict[str, Any]:
        """
        Obtiene los parámetros dinámicos (Auto-tune) desde el estado del sistema.
        """
        state = self.get_sys_config()
        return state.get("dynamic_params", {})

    def update_dynamic_params(self, params: Dict[str, Any]) -> bool:
        """
        Actualiza los parámetros dinámicos en el estado del sistema.
        """
        state = self.get_sys_config()
        state["dynamic_params"] = params
        return self.update_sys_config(state)
    # ========== SYMBOL MAPPINGS (SSOT) ==========

    def save_symbol_mapping(self, internal_symbol: str, provider_id: str, provider_symbol: str, is_default: bool = False) -> None:
        """Save a symbol mapping to the database (SSOT)."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO sys_symbol_mappings (internal_symbol, provider_id, provider_symbol, is_default)
                VALUES (?, ?, ?, ?)
            """, (internal_symbol, provider_id, provider_symbol, 1 if is_default else 0))
            conn.commit()
            logger.debug(f"[SSOT] Saved mapping: {internal_symbol} -> {provider_symbol} ({provider_id})")
        finally:
            self._close_conn(conn)

    def get_symbol_map(self, provider_id: Optional[str] = None) -> Dict[str, Dict[str, str]]:
        """
        Get symbol mappings from database.
        
        Args:
            provider_id: If provided, filtered by this provider.
            
        Returns:
            Nested dict: {internal_symbol: {provider_id: provider_symbol}}
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            if provider_id:
                cursor.execute("""
                    SELECT internal_symbol, provider_id, provider_symbol FROM sys_symbol_mappings 
                    WHERE provider_id = ?
                """, (provider_id,))
            else:
                cursor.execute("SELECT internal_symbol, provider_id, provider_symbol FROM sys_symbol_mappings")
            
            rows = cursor.fetchall()
            mapping = {}
            for row in rows:
                internal = row['internal_symbol']
                pid = row['provider_id']
                psym = row['provider_symbol']
                
                if internal not in mapping:
                    mapping[internal] = {}
                mapping[internal][pid] = psym
                
            return mapping
        finally:
            self._close_conn(conn)

    # ── User Preferences (Perfiles y Autonomía) ──────────────────────────────

    def get_usr_preferences(self, user_id: str = "default") -> Optional[Dict]:
        """Obtiene las preferencias del usuario desde la base de datos."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM usr_preferences WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            columns = [desc[0] for desc in cursor.description]
            prefs = dict(zip(columns, row))
            for json_field in ("auto_trading_symbols", "auto_trading_usr_strategies",
                               "auto_trading_timeframes", "active_filters"):
                if prefs.get(json_field):
                    try:
                        prefs[json_field] = json.loads(prefs[json_field])
                    except ValueError:
                        prefs[json_field] = None
            return prefs
        except Exception as exc:
            logger.error("Error getting user preferences: %s", exc)
            return None
        finally:
            self._close_conn(conn)

    def update_usr_preferences(self, user_id: str, preferences: Dict) -> bool:
        """Actualiza las preferencias del usuario en la base de datos."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            # Serializar campos JSON
            for json_field in ("auto_trading_symbols", "auto_trading_usr_strategies",
                               "auto_trading_timeframes", "active_filters"):
                if json_field in preferences and preferences[json_field] is not None:
                    if not isinstance(preferences[json_field], str):
                        preferences[json_field] = json.dumps(preferences[json_field])

            fields = [f"{k} = ?" for k in preferences.keys() if k != "user_id"]
            values = [v for k, v in preferences.items() if k != "user_id"]
            if not fields:
                return False

            fields.append("updated_at = CURRENT_TIMESTAMP")
            query = f"UPDATE usr_preferences SET {', '.join(fields)} WHERE user_id = ?"
            values.append(user_id)
            cursor.execute(query, values)

            if cursor.rowcount == 0:
                preferences["user_id"] = user_id
                placeholders = ", ".join(["?" for _ in preferences])
                columns = ", ".join(preferences.keys())
                cursor.execute(f"INSERT INTO usr_preferences ({columns}) VALUES ({placeholders})",
                               list(preferences.values()))
            conn.commit()
            return True
        except Exception as exc:
            logger.error("Error updating user preferences: %s", exc)
            conn.rollback()
            return False
        finally:
            self._close_conn(conn)

    def get_default_profile(self, profile_type: str) -> Dict:
        """Retorna configuración por defecto para un tipo de perfil."""
        profiles = {
            "explorer": {
                "profile_type": "explorer",
                "auto_trading_enabled": False,
                "notify_usr_signals": True,
                "notify_usr_executions": False,
                "notify_threshold_score": 0.90,
                "default_view": "feed",
                "require_confirmation": True,
            },
            "active_trader": {
                "profile_type": "active_trader",
                "auto_trading_enabled": False,
                "auto_trading_max_risk": 1.5,
                "notify_usr_signals": True,
                "notify_usr_executions": True,
                "notify_threshold_score": 0.85,
                "default_view": "grid",
                "require_confirmation": True,
                "max_daily_usr_trades": 10,
            },
            "scalper": {
                "profile_type": "scalper",
                "auto_trading_enabled": True,
                "auto_trading_max_risk": 1.0,
                "auto_trading_timeframes": ["M1", "M5"],
                "notify_usr_signals": False,
                "notify_usr_executions": True,
                "notify_threshold_score": 0.90,
                "default_view": "feed",
                "require_confirmation": False,
                "max_daily_usr_trades": 20,
            }
        }
        return profiles.get(profile_type, profiles["active_trader"])

    def resolve_module_enabled(self, account_id: Optional[str], module_name: str) -> bool:
        """
        Resolve final module enabled status with priority logic.
        Priority: 1. GLOBAL disabled -> disabled. 2. OVERRIDE...
        """
        global_enabled = self.get_global_modules_enabled().get(module_name, True)
        if not global_enabled:
            logger.debug("[RESOLVE] Module '%s' DISABLED globally", module_name)
            return False

        if not account_id:
            return global_enabled

        individual_enabled = self.get_individual_modules_enabled(account_id).get(module_name)
        if individual_enabled is not None:
            return individual_enabled

        return global_enabled

    # ── Database Maintenance & Backup ────────────────────────────────────────

    def create_db_backup(self, backup_dir: Optional[str] = None, retention_count: int = 15) -> Optional[str]:
        """Create a backup of the main SQLite database online."""
        import os
        import shutil
        import time

        if self.db_path == ':memory:':
            logger.warning("[BACKUP] Cannot backup in-memory database.")
            return None

        # Determine backup directory
        if not backup_dir:
            db_dir = os.path.dirname(self.db_path) or '.'
            backup_dir = os.path.join(db_dir, 'backups')
        
        os.makedirs(backup_dir, exist_ok=True)

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
        backup_filename = f"sqlite_backup_{timestamp}.sqlite"
        backup_path = os.path.join(backup_dir, backup_filename)

        start_time = time.time()
        conn = self._get_conn()
        try:
            backup_conn = sqlite3.connect(backup_path)
            conn.backup(backup_conn, pages=250, sleep=0.01)
            backup_conn.close()

            file_size_mb = os.path.getsize(backup_path) / (1024 * 1024)
            elapsed = time.time() - start_time
            logger.info("[BACKUP] DB backup created successfully: %s (%.2f MB, %.2fs)",
                        backup_filename, file_size_mb, elapsed)

            # Implement retention logic
            self._cleanup_old_backups(backup_dir, retention_count)

            return backup_path
        except Exception as e:
            logger.error("[BACKUP] Backup failed: %s", e)
            if os.path.exists(backup_path):
                try: os.remove(backup_path)
                except: pass
            return None
        finally:
            self._close_conn(conn)

    def _cleanup_old_backups(self, backup_dir: str, retention_count: int) -> None:
        """Keep only the N most recent backups."""
        import os
        try:
            backups = []
            for f in os.listdir(backup_dir):
                if f.startswith("sqlite_backup_") and f.endswith(".sqlite"):
                    path = os.path.join(backup_dir, f)
                    backups.append((path, os.path.getmtime(path)))
            
            # Sort by modification time (newest first)
            backups.sort(key=lambda x: x[1], reverse=True)
            
            if len(backups) > retention_count:
                for path, _ in backups[retention_count:]:
                    try:
                        os.remove(path)
                        logger.debug("[BACKUP] Retention: Removed old backup %s", os.path.basename(path))
                    except Exception as e:
                        logger.warning("[BACKUP] Could not remove old backup %s: %s", path, e)
        except Exception as e:
            logger.error("[BACKUP] Error during retention cleanup: %s", e)

    def list_db_backups(self) -> List[Dict]:
        """List all available database backups."""
        import os

        if self.db_path == ':memory:':
            return []

        db_dir = os.path.dirname(self.db_path) or '.'
        backup_dir = os.path.join(db_dir, 'backups')

        if not os.path.exists(backup_dir):
            return []

        backups = []
        for filename in os.listdir(backup_dir):
            if filename.startswith("sqlite_backup_") and filename.endswith(".sqlite"):
                filepath = os.path.join(backup_dir, filename)
                stat = os.stat(filepath)
                # Parse timestamp from filename
                try:
                    ts_str = filename.replace("sqlite_backup_", "").replace(".sqlite", "")
                    dt = datetime.strptime(ts_str, '%Y%m%d_%H%M%S').replace(tzinfo=timezone.utc)
                except ValueError:
                    dt = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)

                backups.append({
                    "filename": filename,
                    "path": filepath,
                    "size_mb": round(stat.st_size / (1024 * 1024), 2),
                    "created_at": dt.isoformat(),
                    "timestamp": dt.timestamp()
                })

        # Sort newest first
        backups.sort(key=lambda x: x["timestamp"], reverse=True)
        return backups

    def restore_db_backup(self, backup_filename: str) -> bool:
        """
        Restore the database from a given backup filename.
        Overwrites the current database file. MUST BE USED WITH CAUTION.
        """
        import os
        import shutil

        if self.db_path == ':memory:':
            logger.error("[BACKUP] Cannot restore into in-memory database.")
            return False

        db_dir = os.path.dirname(self.db_path) or '.'
        backup_dir = os.path.join(db_dir, 'backups')
        backup_path = os.path.join(backup_dir, backup_filename)

        if not os.path.exists(backup_path):
            logger.error("[BACKUP] Backup file not found: %s", backup_path)
            return False

        logger.warning("!!! RESTORING DATABASE FROM BACKUP: %s !!!", backup_filename)

        try:
            self._pool.close_all()
            
            temp_db_path = self.db_path + ".tmp"
            if os.path.exists(self.db_path):
                os.rename(self.db_path, temp_db_path)

            shutil.copy2(backup_path, self.db_path)

            if os.path.exists(temp_db_path):
                os.remove(temp_db_path)

            self._pool = getattr(self, '__pool_class__', None)(self.db_path) if hasattr(self, '__pool_class__') else None

            logger.info("[BACKUP] Database restored successfully.")
            return True
        except Exception as e:
            logger.error("[BACKUP] Failed to restore database: %s", e)
            if 'temp_db_path' in locals() and os.path.exists(temp_db_path):
                logger.warning("[BACKUP] Attempting to revert to original DB...")
                try:
                    if os.path.exists(self.db_path):
                        os.remove(self.db_path)
                    os.rename(temp_db_path, self.db_path)
                    logger.info("[BACKUP] Original database reverted.")
                except Exception as revert_exc:
                    logger.critical("[BACKUP] FATAL: Failed to revert database: %s", revert_exc)
            return False

    def check_integrity(self) -> Dict:
        """Run SQLite PRAGMA integrity_check and quick_check."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            cursor.execute("PRAGMA quick_check")
            quick_result = cursor.fetchall()
            
            cursor.execute("PRAGMA integrity_check")
            full_result = cursor.fetchall()
            
            is_ok = (quick_result and quick_result[0][0] == 'ok') and \
                    (full_result and full_result[0][0] == 'ok')
            
            return {
                "status": "ok" if is_ok else "error",
                "quick_check": [row[0] for row in quick_result] if quick_result else ["failed"],
                "integrity_check": [row[0] for row in full_result] if full_result else ["failed"]
            }
        except Exception as e:
            logger.error("[DB] Integrity check failed: %s", e)
            return {"status": "error", "error": str(e)}
        finally:
            self._close_conn(conn)

    def prune_old_backups(self, max_backups: int = 10, max_age_days: int = 30) -> int:
        """Delete backups older than max_age_days or exceeding max_backups count."""
        import os
        from datetime import timedelta

        backups = self.list_db_backups()
        if not backups:
            return 0

        pruned_count = 0
        now = datetime.now(timezone.utc)
        cutoff_date = now - timedelta(days=max_age_days)

        for i, backup in enumerate(backups):
            try:
                dt = datetime.fromisoformat(backup["created_at"])
                should_delete = False

                if dt < cutoff_date:
                    should_delete = True
                elif i >= max_backups:
                    should_delete = True
                
                if should_delete:
                    os.remove(backup["path"])
                    logger.info("[BACKUP] Pruned old backup: %s", backup["filename"])
                    pruned_count += 1
            except Exception as e:
                logger.error("[BACKUP] Failed to prune %s: %s", backup.get("filename"), e)
                
        return pruned_count

    # ── Deduplication Learn ing (PHASE 3) ────────────────────────────────────

    async def get_dedup_events_since(self, cutoff_date: datetime) -> List[Dict]:
        """
        Get all dedup events (signal blockages) since cutoff_date.
        Used by DedupLearner for weekly gap analysis.
        
        Returns:
            List of {symbol, timeframe, strategy, gap_minutes, created_at}
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT symbol, timeframe, strategy, gap_minutes, created_at
                FROM sys_dedup_events
                WHERE created_at >= ?
                ORDER BY created_at ASC
            """, (cutoff_date,))
            
            rows = cursor.fetchall()
            events = []
            for row in rows:
                events.append({
                    "symbol": row[0],
                    "timeframe": row[1],
                    "strategy": row[2],
                    "gap_minutes": row[3],
                    "created_at": row[4]
                })
            
            logger.debug(f"[DEDUP] Fetched {len(events)} events since {cutoff_date}")
            return events
        except Exception as e:
            logger.error(f"[DEDUP] Error fetching dedup events: {e}")
            return []
        finally:
            self._close_conn(conn)

    async def get_dedup_rule(self, symbol: str, timeframe: str, strategy: str) -> Optional[Dict]:
        """
        Get dedup rule for specific (symbol, timeframe, strategy).
        
        Returns:
            {id, base_window_minutes, current_window_minutes, learning_enabled, ...}
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT id, symbol, timeframe, strategy, base_window_minutes, current_window_minutes,
                       volatility_factor, regime_factor, data_points_observed, learning_enabled,
                       manual_override, trace_id, last_adjusted, created_at, updated_at
                FROM sys_dedup_rules
                WHERE symbol = ? AND timeframe = ? AND strategy = ?
            """, (symbol, timeframe, strategy))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            return {
                "id": row[0],
                "symbol": row[1],
                "timeframe": row[2],
                "strategy": row[3],
                "base_window_minutes": row[4],
                "current_window_minutes": row[5],
                "volatility_factor": row[6],
                "regime_factor": row[7],
                "data_points_observed": row[8],
                "learning_enabled": row[9],
                "manual_override": row[10],
                "trace_id": row[11],
                "last_adjusted": row[12],
                "created_at": row[13],
                "updated_at": row[14]
            }
        except Exception as e:
            logger.error(f"[DEDUP] Error fetching rule ({symbol}/{timeframe}/{strategy}): {e}")
            return None
        finally:
            self._close_conn(conn)

    async def update_dedup_rule(
        self,
        symbol: str,
        timeframe: str,
        strategy: str,
        current_window_minutes: int,
        data_points_observed: int,
        learning_enabled: bool = True,
        trace_id: str = ""
    ) -> bool:
        """
        Update or insert dedup rule with learned window.
        
        Args:
            symbol, timeframe, strategy: Key tuple
            current_window_minutes: New window value (from learning)
            data_points_observed: Number of gaps analyzed
            learning_enabled: Allow further learning
            trace_id: Audit trace for this update
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            now = datetime.now(timezone.utc)
            
            cursor.execute("""
                INSERT OR REPLACE INTO sys_dedup_rules
                (symbol, timeframe, strategy, current_window_minutes, data_points_observed,
                 learning_enabled, trace_id, last_adjusted, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                symbol, timeframe, strategy,
                current_window_minutes, data_points_observed,
                1 if learning_enabled else 0,
                trace_id, now, now
            ))
            
            conn.commit()
            logger.info(
                f"[DEDUP] Rule updated: {symbol}/{timeframe}/{strategy} → "
                f"window={current_window_minutes} min (trace={trace_id})"
            )
            return True
        except Exception as e:
            logger.error(f"[DEDUP] Error updating rule: {e}")
            return False
        finally:
            self._close_conn(conn)

