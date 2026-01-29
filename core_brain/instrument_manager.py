"""
Instrument Manager - Gestión de Instrumentos y Configuración Dinámica
=====================================================================

Gestiona la configuración de instrumentos por mercado y categoría.
Provee validación de habilitación, scores mínimos dinámicos y clasificación.

Principios Aplicados:
- Autonomía: Clasificación automática de símbolos
- Flexibilidad: Configuración por categoría (majors/minors/exotics)
- Seguridad: Validación de habilitación antes de operar
- Agnosticismo: Funciona con cualquier símbolo/mercado

Casos de Uso:
1. Validar si un instrumento está habilitado para trading
2. Obtener score mínimo requerido por categoría de instrumento
3. Clasificar símbolos automáticamente (EURUSD -> FOREX/major)
4. Proveer multiplicadores de riesgo por volatilidad
5. Filtrar instrumentos exóticos en horarios volátiles
"""
import json
import logging
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class InstrumentConfig:
    """Configuración de un instrumento o categoría."""
    category: str
    subcategory: str
    enabled: bool
    min_score: float
    risk_multiplier: float
    max_spread: Optional[float] = None
    priority: int = 2
    instruments: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        # instruments ya tiene default_factory, no necesita validación
        pass


class InstrumentManager:
    """
    Gestiona configuración de instrumentos por mercado y categoría.
    
    Features:
    - Auto-clasificación de símbolos (EURUSD -> FOREX/major)
    - Validación de habilitación por categoría
    - Score mínimo dinámico según volatilidad/spread
    - Multiplicadores de riesgo por instrumento
    - Fallback conservador para símbolos desconocidos
    """
    
    def __init__(self, config_path: str = "config/instruments.json"):
        """
        Initialize InstrumentManager.
        
        Args:
            config_path: Path to instruments.json configuration file
        """
        self.config_path = Path(config_path)
        self.config: Dict = {}
        self.symbol_cache: Dict[str, InstrumentConfig] = {}
        
        self._load_config()
        logger.info(
            f"InstrumentManager initialized with {len(self.symbol_cache)} pre-cached symbols"
        )
    
    def _load_config(self) -> None:
        """Load instruments configuration from JSON file."""
        if not self.config_path.exists():
            logger.warning(
                f"Instruments config not found: {self.config_path}. "
                f"Using conservative defaults."
            )
            self.config = self._get_default_config()
            return
        
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            
            # Build cache for all configured instruments
            self._build_symbol_cache()
            
            logger.info(f"Loaded instruments config from {self.config_path}")
            
        except Exception as e:
            logger.error(f"Error loading instruments config: {e}. Using defaults.")
            self.config = self._get_default_config()
    
    def _build_symbol_cache(self) -> None:
        """Build cache of symbol -> InstrumentConfig mappings."""
        for market, categories in self.config.items():
            if market.startswith("_"):  # Skip metadata keys
                continue
            
            for subcategory, settings in categories.items():
                instruments = settings.get("instruments", [])
                
                cfg = InstrumentConfig(
                    category=market,
                    subcategory=subcategory,
                    enabled=settings.get("enabled", False),
                    min_score=settings.get("min_score", 75.0),
                    risk_multiplier=settings.get("risk_multiplier", 1.0),
                    max_spread=settings.get("max_spread_pips") or settings.get("max_spread_bps"),
                    priority=settings.get("priority", 2),
                    instruments=instruments
                )
                
                # Cache each symbol
                for symbol in instruments:
                    self.symbol_cache[symbol.upper()] = cfg
    
    def _get_default_config(self) -> Dict:
        """Return conservative default configuration."""
        return {
            "_global_settings": {
                "default_min_score": 80.0,
                "default_risk_multiplier": 0.8,
                "fallback_behavior": "conservative",
                "unknown_instrument_action": "reject"
            }
        }
    
    def get_config(self, symbol: str) -> Optional[InstrumentConfig]:
        """
        Get configuration for a specific symbol.
        
        Normalizes Yahoo Finance symbols (removes =X suffix) before lookup.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD", "BTCUSDT", "EURUSD=X")
        
        Returns:
            InstrumentConfig if found, None otherwise
        """
        # Normalize Yahoo Finance symbols (EURUSD=X -> EURUSD)
        normalized_symbol = symbol.upper().replace("=X", "")
        
        # Check cache first
        if normalized_symbol in self.symbol_cache:
            return self.symbol_cache[normalized_symbol]
        
        # Try auto-classification
        config = self._auto_classify(normalized_symbol)
        if config:
            self.symbol_cache[normalized_symbol] = config
            return config
        
        logger.warning(f"Symbol {symbol} not found in configuration")
        return None
    
    def _auto_classify(self, symbol: str) -> Optional[InstrumentConfig]:
        """
        Auto-classify symbol based on naming patterns.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            InstrumentConfig if classification succeeds, None otherwise
        """
        # FOREX patterns (currency pairs)
        if len(symbol) == 6 and symbol.isalpha():
            base = symbol[:3]
            quote = symbol[3:]
            
            # Major currencies (including SGD, HKD for broader coverage)
            majors = ["EUR", "USD", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "SGD", "HKD"]
            
            if base in majors and quote in majors:
                # Check if it's a true major pair (involves USD)
                if "USD" in symbol:
                    return self._get_category_config("FOREX", "majors")
                else:
                    return self._get_category_config("FOREX", "minors")
        
        # CRYPTO patterns (ends with USDT, BUSD, etc.)
        crypto_quotes = ["USDT", "BUSD", "USDC", "BTC", "ETH"]
        for quote in crypto_quotes:
            if symbol.endswith(quote):
                base = symbol[:-len(quote)]
                
                # Tier 1 cryptos
                if base in ["BTC", "ETH", "BNB"]:
                    return self._get_category_config("CRYPTO", "tier1")
                else:
                    return self._get_category_config("CRYPTO", "altcoins")
        
        # FUTURES patterns (2-3 letter codes)
        if len(symbol) <= 3 and symbol.isalpha():
            futures = ["ES", "NQ", "YM", "RTY", "CL", "GC", "SI", "NG"]
            if symbol in futures:
                if symbol in ["ES", "NQ", "YM", "RTY"]:
                    return self._get_category_config("FUTURES", "indices")
                else:
                    return self._get_category_config("FUTURES", "commodities")
        
        logger.debug(f"Could not auto-classify symbol: {symbol}")
        return None
    
    def _get_category_config(self, market: str, subcategory: str) -> Optional[InstrumentConfig]:
        """Get configuration for a specific market/subcategory."""
        if market not in self.config:
            return None
        
        if subcategory not in self.config[market]:
            return None
        
        settings = self.config[market][subcategory]
        
        return InstrumentConfig(
            category=market,
            subcategory=subcategory,
            enabled=settings.get("enabled", False),
            min_score=settings.get("min_score", 75.0),
            risk_multiplier=settings.get("risk_multiplier", 1.0),
            max_spread=settings.get("max_spread_pips") or settings.get("max_spread_bps"),
            priority=settings.get("priority", 2),
            instruments=settings.get("instruments", [])
        )
    
    def is_enabled(self, symbol: str) -> bool:
        """
        Check if an instrument is enabled for trading.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            True if enabled, False otherwise
        """
        config = self.get_config(symbol)
        
        if not config:
            # Unknown instrument: check global settings
            global_settings = self.config.get("_global_settings", {})
            action = global_settings.get("unknown_instrument_action", "reject")
            
            if action == "reject":
                logger.warning(f"Unknown instrument {symbol} rejected (default policy)")
                return False
            else:
                logger.warning(f"Unknown instrument {symbol} allowed (permissive policy)")
                return True
        
        return config.enabled
    
    def get_min_score(self, symbol: str) -> float:
        """
        Get minimum required score for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Minimum score threshold (0-100)
        """
        config = self.get_config(symbol)
        
        if not config:
            # Fallback to global default
            global_settings = self.config.get("_global_settings", {})
            default_score = global_settings.get("default_min_score", 80.0)
            
            logger.debug(
                f"Using default min_score {default_score} for unknown symbol {symbol}"
            )
            return default_score
        
        return config.min_score
    
    def get_risk_multiplier(self, symbol: str) -> float:
        """
        Get risk multiplier for position sizing.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Risk multiplier (0.0-1.0)
        """
        config = self.get_config(symbol)
        
        if not config:
            global_settings = self.config.get("_global_settings", {})
            return global_settings.get("default_risk_multiplier", 0.8)
        
        return config.risk_multiplier
    
    def get_max_spread(self, symbol: str) -> Optional[float]:
        """
        Get maximum allowed spread for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Maximum spread in pips/bps, or None if not configured
        """
        config = self.get_config(symbol)
        return config.max_spread if config else None
    
    def get_category_info(self, symbol: str) -> Tuple[str, str]:
        """
        Get market category and subcategory for a symbol.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Tuple of (market, subcategory), e.g., ("FOREX", "majors")
        """
        config = self.get_config(symbol)
        
        if not config:
            return ("UNKNOWN", "UNKNOWN")
        
        return (config.category, config.subcategory)
    
    def validate_symbol(self, symbol: str, score: float) -> Dict:
        """
        Comprehensive validation for a symbol and its score.
        
        Args:
            symbol: Trading symbol
            score: Calculated signal score (0-100)
        
        Returns:
            Dictionary with validation results:
            {
                "valid": bool,
                "enabled": bool,
                "score_passed": bool,
                "min_score_required": float,
                "category": str,
                "subcategory": str,
                "rejection_reason": Optional[str]
            }
        """
        result = {
            "valid": False,
            "enabled": False,
            "score_passed": False,
            "min_score_required": 0.0,
            "category": "UNKNOWN",
            "subcategory": "UNKNOWN",
            "rejection_reason": None
        }
        
        # Check if enabled
        if not self.is_enabled(symbol):
            result["rejection_reason"] = f"Instrument {symbol} is disabled"
            return result
        
        result["enabled"] = True
        
        # Get requirements
        min_score = self.get_min_score(symbol)
        category, subcategory = self.get_category_info(symbol)
        
        result["min_score_required"] = min_score
        result["category"] = category
        result["subcategory"] = subcategory
        
        # Validate score
        if score < min_score:
            result["rejection_reason"] = (
                f"Score {score:.1f} < {min_score:.1f} required for "
                f"{category}/{subcategory}"
            )
            return result
        
        result["score_passed"] = True
        result["valid"] = True
        
        return result
    
    def get_enabled_symbols(self, market: Optional[str] = None) -> List[str]:
        """
        Get list of all enabled symbols, optionally filtered by market.
        
        Args:
            market: Optional market filter (FOREX, CRYPTO, STOCKS, FUTURES)
        
        Returns:
            List of enabled symbol names
        """
        enabled = []
        
        for symbol, config in self.symbol_cache.items():
            if market and config.category != market:
                continue
            
            if config.enabled:
                enabled.append(symbol)
        
        return sorted(enabled)
