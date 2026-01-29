from enum import Enum
from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field

class ConnectorType(Enum):
    """Define los tipos de conectores o fuentes de datos."""
    WEBHOOK = "WEBHOOK"
    METATRADER5 = "METATRADER5"
    NINJATRADER8 = "NINJATRADER8"
    GENERIC = "GENERIC"
    PAPER = "PAPER"

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

class Signal(BaseModel):
    """Representa una señal de trading generada por un motor de análisis."""
    symbol: str
    signal_type: SignalType
    confidence: float
    connector_type: ConnectorType
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    volume: float = 0.01
    timestamp: datetime = Field(default_factory=datetime.now)
    strategy_id: Optional[str] = None
    timeframe: Optional[str] = "M5"  # Default to 5-minute timeframe
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def price(self) -> float:
        """Alias para entry_price usado en algunas partes del sistema."""
        return self.entry_price

    @property
    def regime(self) -> Optional[MarketRegime]:
        """Obtiene el régimen de los metadatos si está disponible."""
        regime_val = self.metadata.get("regime")
        if regime_val:
            try:
                if isinstance(regime_val, MarketRegime):
                    return regime_val
                return MarketRegime(regime_val)
            except ValueError:
                return None
        return None

    @regime.setter
    def regime(self, value: MarketRegime):
        """Establece el régimen en los metadatos."""
        if hasattr(value, 'value'):
            self.metadata["regime"] = value.value
        else:
            self.metadata["regime"] = value

class SignalResult(BaseModel):
    """Representa el resultado de una operación basada en una señal."""
    signal: Signal
    is_win: bool
    pnl: float
    # ... otros campos