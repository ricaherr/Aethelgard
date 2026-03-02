"""
Anomaly Data Models
Definiciones de tipos para eventos de anomalía.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Any
import uuid


class AnomalyType(Enum):
    """Tipología de anomalías detectadas."""
    EXTREME_VOLATILITY = "extreme_volatility"  # Z-Score > 3.0
    FLASH_CRASH = "flash_crash"                # Caída > -2% en 1 vela
    VOLUME_SPIKE = "volume_spike"              # Volumen anómalo
    LIQUIDATION_CASCADE = "liquidation_cascade" # Cascada de liquidaciones
    SYSTEMIC_ANOMALY = "systemic_anomaly"      # Anomalía en múltiples timeframes


@dataclass
class AnomalyEvent:
    """Representa un evento de anomalía detectado."""
    symbol: str
    anomaly_type: AnomalyType
    timestamp: datetime
    z_score: float = 0.0
    confidence: float = 0.0
    drop_percentage: float = 0.0
    volume_spike_detected: bool = False
    trace_id: str = field(default_factory=lambda: f"AN-{uuid.uuid4().hex[:8].upper()}")
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa el evento para persistencia."""
        return {
            "symbol": self.symbol,
            "anomaly_type": self.anomaly_type.value,
            "timestamp": self.timestamp.isoformat(),
            "z_score": self.z_score,
            "confidence": self.confidence,
            "drop_percentage": self.drop_percentage,
            "volume_spike_detected": self.volume_spike_detected,
            "trace_id": self.trace_id,
            "details": self.details,
        }
