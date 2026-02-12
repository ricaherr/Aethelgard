import json
import uuid
import logging
import sqlite3
from typing import Dict, List, Optional, Union, overload
from datetime import datetime
from .base_repo import BaseRepository
from utils.encryption import get_encryptor

logger = logging.getLogger(__name__)

class AccountsMixin(BaseRepository):
    """Mixin for Account, Broker, and Platform database operations."""

    def save_broker(self, broker_data: Dict) -> None:
        """Save broker configuration"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(brokers)")
            columns = [row[1] for row in cursor.fetchall()]

            if 'broker_id' in columns:
                cursor.execute("""
                    INSERT OR REPLACE INTO brokers (broker_id, name, type, website, platforms_available, 
                                                   data_server, auto_provision_available, registration_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    broker_data.get('broker_id') or broker_data.get('id'),
                    broker_data['name'],
                    broker_data.get('type'),
                    broker_data.get('website'),
                    json.dumps(broker_data.get('platforms_available', [])),
                    broker_data.get('data_server'),
                    broker_data.get('auto_provision_available', False),
                    broker_data.get('registration_url')
                ))
            else:
                db_data = dict(broker_data)
                if 'broker_id' in db_data:
                    db_data['id'] = db_data['broker_id']

                cursor.execute("""
                    INSERT OR REPLACE INTO brokers (id, name, platform_id, config)
                    VALUES (?, ?, ?, ?)
                """, (
                    db_data.get('id') or db_data.get('broker_id'),
                    db_data['name'],
                    db_data.get('platform_id', 'unknown'),
                    json.dumps(db_data)
                ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def _get_broker_id_column(self, cursor: sqlite3.Cursor) -> str:
        """Detect broker identifier column for schema compatibility."""
        cursor.execute("PRAGMA table_info(brokers)")
        columns = [row[1] for row in cursor.fetchall()]
        return "broker_id" if "broker_id" in columns else "id"

    def _normalize_broker_row(self, broker: Dict) -> Dict:
        """Normalize broker row for old/new schema compatibility."""
        if 'config' in broker and broker['config']:
            config = json.loads(broker['config'])
            broker['broker_id'] = broker.get('broker_id') or broker.get('id')
            broker['auto_provisioning'] = 'full' if config.get('auto_provision_available') else 'none'

            for key, value in config.items():
                if key not in broker:
                    if isinstance(value, (str, int, float, bool)) or value is None:
                        broker[key] = value
                    elif isinstance(value, (list, dict)):
                        broker[key] = json.dumps(value)
        else:
            broker['broker_id'] = broker.get('broker_id', broker.get('id'))
            broker['auto_provisioning'] = 'full' if broker.get('auto_provision_available') else 'none'

        return broker

    def get_brokers(self) -> List[Dict]:
        """Get all brokers"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM brokers")
            rows = cursor.fetchall()
            return [self._normalize_broker_row(dict(row)) for row in rows]
        finally:
            self._close_conn(conn)

    def get_broker(self, broker_id: str) -> Optional[Dict]:
        """Get specific broker by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            lookup_column = self._get_broker_id_column(cursor)
            cursor.execute(f"SELECT * FROM brokers WHERE {lookup_column} = ?", (broker_id,))
            row = cursor.fetchone()
            if row:
                return self._normalize_broker_row(dict(row))
            return None
        finally:
            self._close_conn(conn)

    def save_platform(self, platform_data: Dict) -> None:
        """Save platform configuration"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO platforms (id, name, type, config)
                VALUES (?, ?, ?, ?)
            """, (
                platform_data['id'],
                platform_data['name'],
                platform_data['type'],
                json.dumps(platform_data.get('config', {}))
            ))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_platforms(self) -> List[Dict]:
        """Get all platforms"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM platforms")
            rows = cursor.fetchall()
            platforms = []
            for row in rows:
                platform = dict(row)
                if 'config' in platform and platform['config']:
                    config = json.loads(platform['config']) if platform['config'] else {}
                    platform.update(config)
                platforms.append(platform)
            return platforms
        finally:
            self._close_conn(conn)

    def save_broker_account(self, *args, **kwargs) -> str:
        """Save broker account - accepts dict, named params, or positional args"""
        if args:
            if len(args) >= 3:
                account_data = {
                    'broker_id': args[0],
                    'platform_id': args[1], 
                    'account_name': args[2],
                    'enabled': args[3] if len(args) > 3 else True
                }
                account_data.update(kwargs)
            else:
                raise ValueError("Not enough positional arguments")
        elif kwargs and 'account_data' not in kwargs:
            account_data = kwargs
        else:
            account_data = kwargs.get('account_data', {})
        
        if 'id' not in account_data and 'account_id' not in account_data:
            account_data['id'] = str(uuid.uuid4())
        elif 'account_id' in account_data:
            account_data['id'] = account_data['account_id']
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO broker_accounts 
                (account_id, broker_id, platform_id, account_name, account_number, server, account_type, enabled, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                account_data['id'],
                account_data.get('broker_id'),
                account_data.get('platform_id'),
                account_data.get('account_name'),
                account_data.get('account_number', account_data.get('login')),
                account_data.get('server'),
                account_data.get('account_type', account_data.get('type', 'demo')),
                account_data.get('enabled', True),
                datetime.now(),
                datetime.now()
            ))
            conn.commit()
        finally:
            self._close_conn(conn)
        
        if account_data.get('password'):
            self.update_credential(account_data['id'], {'password': account_data['password']})
        
        return account_data['id']

    def get_broker_accounts(self, enabled_only: bool = False, broker_id: Optional[str] = None, account_type: Optional[str] = None) -> List[Dict]:
        """Get all broker accounts, optionally filtered by enabled status, broker_id, and account_type"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            query = "SELECT * FROM broker_accounts WHERE 1=1"
            params = []
            if enabled_only:
                query += " AND enabled = 1"
            if broker_id:
                query += " AND broker_id = ?"
                params.append(broker_id)
            if account_type:
                query += " AND account_type = ?"
                params.append(account_type)
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        finally:
            self._close_conn(conn)

    def get_account(self, account_id: str) -> Optional[Dict]:
        """Get specific broker account by ID"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM broker_accounts WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
            return dict(row) if row else None
        finally:
            self._close_conn(conn)

    def update_account_enabled(self, account_id: str, enabled: bool) -> None:
        """Update account enabled status with verification"""
        self.update_account_credentials(account_id=account_id, enabled=enabled)
    
    # ========== MODULE TOGGLES (INDIVIDUAL - Per Account) ==========
    
    def get_individual_modules_enabled(self, account_id: str) -> Dict[str, bool]:
        """
        Get individual module overrides for a specific account.
        Returns empty dict if no overrides are set (inherits global).
        
        Args:
            account_id: The account ID to query
            
        Returns:
            Dict of module overrides {module_name: enabled_status}
        """
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Check if column exists (backwards compatibility)
            cursor.execute("PRAGMA table_info(broker_accounts)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'modules_enabled' not in columns:
                # Add column if missing (auto-migration)
                cursor.execute("""
                    ALTER TABLE broker_accounts 
                    ADD COLUMN modules_enabled TEXT DEFAULT '{}'
                """)
                conn.commit()
                return {}
            
            cursor.execute(
                "SELECT modules_enabled FROM broker_accounts WHERE account_id = ?",
                (account_id,)
            )
            row =cursor.fetchone()
            
            if not row or not row[0]:
                return {}
            
            try:
                return json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Invalid JSON in modules_enabled for account {account_id}")
                return {}
        finally:
            self._close_conn(conn)
    
    def set_individual_module_enabled(self, account_id: str, module_name: str, enabled: bool) -> None:
        """
        Enable or disable a module for a specific account.
        This creates an override for the global setting.
        
        Args:
            account_id: The account ID
            module_name: Name of the module (scanner, executor, etc.)
            enabled: True to enable, False to disable
        """
        modules = self.get_individual_modules_enabled(account_id)
        modules[module_name] = enabled
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Ensure column exists
            cursor.execute("PRAGMA table_info(broker_accounts)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'modules_enabled' not in columns:
                cursor.execute("""
                    ALTER TABLE broker_accounts 
                    ADD COLUMN modules_enabled TEXT DEFAULT '{}'
                """)
            
            cursor.execute(
                "UPDATE broker_accounts SET modules_enabled = ? WHERE account_id = ?",
                (json.dumps(modules), account_id)
            )
            conn.commit()
            logger.info(f"[INDIVIDUAL] Account {account_id}: module '{module_name}' set to {'ENABLED' if enabled else 'DISABLED'}")
        finally:
            self._close_conn(conn)
    
    def set_individual_modules_enabled(self, account_id: str, modules_dict: Dict[str, bool]) -> None:
        """
        Set multiple individual module states for an account.
        
        Args:
            account_id: The account ID
            modules_dict: Dictionary of {module_name: enabled_status}
        """
        current_modules = self.get_individual_modules_enabled(account_id)
        current_modules.update(modules_dict)
        
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            
            # Ensure column exists
            cursor.execute("PRAGMA table_info(broker_accounts)")
            columns = [row[1] for row in cursor.fetchall()]
            
            if 'modules_enabled' not in columns:
                cursor.execute("""
                    ALTER TABLE broker_accounts 
                    ADD COLUMN modules_enabled TEXT DEFAULT '{}'
                """)
            
            cursor.execute(
                "UPDATE broker_accounts SET modules_enabled = ? WHERE account_id = ?",
                (json.dumps(current_modules), account_id)
            )
            conn.commit()
            logger.info(f"[INDIVIDUAL] Account {account_id}: updated module states: {modules_dict}")
        finally:
            self._close_conn(conn)

    def update_account_credentials(self, account_id: str, account_number: Optional[str] = None, 
                                   password: Optional[str] = None, server: Optional[str] = None, 
                                   account_name: Optional[str] = None, account_type: Optional[str] = None,
                                   enabled: Optional[bool] = None) -> None:
        """Update account credentials with explicit mapping and post-write verification."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN TRANSACTION")
            update_fields = []
            update_values = []
            
            if account_name is not None:
                update_fields.append("account_name = ?")
                update_values.append(account_name)
            if account_number is not None:
                update_fields.append("account_number = ?")
                update_values.append(account_number)
            if server is not None:
                update_fields.append("server = ?")
                update_values.append(server)
            if account_type is not None:
                update_fields.append("account_type = ?")
                update_values.append(account_type)
            if enabled is not None:
                update_fields.append("enabled = ?")
                update_values.append(enabled)
            
            update_fields.append("updated_at = ?")
            update_values.append(datetime.now())
            update_values.append(account_id)
            
            if update_fields:
                set_clause = ", ".join(update_fields)
                cursor.execute(f"UPDATE broker_accounts SET {set_clause} WHERE account_id = ?", update_values)
            
            if password is not None:
                cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
                encrypted_data = get_encryptor().encrypt(json.dumps({'password': password}))
                cursor.execute("INSERT INTO credentials (broker_account_id, encrypted_data) VALUES (?, ?)", (account_id, encrypted_data))
            
            conn.commit()
            
            # Post-write verification
            cursor.execute("SELECT account_name, account_number, server, account_type, enabled FROM broker_accounts WHERE account_id = ?", (account_id,))
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Account {account_id} not found after update")
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            self._close_conn(conn)

    def update_credential(self, account_id: str, credential_data: Dict) -> None:
        """Update encrypted credentials for account"""
        encrypted_data = get_encryptor().encrypt(json.dumps(credential_data))
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("INSERT OR REPLACE INTO credentials (broker_account_id, encrypted_data) VALUES (?, ?)", (account_id, encrypted_data))
            conn.commit()
        finally:
            self._close_conn(conn)

    def save_credential(self, account_id: str, credential_type: str, credential_key: str, value: str) -> None:
        """Save a specific credential for an account"""
        existing = self.get_credentials(account_id) or {}
        existing[credential_key] = value
        self.update_credential(account_id, existing)

    @overload
    def get_credentials(self, account_id: str) -> Optional[Dict]: ...
    @overload
    def get_credentials(self, account_id: str, credential_type: str) -> Optional[str]: ...

    def get_credentials(self, account_id: str, credential_type: Optional[str] = None) -> Optional[Union[Dict, str]]:
        """Get decrypted credentials for account."""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT encrypted_data FROM credentials WHERE broker_account_id = ?", (account_id,))
            row = cursor.fetchone()
            if row:
                decrypted = get_encryptor().decrypt(row['encrypted_data'])
                credentials = json.loads(decrypted)
                return credentials.get(credential_type) if credential_type else credentials
            return None
        finally:
            self._close_conn(conn)

    def delete_credential(self, account_id: str) -> None:
        """Delete credentials for account"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
            conn.commit()
        finally:
            self._close_conn(conn)

    def delete_account(self, account_id: str) -> None:
        """Delete broker account and associated credentials"""
        conn = self._get_conn()
        try:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM credentials WHERE broker_account_id = ?", (account_id,))
            cursor.execute("DELETE FROM broker_accounts WHERE account_id = ?", (account_id,))
            conn.commit()
        finally:
            self._close_conn(conn)

    def get_all_accounts(self) -> List[Dict]:
        """Get all broker accounts (alias for get_broker_accounts)"""
        return self.get_broker_accounts()

    def get_broker_provision_status(self) -> List[Dict]:
        """
        Get current broker provisioning status.
        Returns list of broker dicts with their associated accounts.
        """
        brokers = self.get_brokers()
        accounts = self.get_broker_accounts()
        
        for broker in brokers:
            broker['accounts'] = [acc for acc in accounts if acc['broker_id'] == broker['broker_id']]
            broker['account_count'] = len(broker['accounts'])
            
        return brokers
