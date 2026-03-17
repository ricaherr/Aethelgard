import os
import importlib
import logging
import inspect
from enum import Enum
from typing import Dict, Optional, Type, Any, List
from connectors.base_connector import BaseConnector

logger = logging.getLogger(__name__)

class MarketType(Enum):
    CENTRALIZED = "CENTRALIZED"   # Futures, Stocks
    DECENTRALIZED = "DECENTRALIZED" # Forex, Crypto

class ConnectivityOrchestrator:
    """
    Central orchestrator to manage Aethelgard connectors.
    Handles dynamic loading, registration, and health monitoring.
    Uses Database as Single Source of Truth (SSOT).
    """
    _instance = None

    def __new__(cls, *args, **kwargs) -> Any:
        if not cls._instance:
            cls._instance = super(ConnectivityOrchestrator, cls).__new__(cls)
        return cls._instance

    def __init__(self, storage: Any = None) -> None:
        if not hasattr(self, 'initialized'):
            self.connectors: Dict[str, BaseConnector] = {}
            self.failure_counts: Dict[str, int] = {}
            self.manual_states: Dict[str, bool] = {} # True=Enabled, False=Disabled
            self.supports_info: Dict[str, Dict[str, bool]] = {} # data/exec flags
            self.storage = storage
            self.initialized = True
            logger.info("ConnectivityOrchestrator initialized.")

    def set_storage(self, storage: Any) -> None:
        """Inject storage manager if not provided at init."""
        self.storage = storage
        self._load_persistent_states()
        self.load_connectors_from_db()

    def _load_persistent_states(self) -> None:
        """Load connector states from DB."""
        if self.storage:
            self.manual_states = self.storage.get_connector_settings()
            logger.info(f"Loaded {len(self.manual_states)} connector states from DB.")

    def register_connector(self, connector: BaseConnector) -> None:
        """Manually register a connector instance."""
        pid = connector.provider_id
        self.connectors[pid] = connector
        self.failure_counts[pid] = 0
        logger.info(f"Connector registered: {pid}")

    def _instantiate_connector(self, connector_class: Type, base_kwargs: Dict[str, Any]) -> BaseConnector:
        """
        Instantiates a connector dynamically, filtering kwargs based on its __init__ signature.
        Prevents TypeError when trying to inject arguments (like storage) into classes that
        don't explicitly declare them and lack **kwargs.
        """
        try:
            sig = inspect.signature(connector_class.__init__)
        except ValueError:
            # Fallback if signature cannot be determined (e.g. built-ins)
            return connector_class(**base_kwargs)
            
        accepted_params = {
            name for name, param in sig.parameters.items()
            if name != 'self' and param.kind != inspect.Parameter.VAR_KEYWORD
        }
        
        has_var_kwargs = any(
            param.kind == inspect.Parameter.VAR_KEYWORD 
            for param in sig.parameters.values()
        )
        
        if has_var_kwargs:
            filtered_kwargs = base_kwargs
        else:
            filtered_kwargs = {k: v for k, v in base_kwargs.items() if k in accepted_params}
            
        return connector_class(**filtered_kwargs)

    def load_connectors_from_db(self) -> None:
        """
        Instantiate connectors based on the DB (SSOT).

        Two sources are consulted in order:
          1. sys_data_providers  — connector_module + connector_class columns drive instantiation.
          2. sys_broker_accounts — uses platform_id to look up module/class from
                                   sys_data_providers, so no hardcoded registry exists.

        To add a new connector:
          1. Add a row to sys_data_providers with connector_module, connector_class, enabled=True.
          2. Zero code changes needed here or anywhere in the codebase.
        """
        if not self.storage:
            return

        logger.info("Loading connectors from Database (SSOT)...")

        # Pre-fetch all providers once; used by both section 1 and section 2.
        try:
            all_providers = self.storage.get_sys_data_providers()
        except Exception as e:
            logger.error(f"[ConnOrch] Cannot read sys_data_providers: {e}")
            return

        # Build lookup: provider_name → (module_path, class_name)
        # Used by the broker-accounts section to resolve platform connectors.
        platform_lookup: Dict[str, tuple] = {
            p['name']: (p.get('connector_module'), p.get('connector_class'))
            for p in all_providers
            if p.get('connector_module') and p.get('connector_class')
        }

        # 1. sys_data_providers — drives which data-feed connectors are active
        for p in all_providers:
            if not p.get('enabled', False):
                continue  # DB says disabled → skip entirely

            pid = p['name']
            if pid in self.connectors:
                continue  # already loaded

            module_path = p.get('connector_module')
            class_name = p.get('connector_class')
            if not module_path or not class_name:
                logger.debug(f"[ConnOrch] No connector_module/class in DB for '{pid}', skipping.")
                continue

            try:
                module = importlib.import_module(module_path)
                connector_class = getattr(module, class_name)
                conn = self._instantiate_connector(connector_class, {'storage': self.storage})
                self.register_connector(conn)
                self.supports_info[pid] = {
                    "data": bool(p.get('supports_data', 1)),
                    "exec": bool(p.get('supports_exec', 0)),
                }
                logger.info(f"[ConnOrch] Loaded provider connector: {pid} ({class_name})")
            except Exception as e:
                logger.error(f"[ConnOrch] Failed to load connector '{pid}': {e}")

        # 2. Broker Accounts (sys_broker_accounts + usr_broker_accounts)
        # We load platform execution connectos for BOTH system shadow accounts AND user real/demo accounts
        try:
            broker_accounts = []
            # Gather system accounts
            sys_accs = self.storage.get_sys_broker_accounts(enabled_only=True)
            if sys_accs:
                broker_accounts.extend(sys_accs)
            
            # Gather user accounts
            if hasattr(self.storage, 'get_usr_broker_accounts'):
                usr_accs = self.storage.get_usr_broker_accounts(enabled_only=True)
                if usr_accs:
                    broker_accounts.extend(usr_accs)
            
            for acc in broker_accounts:
                platform = acc.get('platform_id', '')
                if not platform:
                    continue
                    
                account_id = acc.get('account_id')
                if not account_id:
                    continue
                
                # We register the connector using the account_id as its unique provider_id for execution
                # This ensures we can have multiple MT5 instances (one per account)
                conn_id = f"{platform}_{account_id}"
                
                if conn_id in self.connectors:
                    continue  # already loaded specific account instance

                module_path, class_name = platform_lookup.get(platform, (None, None))
                if not module_path or not class_name:
                    logger.debug(f"[ConnOrch] No connector info in DB for platform '{platform}', skipping.")
                    continue

                try:
                    module = importlib.import_module(module_path)
                    connector_class = getattr(module, class_name)
                    # Pass the specific account_id so the connector initializes with THAT account's credentials
                    conn = self._instantiate_connector(connector_class, {'storage': self.storage, 'account_id': account_id})
                    
                    # Override provider_id if needed, so the Orchestrator maps them explicitly
                    if hasattr(conn, 'provider_id'):
                        pass # Many connectors have property provider_id, let's leave as is for now, but log it
                        
                    self.register_connector(conn)
                    self.supports_info[conn.provider_id] = {
                        "data": bool(acc.get('supports_data', 0)),
                        "exec": bool(acc.get('supports_exec', 1)), # Usually broker accounts are for exec
                    }
                    logger.info(f"[ConnOrch] Loaded user/broker connector: {conn.provider_id} for acc {account_id} ({class_name})")
                except Exception as e:
                    logger.error(f"[ConnOrch] Failed to load broker connector for acc '{account_id}': {e}")
        except Exception as e:
            logger.error(f"[ConnOrch] Error reading broker_accounts: {e}")

    def get_connector(self, provider_id: str) -> Optional[BaseConnector]:
        """Retrieve a registered connector by its ID."""
        connector = self.connectors.get(provider_id)
        if not connector:
            # Try lazy load if storage is available
            if self.storage:
                self.load_connectors_from_db()
                connector = self.connectors.get(provider_id)
            
            if not connector:
                logger.warning(f"Connector not found: {provider_id}")
                return None
        
        # Check manual state
        if not self.manual_states.get(provider_id, True):
            logger.info(f"Connector {provider_id} is MANUAL_DISABLED.")
            return None

        # Check health status
        if self.failure_counts.get(provider_id, 0) >= 3:
            logger.error(f"Connector {provider_id} is OFFLINE due to repeated failures.")
            return None
            
        return connector

    def enable_connector(self, provider_id: str) -> None:
        """Manually enable a connector and save to DB."""
        self.manual_states[provider_id] = True
        if self.storage:
            self.storage.set_connector_enabled(provider_id, True)
        
        connector = self.connectors.get(provider_id)
        if connector:
            logger.info(f"[USER ACTION] Enabling connector {provider_id}...")
            self.failure_counts[provider_id] = 0

    def disable_connector(self, provider_id: str) -> None:
        """Manually disable a connector, save to DB and disconnect safely."""
        self.manual_states[provider_id] = False
        if self.storage:
            self.storage.set_connector_enabled(provider_id, False)
        
        connector = self.connectors.get(provider_id)
        if connector:
            logger.info(f"[USER ACTION] Manually disabling connector {provider_id}. Disconnecting...")
            try:
                connector.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting {provider_id}: {e}")
            self.failure_counts[provider_id] = 0 

    def report_failure(self, provider_id: str) -> None:
        """Increment failure count for a provider."""
        if provider_id in self.failure_counts:
            self.failure_counts[provider_id] += 1
            count = self.failure_counts[provider_id]
            logger.warning(f"Failure reported for {provider_id}. Count: {count}")
            if count >= 3:
                logger.critical(f"Provider {provider_id} marked as OFFLINE.")

    def report_success(self, provider_id: str) -> None:
        """Reset failure count for a provider."""
        if provider_id in self.failure_counts:
            self.failure_counts[provider_id] = 0

    def get_status_report(self) -> Dict[str, Dict[str, Any]]:
        """Return connectivity status for UI consumption."""
        report = {}
        # Ensure we have latest info
        if self.storage:
            self.load_connectors_from_db()

        for pid, connector in self.connectors.items():
            is_manual_enabled = self.manual_states.get(pid, True)
            
            status = "ONLINE"
            if not is_manual_enabled:
                status = "MANUAL_DISABLED"
            elif self.failure_counts.get(pid, 0) >= 3:
                status = "OFFLINE"

            supports = self.supports_info.get(pid, {"data": True, "exec": True})

            # Defensive: connector methods may throw (e.g., MT5 not installed)
            try:
                is_available = connector.is_available() if is_manual_enabled else False
            except Exception:
                is_available = False

            try:
                latency = connector.get_latency() if is_manual_enabled else 0.0
            except Exception:
                latency = 0.0

            report[pid] = {
                "status": status,
                "failures": self.failure_counts.get(pid, 0),
                "is_available": is_available,
                "is_manual_enabled": is_manual_enabled,
                "latency": latency,
                "supports_data": supports.get("data", False),
                "supports_exec": supports.get("exec", False),
                "last_error": getattr(connector, 'last_error', None)
            }
        return report

    def get_priority_provider(self, market_type: MarketType) -> Optional[BaseConnector]:
        """
        Returns the primary connector that provides Data and is healthy.
        Prefers connectors with supports_data=True from DB.
        """
        # Ensure latest sync
        self.load_connectors_from_db()

        # 1. Look for providers with supports_data = True
        for pid, supports in self.supports_info.items():
            if supports.get("data", False):
                conn = self.get_connector(pid)
                if conn and conn.is_available():
                    return conn
        
        # 2. Fallback to any available connector
        for pid in self.connectors:
            conn = self.get_connector(pid)
            if conn and conn.is_available():
                return conn
            
        return None
