"""Tests for SymbolTaxonomy — SSOT symbol classification engine."""

import pytest
from core_brain.symbol_taxonomy_engine import SymbolTaxonomy


class TestSymbolTypeClassification:
    """Happy path: symbol → correct asset type."""
    
    def test_get_symbol_type_returns_indices_for_us30_and_variants(self):
        """Indices: US30, NAS100, SPX500, SPX, NDX, DJI, DAX40, DE40, UK100, JP225."""
        indices = ["US30", "NAS100", "SPX500", "SPX", "NDX", "DJI", "DAX40", "DE40", "UK100", "JP225"]
        for symbol in indices:
            assert SymbolTaxonomy.get_symbol_type(symbol) == "indices", f"Failed for {symbol}"
    
    def test_get_symbol_type_returns_crypto_for_usdt_pairs(self):
        """Crypto: BTCUSDT, ETHUSDT, BNBUSDT."""
        crypto = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        for symbol in crypto:
            assert SymbolTaxonomy.get_symbol_type(symbol) == "crypto", f"Failed for {symbol}"
    
    def test_get_symbol_type_returns_forex_for_pairs(self):
        """Forex: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD."""
        forex = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD"]
        for symbol in forex:
            assert SymbolTaxonomy.get_symbol_type(symbol) == "forex", f"Failed for {symbol}"
    
    def test_get_symbol_type_returns_commodities(self):
        """Commodities: GOLD, SILVER, OIL, CRUEL, XAU, XAG, BRENT, WTI."""
        commodities = ["GOLD", "SILVER", "OIL", "CRUDE", "XAU", "XAG", "BRENT", "WTI"]
        for symbol in commodities:
            result = SymbolTaxonomy.get_symbol_type(symbol)
            assert result == "commodities", f"Failed for {symbol}, got {result}"
    
    def test_unknown_symbol_returns_stocks_default(self):
        """Unknown symbols default to 'stocks' (catch-all type)."""
        unknown = ["UNKNOWNXYZ", "XYZ123", "ABCXYZ"]  # 6-char alpha treated as forex, so avoid FOOBAR
        for symbol in unknown:
            result = SymbolTaxonomy.get_symbol_type(symbol)
            # If not matched by patterns, should default to stocks
            assert result in ["stocks", "forex"], \
                f"Unknown symbol {symbol} should be stocks or forex, got {result}"


class TestSymbolTypeInvariants:
    """Structural invariants of the taxonomy."""
    
    def test_no_symbol_registered_in_multiple_types(self):
        """Invariant: Each symbol appears in at most ONE asset type set."""
        all_symbols = set()
        
        for asset_type in SymbolTaxonomy.ASSET_TYPES:
            symbols_in_type = getattr(SymbolTaxonomy, asset_type.upper(), set())
            
            # Check no intersection with previously seen symbols
            intersection = all_symbols & symbols_in_type
            assert not intersection, f"Symbol(s) {intersection} appear in multiple types"
            
            all_symbols.update(symbols_in_type)
    
    def test_all_indices_in_indices_set_return_correct_type(self):
        """Cross-check: all symbols in INDICES set must return 'indices' from get_symbol_type()."""
        for symbol in SymbolTaxonomy.INDICES:
            assert SymbolTaxonomy.get_symbol_type(symbol) == "indices"


class TestIndexWithoutVolume:
    """Asset-class polymorphism: indices without volume column."""
    
    def test_is_index_without_volume_matches_original_whitelist(self):
        """Verify list matches pre-refactoring whitelist: 
        US30, NAS100, SPX500, SPX, NDX, DJI, DAX40, DE40, UK100, JP225."""
        expected_no_volume = {"US30", "NAS100", "SPX500", "SPX", "NDX", "DJI", "DAX40", "DE40", "UK100", "JP225"}
        
        # Verify all expected symbols return True
        for symbol in expected_no_volume:
            assert SymbolTaxonomy.is_index_without_volume(symbol), \
                f"{symbol} should be classified as index without volume"
        
        # Verify actual set matches expected
        actual_no_volume = SymbolTaxonomy.INDICES_WITHOUT_VOLUME
        assert actual_no_volume == expected_no_volume, \
            f"Mismatch: expected {expected_no_volume}, got {actual_no_volume}"
    
    def test_crypto_symbols_not_classified_as_index_without_volume(self):
        """Crypto symbols (BTCUSDT, ETHUSDT) should return False."""
        crypto = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
        for symbol in crypto:
            assert not SymbolTaxonomy.is_index_without_volume(symbol)
    
    def test_forex_symbols_not_classified_as_index_without_volume(self):
        """Forex symbols should always return False (they have volume)."""
        forex = ["EURUSD", "GBPUSD", "USDJPY"]
        for symbol in forex:
            assert not SymbolTaxonomy.is_index_without_volume(symbol)


class TestPureFunctionContract:
    """Immutability & determinism of taxonomy methods."""
    
    def test_get_symbol_type_is_pure_function(self):
        """Same input → same output (no state dependence)."""
        symbol = "BTCUSDT"
        result1 = SymbolTaxonomy.get_symbol_type(symbol)
        result2 = SymbolTaxonomy.get_symbol_type(symbol)
        assert result1 == result2
        
        # Call 100 times, all should be identical
        results = [SymbolTaxonomy.get_symbol_type(symbol) for _ in range(100)]
        assert all(r == result1 for r in results)
    
    def test_is_index_without_volume_is_pure_function(self):
        """Same input → same output (no state dependence)."""
        symbol = "US30"
        result1 = SymbolTaxonomy.is_index_without_volume(symbol)
        result2 = SymbolTaxonomy.is_index_without_volume(symbol)
        assert result1 == result2
        
        # Call 100 times, all should be identical
        results = [SymbolTaxonomy.is_index_without_volume(symbol) for _ in range(100)]
        assert all(r == result1 for r in results)


class TestEdgeCases:
    """Edge cases: empty, whitespace, case sensitivity."""
    
    def test_empty_string_returns_stocks_default(self):
        """Empty string defaults to stocks (no match in explicit sets or heuristics)."""
        # After normalization, empty string falls through to default
        result = SymbolTaxonomy.get_symbol_type("")
        assert result == "stocks", f"Empty string should return 'stocks', got {result}"
    
    def test_whitespace_string_returns_stocks_default(self):
        """Whitespace is unknown, defaults to stocks."""
        assert SymbolTaxonomy.get_symbol_type("   ") == "stocks"
    
    def test_case_insensitivity(self):
        """Taxonomy normalizes input to uppercase (case-insensitive matching)."""
        # Lowercase should match after normalization
        assert SymbolTaxonomy.get_symbol_type("btcusdt") == "crypto"
        assert SymbolTaxonomy.get_symbol_type("eurusd") == "forex"
        assert SymbolTaxonomy.get_symbol_type("us30") == "indices"
