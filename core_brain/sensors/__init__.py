"""
Sensors Module - Market Anomaly Detection & Pattern Recognition

Available Sensors:
- ImbalanceDetector: Fair Value Gap (FVG) detection
- MovingAverageSensor: SMA 20/200 institutional levels
- CandlestickPatternDetector: Rejection tails & hammer patterns
- SessionLiquiditySensor: London session High/Low detection
- FibonacciExtender: Fibonacci extension projections (S-0005 SESS_EXT_0001)
- MarketStructureAnalyzer: HH/HL/LH/LL & Breaker Block detection (S-0006 STRUC_SHIFT_0001)
"""

from .imbalance_detector import ImbalanceDetector
from .moving_average_sensor import MovingAverageSensor
from .candlestick_pattern_detector import CandlestickPatternDetector
from .session_liquidity_sensor import SessionLiquiditySensor
from .fibonacci_extender import FibonacciExtender, initialize_fibonacci_extender
from .market_structure_analyzer import MarketStructureAnalyzer

__all__ = [
    "ImbalanceDetector",
    "MovingAverageSensor",
    "CandlestickPatternDetector",
    "SessionLiquiditySensor",
    "FibonacciExtender",
    "initialize_fibonacci_extender",
    "MarketStructureAnalyzer",
]

