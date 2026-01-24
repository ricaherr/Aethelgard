"""
Modelos de datos para señales de trading y feedback
"""
from enum import Enum
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class ConnectorType(str, Enum):
    """Tipos de conectores soportados"""
    NINJATRADER = "NT"
    METATRADER5 = "MT5"
    TRADINGVIEW = "TV"


class MarketRegime(str, Enum):
    """Regímenes de mercado identificados"""
    TREND = "TREND"
    RANGE = "RANGE"
    CRASH = "CRASH"
    NEUTRAL = "NEUTRAL"


class SignalType(str, Enum):
    """Tipos de señales"""
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    MODIFY = "MODIFY"


class MembershipTier(str, Enum):
    """Niveles de membresía"""
    FREE = "FREE"
    PREMIUM = "PREMIUM"
    ELITE = "ELITE"


class Signal(BaseModel):
    """Modelo de señal de trading recibida"""
    connector: ConnectorType = Field(..., description="Tipo de conector origen")
    symbol: str = Field(..., description="Símbolo del instrumento")
    signal_type: SignalType = Field(..., description="Tipo de señal")
    price: float = Field(..., description="Precio de la señal")
    timestamp: datetime = Field(default_factory=datetime.now, description="Timestamp de la señal")
    volume: Optional[float] = Field(None, description="Volumen/contratos")
    stop_loss: Optional[float] = Field(None, description="Stop loss")
    take_profit: Optional[float] = Field(None, description="Take profit")
    metadata: Optional[dict] = Field(default_factory=dict, description="Metadatos adicionales")
    regime: Optional[MarketRegime] = Field(None, description="Régimen de mercado detectado")
    strategy_id: Optional[str] = Field(None, description="ID de la estrategia que generó la señal")
    
    # Campos de scoring y membresía
    score: Optional[float] = Field(None, ge=0.0, le=100.0, description="Score de oportunidad (0-100)")
    membership_tier: MembershipTier = Field(default=MembershipTier.FREE, description="Nivel mínimo de membresía requerido")
    
    # Indicadores de calidad de señal (Oliver Vélez)
    is_elephant_candle: Optional[bool] = Field(None, description="Es una vela elefante (vela de alto momentum)")
    volume_above_average: Optional[bool] = Field(None, description="Volumen superior al promedio")
    near_sma20: Optional[bool] = Field(None, description="Precio cerca de SMA 20 (zona de rebote)")


class SignalResult(BaseModel):
    """Modelo de resultado de una señal ejecutada"""
    signal_id: int = Field(..., description="ID de la señal original")
    executed: bool = Field(..., description="Si la señal fue ejecutada")
    execution_price: Optional[float] = Field(None, description="Precio de ejecución")
    execution_time: Optional[datetime] = Field(None, description="Timestamp de ejecución")
    pnl: Optional[float] = Field(None, description="Profit and Loss")
    closed_at: Optional[datetime] = Field(None, description="Timestamp de cierre")
    notes: Optional[str] = Field(None, description="Notas adicionales")
    feedback_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Score de feedback 0-1")
