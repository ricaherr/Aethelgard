"""
Symbol normalization utilities — provider-agnostic string operations.

These functions have zero broker-specific dependencies and can be used
anywhere in the codebase without importing connector implementations.
"""


def normalize_symbol(symbol: str) -> str:
    """
    Strip provider-specific suffixes from a symbol string.

    Yahoo Finance appends '=X' to forex pairs (e.g. 'USDJPY=X').
    This function removes that suffix so the symbol matches the
    format expected by execution brokers (MT5, cTrader, FIX, etc.).

    Examples:
        USDJPY=X  → USDJPY
        GBPUSD=X  → GBPUSD
        EURUSD    → EURUSD  (no-op)
        AAPL      → AAPL    (no-op)
    """
    if not symbol:
        return symbol
    return symbol.replace("=X", "")
