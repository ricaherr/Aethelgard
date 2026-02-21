from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime

class BaseConnector(ABC):
    """
    Abstract Base Class for all Aethelgard Connectors.
    All broker-specific connectors must implement this interface.
    """

    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection with the broker/provider.
        Returns: True if successful, False otherwise.
        """
        pass

    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close the connection with the broker/provider.
        Returns: True if successful.
        """
        pass

    @abstractmethod
    def get_market_data(self, symbol: str, timeframe: str, count: int) -> Optional[Any]:
        """
        Fetch OHLC data for a specific symbol.
        Time standard: UTC ISO 8601.
        
        Args:
            symbol: Internal Aethelgard symbol.
            timeframe: Timeframe (M1, M5, H1, etc.)
            count: Number of bars.
            
        Returns:
            Data in normalized Aethelgard format (DataFrame or similar).
        """
        pass

    @abstractmethod
    def execute_order(self, signal: Any) -> Dict[str, Any]:
        """
        Execute an order based on a signal.
        
        Args:
            signal: Signal object with direction, volume, SL, TP.
            
        Returns:
            Execution result status and details.
        """
        pass

    @abstractmethod
    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Get current open positions from the broker.
        
        Returns:
            List of normalized position dictionaries.
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """
        Check if the connector is currently online and ready.
        """
        pass

    @abstractmethod
    def get_latency(self) -> float:
        """
        Measure and return current latency to the provider in milliseconds.
        """
        pass

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """
        Unique identifier for the provider (e.g., 'mt5', 'oanda', 'binance').
        """
        pass
