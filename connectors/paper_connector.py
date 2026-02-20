import logging
import uuid
from datetime import datetime
from typing import Dict, Any
from models.signal import Signal

logger = logging.getLogger(__name__)

class PaperConnector:
    """
    Paper Trading Connector for Aethelgard.
    Simulates execution of signals without real broker interaction.
    """
    
    def __init__(self, instrument_manager=None) -> None:
        self.instrument_manager = instrument_manager
        logger.info("PaperConnector initialized (DI InstrumentManager: %s)", bool(instrument_manager))
        
    def connect(self) -> bool:
        """Simulate connection"""
        return True
        
    def execute_signal(self, signal: Signal) -> Dict:
        """
        Simulate signal execution.
        Returns a successful result for any valid signal.
        """
        logger.info(f"Ejecutando simulación (Paper Trading): {signal.symbol} {signal.signal_type} @ {signal.entry_price}")
        
        # Simulate local delay
        import time
        time.sleep(0.5)
        
        ticket = str(uuid.uuid4())[:8].upper()
        
        return {
            "success": True,
            "status": "success",
            "ticket": ticket,
            "order_id": ticket,
            "price": signal.entry_price,
            "timestamp": datetime.now().isoformat(),
            "message": f"Signal executed successfully in paper mode (Ticket: {ticket})"
        }

    def get_closed_positions(self, hours: int = 24) -> list[dict]:
        """Return empty list for paper mode (no real closed positions)."""
        return []
    
    def get_open_positions(self) -> list[dict]:
        """Return empty list for paper mode (no real open positions tracked)."""
        return []
    
    def get_account_balance(self) -> float:
        """Return simulated account balance for paper trading."""
        return 10000.0
    
    def get_symbol_info(self, symbol: str) -> Any:
        """
        Return simulated symbol info for paper trading.
        Uses injected InstrumentManager for precision/config (SSOT).
        """
        from types import SimpleNamespace
        if not self.instrument_manager:
            raise RuntimeError("PaperConnector requiere InstrumentManager inyectado para get_symbol_info (SSOT)")
        digits = self.instrument_manager.get_default_precision(symbol)
        point = 1.0 / (10**digits)
        return SimpleNamespace(
            digits=digits,
            point=point,
            volume_min=0.01,
            volume_max=100.0,
            volume_step=0.01,
            trade_contract_size=100000,
            currency_profit='USD',
            currency_base=symbol[:3] if len(symbol) >= 6 else 'USD'
        )
        
    def close_connections(self) -> None:
        """Cleanup"""
        logger.info("PaperConnector connections closed")
