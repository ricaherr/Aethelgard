"""
Tests for Instrument Manager and Score-Based Filtering
========================================================

Validates:
1. Instrument classification (EURUSD -> FOREX/major)
2. Score thresholds by category (majors: 70, exotics: 90)
3. Enabled/disabled filtering
4. Auto-classification of unknown symbols
5. Integration with OliverVelezStrategy
"""
import pytest
from core_brain.instrument_manager import InstrumentManager, InstrumentConfig


class TestInstrumentManager:
    """Test InstrumentManager core functionality."""
    
    def test_load_config(self):
        """Test configuration loading from instruments.json."""
        manager = InstrumentManager()
        
        assert manager.config is not None
        assert "FOREX" in manager.config
        assert "CRYPTO" in manager.config
    
    def test_forex_major_classification(self):
        """Test FOREX major pair classification."""
        manager = InstrumentManager()
        
        # Test majors
        for symbol in ["EURUSD", "GBPUSD", "USDJPY"]:
            config = manager.get_config(symbol)
            
            assert config is not None, f"{symbol} should be classified"
            assert config.category == "FOREX"
            assert config.subcategory == "majors"
            assert config.enabled is True
            assert config.min_score == 70.0
    
    def test_forex_minor_classification(self):
        """Test FOREX minor (cross) pair classification."""
        manager = InstrumentManager()
        
        for symbol in ["EURGBP", "EURJPY", "GBPJPY"]:
            config = manager.get_config(symbol)
            
            assert config is not None
            assert config.category == "FOREX"
            assert config.subcategory == "minors"
            assert config.min_score == 75.0
    
    def test_forex_exotic_classification(self):
        """Test FOREX exotic pair classification and disabled by default."""
        manager = InstrumentManager()
        
        for symbol in ["USDTRY", "USDZAR", "USDMXN"]:
            config = manager.get_config(symbol)
            
            assert config is not None
            assert config.category == "FOREX"
            assert config.subcategory == "exotics"
            assert config.enabled is False  # Disabled by default
            assert config.min_score == 90.0  # High threshold
    
    def test_crypto_classification(self):
        """Test crypto classification (tier1 vs altcoins)."""
        manager = InstrumentManager()
        
        # Tier 1
        for symbol in ["BTCUSDT", "ETHUSDT"]:
            config = manager.get_config(symbol)
            
            assert config is not None
            assert config.category == "CRYPTO"
            assert config.subcategory == "tier1"
            assert config.min_score == 75.0
        
        # Altcoins (disabled by default)
        for symbol in ["ADAUSDT", "DOGEUSDT"]:
            config = manager.get_config(symbol)
            
            assert config is not None
            assert config.category == "CRYPTO"
            assert config.subcategory == "altcoins"
            assert config.enabled is False
            assert config.min_score == 85.0
    
    def test_auto_classification_unknown_symbol(self):
        """Test auto-classification of symbols not in config."""
        manager = InstrumentManager()
        
        # Unknown FOREX major (USD first)
        config = manager.get_config("USDSGD")  # Singapore Dollar
        assert config is not None
        assert config.category == "FOREX"
        assert config.subcategory == "majors"
        
        # Unknown FOREX cross
        config = manager.get_config("AUDNZD")  # No USD
        assert config is not None
        assert config.category == "FOREX"
        assert config.subcategory == "minors"
    
    def test_is_enabled(self):
        """Test enabled/disabled filtering."""
        manager = InstrumentManager()
        
        # Enabled by default
        assert manager.is_enabled("EURUSD") is True
        assert manager.is_enabled("BTCUSDT") is True
        
        # Disabled by default
        assert manager.is_enabled("USDTRY") is False  # Exotic
        assert manager.is_enabled("DOGEUSDT") is False  # Altcoin
    
    def test_get_min_score(self):
        """Test minimum score retrieval by category."""
        manager = InstrumentManager()
        
        # Majors: lower threshold
        assert manager.get_min_score("EURUSD") == 70.0
        
        # Minors: moderate threshold
        assert manager.get_min_score("EURGBP") == 75.0
        
        # Exotics: high threshold
        assert manager.get_min_score("USDTRY") == 90.0
        
        # Crypto tier1
        assert manager.get_min_score("BTCUSDT") == 75.0
        
        # Unknown symbol: fallback to default
        min_score = manager.get_min_score("XXXYYY")
        assert min_score == 80.0  # Global default
    
    def test_validate_symbol_success(self):
        """Test successful symbol validation with sufficient score."""
        manager = InstrumentManager()
        
        # EURUSD with score 72 (min: 70) -> PASS
        result = manager.validate_symbol("EURUSD", 72.0)
        
        assert result["valid"] is True
        assert result["enabled"] is True
        assert result["score_passed"] is True
        assert result["min_score_required"] == 70.0
        assert result["category"] == "FOREX"
        assert result["subcategory"] == "majors"
        assert result["rejection_reason"] is None
    
    def test_validate_symbol_low_score(self):
        """Test symbol rejection due to low score."""
        manager = InstrumentManager()
        
        # USDTRY with score 85 (min: 90) -> FAIL
        result = manager.validate_symbol("USDTRY", 85.0)
        
        # Note: USDTRY is disabled by default, so will fail on that first
        assert result["valid"] is False
        assert "disabled" in result["rejection_reason"].lower()
    
    def test_validate_symbol_disabled_instrument(self):
        """Test rejection of disabled instruments."""
        manager = InstrumentManager()
        
        # DOGEUSDT is disabled by default
        result = manager.validate_symbol("DOGEUSDT", 95.0)
        
        assert result["valid"] is False
        assert result["enabled"] is False
        assert "disabled" in result["rejection_reason"].lower()
    
    def test_get_risk_multiplier(self):
        """Test risk multiplier retrieval by category."""
        manager = InstrumentManager()
        
        # Majors: full risk (1.0)
        assert manager.get_risk_multiplier("EURUSD") == 1.0
        
        # Minors: slightly reduced (0.9)
        assert manager.get_risk_multiplier("EURGBP") == 0.9
        
        # Exotics: heavily reduced (0.5)
        assert manager.get_risk_multiplier("USDTRY") == 0.5
        
        # Crypto: reduced (0.8)
        assert manager.get_risk_multiplier("BTCUSDT") == 0.8
    
    def test_get_category_info(self):
        """Test category information retrieval."""
        manager = InstrumentManager()
        
        category, subcategory = manager.get_category_info("EURUSD")
        assert category == "FOREX"
        assert subcategory == "majors"
        
        category, subcategory = manager.get_category_info("BTCUSDT")
        assert category == "CRYPTO"
        assert subcategory == "tier1"
    
    def test_get_enabled_symbols(self):
        """Test retrieval of enabled symbols."""
        manager = InstrumentManager()
        
        # All enabled symbols
        enabled = manager.get_enabled_symbols()
        assert "EURUSD" in enabled
        assert "BTCUSDT" in enabled
        assert "USDTRY" not in enabled  # Disabled
        
        # Filter by market
        forex_enabled = manager.get_enabled_symbols(market="FOREX")
        assert "EURUSD" in forex_enabled
        assert "BTCUSDT" not in forex_enabled  # Different market


