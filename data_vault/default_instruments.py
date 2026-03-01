"""
Canonical default instruments_config for SSOT.
Used by schema seed, migrations, and InstrumentManager when DB has no config.
NO imports from core_brain or connectors.
"""

from typing import Dict, Any

# Full catalog: FOREX (majors, minors, exotics), CRYPTO, METALS, INDEXES.
# Each category includes description and actives for UI/API compatibility.
DEFAULT_INSTRUMENTS_CONFIG: Dict[str, Any] = {
    "FOREX": {
        "majors": {
            "description": "Pares principales",
            "enabled": True,
            "instruments": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD"],
            "min_score": 70.0,
            "risk_multiplier": 1.0,
            "max_spread_pips": 2.0,
            "priority": 1,
            "actives": {},
        },
        "minors": {
            "description": "Cruces menores",
            "enabled": True,
            "instruments": ["EURGBP", "EURJPY", "GBPJPY", "EURAUD", "EURNZD", "GBPAUD", "AUDNZD", "AUDJPY"],
            "min_score": 75.0,
            "risk_multiplier": 0.9,
            "max_spread_pips": 4.0,
            "priority": 2,
            "actives": {},
        },
        "exotics": {
            "description": "Pares exóticos",
            "enabled": False,
            "instruments": ["USDTRY", "USDZAR", "USDMXN", "USDRUB", "EURTRY", "GBPTRY", "USDBRL", "USDCLP"],
            "min_score": 90.0,
            "risk_multiplier": 0.5,
            "max_spread_pips": 30.0,
            "priority": 3,
            "actives": {},
        },
    },
    "CRYPTO": {
        "tier1": {
            "description": "Tier 1",
            "enabled": True,
            "instruments": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            "min_score": 75.0,
            "risk_multiplier": 0.8,
            "max_spread_bps": 10,
            "priority": 1,
            "actives": {},
        },
        "altcoins": {
            "description": "Altcoins",
            "enabled": False,
            "instruments": ["ADAUSDT", "DOGEUSDT", "SHIBUSDT", "XRPUSDT", "SOLUSDT", "DOTUSDT", "MATICUSDT"],
            "min_score": 85.0,
            "risk_multiplier": 0.5,
            "max_spread_bps": 50,
            "priority": 2,
            "actives": {},
        },
    },
    "METALS": {
        "spot": {
            "description": "Metales spot",
            "enabled": True,
            "instruments": ["XAUUSD", "XAGUSD"],
            "min_score": 75.0,
            "risk_multiplier": 0.8,
            "priority": 1,
            "actives": {},
        },
    },
    "INDEXES": {
        "majors": {
            "description": "Índices principales",
            "enabled": True,
            "instruments": ["US30", "NAS100", "SPX500"],
            "min_score": 75.0,
            "risk_multiplier": 0.8,
            "priority": 1,
            "actives": {},
        },
    },
    "_global_settings": {
        "default_min_score": 80.0,
        "default_risk_multiplier": 0.8,
        "fallback_behavior": "conservative",
        "unknown_instrument_action": "reject",
    },
}
