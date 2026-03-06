"""
Execution Mode, Provider, and Account Type Constants.

SSOT (Single Source of Truth) for all execution mode configurations.
Used by FASE D (Trade Results migration) and execution routing.
"""
from enum import Enum


class ExecutionMode(str, Enum):
    """
    Execution mode for strategies.
    
    - LIVE: Real trading with actual money
    - SHADOW: Paper trading (virtual account, no real execution)
    - QUARANTINE: Strategy disabled (awaiting manual intervention)
    """
    LIVE = "LIVE"
    SHADOW = "SHADOW"
    QUARANTINE = "QUARANTINE"
    
    @classmethod
    def default(cls) -> str:
        """Default execution mode is LIVE for backward compatibility."""
        return cls.LIVE.value


class Provider(str, Enum):
    """
    Data/execution provider platform.
    
    - MT5: MetaTrader5 platform
    - NT: NinjaTrader platform
    - FIX: FIX protocol broker
    - INTERNAL: Internal paper trading engine
    """
    MT5 = "MT5"
    NT = "NT"
    FIX = "FIX"
    INTERNAL = "INTERNAL"
    
    @classmethod
    def default(cls) -> str:
        """Default provider is MT5 for backward compatibility."""
        return cls.MT5.value


class AccountType(str, Enum):
    """
    Account type (real vs demo).
    
    - REAL: Live account with real capital
    - DEMO: Demo account for testing
    """
    REAL = "REAL"
    DEMO = "DEMO"
    
    @classmethod
    def default(cls) -> str:
        """Default account type is REAL for backward compatibility."""
        return cls.REAL.value


# ============================================================================
# CONSTANTS FOR PLATFORM_ID AND BROKER MATCHING (Lowercase)
# ============================================================================
# Used by connectors (mt5_connector.py, etc.) which use lowercase platform IDs

PLATFORM_ID_MT5 = "mt5"
PLATFORM_ID_NT = "nt"
PLATFORM_ID_FIX = "fix"
PLATFORM_ID_INTERNAL = "internal"
PLATFORM_ID_PAPER = "paper"

# Mapping from lowercase platform_id to Provider enum
PLATFORM_ID_TO_PROVIDER = {
    PLATFORM_ID_MT5: Provider.MT5,
    PLATFORM_ID_NT: Provider.NT,
    PLATFORM_ID_FIX: Provider.FIX,
    PLATFORM_ID_INTERNAL: Provider.INTERNAL,
    PLATFORM_ID_PAPER: Provider.INTERNAL,  # Paper trading is INTERNAL provider
}

# Broker name keywords to provider mapping
BROKER_KEYWORDS_TO_PROVIDER = {
    "metatrader": Provider.MT5,
    "mt5": Provider.MT5,
    "meta": Provider.MT5,
    "ninja": Provider.NT,
    "ninjatrader": Provider.NT,
    "fix": Provider.FIX,
    "internal": Provider.INTERNAL,
    "paper": Provider.INTERNAL,
}

# Broker name keywords to account type mapping
BROKER_KEYWORDS_TO_ACCOUNT_TYPE = {
    "demo": AccountType.DEMO,
    "paper": AccountType.DEMO,
    "practice": AccountType.DEMO,
    "test": AccountType.DEMO,
    "real": AccountType.REAL,
    "live": AccountType.REAL,
}
