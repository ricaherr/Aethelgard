"""
Market Utils - Backward Compatibility Shim
==========================================

All normalization functions have been moved to utils/market_ops.py
(neutral zone, zero imports from core_brain/ or connectors/).

This module re-exports them for backward compatibility during migration.
New code should import directly from utils.market_ops.
"""
from utils.market_ops import normalize_price, normalize_volume, calculate_pip_size  # noqa: F401
from utils.time_utils import to_utc  # noqa: F401
