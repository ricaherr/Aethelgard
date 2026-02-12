#!/usr/bin/env python
"""
BACKFILL POSITION METADATA - Recuperar metadata desde MT5

PROBLEMA:
- 27 operaciones abiertas NO tienen metadata (abiertas antes de implementación)
- PositionManager necesita metadata para breakeven/trailing stops

SOLUCIÓN:
- Consultar MT5 para obtener datos de posiciones abiertas
- Calcular initial_risk_usd basado en (entry - SL) * volume
- Guardar metadata completa en position_metadata table

METADATA DISPONIBLE EN MT5:
- ticket (position ID)
- symbol
- entry_price (price_open)
- sl, tp
- volume
- open_time
- commission, swap

METADATA CALCULADA:
- initial_risk_usd: (entry - SL) * volume * contract_size * point_value
- entry_regime: NEUTRAL (no tenemos histórico ADX del momento)
- timeframe: D1 (default para posiciones sin timeframe conocido)
"""

import sys
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import MetaTrader5 as mt5
from data_vault.storage import StorageManager
from core_brain.risk_calculator import RiskCalculator


class MT5ConnectorWrapper:
    """
    Lightweight wrapper for MT5 API to work with RiskCalculator.
    Only used in this script - not a full connector.
    """
    def get_symbol_info(self, symbol: str):
        """Get symbol info from MT5"""
        return mt5.symbol_info(symbol)
    
    def get_current_price(self, symbol: str):
        """Get current bid price from MT5"""
        tick = mt5.symbol_info_tick(symbol)
        return tick.bid if tick else None


def connect_mt5() -> bool:
    """Connect to MT5 terminal (existing instance)"""
    # Don't specify path - connect to already running instance
    if not mt5.initialize():
        error = mt5.last_error()
        print(f"[ERROR] MT5 initialization failed: {error}")
        return False
    
    print(f"[OK] MT5 connected: {mt5.terminal_info()._asdict()['company']}")
    return True


def get_open_positions():
    """Get all open positions from MT5"""
    positions = mt5.positions_get()
    
    if positions is None:
        print("[WARN] No positions found or error getting positions")
        return []
    
    print(f"[INFO] Found {len(positions)} open positions")
    return positions


def calculate_initial_risk(position, risk_calculator: RiskCalculator) -> float:
    """
    Calculate initial risk in USD using RiskCalculator (universal, multi-asset).
    
    Args:
        position: MT5 position object
        risk_calculator: RiskCalculator instance
        
    Returns:
        Risk in USD (0.0 if SL not set)
    """
    entry = position.price_open
    sl = position.sl
    volume = position.volume
    symbol = position.symbol
    
    if sl == 0:
        # No SL set - cannot calculate risk reliably
        return 0.0
    
    # Use RiskCalculator for universal calculation
    risk_usd = risk_calculator.calculate_initial_risk_usd(
        symbol=symbol,
        entry_price=entry,
        stop_loss=sl,
        volume=volume
    )
    
    return risk_usd


def backfill_metadata(storage: StorageManager, positions, risk_calculator: RiskCalculator, force: bool = False) -> int:
    """
    Backfill position_metadata table with data from MT5.
    
    Args:
        storage: StorageManager instance
        positions: List of MT5 positions
        risk_calculator: RiskCalculator instance for universal risk calculation
        force: If True, update existing metadata with corrected values
    
    Returns: Number of positions backfilled/updated
    """
    backfilled = 0
    
    for pos in positions:
        ticket = pos.ticket
        
        # Check if metadata already exists (skip only if not forcing)
        existing = storage.get_position_metadata(ticket)
        if existing and not force:
            print(f"[SKIP] Ticket {ticket} already has metadata (use --force to update)")
            continue
        
        # Calculate metadata using RiskCalculator (universal, multi-asset)
        initial_risk = calculate_initial_risk(pos, risk_calculator)
        
        # Build metadata dict
        metadata = {
            'ticket': ticket,
            'symbol': pos.symbol,
            'entry_price': pos.price_open,
            'entry_time': datetime.fromtimestamp(pos.time).isoformat(),
            'sl': pos.sl,
            'tp': pos.tp,
            'volume': pos.volume,
            'initial_risk_usd': initial_risk,
            'entry_regime': 'NEUTRAL',  # Unknown (no historical ADX)
            'timeframe': 'D1',  # Default assumption
            'backfilled': True,  # Mark as backfilled
            'commission': pos.commission if hasattr(pos, 'commission') else 0.0,
            'swap': pos.swap if hasattr(pos, 'swap') else 0.0,
        }
        
        # Save to database (REPLACE INTO - updates if exists)
        success = storage.update_position_metadata(ticket, metadata)
        
        if success:
            action = "Updated" if existing else "Backfilled"
            print(f"[OK] {action} ticket {ticket}: {pos.symbol}, risk=${initial_risk:.2f}")
            backfilled += 1
        else:
            print(f"[ERROR] Failed to backfill ticket {ticket}")
    
    return backfilled


def main():
    """Main backfill process"""
    import sys
    
    # Check for --force flag
    force_update = '--force' in sys.argv
    
    print("\n" + "=" * 80)
    print("[START] BACKFILL POSITION METADATA FROM MT5")
    if force_update:
        print("[MODE] FORCE UPDATE - Will overwrite existing metadata with corrected values")
    print("=" * 80)
    
    # Connect to MT5
    if not connect_mt5():
        print("[CRITICAL] Cannot connect to MT5 - Aborting")
        return 1
    
    try:
        # Get open positions
        positions = get_open_positions()
        
        if not positions:
            print("[INFO] No positions to backfill")
            return 0
        
        # Initialize storage
        storage = StorageManager()
        
        # Initialize RiskCalculator with MT5 wrapper
        mt5_wrapper = MT5ConnectorWrapper()
        risk_calculator = RiskCalculator(mt5_wrapper)
        print("[INFO] RiskCalculator initialized (universal, multi-asset)")
        
        # Backfill metadata (with force flag if specified)
        backfilled = backfill_metadata(storage, positions, risk_calculator, force=force_update)
        
        print("\n" + "=" * 80)
        print(f"[SUMMARY] Backfilled {backfilled}/{len(positions)} positions")
        print("=" * 80)
        
        if backfilled > 0:
            print("\n[NEXT STEPS]:")
            print("1. Verificar metadata guardada:")
            print("   python -c \"from data_vault.storage import StorageManager; s=StorageManager(); print(s.get_position_metadata(TICKET))\"")
            print("\n2. Ejecutar PositionManager:")
            print("   python start.py")
            print("\n3. Observar logs de breakeven/trailing stops")
        
        return 0
        
    finally:
        mt5.shutdown()
        print("\n[OK] MT5 disconnected")


if __name__ == "__main__":
    sys.exit(main())
