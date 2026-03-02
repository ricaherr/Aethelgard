"""
CoherenceService - Coherence Drift Monitoring (HU 6.3)
Detects divergence between Theoretical Performance (Shadow) and Live Execution.

Mission: In milliseconds, determine if market reality is breaking our theory.
"Ejecutor, el sistema ya sabe defenderse del caos externo. Ahora debe aprender
a detectar su propia fatiga interna."

TIMEZONE NOTE: All timestamps are normalized to UTC using utils.time_utils.to_utc().
SQLite doesn't have native DATE type - timestamps are stored as ISO 8601 strings.
Database schema uses DEFAULT CURRENT_TIMESTAMP for automatic UTC normalization.

Trace_ID: COHERENCE-DRIFT-2026-001
Author: Aethelgard AI System
"""
import logging
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional, Tuple
from statistics import mean, stdev

from data_vault.storage import StorageManager
from utils.time_utils import to_utc, to_utc_datetime

logger = logging.getLogger(__name__)


class CoherenceService:
    """
    Real-time Coherence Monitor: Shadow Portfolio vs Live Execution.
    
    Responsibilities:
    1. Compare theoretical Sharpe (from SHADOW logs) vs actual (from LIVE logs)
    2. Detect performance degradation > 15%
    3. Calculate coherence score (0-100%)
    4. Emit VETO when coherence < 80%
    5. Register coherence events for audit trail
    
    Design: Injected StorageManager, no external dependencies beyond stdlib.
    Execution: Async-ready, minimal latency path (~50ms worst-case for calculation).
    """
    
    def __init__(
        self,
        storage: StorageManager,
        min_coherence_threshold: Optional[float] = None,
        max_performance_degradation: Optional[float] = None,
        min_executions_for_analysis: Optional[int] = None,
    ):
        """
        Initialize CoherenceService with dependency injection.
        Thresholds are loaded from system_state (SSOT) if available.
        
        Args:
            storage: StorageManager for data access (dependency injection)
            min_coherence_threshold: Override default from DB (for testing)
            max_performance_degradation: Override default from DB (for testing)
            min_executions_for_analysis: Override default from DB (for testing)
        """
        self.storage = storage
        self.tenant_id = getattr(storage, "tenant_id", "default")
        
        # Load configuration from DB (SSOT - Regla 14)
        self._load_coherence_config()
        
        # Allow test overrides
        if min_coherence_threshold is not None:
            self.min_coherence_threshold = min_coherence_threshold
        if max_performance_degradation is not None:
            self.max_performance_degradation = max_performance_degradation
        if min_executions_for_analysis is not None:
            self.min_executions_for_analysis = min_executions_for_analysis
        
        logger.info(
            f"CoherenceService initialized (SSOT): threshold={self.min_coherence_threshold*100:.0f}%, "
            f"max_degradation={self.max_performance_degradation*100:.0f}%, "
            f"min_executions={self.min_executions_for_analysis}"
        )
    
    def _load_coherence_config(self) -> None:
        """
        Load coherence thresholds from system_state (SSOT).
        Uses sensible defaults if configuration doesn't exist yet.
        """
        try:
            state = self.storage.get_system_state()
            config = state.get("coherence_config", {})
            
            # Load from DB or use defaults
            self.min_coherence_threshold = float(
                config.get("min_coherence_threshold", 0.80)
            )
            self.max_performance_degradation = float(
                config.get("max_performance_degradation", 0.15)
            )
            self.min_executions_for_analysis = int(
                config.get("min_executions_for_analysis", 5)
            )
            
            logger.debug(
                f"Coherence config loaded from DB: "
                f"threshold={self.min_coherence_threshold}, "
                f"max_degradation={self.max_performance_degradation}, "
                f"min_executions={self.min_executions_for_analysis}"
            )
            
        except Exception as e:
            # Fallback to defaults if DB read fails
            logger.warning(f"Failed to load coherence_config from DB, using defaults: {e}")
            self.min_coherence_threshold = 0.80
            self.max_performance_degradation = 0.15
            self.min_executions_for_analysis = 5
    
    def detect_drift(
        self,
        symbol: str,
        window_minutes: int = 60,
        strategy_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detect drift between shadow (theoretical) and live (actual) performance.
        
        Args:
            symbol: Trading symbol (e.g., "EURUSD")
            window_minutes: Look-back window for analysis (default: 60 minutes)
            strategy_id: Optional strategy ID for targeted analysis
        
        Returns:
            Dictionary with:
            - coherence_score: float (0.0-1.0)
            - status: "COHERENT" | "INCOHERENT" | "INSUFFICIENT_DATA" | "MONITORING"
            - veto_new_entries: bool (True if coherence < 80%)
            - theoretical_sharpe: float
            - real_sharpe: float
            - performance_degradation: float (ratio)
            - executions_analyzed: int
            - recovery_trend: bool (optional)
            - reason: str (explanation)
            - timestamp: str (ISO 8601)
        """
        trace_id = f"COH-{uuid.uuid4().hex[:8].upper()}"
        start_time = datetime.now(timezone.utc)
        timestamp_utc = to_utc(start_time)
        
        try:
            # 1. Fetch execution logs within time window
            executions = self._fetch_executions(symbol, window_minutes, strategy_id)
            
            if not executions:
                return {
                    "coherence_score": 0.0,
                    "status": "INSUFFICIENT_DATA",
                    "veto_new_entries": True,
                    "executions_analyzed": 0,
                    "reason": f"No executions found for {symbol} in last {window_minutes} minutes",
                    "timestamp": timestamp_utc,
                    "trace_id": trace_id,
                }
            
            if len(executions) < self.min_executions_for_analysis:
                return {
                    "coherence_score": 0.0,
                    "status": "INSUFFICIENT_DATA",
                    "veto_new_entries": False,  # Don't veto, just monitor
                    "executions_analyzed": len(executions),
                    "reason": f"Insufficient executions ({len(executions)}/{self.min_executions_for_analysis})",
                    "timestamp": timestamp_utc,
                    "trace_id": trace_id,
                }
            
            # 2. Calculate theoretical performance (ideal, zero slippage/latency)
            theoretical_sharpe = self._calculate_theoretical_sharpe()
            
            # 3. Calculate real performance (with slippage & latency)
            real_sharpe = self._calculate_sharpe_ratio(executions)
            
            # 4. Calculate latency metrics
            theoretical_latency, real_latency = self._calculate_latency_metrics(executions)
            
            # 5. Compute coherence score
            coherence_score = self._calculate_coherence_score(
                theoretical_sharpe, real_sharpe, theoretical_latency, real_latency
            )
            
            # 6. Determine performance degradation
            performance_degradation = self._calculate_degradation(theoretical_sharpe, real_sharpe)
            
            # 7. Assess coherence status
            status, veto = self._assess_coherence_status(
                coherence_score, performance_degradation
            )
            
            # 8. Check for recovery trend (if was previously incoherent)
            recovery_trend = self._check_recovery_trend(symbol, executions)
            
            # 9. Register event in audit trail
            self._register_coherence_event(
                symbol=symbol,
                strategy_id=strategy_id,
                status=status,
                coherence_score=coherence_score,
                performance_degradation=performance_degradation,
                trace_id=trace_id,
                details={
                    "theoretical_sharpe": theoretical_sharpe,
                    "real_sharpe": real_sharpe,
                    "executions_analyzed": len(executions),
                    "recovery_trend": recovery_trend,
                }
            )
            
            result = {
                "coherence_score": coherence_score,
                "status": status,
                "veto_new_entries": veto,
                "theoretical_sharpe": theoretical_sharpe,
                "real_sharpe": real_sharpe,
                "performance_degradation": performance_degradation,
                "executions_analyzed": len(executions),
                "theoretical_latency_ms": theoretical_latency,
                "real_latency_ms": real_latency,
                "timestamp": timestamp_utc,
                "trace_id": trace_id,
            }
            
            if recovery_trend:
                result["recovery_trend"] = True
                result["reason"] = "System recovering after drift period"
            else:
                result["reason"] = self._build_reason_string(
                    status, coherence_score, performance_degradation
                )
            
            # Log result
            log_level = logging.WARNING if veto else logging.INFO
            logger.log(
                log_level,
                f"[{trace_id}] Coherence Check: {symbol} | "
                f"Score={coherence_score*100:.1f}% | Status={status} | "
                f"Degradation={performance_degradation*100:.1f}% | Veto={veto}"
            )
            
            return result
            
        except Exception as e:
            logger.exception(
                f"[{trace_id}] Error in detect_drift: {e}"
            )
            return {
                "coherence_score": 0.0,
                "status": "ERROR",
                "veto_new_entries": True,
                "reason": f"Error during drift detection: {str(e)}",
                "timestamp": timestamp_utc,
                "trace_id": trace_id,
            }
    
    def _fetch_executions(
        self,
        symbol: str,
        window_minutes: int,
        strategy_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Fetch execution logs within time window using StorageManager API.
        
        Returns:
            List of execution dictionaries with time-series data
        """
        try:
            # Use StorageManager's method to fetch execution logs
            executions = self.storage.get_execution_shadow_logs_by_symbol_and_window(
                symbol=symbol,
                window_minutes=window_minutes,
                tenant_id=self.tenant_id,
                status_filter="SUCCESS"
            )
            
            # Format results to match expected structure
            formatted = []
            for e in executions:
                formatted.append({
                    "signal_id": e.get("signal_id"),
                    "symbol": e.get("symbol"),
                    "theoretical_price": float(e.get("theoretical_price", 0)),
                    "real_price": float(e.get("real_price", 0)),
                    "slippage_pips": float(e.get("slippage_pips", 0)),
                    "latency_ms": float(e.get("latency_ms", 0)),
                    "status": e.get("status"),
                    "timestamp": e.get("timestamp"),
                })
            
            return formatted
            
        except Exception as e:
            logger.error(f"Error fetching executions for {symbol}: {e}")
            return []
    
    def _calculate_theoretical_sharpe(self) -> float:
        """
        Calculate theoretical Sharpe Ratio (ideal conditions: zero slippage, zero latency).
        
        For perfect execution:
        - Risk-free rate: 0% (conservative)
        - Returns: 1.0% daily (baseline trading expectation)
        - Volatility: 2.0% daily (assumed market volatility)
        
        Sharpe = (1.0% - 0%) / 2.0% = 0.5
        
        This is a baseline; adjust based on strategy characteristics if available.
        """
        return 0.5  # Conservative baseline for theoretical Sharpe
    
    def _calculate_sharpe_ratio(self, executions: List[Dict[str, Any]]) -> float:
        """
        Calculate Sharpe Ratio from actual executions (with slippage/latency cost).
        
        Formula: Sharpe = (Mean Return - Risk-Free Rate) / StdDev(Returns)
        
        Return proxy: -slippage_pips (negative return due to slippage)
        Latency cost: Embedded in slippage estimation
        
        Args:
            executions: List of execution dictionaries
        
        Returns:
            Sharpe Ratio (float >= 0)
        """
        if len(executions) < 2:
            return 0.0
        
        try:
            # Extract slippage (negative return proxy)
            slippages = [e.get("slippage_pips", 0.0) for e in executions]
            
            if not slippages or all(s == 0.0 for s in slippages):
                # Perfect execution (no slippage)
                return 0.5  # Return theoretical
            
            mean_slippage = mean(slippages)
            std_slippage = stdev(slippages) if len(slippages) > 1 else 0.0
            
            # Risk-free rate = 0% (conservative)
            # Return = -mean_slippage (negative due to cost)
            # Volatility = std_slippage
            
            if std_slippage == 0.0:
                # No variance = perfect consistency, but negative returns
                return max(0.0, 0.5 - (mean_slippage / 10.0))
            
            # Sharpe = (Return - RfR) / Vol
            # Return is inverted because slippage is a cost
            sharpe = (0.0 - mean_slippage) / std_slippage
            
            # Cap Sharpe at reasonable range [0, 2.0]
            return max(0.0, min(2.0, sharpe + 0.5))  # Add baseline + dampen
            
        except Exception as e:
            logger.warning(f"Error calculating Sharpe: {e}")
            return 0.0
    
    def _calculate_latency_metrics(self, executions: List[Dict[str, Any]]) -> Tuple[float, float]:
        """
        Calculate latency metrics.
        
        Returns:
            (theoretical_latency_ms, real_latency_ms)
        """
        if not executions:
            return 0.0, 0.0
        
        real_latencies = [e.get("latency_ms", 0.0) for e in executions]
        real_avg = mean(real_latencies) if real_latencies else 0.0
        
        # Theoretical latency: network best-case (5-10ms for institutional)
        theoretical_latency = 5.0
        
        return theoretical_latency, real_avg
    
    def _calculate_coherence_score(
        self,
        theoretical_sharpe: float,
        real_sharpe: float,
        theoretical_latency: float,
        real_latency: float,
    ) -> float:
        """
        Calculate overall coherence score (0.0-1.0).
        
        Coherence = (Performance Coherence × 0.7) + (Latency Coherence × 0.3)
        
        Performance Coherence: How close real Sharpe is to theoretical Sharpe
        Latency Coherence: How close real latency is to theoretical latency
        
        Args:
            theoretical_sharpe: Ideal Sharpe Ratio
            real_sharpe: Actually observed Sharpe Ratio
            theoretical_latency: Target latency (ms)
            real_latency: Observed latency (ms)
        
        Returns:
            Coherence score (0.0 - 1.0)
        """
        # Performance component: ratio of real to theoretical
        if theoretical_sharpe > 0:
            perf_coherence = min(1.0, real_sharpe / theoretical_sharpe)
        else:
            perf_coherence = 1.0 if real_sharpe == 0.0 else 0.5
        
        # Latency component: inverse ratio (lower latency = higher coherence)
        if real_latency == 0.0:
            latency_coherence = 1.0
        else:
            latency_ratio = theoretical_latency / real_latency if real_latency > 0 else 1.0
            latency_coherence = min(1.0, max(0.0, latency_ratio))
        
        # Weighted combination
        coherence = (perf_coherence * 0.7) + (latency_coherence * 0.3)
        
        return max(0.0, min(1.0, coherence))
    
    def _calculate_degradation(self, theoretical: float, real: float) -> float:
        """
        Calculate performance degradation ratio.
        
        Degradation = (Theoretical - Real) / Theoretical
        
        Returns:
            Ratio (0.0 = no degradation, 1.0 = complete loss)
        """
        if theoretical == 0.0:
            return 0.0 if real == 0.0 else 1.0
        
        degradation = (theoretical - real) / theoretical
        return max(0.0, min(1.0, degradation))
    
    def _assess_coherence_status(
        self,
        coherence_score: float,
        degradation: float,
    ) -> Tuple[str, bool]:
        """
        Assess coherence status and determine veto flag.
        
        Returns:
            (status: str, veto_new_entries: bool)
        """
        # Determine status
        if coherence_score >= self.min_coherence_threshold:
            if degradation <= self.max_performance_degradation:
                status = "COHERENT"
                veto = False
            else:
                status = "MONITORING"  # Degraded but above threshold
                veto = False
        else:
            status = "INCOHERENT"
            veto = True  # Block new entries if coherence < 80%
        
        return status, veto
    
    def _check_recovery_trend(self, symbol: str, executions: List[Dict[str, Any]]) -> bool:
        """
        Detect if system is recovering from a drift period.
        
        Logic: If recent executions show improving metrics (decreasing slippage trend),
        return True to signal recovery.
        
        Returns:
            bool: True if recovery trend detected
        """
        if len(executions) < 3:
            return False
        
        try:
            # Recent 3 vs previous 3
            recent = [e.get("slippage_pips", 0.0) for e in executions[-3:]]
            previous = [e.get("slippage_pips", 0.0) for e in executions[-6:-3]] if len(executions) >= 6 else None
            
            if not previous:
                return False
            
            recent_avg = mean(recent)
            previous_avg = mean(previous)
            
            # Recovery if slippage trend is improving
            recovery = recent_avg < previous_avg * 0.9  # 10% improvement
            
            return recovery
            
        except Exception as e:
            logger.warning(f"Error checking recovery trend: {e}")
            return False
    
    def _register_coherence_event(
        self,
        symbol: str,
        strategy_id: Optional[str],
        status: str,
        coherence_score: float,
        performance_degradation: float,
        trace_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Register coherence event in audit trail using StorageManager API.
        
        Args:
            symbol: Trading symbol
            strategy_id: Strategy ID (optional)
            status: Coherence status
            coherence_score: Calculated score (0-1)
            performance_degradation: Degradation ratio (0-1)
            trace_id: Trace ID for audit trail
            details: Additional metadata
        """
        try:
            success = self.storage.register_coherence_event(
                symbol=symbol,
                strategy_id=strategy_id,
                status=status,
                coherence_score=coherence_score,
                performance_degradation=performance_degradation,
                trace_id=trace_id,
                details=details,
            )
            
            if success:
                logger.info(f"[{trace_id}] Coherence event registered: {symbol} {status}")
            else:
                logger.warning(f"[{trace_id}] Failed to register coherence event")
            
        except Exception as e:
            logger.exception(f"Error registering coherence event: {e}")
    
    def _build_reason_string(self, status: str, coherence_score: float, degradation: float) -> str:
        """Build human-readable reason for coherence status."""
        if status == "COHERENT":
            return f"System coherent. Coherence={coherence_score*100:.1f}%, Degradation={degradation*100:.1f}%"
        elif status == "INCOHERENT":
            return (
                f"CRITICAL DRIFT DETECTED: Model coherence below threshold. "
                f"Coherence={coherence_score*100:.1f}% (min 80%), Degradation={degradation*100:.1f}%. "
                f"Blocking new entries to prevent losses on invalid model."
            )
        else:  # MONITORING
            return (
                f"Elevated degradation detected. Coherence={coherence_score*100:.1f}%, "
                f"Degradation={degradation*100:.1f}%. Continuing with caution."
            )
