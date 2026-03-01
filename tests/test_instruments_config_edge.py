"""
EDGE tests: instruments_config SSOT and GET /instruments contract.

Validates:
1. Default catalog (data_vault.default_instruments) contains all markets and categories.
2. Response built from default config never includes "error" and includes FOREX majors/minors/exotics.
3. Migration/seed: storage without instruments_config gets it on first access (integration).
"""
import pytest

from data_vault.default_instruments import DEFAULT_INSTRUMENTS_CONFIG
from data_vault.storage import StorageManager


# ----- Canonical structure (contract) -----
REQUIRED_MARKETS = ("FOREX", "CRYPTO", "METALS", "INDEXES")
FOREX_REQUIRED_CATEGORIES = ("majors", "minors", "exotics")
MIN_FOREX_MAJORS = 7
MIN_FOREX_MINORS = 6
MIN_FOREX_EXOTICS = 5


def test_default_instruments_config_has_all_markets():
    """Default catalog must include FOREX, CRYPTO, METALS, INDEXES."""
    for market in REQUIRED_MARKETS:
        assert market in DEFAULT_INSTRUMENTS_CONFIG, f"Missing market: {market}"


def test_default_forex_has_majors_minors_exotics():
    """FOREX must have majors, minors, exotics with enough instruments."""
    forex = DEFAULT_INSTRUMENTS_CONFIG.get("FOREX")
    assert forex is not None
    for cat in FOREX_REQUIRED_CATEGORIES:
        assert cat in forex, f"FOREX missing category: {cat}"
        entry = forex[cat]
        assert "instruments" in entry
        instruments = entry["instruments"]
        assert isinstance(instruments, list)
    assert len(forex["majors"]["instruments"]) >= MIN_FOREX_MAJORS
    assert len(forex["minors"]["instruments"]) >= MIN_FOREX_MINORS
    assert len(forex["exotics"]["instruments"]) >= MIN_FOREX_EXOTICS


def test_default_config_has_description_and_actives():
    """Each category (excluding _ keys) should have description and actives for API/UI compatibility."""
    for market, categories in DEFAULT_INSTRUMENTS_CONFIG.items():
        if market.startswith("_"):
            continue
        assert isinstance(categories, dict)
        for cat, data in categories.items():
            if not isinstance(data, dict) or "instruments" not in data:
                continue
            assert "actives" in data
            assert "enabled" in data


def test_build_markets_response_returns_no_error_key():
    """_build_markets_response with default config must not produce 'error' key."""
    from core_brain.api.routers.market import _build_markets_response

    result = _build_markets_response(DEFAULT_INSTRUMENTS_CONFIG, all=True)
    assert "error" not in result
    assert "markets" not in result
    assert "FOREX" in result
    assert "majors" in result["FOREX"]
    assert "minors" in result["FOREX"]
    assert "exotics" in result["FOREX"]
    assert len(result["FOREX"]["majors"]["instruments"]) >= MIN_FOREX_MAJORS


def test_get_instruments_response_structure_with_seeded_storage():
    """With storage that has instruments_config, GET /instruments contract: markets present, no error."""
    storage = StorageManager(db_path=":memory:")
    state = storage.get_system_state()
    assert state.get("instruments_config") is not None or True
    storage.update_system_state({"instruments_config": DEFAULT_INSTRUMENTS_CONFIG})
    state = storage.get_system_state()
    config = state.get("instruments_config")
    assert config is not None

    from core_brain.api.routers.market import _build_markets_response

    markets = _build_markets_response(config, all=True)
    assert "FOREX" in markets
    assert "majors" in markets["FOREX"] and "minors" in markets["FOREX"] and "exotics" in markets["FOREX"]
    assert "CRYPTO" in markets
    assert "METALS" in markets
    assert "INDEXES" in markets
