from enum import Enum
from typing import Optional, Any
from dataclasses import dataclass, field
from datetime import datetime

class ConnectorType(Enum):
    """Define los tipos de conectores o fuentes de datos."""
    WEBHOOK = "WEBHOOK"
    METATRADER5 = "METATRADER5"
    NINJATRADER8 = "NINJATRADER8"
    GENERIC = "GENERIC"

@dataclass
class Signal:
    """Representa una señal de trading generada por un scanner."""
    symbol: str
    signal_type: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float
    # ... otros campos relevantes
    
@dataclass
class SignalResult:
    """Representa el resultado de una operación basada en una señal."""
    signal: Signal
    is_win: bool
    pnl: float
    # ... otros campos

class MarketRegime(Enum):
    """Representa el régimen o estado actual del mercado."""
    BULL = "BULL"
    BEAR = "BEAR"
    RANGE = "RANGE"
    CRASH = "CRASH"
    NORMAL = "NORMAL"