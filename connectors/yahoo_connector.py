import logging
from typing import List, Dict, Any, Optional
from connectors.base_connector import BaseConnector
from connectors.generic_data_provider import GenericDataProvider

logger = logging.getLogger(__name__)

class YahooConnector(BaseConnector):
    """
    Wrapper for GenericDataProvider (Yahoo Finance) to comply with BaseConnector interface.
    Used for data-only support (Source Fidelity).
    """

    def __init__(self, storage: Any = None):
        self._provider = GenericDataProvider(storage=storage)
        self._storage = storage

    def connect(self) -> bool:
        """Yahoo Finance doesn't require explicit connection."""
        return True

    def disconnect(self) -> bool:
        return True

    def get_market_data(self, symbol: str, timeframe: str, count: int) -> Optional[Any]:
        return self._provider.fetch_ohlc(symbol, timeframe, count)

    def execute_order(self, signal: Any) -> Dict[str, Any]:
        """Yahoo does NOT support execution."""
        msg = f"YahooConnector does not support order execution for {signal.symbol}"
        logger.warning(msg)
        return {"status": "FAILED", "error": msg}

    def get_positions(self) -> List[Dict[str, Any]]:
        return []

    def is_available(self) -> bool:
        return True

    def get_latency(self) -> float:
        """Simulated latency for API request."""
        return 200.0

    @property
    def provider_id(self) -> str:
        return "yahoo"
