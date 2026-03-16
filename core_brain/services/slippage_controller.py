"""
HU 5.2 - Adaptive Slippage Controller
Computes dynamic slippage limits using:
  1. Asset class limits from DB (dynamic_params["slippage_config"])
  2. Market regime multipliers from DB
  3. p90 auto-calibration from execution shadow logs

SSOT: All numeric limits live in dynamic_params (DB).
      market_type must be passed explicitly by the caller (no symbol string matching).
"""
import logging
from decimal import Decimal
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SlippageController:
    """
    Computes adaptive slippage limits per asset class and market regime.

    Config is read from storage.get_dynamic_params()["slippage_config"].
    Falls back to _DEFAULT_CONFIG only during bootstrap (empty DB).

    Dependency Injection: storage must be passed at construction time.
    """

    # Bootstrap fallback only — real config lives in DB (dynamic_params.slippage_config)
    _DEFAULT_CONFIG: Dict[str, Any] = {
        "class_limits": {
            "FOREX_MAJOR": "1.5",
            "FOREX_CROSS": "2.5",
            "INDICES": "3.0",
            "CRYPTO": "5.0",
            "DEFAULT": "2.0",
        },
        "regime_multipliers": {
            "VOLATILE": "1.5",
            "EXPANSION_HIGH": "1.5",
            "RANGING": "0.85",
            "RANGING_STRONG": "0.85",
            "TRENDING": "1.2",
            "EXPANSION": "1.2",
            "DEFAULT": "1.0",
        },
        "p90_min_records": 50,
        "p90_cap_multiplier": "3.0",
    }

    def __init__(self, storage: Any) -> None:
        self.storage = storage
        self._config_cache: Optional[Dict[str, Any]] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def get_limit(
        self,
        symbol: str,
        regime: Optional[str] = None,
        market_type: Optional[str] = None,
    ) -> Decimal:
        """
        Return the adaptive slippage limit for a symbol.

        Args:
            symbol: Trading symbol for p90 history lookup.
            regime: Market regime key (e.g. "VOLATILE", "RANGING"). None → DEFAULT.
            market_type: Asset class key from signal.metadata (e.g. "FOREX_MAJOR").
                         Must be provided by the caller — NOT derived from symbol name.
                         None → DEFAULT limit applies.

        Returns:
            Decimal: Maximum allowed slippage in pips.
        """
        config = self._get_config()

        base_limit = self._resolve_base_limit(config, market_type)
        multiplier = self._resolve_regime_multiplier(config, regime)
        calculated = base_limit * multiplier

        p90_min = int(config.get("p90_min_records", 50))
        cap = base_limit * Decimal(str(config.get("p90_cap_multiplier", "3.0")))

        p90 = self._get_p90_slippage(symbol, p90_min)
        if p90 is not None and p90 > calculated:
            return min(p90, cap)

        return calculated

    # ── Private helpers ────────────────────────────────────────────────────────

    def _get_config(self) -> Dict[str, Any]:
        if self._config_cache is not None:
            return self._config_cache
        try:
            params = self.storage.get_dynamic_params()
            if isinstance(params, dict) and "slippage_config" in params:
                self._config_cache = params["slippage_config"]
                return self._config_cache
        except Exception as exc:
            logger.warning("[SlippageController] Could not load config from DB: %s. Using defaults.", exc)
        return self._DEFAULT_CONFIG

    def _resolve_base_limit(self, config: Dict[str, Any], market_type: Optional[str]) -> Decimal:
        class_limits: Dict[str, str] = config.get(
            "class_limits", self._DEFAULT_CONFIG["class_limits"]
        )
        key = (market_type or "DEFAULT").upper()
        raw = class_limits.get(key, class_limits.get("DEFAULT", "2.0"))
        return Decimal(str(raw))

    def _resolve_regime_multiplier(self, config: Dict[str, Any], regime: Optional[str]) -> Decimal:
        multipliers: Dict[str, str] = config.get(
            "regime_multipliers", self._DEFAULT_CONFIG["regime_multipliers"]
        )
        key = (regime or "DEFAULT").upper()
        raw = multipliers.get(key, multipliers.get("DEFAULT", "1.0"))
        return Decimal(str(raw))

    def _get_p90_slippage(self, symbol: str, min_records: int) -> Optional[Decimal]:
        try:
            return self.storage.get_slippage_p90(symbol, min_records)
        except Exception as exc:
            logger.debug("[SlippageController] p90 lookup failed for %s: %s", symbol, exc)
            return None