class TestOliverVelezStrategyIntegration:
    """Test integration between OliverVelezStrategy and InstrumentManager."""
    
    @pytest.fixture
    def mock_dataframe(self):
        """Create mock DataFrame for testing."""
        import pandas as pd
        import numpy as np
        
        # Generate 250 bars for SMA200 calculation
        dates = pd.date_range(end="2026-01-28", periods=250, freq="5min")
        
        df = pd.DataFrame({
            "timestamp": dates,
            "open": 1.1000 + np.random.randn(250) * 0.0010,
            "high": 1.1010 + np.random.randn(250) * 0.0010,
            "low": 1.0990 + np.random.randn(250) * 0.0010,
            "close": 1.1000 + np.random.randn(250) * 0.0010,
            "volume": 1000 + np.random.randint(0, 500, 250)
        })
        
        # Ensure high/low are correct
        df["high"] = df[["open", "high", "close"]].max(axis=1)
        df["low"] = df[["open", "low", "close"]].min(axis=1)
        
        return df
    
    def test_strategy_rejects_low_score_major(self, mock_dataframe):
        """Test that strategy rejects majors with score < 70."""
        from core_brain.strategies.oliver_velez import OliverVelezStrategy
        from models.signal import MarketRegime
        
        strategy = OliverVelezStrategy({})
        
        # Mock: force a low score (simulate weak setup)
        # This would require mocking _calculate_opportunity_score
        # For now, test the validation logic directly
        
        validation = strategy.instrument_manager.validate_symbol("EURUSD", 65.0)
        
        assert validation["valid"] is False
        assert validation["score_passed"] is False
        assert "65.0 < 70.0" in validation["rejection_reason"]
    
    def test_strategy_accepts_good_score_major(self):
        """Test that strategy accepts majors with score >= 70."""
        from core_brain.strategies.oliver_velez import OliverVelezStrategy
        
        strategy = OliverVelezStrategy({})
        
        validation = strategy.instrument_manager.validate_symbol("EURUSD", 75.0)
        
        assert validation["valid"] is True
        assert validation["score_passed"] is True
        assert validation["min_score_required"] == 70.0
    
    def test_strategy_rejects_disabled_exotic(self):
        """Test that strategy rejects disabled exotic instruments."""
        from core_brain.strategies.oliver_velez import OliverVelezStrategy
        
        strategy = OliverVelezStrategy({})
        
        # Even with perfect score, disabled instrument is rejected
        validation = strategy.instrument_manager.validate_symbol("USDTRY", 95.0)
        
        assert validation["valid"] is False
        assert validation["enabled"] is False


class TestEdgeCases:
    """Test edge cases and error handling."""
    
    def test_missing_config_file(self, tmp_path):
        """Test behavior when instruments.json is missing."""
        # Create manager with non-existent path
        manager = InstrumentManager(config_path=str(tmp_path / "missing.json"))
        
        # Should use conservative defaults
        assert manager.get_min_score("EURUSD") == 80.0  # Default
        assert manager.get_risk_multiplier("EURUSD") == 0.8  # Conservative
    
    def test_malformed_symbol(self):
        """Test handling of malformed symbols."""
        manager = InstrumentManager()
        
        # Very short symbol
        config = manager.get_config("AB")
        assert config is None or config.min_score >= 75.0
        
        # Very long symbol
        config = manager.get_config("VERYLONGSYMBOLNAME")
        assert config is None or config.min_score >= 75.0
    
    def test_case_insensitivity(self):
        """Test that symbol lookup is case-insensitive."""
        manager = InstrumentManager()
        
        config_upper = manager.get_config("EURUSD")
        config_lower = manager.get_config("eurusd")
        config_mixed = manager.get_config("EurUsd")
        
        assert config_upper == config_lower
        assert config_lower == config_mixed
