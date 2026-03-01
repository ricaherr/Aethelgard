import logging
from datetime import datetime
from typing import Dict, Tuple, Any, Optional

import pandas as pd

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


class ConfluenceService:
    """
    Engine for Multi-Market Correlation & Confluence analysis.
    Includes SmT divergence and Predator Sense (liquidity sweep divergence).
    """

    CORRELATION_MAP = {
        "EURUSD": {"inverse": ["DXY", "USDJPY", "USDCAD"], "direct": ["GBPUSD", "AUDUSD"]},
        "GBPUSD": {"inverse": ["DXY"], "direct": ["EURUSD"]},
        "BTCUSD": {"direct": ["ETHUSD", "NDX", "NAS100"]},
        "BTC": {"direct": ["ETH", "NAS100"]},
        "XAUUSD": {"inverse": ["DXY", "USDJPY"], "direct": ["XAGUSD"]},
        "GOLD": {"inverse": ["DXY"], "direct": ["SILVER"]},
    }

    def __init__(self, storage: StorageManager):
        self.storage = storage
        logger.info("ConfluenceService initialized.")

    def _normalize_symbol(self, symbol: str) -> str:
        return (symbol or "").replace("=X", "").replace(".", "").upper()

    def _normalize_ohlcv(self, df: Any) -> pd.DataFrame:
        """Normalize OHLCV columns for robust downstream analytics."""
        if df is None:
            return pd.DataFrame()

        if not isinstance(df, pd.DataFrame):
            return pd.DataFrame()

        if df.empty:
            return pd.DataFrame()

        cols = {str(c).lower(): c for c in df.columns}
        remap = {}
        if "high" in cols:
            remap[cols["high"]] = "high"
        if "low" in cols:
            remap[cols["low"]] = "low"
        if "close" in cols:
            remap[cols["close"]] = "close"
        if "open" in cols:
            remap[cols["open"]] = "open"
        if "volume" in cols:
            remap[cols["volume"]] = "volume"
        if "tick_volume" in cols and "volume" not in remap.values():
            remap[cols["tick_volume"]] = "volume"

        normalized = df.rename(columns=remap)
        required_cols = {"high", "low", "close"}
        if not required_cols.issubset(set(normalized.columns)):
            return pd.DataFrame()
        return normalized

    def _fetch_ohlcv(self, connector: Any, symbol: str, timeframe: str, count: int = 60) -> pd.DataFrame:
        """Fetch OHLCV from a connector with graceful fallback."""
        try:
            raw = None
            if connector is not None and hasattr(connector, "fetch_ohlc"):
                raw = connector.fetch_ohlc(symbol, timeframe, count=count)
            elif connector is not None and hasattr(connector, "get_market_data"):
                raw = connector.get_market_data(symbol, timeframe, count=count)
            return self._normalize_ohlcv(raw)
        except Exception as exc:
            logger.debug("Could not fetch OHLCV for %s: %s", symbol, exc)
            return pd.DataFrame()

    def get_correlation_coefficient(self, data_a: pd.Series, data_b: pd.Series, window: int = 20) -> float:
        """Calculate Pearson correlation coefficient."""
        if len(data_a) < window or len(data_b) < window:
            return 0.0
        try:
            return float(data_a.tail(window).corr(data_b.tail(window)))
        except Exception:
            return 0.0

    def detect_divergence(
        self,
        base_data: pd.DataFrame,
        correlated_data: pd.DataFrame,
        inverse: bool = False
    ) -> Dict[str, Any]:
        """
        Detect SmT-style divergence between two assets.
        """
        base = self._normalize_ohlcv(base_data)
        corr = self._normalize_ohlcv(correlated_data)
        if base.empty or corr.empty or len(base) < 24 or len(corr) < 24:
            return {"divergence": False, "type": "NONE", "confidence": 0.0}

        last_high_a = float(base["high"].iloc[-10:].max())
        prev_high_a = float(base["high"].iloc[-20:-10].max())
        last_high_b = float(corr["high"].iloc[-10:].max())
        prev_high_b = float(corr["high"].iloc[-20:-10].max())

        last_low_a = float(base["low"].iloc[-10:].min())
        prev_low_a = float(base["low"].iloc[-20:-10].min())
        last_low_b = float(corr["low"].iloc[-10:].min())
        prev_low_b = float(corr["low"].iloc[-20:-10].min())

        divergence = False
        div_type = "NONE"
        confidence = 0.0

        if last_low_a < prev_low_a and not (last_low_b < prev_low_b) and not inverse:
            divergence = True
            div_type = "BULLISH_SYMMETRIC"
            confidence = 0.80
        elif last_low_a < prev_low_a and not (last_high_b > prev_high_b) and inverse:
            divergence = True
            div_type = "BULLISH_INVERSE"
            confidence = 0.85
        elif last_high_a > prev_high_a and not (last_high_b > prev_high_b) and not inverse:
            divergence = True
            div_type = "BEARISH_SYMMETRIC"
            confidence = 0.80
        elif last_high_a > prev_high_a and not (last_low_b < prev_low_b) and inverse:
            divergence = True
            div_type = "BEARISH_INVERSE"
            confidence = 0.85

        return {
            "divergence": divergence,
            "type": div_type,
            "confidence": confidence,
            "metrics": {
                "base_ll": last_low_a < prev_low_a,
                "corr_ll": last_low_b < prev_low_b,
                "base_hh": last_high_a > prev_high_a,
                "corr_hh": last_high_b > prev_high_b,
            },
        }

    def detect_predator_divergence(
        self,
        base_data: pd.DataFrame,
        correlated_data: pd.DataFrame,
        inverse: bool = False
    ) -> Dict[str, Any]:
        """
        Predator Sense: detect liquidity sweep in correlated market while base is stagnant.
        Example: DXY sweeps highs while EURUSD stalls -> bullish reversal risk for EURUSD.
        """
        base = self._normalize_ohlcv(base_data)
        corr = self._normalize_ohlcv(correlated_data)
        if base.empty or corr.empty or len(base) < 30 or len(corr) < 30:
            return {
                "detected": False,
                "state": "DORMANT",
                "strength": 0.0,
                "signal_bias": "NEUTRAL",
                "message": "Insufficient data for predator divergence.",
                "metrics": {},
            }

        base_recent = base.iloc[-12:]
        base_prev = base.iloc[-24:-12]
        corr_recent = corr.iloc[-12:]
        corr_prev = corr.iloc[-24:-12]

        base_recent_range = float((base_recent["high"] - base_recent["low"]).mean())
        base_prev_range = float((base_prev["high"] - base_prev["low"]).mean()) or 1e-9
        base_momentum = abs(float(base["close"].iloc[-1] - base["close"].iloc[-12])) / max(
            abs(float(base["close"].iloc[-12])), 1e-9
        )

        stagnation_ratio = 1.0 - min(1.0, base_recent_range / base_prev_range)
        stagnation_confirmed = base_momentum < 0.0015 and base_recent_range <= (base_prev_range * 0.85)

        corr_recent_high = float(corr_recent["high"].max())
        corr_prev_high = float(corr_prev["high"].max()) or 1e-9
        corr_recent_low = float(corr_recent["low"].min())
        corr_prev_low = float(corr_prev["low"].min()) or 1e-9

        sweep_up = corr_recent_high > corr_prev_high * 1.0008
        sweep_down = corr_recent_low < corr_prev_low * 0.9992

        sweep_up_intensity = max(0.0, (corr_recent_high - corr_prev_high) / max(abs(corr_prev_high), 1e-9))
        sweep_down_intensity = max(0.0, (corr_prev_low - corr_recent_low) / max(abs(corr_prev_low), 1e-9))
        sweep_intensity = max(sweep_up_intensity, sweep_down_intensity)

        raw_strength = (stagnation_ratio * 65.0) + min(35.0, sweep_intensity * 10000.0)
        strength = max(0.0, min(100.0, raw_strength))

        signal_bias = "NEUTRAL"
        if inverse and sweep_up:
            signal_bias = "BUY"
        elif inverse and sweep_down:
            signal_bias = "SELL"
        elif not inverse and sweep_up:
            signal_bias = "SELL"
        elif not inverse and sweep_down:
            signal_bias = "BUY"

        detected = bool(stagnation_confirmed and (sweep_up or sweep_down) and strength >= 55.0)
        if strength >= 70.0:
            state = "PREDATOR_ACTIVE"
        elif strength >= 45.0:
            state = "TRACKING"
        else:
            state = "DORMANT"

        message = (
            "Liquidity sweep detected with base stagnation."
            if detected
            else "No decisive inter-market predator pattern."
        )

        return {
            "detected": detected,
            "state": state,
            "strength": round(strength, 2),
            "signal_bias": signal_bias,
            "message": message,
            "metrics": {
                "base_stagnation_ratio": round(stagnation_ratio, 4),
                "base_momentum": round(base_momentum, 6),
                "sweep_up": sweep_up,
                "sweep_down": sweep_down,
                "sweep_intensity": round(sweep_intensity, 6),
            },
        }

    def get_predator_radar(
        self,
        symbol: str,
        timeframe: str = "M5",
        connector: Optional[Any] = None,
        base_ohlcv: Optional[pd.DataFrame] = None,
        correlated_ohlcv: Optional[pd.DataFrame] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Return a normalized Predator Radar snapshot for UI/monitoring.
        trace_id is optional and used for audit logs when present.
        """
        symbol_clean = self._normalize_symbol(symbol)
        correlations = self.CORRELATION_MAP.get(symbol_clean, {})
        inverse_targets = correlations.get("inverse", [])
        direct_targets = correlations.get("direct", [])
        anchor = inverse_targets[0] if inverse_targets else (direct_targets[0] if direct_targets else None)
        is_inverse = bool(anchor and anchor in inverse_targets)

        if not anchor:
            return {
                "symbol": symbol_clean,
                "anchor": None,
                "timeframe": timeframe,
                "detected": False,
                "state": "UNMAPPED",
                "divergence_strength": 0.0,
                "signal_bias": "NEUTRAL",
                "message": "No inter-market correlation mapping for symbol.",
                "timestamp": datetime.now().isoformat(),
                "metrics": {},
            }

        base_df = self._normalize_ohlcv(base_ohlcv) if base_ohlcv is not None else self._fetch_ohlcv(
            connector, symbol, timeframe, count=80
        )
        corr_df = self._normalize_ohlcv(correlated_ohlcv) if correlated_ohlcv is not None else self._fetch_ohlcv(
            connector, anchor, timeframe, count=80
        )

        predator = self.detect_predator_divergence(base_df, corr_df, inverse=is_inverse)
        return {
            "symbol": symbol_clean,
            "anchor": anchor,
            "timeframe": timeframe,
            "inverse_correlation": is_inverse,
            "detected": predator["detected"],
            "state": predator["state"],
            "divergence_strength": predator["strength"],
            "signal_bias": predator["signal_bias"],
            "message": predator["message"],
            "timestamp": datetime.now().isoformat(),
            "metrics": predator["metrics"],
        }

    def validate_confluence(
        self,
        symbol: str,
        side: str,
        connector: Any,
        timeframe: str = "M5",
        trace_id: Optional[str] = None,
    ) -> Tuple[bool, str, float]:
        """
        Main entry point for RiskManager to validate a trade.
        Returns (is_confirmed, reason, confidence_penalty).
        Veto reasons are prefixed with [CONFLUENCE_VETO][Trace_ID: trace_id] when trace_id is set.
        """
        symbol_clean = self._normalize_symbol(symbol)
        correlations = self.CORRELATION_MAP.get(symbol_clean)
        trade_side = (side or "").upper()
        prefix = f"[CONFLUENCE_VETO][Trace_ID: {trace_id}] " if trace_id else ""

        if not correlations:
            return True, "No correlation map for asset, skipping check.", 0.0

        inverse_targets = correlations.get("inverse", [])
        direct_targets = correlations.get("direct", [])
        target_corr = inverse_targets[0] if inverse_targets else (direct_targets[0] if direct_targets else None)
        if not target_corr:
            return True, "No correlated anchor configured, skipping check.", 0.0

        try:
            base_ohlcv = self._fetch_ohlcv(connector, symbol, timeframe, count=80)
            corr_ohlcv = self._fetch_ohlcv(connector, target_corr, timeframe, count=80)

            if base_ohlcv.empty or corr_ohlcv.empty:
                return True, "Insufficient data for correlation check", 0.0

            is_inverse = target_corr in inverse_targets

            predator = self.get_predator_radar(
                symbol=symbol,
                timeframe=timeframe,
                connector=connector,
                base_ohlcv=base_ohlcv,
                correlated_ohlcv=corr_ohlcv,
                trace_id=trace_id,
            )
            if predator["detected"] and predator["divergence_strength"] >= 55.0:
                expected_side = predator["signal_bias"]
                if expected_side in {"BUY", "SELL"} and trade_side != expected_side:
                    msg = (
                        f"PREDATOR_VETO: {symbol_clean} vs {target_corr} "
                        f"shows {predator['state']} ({predator['divergence_strength']:.1f}) "
                        f"favoring {expected_side}."
                    )
                    return False, prefix + msg, 0.20
                if expected_side in {"BUY", "SELL"} and trade_side == expected_side:
                    return (
                        True,
                        (
                            f"PREDATOR_CONFIRM: {symbol_clean} vs {target_corr} "
                            f"{predator['state']} ({predator['divergence_strength']:.1f}) aligned with {trade_side}."
                        ),
                        0.0,
                    )

            div_data = self.detect_divergence(base_ohlcv, corr_ohlcv, inverse=is_inverse)
            if div_data["divergence"]:
                is_bullish_div = "BULLISH" in div_data["type"]
                is_bearish_div = "BEARISH" in div_data["type"]
                if (trade_side == "BUY" and is_bullish_div) or (trade_side == "SELL" and is_bearish_div):
                    return True, f"CONFIRMED: {div_data['type']} divergence detected with {target_corr}", 0.0
                return False, prefix + f"VETO: Divergence {div_data['type']} conflicts with {trade_side} signal", 0.15

            if is_inverse and len(base_ohlcv) >= 10 and len(corr_ohlcv) >= 10:
                base_trend = bool(base_ohlcv["close"].iloc[-1] > base_ohlcv["close"].iloc[-10])
                corr_trend = bool(corr_ohlcv["close"].iloc[-1] > corr_ohlcv["close"].iloc[-10])
                if base_trend == corr_trend:
                    return False, prefix + f"CHOPPY: Alignment failure between {symbol} and {target_corr}", 0.20

            return True, f"Aligned with {target_corr}", 0.0
        except Exception as exc:
            logger.error("Error in confluence validation for %s: %s", symbol, exc)
            return True, f"Check failed: {exc}", 0.0
