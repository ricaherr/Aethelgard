#!/usr/bin/env python3
"""
Register CONV_STRIKE_0001 Strategy in Database
===============================================

Registers the Trifecta Convergence strategy with affinity scores.
Runs ONCE during alpha phase to populate strategy metadata.

TRACE_ID: SETUP-STRATEGY-CONV-STRIKE-001
"""
import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from data_vault.storage import StorageManager

logging.basicConfig(
    level=logging.INFO,
    format='[%(name)s] %(levelname)s: %(message)s'
)
logger = logging.getLogger(__name__)


def register_trifecta_strategy():
    """Register CONV_STRIKE_0001 with affinity scores."""
    try:
        storage = StorageManager()
        
        # Strategy metadata
        class_id = "CONV_STRIKE_0001"
        mnemonic = "CONV_STRIKE_TRIFECTA"
        version = "1.0"
        
        # Affinity scores from Quanter analysis
        affinity_scores = {
            "EUR/USD": 0.88,  # PRIME - respects SMA 20 after expansions
            "USD/JPY": 0.75,  # MONITOR - acceptable but prone to deep wicks
            "GBP/JPY": 0.45,  # VETO - excessive noise, violations without clean reversions
        }
        
        # Market whitelist (assets where this strategy can execute)
        market_whitelist = list(affinity_scores.keys())
        
        # Description
        description = (
            "S-0002: Trifecta Convergence - Mean reversion within trend. "
            "Detects rejection tails at SMA 20 (M5/M15) with macro confirmation (SMA 200 H1). "
            "Affinity-based execution filtering. Risk: 1% per trade, Ratio: 1:2.5"
        )
        
        # Register strategy (will skip if already exists)
        try:
            result = storage.create_strategy(
                class_id=class_id,
                mnemonic=mnemonic,
                version=version,
                affinity_scores=affinity_scores,
                market_whitelist=market_whitelist,
                description=description
            )
            logger.info(f"✅ Strategy {class_id} registered successfully")
            logger.info(f"   Affinity Scores: {affinity_scores}")
            logger.info(f"   Market Whitelist: {market_whitelist}")
            
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"⚠️  Strategy {class_id} already registered (OK)")
                # Verify existing scores
                existing = storage.get_strategy_affinity_scores(class_id)
                if existing:
                    logger.info(f"   Existing Affinity Scores: {existing}")
            else:
                raise
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to register strategy: {e}", exc_info=True)
        return False


if __name__ == "__main__":
    success = register_trifecta_strategy()
    sys.exit(0 if success else 1)
