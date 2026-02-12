"""
RiskCalculator - Universal risk calculation for multi-asset trading.

Calculates initial risk (USD) dynamically for ANY instrument:
- Forex (major, cross, JPY pairs)
- Precious metals (XAUUSD, XAGUSD)
- Crypto (BTCUSD, ETHUSD)
- Indices (US30, NAS100, etc.)

Handles:
- Dynamic contract_size from broker (NO hardcoding)
- Currency conversion (direct, inverse, triangulation)
- Fallback to safe defaults if data unavailable

Architecture:
- Agnostic: Works with any connector that provides get_symbol_info() and get_current_price()
- Dependency Injection: Connector passed in __init__
- SSOT: Single Source of Truth for risk calculation
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class RiskCalculator:
    """
    Universal risk calculator for multi-asset trading.
    
    Formula:
        Risk (Quote Currency) = |Entry - SL| × Volume × Contract Size
        Risk (USD) = Risk (Quote Currency) × Conversion Rate to USD
    """
    
    def __init__(self, connector):
        """
        Initialize RiskCalculator with broker connector.
        
        Args:
            connector: Broker connector with methods:
                - get_symbol_info(symbol) -> SymbolInfo with trade_contract_size
                - get_current_price(symbol) -> float (bid price)
        """
        self.connector = connector
        
    def calculate_initial_risk_usd(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        volume: float
    ) -> float:
        """
        Calculate initial risk in USD for a trade.
        
        Args:
            symbol: Trading symbol (EURUSD, XAUUSD, BTCUSD, etc.)
            entry_price: Entry price
            stop_loss: Stop loss price
            volume: Position size in lots
            
        Returns:
            Risk in USD (float). Returns 0.0 if calculation fails.
            
        Examples:
            EURUSD: Entry=1.0800, SL=1.0750, Vol=0.1
                => Risk = (0.0050) * 0.1 * 100,000 = $50 USD
                
            XAUUSD: Entry=2050, SL=2040, Vol=0.1
                => Risk = (10) * 0.1 * 100 = $100 USD
                
            USDJPY: Entry=150.00, SL=149.00, Vol=0.1
                => Risk_JPY = (1.00) * 0.1 * 100,000 = 10,000 JPY
                => Risk_USD = 10,000 / 149.50 ≈ $66.89
        """
        # Validation
        if volume == 0:
            return 0.0
        if entry_price == stop_loss:
            return 0.0
            
        # 1. Get contract size dynamically from broker
        symbol_info = self.connector.get_symbol_info(symbol)
        if not symbol_info:
            logger.warning(f"[RiskCalc] Symbol {symbol} not found - cannot calculate risk")
            return 0.0
            
        contract_size = symbol_info.trade_contract_size
        logger.debug(f"[RiskCalc] {symbol} contract_size={contract_size}")
        
        # 2. Calculate price difference
        price_diff = abs(entry_price - stop_loss)
        
        # 3. Calculate risk in quote currency
        risk_quote_currency = price_diff * volume * contract_size
        logger.debug(
            f"[RiskCalc] {symbol} price_diff={price_diff:.5f}, "
            f"volume={volume}, contract_size={contract_size} => "
            f"risk_quote={risk_quote_currency:.2f}"
        )
        
        # 4. Convert to USD
        risk_usd = self._convert_to_usd(symbol, risk_quote_currency)
        logger.info(
            f"[RiskCalc] {symbol} FINAL RISK: ${risk_usd:.2f} USD "
            f"(Entry={entry_price}, SL={stop_loss}, Vol={volume})"
        )
        
        return risk_usd
    
    def _convert_to_usd(self, symbol: str, risk_quote_currency: float) -> float:
        """
        Convert risk from quote currency to USD.
        
        Cases:
            1. Quote = USD (EURUSD, GBPUSD, XAUUSD) => No conversion
            2. Indices quoted in USD (US30, NAS100, SPX500) => No conversion
            3. Base = USD (USDJPY, USDCAD) => Divide by current rate
            4. Cross pair (EURGBP, EURCHF) => Triangulation via USD pair
        
        Args:
            symbol: Trading symbol
            risk_quote_currency: Risk in quote currency
            
        Returns:
            Risk in USD
        """
        # Case 1: Quote currency IS USD
        if symbol.endswith('USD'):
            logger.debug(f"[RiskCalc] {symbol} quote=USD, no conversion needed")
            return risk_quote_currency
        
        # Case 2: Indices and CFDs quoted in USD (common patterns)
        usd_quoted_symbols = ['US30', 'US100', 'US500', 'NAS100', 'SPX500', 'DJ30']
        if any(symbol.startswith(prefix) for prefix in usd_quoted_symbols):
            logger.debug(f"[RiskCalc] {symbol} is USD-quoted index, no conversion needed")
            return risk_quote_currency
        
        # Case 2: Base currency IS USD (inverse pair)
        if symbol.startswith('USD'):
            # Example: USDJPY, risk in JPY
            # Need to divide by current USD/JPY rate
            current_rate = self.connector.get_current_price(symbol)
            if not current_rate or current_rate == 0:
                logger.warning(f"[RiskCalc] Failed to get current price for {symbol}, cannot convert")
                return 0.0
            
            risk_usd = risk_quote_currency / current_rate
            logger.debug(
                f"[RiskCalc] {symbol} base=USD, risk_quote={risk_quote_currency:.2f}, "
                f"rate={current_rate:.5f} => risk_usd={risk_usd:.2f}"
            )
            return risk_usd
        
        # Case 3: Cross pair (neither base nor quote is USD)
        # Example: EURGBP (quote=GBP), EURCHF (quote=CHF)
        quote_currency = symbol[-3:]  # Last 3 chars
        conversion_rate = self._find_conversion_rate(quote_currency)
        
        if not conversion_rate:
            logger.warning(
                f"[RiskCalc] Could not find conversion rate for {quote_currency} to USD, "
                f"cannot calculate risk for {symbol}"
            )
            return 0.0
        
        risk_usd = risk_quote_currency * conversion_rate
        logger.debug(
            f"[RiskCalc] {symbol} cross pair, quote={quote_currency}, "
            f"risk_quote={risk_quote_currency:.2f}, conversion={conversion_rate:.5f} => "
            f"risk_usd={risk_usd:.2f}"
        )
        return risk_usd
    
    def _find_conversion_rate(self, quote_currency: str) -> Optional[float]:
        """
        Find conversion rate from quote_currency to USD.
        
        Strategy:
            1. Try QUOTE+USD (e.g., GBPUSD for GBP) => multiply
            2. Try USD+QUOTE (e.g., USDCHF for CHF) => divide
            3. Return None if not found
        
        Args:
            quote_currency: 3-letter currency code (GBP, CHF, JPY, etc.)
            
        Returns:
            Conversion rate (float) or None
            
        Examples:
            GBP: GBPUSD = 1.26 => rate = 1.26 (multiply)
            CHF: USDCHF = 0.88 => rate = 1/0.88 = 1.136 (divide)
            JPY: USDJPY = 149.5 => rate = 1/149.5 = 0.0067 (divide)
        """
        # Try direct pair: QUOTE+USD (e.g., GBPUSD)
        direct_pair = f"{quote_currency}USD"
        direct_rate = self.connector.get_current_price(direct_pair)
        if direct_rate and direct_rate > 0:
            logger.debug(f"[RiskCalc] Found {direct_pair}={direct_rate:.5f} (direct)")
            return direct_rate
        
        # Try inverse pair: USD+QUOTE (e.g., USDCHF)
        inverse_pair = f"USD{quote_currency}"
        inverse_rate = self.connector.get_current_price(inverse_pair)
        if inverse_rate and inverse_rate > 0:
            conversion_rate = 1.0 / inverse_rate
            logger.debug(
                f"[RiskCalc] Found {inverse_pair}={inverse_rate:.5f}, "
                f"inverse={conversion_rate:.5f}"
            )
            return conversion_rate
        
        logger.warning(f"[RiskCalc] No conversion pair found for {quote_currency} to USD")
        return None
