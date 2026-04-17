from enum import Enum
from typing import Optional, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field

# Flag que identifica señales generadas bajo modo de exploración adaptativa (solo DEMO).
EXPLORATION_ON: str = "exploration_mode"

class ConnectorType(Enum):
    """Define los tipos de conectores o fuentes de datos."""
    WEBHOOK = "WEBHOOK"
    METATRADER5 = "METATRADER5"
    NINJATRADER8 = "NINJATRADER8"
    GENERIC = "GENERIC"
    PAPER = "PAPER"
    FIX = "FIX"

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

class ReviewStatus(Enum):
    """Estados de review para señales de grado B/C (DISC-001: Signal Review Queue)."""
    NONE = "NONE"  # Señal no requiere review (A+/A grades)
    PENDING = "PENDING"  # Esperando aprobación del trader
    APPROVED = "APPROVED"  # Trader aprobó → ejecutada
    REJECTED = "REJECTED"  # Trader rechazó → archivada
    AUTO_EXECUTED = "AUTO_EXECUTED"  # Timeout 5 min, ejecutada automáticamente

class Signal(BaseModel):
    """
    Representa una señal de trading generada por un motor de análisis.
    
    Incluye trazabilidad completa para soportar:
    - Múltiples cuentas (DEMO y REAL)
    - Múltiples plataformas (MT5, NT8, Binance, etc.)
    - Múltiples mercados (Forex, Crypto, Stocks)
    """
    # Core signal data
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
    
    # Pipeline tracking
    trace_id: Optional[str] = None  # Unique ID for pipeline tracking
    status: Optional[str] = None    # Status in pipeline: None, 'VETADO', 'APROBADO', etc.
    
    # Traceability fields (WHERE was this executed?)
    account_id: Optional[str] = None        # UUID de cuenta en DB (foreign key)
    account_type: Optional[str] = "DEMO"    # DEMO o REAL
    market_type: Optional[str] = "FOREX"    # FOREX, CRYPTO, STOCKS, FUTURES
    platform: Optional[str] = None          # MT5, NT8, BINANCE, PAPER, etc.
    order_id: Optional[str] = None          # ID de orden del broker (si ejecutada)
    provider_source: Optional[str] = None   # ID del proveedor de datos (ej: MT5, YAHOO)
    
    # Metadata adicional
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
    def regime(self, value: MarketRegime) -> None:
        """Establece el régimen en los metadatos."""
        if hasattr(value, 'value'):
            self.metadata["regime"] = value.value
        else:
            self.metadata["regime"] = value

class FractalContext(BaseModel):
    """
    Contexto de alineación multi-temporal (Fractal Unification).
    Encapsula el estado de sincronización entre M15, H1 y H4.
    """
    m15_regime: MarketRegime = MarketRegime.NORMAL
    h1_regime: MarketRegime = MarketRegime.NORMAL
    h4_regime: MarketRegime = MarketRegime.NORMAL
    
    # Veto Fractal: Si H4=BEAR Y M15=BULL → RETRACEMENT_RISK
    veto_signal: Optional[str] = None  # "RETRACEMENT_RISK", "ALIGNED", None
    confidence_threshold: float = 0.75  # Umbral default (eleva a 0.90 si veto=RETRACEMENT_RISK)
    
    # Metadata
    timestamp: datetime = Field(default_factory=datetime.now)
    trace_id: Optional[str] = None
    
    @property
    def is_fractally_aligned(self) -> bool:
        """Retorna True si todas las temporalidades tienen el mismo sesgo."""
        regimes = [self.m15_regime, self.h1_regime, self.h4_regime]
        return len(set(regimes)) == 1
    
    @property
    def alignment_score(self) -> float:
        """Puntaje de alineación (0.0 = ninguna, 1.0 = perfecta)."""
        regimes = [self.m15_regime, self.h1_regime, self.h4_regime]
        from collections import Counter
        counts = Counter(regimes)
        max_count = max(counts.values())
        return max_count / len(regimes)


class SignalResult(BaseModel):
    """Representa el resultado de una operación basada en una señal."""
    signal: Signal
    is_win: bool
    pnl: float
    # ... otros campos