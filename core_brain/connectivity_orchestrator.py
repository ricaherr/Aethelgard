import os
import importlib
import logging
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

    def load_connectors_from_db(self) -> None:
        """
        Instantiate connectors based on DB enabled providers and accounts.
        FOLLOWS SSOT RULE.
        """
        if not self.storage:
            return

        logger.info("Loading connectors from Database (SSOT)...")
        
        # 1. Load Data Providers
        try:
            providers = self.storage.get_data_providers()
            for p in providers:
                if not p.get('enabled', False): continue
                
                pid = p['name']
                # Avoid re-loading if already active
                if pid in self.connectors: continue

                # Logic to instantiate correct provider class
                if pid == 'yahoo':
                    from connectors.yahoo_connector import YahooConnector
                    try:
                        conn = YahooConnector(storage=self.storage)
                        self.register_connector(conn)
                        self.supports_info[pid] = {
                            "data": bool(p.get('supports_data', 0)),
                            "exec": bool(p.get('supports_exec', 0))
                        }
                    except Exception as e:
                        logger.error(f"Failed to load Yahoo connector: {e}")
                elif pid == 'mt5' and pid not in self.connectors:
                    from connectors.mt5_connector import MT5Connector
                    try:
                        conn = MT5Connector(storage=self.storage)
                        self.register_connector(conn)
                        self.supports_info[pid] = {
                            "data": bool(p.get('supports_data', 0)),
                            "exec": bool(p.get('supports_exec', 0))
                        }
                    except Exception as e:
                        logger.error(f"Failed to load MT5 connector: {e}")

        except Exception as e:
            logger.error(f"Error loading providers from DB: {e}")

        # 2. Load Broker Accounts
        try:
            accounts = self.storage.get_broker_accounts(enabled_only=True)
            for acc in accounts:
                pid = acc['broker_id']
                if pid in self.connectors: continue
                
                # If it uses MT5, we might already have it or need a specific account instance
                if acc['platform_id'] == 'mt5':
                    from connectors.mt5_connector import MT5Connector
                    try:
                        conn = MT5Connector(storage=self.storage, account_id=acc['account_id'])
                        self.register_connector(conn)
                        self.supports_info[pid] = {
                            "data": bool(acc.get('supports_data', 0)),
                            "exec": bool(acc.get('supports_exec', 0))
                        }
                    except Exception as e:
                        logger.error(f"Failed to load broker connector {pid}: {e}")
        except Exception as e:
            logger.error(f"Error loading accounts from DB: {e}")

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

            report[pid] = {
                "status": status,
                "failures": self.failure_counts.get(pid, 0),
                "is_available": connector.is_available() if is_manual_enabled else False,
                "is_manual_enabled": is_manual_enabled,
                "latency": connector.get_latency() if is_manual_enabled else 0.0,
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
