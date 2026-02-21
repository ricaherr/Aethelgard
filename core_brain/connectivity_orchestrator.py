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
            self.storage = storage
            self.initialized = True
            logger.info("ConnectivityOrchestrator initialized.")

    def set_storage(self, storage: Any) -> None:
        """Inject storage manager if not provided at init."""
        self.storage = storage
        self._load_persistent_states()

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

    def load_connectors(self, directory: str = "connectors") -> None:
        """
        Dynamically load all connectors from the specified directory.
        Looks for classes inheriting from BaseConnector.
        """
        # Note: This is a simplified version, implementation details depend on file naming
        # For now, we assume explicit registration or specific naming convention
        logger.info(f"Scanning for connectors in {directory}...")
        # Implementation logic for dynamic import would go here
        pass

    def get_connector(self, provider_id: str) -> Optional[BaseConnector]:
        """Retrieve a registered connector by its ID."""
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
            # We don't automatically connect here, let the system do it on next retry if needed
            # or we could force a connect() attempt if the connector supports it.
            # Reset failures for a fresh start
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
            self.failure_counts[provider_id] = 0 # Reset health count while disabled

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
        for pid, connector in self.connectors.items():
            is_manual_enabled = self.manual_states.get(pid, True)
            
            status = "ONLINE"
            if not is_manual_enabled:
                status = "MANUAL_DISABLED"
            elif self.failure_counts.get(pid, 0) >= 3:
                status = "OFFLINE"

            report[pid] = {
                "status": status,
                "failures": self.failure_counts.get(pid, 0),
                "is_available": connector.is_available() if is_manual_enabled else False,
                "is_manual_enabled": is_manual_enabled,
                "latency": connector.get_latency() if is_manual_enabled else 0.0
            }
        return report
    def get_priority_provider(self, market_type: MarketType) -> Optional[BaseConnector]:
        """
        Returns the primary connector that provides both Data and Execution for a market.
        Currently, for DECENTRALIZED markets (Forex/Crypto), MT5 is the priority.
        For CENTRALIZED, it might vary.
        """
        # Logic to determine priority provider based on availability and market type
        if market_type == MarketType.DECENTRALIZED:
            return self.get_connector("MT5")
        
        # Fallback to first available connector if not specified
        if self.connectors:
            return next(iter(self.connectors.values()))
            
        return None
