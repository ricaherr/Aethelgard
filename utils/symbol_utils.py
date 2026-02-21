import logging
from typing import Optional, Dict

logger = logging.getLogger(__name__)

class SymbolTranslator:
    """
    Utility to translate internal Aethelgard symbols to provider-specific formats (SSOT).
    """
    _mapping_cache: Optional[Dict] = None

    @classmethod
    def _load_mapping(cls) -> None:
        """Loads mappings from DB via StorageManager."""
        if cls._mapping_cache is None:
            try:
                from data_vault.storage import StorageManager
                storage = StorageManager()
                # get_symbol_map returns {internal_symbol: {provider_id: provider_symbol}}
                mapping = storage.get_symbol_map()
                if mapping:
                    cls._mapping_cache = {"internal_to_provider": mapping}
                    logger.debug("[SSOT] Symbol mappings loaded from DB.")
                else:
                    logger.warning("[SSOT] No symbol mappings found in DB. Using defaults.")
                    cls._mapping_cache = {"internal_to_provider": {}}
            except Exception as e:
                logger.error(f"[SSOT] Error loading symbol mappings from DB: {e}")
                cls._mapping_cache = {"internal_to_provider": {}}

    @classmethod
    def translate(cls, symbol: str, provider_id: str, suffix: str = "") -> str:
        """
        Translates internal symbol to provider format.
        
        Args:
            symbol: Internal symbol (e.g., 'EURUSD').
            provider_id: ID of the provider (e.g., 'oanda', 'yahoo').
            suffix: Optional suffix for some brokers.
            
        Returns:
            Provider-specific symbol string.
        """
        cls._load_mapping()
        
        # 1. Check direct mapping
        mappings = cls._mapping_cache.get("internal_to_provider", {})
        if symbol in mappings:
            provider_symbol = mappings[symbol].get(provider_id)
            if provider_symbol:
                return provider_symbol + suffix
            
            # 2. Fallback to mt5_default if provider is an mt5 variant
            if provider_id.startswith("mt5_"):
                default_mt5 = mappings[symbol].get("mt5_default")
                if default_mt5:
                    return default_mt5 + suffix
        
        # 3. Final fallback: Return symbol as is + suffix
        return symbol + suffix

    @classmethod
    def clear_cache(cls) -> None:
        """Clears memory cache to force reload from DB."""
        cls._mapping_cache = None
