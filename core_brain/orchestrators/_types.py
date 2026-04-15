"""
Shared dataclasses for orchestrator pipeline.
No imports from main_orchestrator to avoid circular dependencies.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional


@dataclass
class PriceSnapshot:
    """Atomic snapshot of price data with provider traceability.

    Ensures every decision in the pipeline knows:
    - WHAT data was used (df)
    - WHERE it came from (provider_source)
    - WHEN it was captured (timestamp)

    Rule: If MT5 is connected, MT5 is the SSOT for live prices.
    Yahoo is strictly a historical fallback.
    """

    symbol: str
    timeframe: str
    df: Any  # pd.DataFrame
    provider_source: str
    timestamp: datetime = field(default_factory=datetime.now)
    regime: Optional[Any] = None  # MarketRegime


@dataclass
class ScanBundle:
    """Data produced by the scan phase and consumed by subsequent phases."""

    scan_results_with_data: Dict[str, Any]  # full scan data including DataFrames
    price_snapshots: Dict[str, PriceSnapshot]  # keyed by "symbol|timeframe"
    scan_results: Dict[str, Any]  # {symbol: MarketRegime}
    trace_id: str
    # Infra-cause hint: populated when backpressure or timeout forced scan skip.
    # Downstream consumers (signal pipeline, OEM) use this to distinguish
    # infra-caused silence from business-logic silence.
    infra_skip_reason: Optional[str] = None  # e.g. "backpressure_db_latency", "scan_timeout"
