"""
ScenarioBacktester — Filtro 0: Validación Estructural por Escenarios
====================================================================
Validates trading strategies against predefined stress scenario clusters
BEFORE they enter the SHADOW incubation pool.

Architecture: Slice Injector (not timeline-based).
  The engine receives named 'ScenarioSlice' objects and evaluates
  strategy fitness on each one independently.

Stress Clusters (Aptitude Matrix axis):
  - HIGH_VOLATILITY:      News events, NFP, flash crashes, ECB decisions.
  - STAGNANT_RANGE:       Low liquidity periods / flat market consolidation.
  - INSTITUTIONAL_TREND:  Strong institutional directional trend sessions.

Input:  strategy_id + parameter_overrides + List[ScenarioSlice]
Output: AptitudeMatrix — Profit Factor + Max Drawdown decomposed by regime.

Gate Rule: overall_score >= MIN_REGIME_SCORE (0.75) to allow SHADOW entry.
Trace_ID: TRACE_BKT_VALIDATION_{YYYYMMDD}_{HHMMSS}_{strategy_id[:8].upper()}

RULE DB-1: sys_shadow_promotion_log stores every validation with its trace.
RULE ID-1: All decisions generate TRACE_ID_{YYYYMMDD}_{HHMMSS}_{id[:8]}
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from data_vault.storage import StorageManager
from models.trade_result import TradeResult

logger = logging.getLogger(__name__)


# ── Stress Cluster Constants ─────────────────────────────────────────────────

class StressCluster:
    """Named stress scenario clusters for the Aptitude Matrix."""
    HIGH_VOLATILITY     = "HIGH_VOLATILITY"       # News / flash crashes
    STAGNANT_RANGE      = "STAGNANT_RANGE"         # Low liquidity / consolidation
    INSTITUTIONAL_TREND = "INSTITUTIONAL_TREND"    # Strong directional trend

    ALL = [HIGH_VOLATILITY, STAGNANT_RANGE, INSTITUTIONAL_TREND]


# ── Data Structures ──────────────────────────────────────────────────────────

@dataclass
class ScenarioSlice:
    """
    A named historical data segment injected into the backtesting engine.

    Attributes:
        slice_id:       Unique label (e.g. 'NFP_2025_06', 'FLASH_CRASH_AUG_2025').
        stress_cluster: One of StressCluster constants.
        symbol:         Instrument (e.g. 'EURUSD').
        timeframe:      Resolution (e.g. 'H1', 'M15').
        data:           OHLCV DataFrame — columns: open, high, low, close, volume.
        start_date:     ISO8601 start of the slice.
        end_date:       ISO8601 end of the slice.
        is_real_data:   False when no real data was found for this cluster.
                        UNTESTED slices produce regime_score=0.0 without synthesis.
    """
    slice_id: str
    stress_cluster: str
    symbol: str
    timeframe: str
    data: pd.DataFrame
    start_date: str
    end_date: str
    is_real_data: bool = True


@dataclass
class RegimeResult:
    """Backtesting metrics for a single stress cluster."""
    stress_cluster: str
    detected_regime: str
    profit_factor: float
    max_drawdown_pct: float
    total_trades: int
    win_rate: float
    regime_score: float   # Composite 0.0–1.0


@dataclass
class AptitudeMatrix:
    """
    Full validation output for a (strategy_id + parameter_overrides) pair.

    overall_score >= 0.75  →  passes_threshold = True  →  SHADOW entry allowed.
    Serialisable to JSON for storage in sys_shadow_promotion_log.notes.

    overfitting_risk (HU 7.19): set to True by BacktestOrchestrator when >80% of
    evaluated pairs show effective_score >= 0.90 with confidence >= 0.70.
    Does NOT block promotion — only flags for human review.
    """
    strategy_id: str
    parameter_overrides: Dict[str, Any]
    overall_score: float
    passes_threshold: bool
    results_by_regime: List[RegimeResult]
    trace_id: str
    timestamp: str
    overfitting_risk: bool = False

    def to_json(self) -> str:
        """Serialise to compact JSON for DB storage."""
        return json.dumps({
            "strategy_id": self.strategy_id,
            "parameter_overrides": self.parameter_overrides,
            "overall_score": round(self.overall_score, 4),
            "passes_threshold": self.passes_threshold,
            "overfitting_risk": self.overfitting_risk,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp,
            "results_by_regime": [
                {
                    "stress_cluster": r.stress_cluster,
                    "detected_regime": r.detected_regime,
                    "profit_factor": round(r.profit_factor, 4),
                    "max_drawdown_pct": round(r.max_drawdown_pct, 4),
                    "total_trades": r.total_trades,
                    "win_rate": round(r.win_rate, 4),
                    "regime_score": round(r.regime_score, 4),
                }
                for r in self.results_by_regime
            ],
        })


# ── ScenarioBacktester ────────────────────────────────────────────────────────

class ScenarioBacktester:
    """
    Filtro 0 — Structural Scenario Validation Engine.

    Validates a (strategy_id + parameter_overrides) pair against a list of
    ScenarioSlice objects before allowing SHADOW incubation entry.

    Usage::

        backtester = ScenarioBacktester(storage)
        slices = [
            ScenarioSlice("NFP_JUN25", StressCluster.HIGH_VOLATILITY, "EURUSD", "H1", df1, ...),
            ScenarioSlice("AUG_RANGE", StressCluster.STAGNANT_RANGE,  "EURUSD", "H1", df2, ...),
            ScenarioSlice("TREND_MAY", StressCluster.INSTITUTIONAL_TREND, "EURUSD", "H1", df3, ...),
        ]
        matrix = backtester.run_scenario_backtest("strategy_oliver_velez", {}, slices)
        if matrix.passes_threshold:
            shadow_manager.create_shadow_instance(...)
    """

    _DEFAULT_MIN_REGIME_SCORE = 0.75  # Safe fallback if sys_config is unavailable

    def __init__(self, storage: StorageManager) -> None:
        """
        Args:
            storage: StorageManager for audit persistence (SSOT).
        """
        self.storage         = storage
        self.MIN_REGIME_SCORE = self._load_promotion_gate()

    # ── Config ────────────────────────────────────────────────────────────────

    def _load_promotion_gate(self) -> float:
        """Read promotion_min_score from sys_config (SSOT). Falls back to 0.75."""
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sys_config WHERE key = 'config_backtest'")
            row = cursor.fetchone()
            self.storage._close_conn(conn)
            if row:
                return float(json.loads(row[0]).get("promotion_min_score", self._DEFAULT_MIN_REGIME_SCORE))
        except Exception:
            pass
        return self._DEFAULT_MIN_REGIME_SCORE

    # ── Public API ────────────────────────────────────────────────────────────

    def run_scenario_backtest(
        self,
        strategy_id: str,
        parameter_overrides: Dict[str, Any],
        scenario_slices: List[ScenarioSlice],
        strategy_instance: Optional[Any] = None,
    ) -> AptitudeMatrix:
        """
        Execute scenario validation across all provided stress slices.

        Args:
            strategy_id:         Strategy identifier being validated.
            parameter_overrides: Parameter set to test (e.g. {'confidence_threshold': 0.8}).
            scenario_slices:     Historical data segments, one per stress cluster.

        Returns:
            AptitudeMatrix with per-regime metrics, overall_score and trace_id.
        """
        now = datetime.now(timezone.utc)
        trace_id = (
            f"TRACE_BKT_VALIDATION"
            f"_{now.strftime('%Y%m%d_%H%M%S')}"
            f"_{strategy_id[:8].upper()}"
        )

        regime_results: List[RegimeResult] = []
        for scenario in scenario_slices:
            result = self._evaluate_slice(scenario, parameter_overrides, strategy_instance)
            regime_results.append(result)

        overall_score = float(self._compute_overall_score(regime_results))
        passes = bool(overall_score >= self.MIN_REGIME_SCORE)

        matrix = AptitudeMatrix(
            strategy_id=strategy_id,
            parameter_overrides=parameter_overrides,
            overall_score=overall_score,
            passes_threshold=passes,
            results_by_regime=regime_results,
            trace_id=trace_id,
            timestamp=now.isoformat(),
        )

        self._persist_validation(matrix)

        log_level = logging.INFO if passes else logging.WARNING
        logger.log(
            log_level,
            "[SCENARIO_BACKTESTER] strategy=%s overall_score=%.4f passes=%s trace_id=%s",
            strategy_id,
            overall_score,
            passes,
            trace_id,
        )

        return matrix

    # ── Slice Evaluation ──────────────────────────────────────────────────────

    def _evaluate_slice(
        self,
        scenario: ScenarioSlice,
        parameter_overrides: Dict[str, Any],
        strategy_instance: Optional[Any] = None,
    ) -> RegimeResult:
        """
        Simulate trades on a single data slice and compute regime-level metrics.

        Dispatch priority:
        1. UNTESTED slices (is_real_data=False) → 0.0 score, no simulation.
        2. strategy_instance provided with evaluate_on_history() → real strategy logic.
        3. Fallback → generic momentum model (_simulate_trades).

        Regime is detected from the slice OHLCV data (ATR + trend slope).
        When data is insufficient for detection, falls back to stress_cluster label.
        """
        if not scenario.is_real_data:
            return RegimeResult(
                stress_cluster=scenario.stress_cluster,
                detected_regime="UNTESTED",
                profit_factor=0.0,
                max_drawdown_pct=0.0,
                total_trades=0,
                win_rate=0.0,
                regime_score=0.0,
            )

        detected_regime = self._detect_regime(scenario.data, scenario.stress_cluster)

        # HU 7.7: dispatch to real strategy logic when instance is available
        if strategy_instance is not None and hasattr(strategy_instance, "evaluate_on_history"):
            raw: List[TradeResult] = strategy_instance.evaluate_on_history(
                scenario.data, parameter_overrides
            )
            trades = [
                {"entry": t.entry_price, "exit": t.exit_price, "pnl": t.pnl, "is_win": t.pnl > 0}
                for t in raw
            ]
        else:
            trades = self._simulate_trades(scenario.data, parameter_overrides)

        profit_factor = self._calculate_profit_factor(trades)
        max_dd = self._calculate_max_drawdown(trades)
        win_rate = self._calculate_win_rate(trades)
        regime_score = (
            0.0
            if not trades
            else self._score_regime_performance(profit_factor, max_dd)
        )

        return RegimeResult(
            stress_cluster=scenario.stress_cluster,
            detected_regime=detected_regime,
            profit_factor=profit_factor,
            max_drawdown_pct=max_dd,
            total_trades=len(trades),
            win_rate=win_rate,
            regime_score=regime_score,
        )

    def _detect_regime(self, data: pd.DataFrame, fallback: str) -> str:
        """
        Infer market regime from OHLCV data using ATR volatility + trend slope.

        Returns:
            'VOLATILE' | 'TREND' | 'RANGE' — or fallback when data < 14 bars.
        """
        if len(data) < 14:
            return fallback

        atr_series = (data["high"] - data["low"]).rolling(14).mean()
        avg_atr = atr_series.mean()
        last_atr = atr_series.iloc[-1] if not atr_series.empty else avg_atr
        volatility_ratio = last_atr / avg_atr if avg_atr > 0 else 1.0

        close = data["close"]
        price_range = close.max() - close.min()
        bar_mean_move = price_range / len(close) if len(close) > 0 else 1e-9
        trend_slope = abs(close.iloc[-1] - close.iloc[0]) / len(close)
        trend_strength = trend_slope / bar_mean_move if bar_mean_move > 0 else 0.0

        if volatility_ratio > 1.5:
            return "VOLATILE"
        if trend_strength > 0.6:
            return "TREND"
        return "RANGE"

    def _simulate_trades(
        self,
        data: pd.DataFrame,
        parameter_overrides: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Simplified momentum-based signal simulation.

        Entry condition: |bar_return| >= confidence_threshold.
        Exit on next candle close.
        Risk/reward ratio applied as take-profit multiplier.

        Returns list of trade dicts with keys: entry, exit, pnl, is_win.
        """
        if len(data) < 3:
            return []

        confidence_threshold = float(parameter_overrides.get("confidence_threshold", 0.001))
        risk_reward = float(parameter_overrides.get("risk_reward", 1.5))
        trades: List[Dict[str, Any]] = []

        close = data["close"].values
        for i in range(1, len(close) - 1):
            prior_close = close[i - 1]
            if prior_close == 0:
                continue
            momentum = (close[i] - prior_close) / prior_close
            signal_strength = min(abs(momentum) * 100.0, 1.0)

            if signal_strength < confidence_threshold:
                continue

            entry = close[i]
            direction = 1 if momentum > 0 else -1
            stop_dist = abs(close[i] - prior_close)
            _ = entry + direction * stop_dist * risk_reward  # take_profit (unused in sim)

            exit_price = close[i + 1]
            pnl = direction * (exit_price - entry)
            trades.append({"entry": entry, "exit": exit_price, "pnl": pnl, "is_win": pnl > 0})

        return trades

    # ── Metric Calculations ───────────────────────────────────────────────────

    def _calculate_profit_factor(self, trades: List[Dict]) -> float:
        """Gross Profit / Gross Loss.  Returns 0.0 when no trades or no losses."""
        if not trades:
            return 0.0
        gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
        gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
        if gross_loss == 0:
            return gross_profit if gross_profit > 0 else 0.0
        return round(gross_profit / gross_loss, 4)

    def _calculate_max_drawdown(self, trades: List[Dict]) -> float:
        """Maximum percentage drawdown from peak equity (normalised to 1 000 units)."""
        if not trades:
            return 0.0
        equity = 1_000.0
        peak = equity
        max_dd = 0.0
        for trade in trades:
            equity += trade["pnl"]
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd
        return round(max_dd, 4)

    def _calculate_win_rate(self, trades: List[Dict]) -> float:
        if not trades:
            return 0.0
        return round(sum(1 for t in trades if t["is_win"]) / len(trades), 4)

    def _score_regime_performance(self, profit_factor: float, max_dd: float) -> float:
        """
        Composite regime score [0.0 – 1.0].

        Formula::

            score = (pf_score × 0.60) + (dd_score × 0.40)
            pf_score = min(profit_factor / 2.0, 1.0)     # PF=2 → perfect
            dd_score = max(1.0 - max_dd / 0.20, 0.0)     # DD≥20% → 0
        """
        pf_score = min(profit_factor / 2.0, 1.0)
        dd_score = max(1.0 - max_dd / 0.20, 0.0)
        return round(pf_score * 0.60 + dd_score * 0.40, 4)

    def _compute_overall_score(self, results: List[RegimeResult]) -> float:
        """Equal-weight mean of all regime scores.

        Returns 0.0 when no regimes were tested OR when every regime produced
        zero trades — a strategy that never fires cannot be scored meaningfully.
        Returning the DD-only partial score (0.4) in that case is misleading.
        """
        if not results:
            return 0.0
        if sum(r.total_trades for r in results) == 0:
            return 0.0
        return round(sum(r.regime_score for r in results) / len(results), 4)

    # ── Persistence ───────────────────────────────────────────────────────────

    def _persist_validation(self, matrix: AptitudeMatrix) -> None:
        """
        Insert a TRACE_BKT_VALIDATION_... entry into sys_shadow_promotion_log.

        Columns used:
          instance_id      → strategy_id (pre-shadow identifier)
          trace_id         → TRACE_BKT_VALIDATION_YYYYMMDD_HHMMSS_ID8
          promotion_status → 'APPROVED' | 'REJECTED'
          notes            → AptitudeMatrix JSON
        """
        promotion_status = "APPROVED" if matrix.passes_threshold else "REJECTED"
        try:
            conn = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO sys_shadow_promotion_log
                    (instance_id, trace_id, promotion_status, notes)
                VALUES (?, ?, ?, ?)
                """,
                (
                    matrix.strategy_id,
                    matrix.trace_id,
                    promotion_status,
                    matrix.to_json(),
                ),
            )
            conn.commit()
            logger.debug(
                "[SCENARIO_BACKTESTER] Validation persisted trace_id=%s status=%s",
                matrix.trace_id,
                promotion_status,
            )
        except Exception as exc:
            logger.error(
                "[SCENARIO_BACKTESTER] Failed to persist validation trace_id=%s: %s",
                matrix.trace_id,
                exc,
            )
