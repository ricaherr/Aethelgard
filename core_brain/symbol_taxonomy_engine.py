"""Single Source of Truth for symbol classification across the system.

This module defines the canonical taxonomy of financial symbols, preventing
duplication across components like DataProviderManager and MarketStructureAnalyzer.

All classification logic is pure (no side effects, deterministic).
All symbol sets are immutable and defined at module load time.
"""

from typing import Optional, Set


class SymbolTaxonomy:
    """
    SSOT for symbol type classification.
    
    INVARIANTS:
    - Every symbol belongs to EXACTLY ONE asset type
    - All asset type sets are disjoint (no symbol in multiple sets)
    - get_symbol_type() returns deterministic results (pure function)
    - is_index_without_volume() only returns True for indices lacking volume data
    """
    
    # Asset type definitions (enumerated set)
    ASSET_TYPES: Set[str] = {"indices", "crypto", "forex", "commodities", "stocks"}
    
    # ===== INDICES =====
    # Common index symbols used in CFD/derivative platforms
    INDICES: Set[str] = {
        "US30", "NAS100", "SPX500", "SPX", "NDX",  # US indices
        "DJI",  # Dow Jones Index (alias)
        "DAX40", "DE40",  # German indices (same underlying)
        "UK100",  # FTSE 100
        "JP225",  # Nikkei 225
    }
    
    # ===== CRYPTO =====
    # USDT pairs (spot market standard notation)
    CRYPTO: Set[str] = {
        "BTCUSDT", "ETHUSDT", "BNBUSDT",
        "SOLUSDT", "XRPUSDT", "LTCUSDT", "ADAUSDT",
    }
    
    # ===== FOREX =====
    # Major currency pairs (6-character alphabetic format: AABBCCDD where A/B/C/D are currency codes)
    # Examples: EURUSD, GBPJPY, USDJPY, AUDUSD, NZDUSD, USDCAD
    FOREX: Set[str] = {
        "EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD",
        "EURGBP", "EURJPY", "GBPJPY", "CHFJPY", "AUDCAD", "AUDNZD",
        "CADJPY", "NZDJPY", "USDCHF", "EURAUD", "EURDKK", "EURNOK",
        "EURSEK", "GBPCHF", "GBPNZD", "GBPAUD", "SGDJPY", "ZARJPY",
    }
    
    # ===== COMMODITIES =====
    # Natural resources and precious metals
    COMMODITIES: Set[str] = {
        "GOLD", "SILVER", "OIL", "CRUDE",
        "XAU",  # Gold (Forex notation)
        "XAG",  # Silver (Forex notation)
        "BRENT", "WTI",  # Oil variants
        "NATURAL_GAS",
    }
    
    # ===== STOCKS =====
    # Default fallback type for unknown symbols.
    # This set is NOT maintained (stocks are infinite and unknown at design time).
    # Stocks is the catch-all type for any symbol not matching other patterns.
    
    # ===== INDICES WITHOUT VOLUME =====
    # Subset of INDICES that do NOT expose volume columns in market feeds
    # Context: CFD indices are calculated instruments; volume is often unavailable or fictional
    # Note: This must remain a subset of INDICES; violation triggers invariant failure
    INDICES_WITHOUT_VOLUME: Set[str] = {
        "US30", "NAS100", "SPX500", "SPX", "NDX",
        "DJI", "DAX40", "DE40", "UK100", "JP225",
    }
    
    # Invariant check: INDICES_WITHOUT_VOLUME ⊆ INDICES
    @classmethod
    def _validate_invariants(cls) -> None:
        """Verify structural invariants at module load time."""
        all_symbols = set()
        
        # 1. Check disjoint sets (only for explicitly defined sets, not "stocks" which is catch-all)
        explicit_types = {"INDICES", "CRYPTO", "FOREX", "COMMODITIES"}
        for asset_type in explicit_types:
            symbols = getattr(cls, asset_type)
            intersection = all_symbols & symbols
            if intersection:
                raise AssertionError(
                    f"Symbol(s) {intersection} appear in multiple asset types"
                )
            all_symbols.update(symbols)
        
        # 2. Check INDICES_WITHOUT_VOLUME ⊆ INDICES
        if not cls.INDICES_WITHOUT_VOLUME.issubset(cls.INDICES):
            difference = cls.INDICES_WITHOUT_VOLUME - cls.INDICES
            raise AssertionError(
                f"INDICES_WITHOUT_VOLUME contains non-indices: {difference}"
            )
    
    @staticmethod
    def get_symbol_type(symbol: str) -> str:
        """
        Classify a symbol into its asset type.
        
        Pre:
            - symbol is string (possibly empty)
        
        Post:
            - Returns one of {"indices", "crypto", "forex", "commodities", "stocks"}
            - Always returns a type (never None); unknown symbols default to "stocks"
        
        Invariant:
            - Deterministic: same symbol → same classification (pure function, no side effects)
        
        Args:
            symbol: Symbol string (e.g., "BTCUSDT", "EURUSD", "US30")
        
        Returns:
            Asset type name; defaults to "stocks" for unknown symbols
        """
        # Normalize: uppercase, remove separators
        clean_symbol = symbol.upper().replace("/", "").replace("-", "").replace("_", "")
        
        # Classify by explicit set membership (priority order)
        if clean_symbol in SymbolTaxonomy.INDICES:
            return "indices"
        
        if clean_symbol in SymbolTaxonomy.CRYPTO:
            return "crypto"
        
        if clean_symbol in SymbolTaxonomy.FOREX:
            return "forex"
        
        if clean_symbol in SymbolTaxonomy.COMMODITIES:
            return "commodities"
        
        # Fallback heuristics for unknown symbols (pattern-based)
        # These maintain backward compatibility with _detect_symbol_type()
        
        # Heuristic 1: USDT pairs → crypto
        if clean_symbol.endswith("USDT"):
            return "crypto"
        
        # Heuristic 2: Known crypto tickers → crypto
        if any(ticker in clean_symbol for ticker in ["BTC", "ETH", "BNB", "SOL", "XRP", "LTC", "ADA"]):
            return "crypto"
        
        # Heuristic 3: 6-char pure alphabetic → forex
        if len(clean_symbol) == 6 and all(c.isalpha() for c in clean_symbol):
            return "forex"
        
        # Heuristic 4: Commodity tokens → commodities
        if any(token in clean_symbol for token in ["GOLD", "SILVER", "OIL", "XAU", "XAG", "BRENT", "WTI"]):
            return "commodities"
        
        # Default: stocks (catch-all for unknown symbols and empty strings)
        return "stocks"
    
    @staticmethod
    def is_index_without_volume(symbol: str) -> bool:
        """
        Check if a symbol is an index that does NOT expose volume column.
        
        Context:
            - Some asset classes (indices, forex) have different data contracts
            - Indices are often OTC instruments without real volume
            - Forex pairs also lack volume in some feeds
        
        Pre:
            - symbol is non-empty string
        
        Post:
            - Returns bool
            - True only if symbol is in INDICES_WITHOUT_VOLUME
        
        Invariant:
            - If True, then get_symbol_type(symbol) == "indices"
            - Deterministic: same input → same output
        
        Args:
            symbol: Symbol string (e.g., "US30", "EUR/USD")
        
        Returns:
            True if symbol lacks volume; False otherwise
        """
        clean_symbol = symbol.upper().replace("/", "").replace("-", "").replace("_", "")
        return clean_symbol in SymbolTaxonomy.INDICES_WITHOUT_VOLUME


# Validate invariants at module load time
SymbolTaxonomy._validate_invariants()
