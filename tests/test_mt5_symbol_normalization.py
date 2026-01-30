"""
Tests for MT5 symbol normalization.
"""
from connectors.mt5_connector import MT5Connector


def test_mt5_normalize_symbol_removes_yahoo_suffix():
    assert MT5Connector.normalize_symbol("USDJPY=X") == "USDJPY"
    assert MT5Connector.normalize_symbol("EURUSD=X") == "EURUSD"


def test_mt5_normalize_symbol_keeps_native():
    assert MT5Connector.normalize_symbol("EURUSD") == "EURUSD"
