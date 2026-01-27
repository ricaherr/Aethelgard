from enum import Enum
from typing import Optional, Any, Dict
from dataclasses import dataclass, field
from datetime import datetime

class ConnectorType(Enum):
    """Define los tipos de conectores o fuentes de datos."""
    WEBHOOK = "WEBHOOK"
    METATRADER5 = "METATRADER5"
    NINJATRADER8 = "NINJATRADER8"
    GENERIC = "GENERIC"

class SignalType(Enum):
    """Define los tipos de señales de trading."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE = "CLOSE"
    MODIFY = "MODIFY"

class MembershipTier(Enum):
    """Define los niveles de membresía de usuarios."""
    FREE = "FREE"
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    ELITE = "ELITE"
    VIP = "VIP"

@dataclass
class Signal:
    """Representa una señal de trading generada por un scanner."""
    symbol: str
    signal_type: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float
    connector_type: ConnectorType  # Tipo de conector a usar
    entry_price: float = 0.0  # Precio de entrada sugerido
    stop_loss: float = 0.0  # Stop loss en precio
    take_profit: float = 0.0  # Take profit en precio
    volume: float = 0.01  # Volumen/tamaño de posición
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Información adicional
    
@dataclass
class SignalResult:
    """Representa el resultado de una operación basada en una señal."""
    signal: Signal
    is_win: bool
    pnl: float
    # ... otros campos

class MarketRegime(Enum):
    """Representa el régimen o estado actual del mercado."""
    TREND = "TREND"
    RANGE = "RANGE"
    VOLATILE = "VOLATILE"
    SHOCK = "SHOCK"
    BULL = "BULL"
    BEAR = "BEAR"
    CRASH = "CRASH"
    NORMAL = "NORMAL"