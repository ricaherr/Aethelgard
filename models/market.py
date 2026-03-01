"""
Pydantic models for market/analysis API responses.
"""
from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class PredatorRadarMetrics(BaseModel):
    """Metrics sub-object for predator divergence."""
    model_config = ConfigDict(extra="allow")
    base_stagnation_ratio: Optional[float] = None
    base_momentum: Optional[float] = None
    sweep_up: Optional[bool] = None
    sweep_down: Optional[bool] = None
    sweep_intensity: Optional[float] = None


class PredatorRadarResponse(BaseModel):
    """Response schema for GET /api/analysis/predator-radar (HU 2.2)."""
    model_config = ConfigDict(extra="allow")
    symbol: str
    anchor: Optional[str] = None
    timeframe: str = "M5"
    inverse_correlation: bool = False
    detected: bool = False
    state: str = "DORMANT"
    divergence_strength: float = 0.0
    signal_bias: str = "NEUTRAL"
    message: str = ""
    timestamp: str = ""
    metrics: Dict[str, Any] = Field(default_factory=dict)
