"""
Market Ops - Pure Normalization Utilities (Neutral Zone)
========================================================

Contains broker-agnostic normalization functions for prices, volumes, and pips.

RULE: This module MUST NOT import anything from core_brain/ or connectors/.
     It is a pure leaf in the dependency tree.

Hierarchy of Normalization:
1. Real broker data (digits, point, volume_step).
2. Technical deduction (digits calculated from point).
3. InstrumentManager classification (agnostic fallback).
4. Safe industry defaults.
"""
import logging
import math
from typing import Any, Optional

logger = logging.getLogger(__name__)


def normalize_price(
    price: float,
    symbol_info: Any = None,
    symbol: str = None,
    instrument_manager: Any = None
) -> float:
    """
    Normalize instrument price with hierarchical fallback.

    Args:
        price: Price to normalize.
        symbol_info: Broker symbol info object (optional).
        symbol: Symbol name (optional, for category fallback).
        instrument_manager: InstrumentManager instance (optional, for fallback).

    Returns:
        float: Price rounded to correct precision.
    """
    if price is None:
        return 0.0

    digits = None

    # Level 1: Direct broker data
    if symbol_info and hasattr(symbol_info, 'digits'):
        digits = symbol_info.digits

    # Level 2: Deduction from point (if digits unavailable)
    if digits is None and symbol_info and hasattr(symbol_info, 'point') and symbol_info.point > 0:
        try:
            digits = round(-math.log10(symbol_info.point))
        except (ValueError, OverflowError):
            pass

    # Level 3: Category fallback (InstrumentManager)
    if digits is None and symbol and instrument_manager:
        digits = instrument_manager.get_default_precision(symbol)

    # Level 4: Safe industry defaults
    if digits is None:
        if symbol:
            symbol_up = symbol.upper()
            if 'JPY' in symbol_up:
                digits = 3
            elif any(m in symbol_up for m in ['XAU', 'XAG', 'GOLD', 'SILVER']):
                digits = 2
            elif len(symbol_up) == 6 or '.X' in symbol_up or '=X' in symbol_up:
                digits = 5
            else:
                digits = 2
        else:
            digits = 5

    return round(float(price), digits)


def normalize_volume(
    volume: float,
    symbol_info: Any
) -> float:
    """
    Normalize lot volume according to broker limits and step.

    Args:
        volume: Suggested volume.
        symbol_info: Broker symbol info object.

    Returns:
        float: Normalized volume clamped within broker limits.
    """
    try:
        if not symbol_info:
            return round(volume, 2)

        min_lot = getattr(symbol_info, 'volume_min', 0.01)
        max_lot = getattr(symbol_info, 'volume_max', 100.0)
        step = getattr(symbol_info, 'volume_step', 0.01)

        # Clamp to min/max range
        normalized = max(min_lot, min(volume, max_lot))

        # Round to nearest step
        if step > 0:
            steps_count = round(normalized / step)
            normalized = steps_count * step

            # Ensure we don't go below min due to rounding
            if normalized < min_lot:
                normalized = min_lot
        else:
            normalized = round(normalized, 2)

        # Final re-clamping for safety
        return round(max(min_lot, min(normalized, max_lot)), 8)

    except Exception as e:
        logger.error(f"Error normalizing volume: {e}")
        return round(volume, 2)


def calculate_pip_size(
    symbol_info: Any = None,
    symbol: str = None,
    instrument_manager: Any = None
) -> float:
    """
    Calculate pip size (minimum relevant price movement unit).
    For Forex: 4th or 2nd decimal (0.0001 or 0.01).
    For others: Uses broker point.
    """
    digits = None
    point = getattr(symbol_info, 'point', 0.0)

    # 1. Get digits
    if symbol_info and hasattr(symbol_info, 'digits'):
        digits = symbol_info.digits
    elif symbol and instrument_manager:
        digits = instrument_manager.get_default_precision(symbol)

    # 2. Pip vs Point logic
    if digits is not None:
        digits = int(digits)
        if digits in [3, 5]:  # Forex with fractional pips (pips = 10 * point)
            if point > 0:
                return point * 10
            return 0.0001 if digits == 5 else 0.01

        if digits in [2, 4]:  # Forex without fractional pips or Indices
            if point > 0:
                return point
            return 0.0001 if digits == 4 else 0.01

    # 3. Final fallback to broker point or standard pips
    if point > 0:
        return point

    # 4. Manual fallback by name (last resort)
    if symbol and 'JPY' in symbol.upper():
        return 0.01
    return 0.0001


def classify_asset_type(symbol: str) -> str:
    """
    Classify a trading symbol into its asset type.

    Args:
        symbol: Trading symbol (e.g., "EURUSD", "XAUUSD", "BTCUSD", "US30").

    Returns:
        str: One of "forex", "metal", "crypto", "index".
    """
    if not symbol:
        return "forex"

    s = symbol.upper()

    if s.startswith("XAU") or s.startswith("XAG"):
        return "metal"
    if s.startswith("BTC") or s.startswith("ETH"):
        return "crypto"
    if any(idx in s for idx in ["US30", "NAS100", "SPX500", "DJ30"]):
        return "index"

    return "forex"


def calculate_r_multiple(current_profit: float, initial_risk: float) -> float:
    """
    Calculate R-multiple (profit expressed as multiples of initial risk).

    Args:
        current_profit: Current P/L in USD.
        initial_risk: Initial risk in USD at entry.

    Returns:
        float: R-multiple rounded to 2 decimals. 0.0 if no risk data.
    """
    if initial_risk <= 0:
        return 0.0
    return round(current_profit / initial_risk, 2)
