"""
Test: POST /instruments endpoint persists changes to DB correctly
=====================================================

Issue: POST endpoint returns success but DB doesn't update.
Fix: Validate json serialization and DB persistence.
"""
import json
import pytest
import sqlite3
from data_vault.storage import StorageManager
from data_vault.default_instruments import DEFAULT_INSTRUMENTS_CONFIG
from core_brain.instrument_manager import InstrumentManager


@pytest.fixture
def storage():
    """Create temp in-memory storage for testing"""
    db = StorageManager(db_path=":memory:")
    return db


def test_update_sys_config_json_serialization(storage):
    """
    Test that update_sys_config correctly json.dumps() the instruments_config dict
    """
    # Get initial state
    initial_state = storage.get_sys_config()
    assert "instruments_config" in initial_state
    
    initial_config = initial_state["instruments_config"]
    assert isinstance(initial_config, dict), "instruments_config should be dict after get_sys_config()"
    
    # Verify METALS/spot is enabled by default
    assert initial_config["METALS"]["spot"]["enabled"] is True
    
    # Simulate what the POST endpoint does: modify and persist
    modified_config = initial_config.copy()
    modified_config["METALS"]["spot"]["enabled"] = False  # Change to disabled
    
    # Persist (same as endpoint does)
    storage.update_sys_config({"instruments_config": modified_config})
    
    # Verify it persisted correctly
    reloaded_state = storage.get_sys_config()
    reloaded_config = reloaded_state["instruments_config"]
    
    assert isinstance(reloaded_config, dict), "Reloaded config should still be dict"
    assert reloaded_config["METALS"]["spot"]["enabled"] is False, "Change should persist in DB"
    print(f"✅ METALS/spot enabled persisted: {reloaded_config['METALS']['spot']['enabled']}")


def test_post_endpoint_simulation_metals_disabled(storage):
    """
    Simulate exact POST endpoint flow for disabling METALS/spot category
    """
    # Get state
    state = storage.get_sys_config()
    instruments_config = state.get("instruments_config")
    assert instruments_config is not None
    
    # Validate structure (same checks as POST endpoint)
    if isinstance(instruments_config, str):
        instruments_config = json.loads(instruments_config)
    assert isinstance(instruments_config, dict)
    
    market = "METALS"
    category = "spot"
    assert market in instruments_config
    assert category in instruments_config[market]
    
    # Prepare data to update (from UI payload)
    data = {
        "description": "Metales spot",
        "instruments": ["XAUUSD", "XAGUSD"],
        "priority": 1,
        "min_score": 75,
        "risk_multiplier": 0.8,
        "enabled": False,  # User disabled it
        "actives": {}
    }
    
    # Update (same as POST endpoint)
    instruments_config[market][category].update(data)
    
    # Persist
    storage.update_sys_config({"instruments_config": instruments_config})
    
    # Reload and verify
    reloaded_state = storage.get_sys_config()
    reloaded_config = reloaded_state["instruments_config"]
    
    assert reloaded_config["METALS"]["spot"]["enabled"] is False
    assert reloaded_config["METALS"]["spot"]["instruments"] == ["XAUUSD", "XAGUSD"]
    print(f"✅ POST simulation persisted correctly: METALS/spot enabled={reloaded_config['METALS']['spot']['enabled']}")


def test_instrument_manager_reflects_disabled_category(storage):
    """
    Verify that InstrumentManager respects disabled categories
    """
    # Initial: METALS should be enabled
    manager = InstrumentManager(storage=storage)
    xau_enabled = manager.is_enabled("XAUUSD")
    assert xau_enabled is True, "XAUUSD should be enabled initially"
    print(f"✅ Initial state: XAUUSD enabled={xau_enabled}")
    
    # Disable METALS/spot
    state = storage.get_sys_config()
    config = state["instruments_config"]
    config["METALS"]["spot"]["enabled"] = False
    storage.update_sys_config({"instruments_config": config})
    
    # CRITICAL: Recreate manager to reload config from DB
    manager2 = InstrumentManager(storage=storage)
    xau_enabled_after = manager2.is_enabled("XAUUSD")
    assert xau_enabled_after is False, "XAUUSD should be disabled after category disabled"
    print(f"✅ After update: XAUUSD enabled={xau_enabled_after}")


def test_get_enabled_symbols_excludes_disabled_category(storage):
    """
    Verify get_enabled_symbols respects category-level enabled flag
    """
    # Initial count
    manager = InstrumentManager(storage=storage)
    enabled_all = manager.get_enabled_symbols()
    metals_count_before = len([s for s in enabled_all if "XAU" in s or "XAG" in s])
    assert metals_count_before == 2, f"Should have 2 metals symbols initially, got {metals_count_before}"
    print(f"✅ Initial metals symbols: {metals_count_before}")
    
    # Disable METALS/spot category
    state = storage.get_sys_config()
    config = state["instruments_config"]
    config["METALS"]["spot"]["enabled"] = False
    storage.update_sys_config({"instruments_config": config})
    
    # Reload and recount
    manager2 = InstrumentManager(storage=storage)
    enabled_all_after = manager2.get_enabled_symbols()
    metals_count_after = len([s for s in enabled_all_after if "XAU" in s or "XAG" in s])
    assert metals_count_after == 0, f"Should have 0 metals symbols after disabling, got {metals_count_after}"
    print(f"✅ After disable: metals symbols={metals_count_after}")


def test_respect_actives_dict_per_symbol(storage):
    """
    Verify that actives dict disables individual symbols while keeping category enabled
    """
    # Setup: FOREX/majors category is enabled, but disable GBPUSD individually
    state = storage.get_sys_config()
    config = state["instruments_config"]
    
    # Enable category but disable GBPUSD in actives
    config["FOREX"]["majors"]["enabled"] = True
    config["FOREX"]["majors"]["actives"]["GBPUSD"] = False
    config["FOREX"]["majors"]["actives"]["EURUSD"] = True
    
    storage.update_sys_config({"instruments_config": config})
    
    # Reload manager
    manager = InstrumentManager(storage=storage)
    
    # EURUSD should be enabled (category enabled + actives allows)
    eurusd_enabled = manager.is_enabled("EURUSD")
    assert eurusd_enabled is True, "EURUSD should be enabled"
    print(f"✅ EURUSD enabled={eurusd_enabled}")
    
    # GBPUSD should be disabled (even though category enabled, actives disables it)
    gbpusd_enabled = manager.is_enabled("GBPUSD")
    assert gbpusd_enabled is False, "GBPUSD should be disabled by actives"
    print(f"✅ GBPUSD enabled={gbpusd_enabled} (disabled via actives)")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
