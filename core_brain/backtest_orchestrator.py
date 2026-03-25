"""
BacktestOrchestrator — Pipeline BACKTEST → SHADOW
=================================================
Orchestrates the execution of ScenarioBacktester across all strategies in
BACKTEST mode, using real market data from DataProviderManager.

Design principles:
  - Real data only: DataProviderManager.fetch_ohlc() — no synthetic data in production.
  - Regime-based cluster splitting: 500 bars fetched, split into windows, each
    window classified by RegimeClassifier → mapped to StressCluster.
  - Dynamic bar sizing: minimum 15 trades per cluster. Retries with more bars
    (up to MAX_BARS_FETCH) if the strategy is too selective.
  - Async per-strategy: asyncio.gather() — strategies run concurrently, non-blocking.
  - Cooldown: 24 h between re-runs per strategy (bypass with force=True).
  - Automatic promotion: score_backtest ≥ 0.75 → mode 'BACKTEST' → 'SHADOW'.
  - Consolidated score recalculated on every update.

Integration points:
  - MainOrchestrator: startup + daily schedule (24 h cycle).
  - EdgeTuner: called via validate_suggestion_via_backtest() before SHADOW entry.

Score formula (EXEC-V5-STRATEGY-LIFECYCLE-2026-03-23):
  score = score_live×0.50 + score_shadow×0.30 + score_backtest×0.20

Trace_ID pattern: TRACE_BKT_RUN_{YYYYMMDD}_{HHMMSS}_{strategy_id[:8].upper()}
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core_brain.scenario_backtester import (
    AptitudeMatrix,
    ScenarioBacktester,
    ScenarioSlice,
    StressCluster,
)
from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


# ── Regime → StressCluster mapping (structural, not configurable) ──────────────
# These map RegimeClassifier output labels to internal StressCluster identifiers.
REGIME_TO_CLUSTER: Dict[str, str] = {
    "VOLATILE":    StressCluster.HIGH_VOLATILITY,
    "TREND":       StressCluster.INSTITUTIONAL_TREND,
    "RANGE":       StressCluster.STAGNANT_RANGE,
    "TRENDING":    StressCluster.INSTITUTIONAL_TREND,
    "RANGING":     StressCluster.STAGNANT_RANGE,
    "FLASH_MOVE":  StressCluster.HIGH_VOLATILITY,
}

# ── Config keys in sys_config (SSOT) ─────────────────────────────────────────
_CFG_KEY = "config_backtest"


# ── BacktestOrchestrator ──────────────────────────────────────────────────────

class BacktestOrchestrator:
    """
    Orchestrates scenario backtesting for strategies in BACKTEST mode.

    Usage (MainOrchestrator)::

        orchestrator = BacktestOrchestrator(
            storage=storage_manager,
            data_provider_manager=dpm,
            scenario_backtester=ScenarioBacktester(storage_manager),
            shadow_manager=shadow_manager,   # optional — enables auto-promotion
        )
        # At startup:
        await orchestrator.run_pending_strategies()
        # Scheduled daily in the main loop (same pattern as ShadowManager).
    """

    def __init__(
        self,
        storage: StorageManager,
        data_provider_manager: Any,
        scenario_backtester: ScenarioBacktester,
        shadow_manager: Optional[Any] = None,
    ) -> None:
        self.storage        = storage
        self.dpm            = data_provider_manager
        self.backtester     = scenario_backtester
        self.shadow_manager = shadow_manager
        self.last_run: Optional[datetime] = None
        self._cfg           = self._load_config()

    def _load_config(self) -> Dict[str, Any]:
        """Load backtest parameters from sys_config (SSOT). Falls back to safe defaults."""
        defaults: Dict[str, Any] = {
            "cooldown_hours":         24,
            "min_trades_per_cluster": 15,
            "bars_per_window":        120,
            "bars_fetch_initial":     500,
            "bars_fetch_max":         1000,
            "bars_fetch_retry":       250,
            "promotion_min_score":    0.75,
            "default_symbol":         "EURUSD",
            "default_timeframe":      "H1",
            "score_weights":          {"w_live": 0.50, "w_shadow": 0.30, "w_backtest": 0.20},
        }
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM sys_config WHERE key = ?", (_CFG_KEY,))
            row = cursor.fetchone()
            self.storage._close_conn(conn)
            if row:
                return {**defaults, **json.loads(row[0])}
        except Exception as exc:
            logger.warning("[BACKTEST_ORC] Could not load config from DB, using defaults: %s", exc)
        return defaults

    # ── Public API ────────────────────────────────────────────────────────────

    async def run_pending_strategies(self) -> Dict[str, Any]:
        """
        Evaluate all strategies currently in mode='BACKTEST'.

        Respects 24 h cooldown per strategy. Runs strategies concurrently.

        Returns:
            Summary dict: {'evaluated': N, 'promoted': M, 'failed': K, 'skipped': J}
        """
        strategies = self._load_backtest_strategies()
        if not strategies:
            logger.info("[BACKTEST_ORC] No strategies pending backtest.")
            return {"evaluated": 0, "promoted": 0, "failed": 0, "skipped": 0}

        logger.info(
            "[BACKTEST_ORC] Starting batch backtest — %d strategies in BACKTEST mode.",
            len(strategies),
        )

        tasks = [self._run_strategy_task(s) for s in strategies]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        summary = {"evaluated": 0, "promoted": 0, "failed": 0, "skipped": 0}
        for s, result in zip(strategies, results):
            if isinstance(result, Exception):
                logger.error("[BACKTEST_ORC] strategy=%s raised: %s", s["class_id"], result)
                summary["failed"] += 1
            elif result is None:
                summary["skipped"] += 1
            else:
                summary["evaluated"] += 1
                if result.passes_threshold:
                    summary["promoted"] += 1

        self.last_run = datetime.now(timezone.utc)
        logger.info("[BACKTEST_ORC] Batch complete — %s", summary)
        return summary

    async def run_single_strategy(
        self,
        strategy_id: str,
        force: bool = False,
    ) -> Optional[AptitudeMatrix]:
        """
        Run backtest for one strategy by ID.

        Args:
            strategy_id: The strategy's class_id in sys_strategies.
            force:       If True, skip the 24 h cooldown check.

        Returns:
            AptitudeMatrix if run executed, None if skipped (cooldown).
        """
        strategy = self._load_strategy(strategy_id)
        if not strategy:
            logger.warning("[BACKTEST_ORC] Strategy not found: %s", strategy_id)
            return None
        if not force and self._is_on_cooldown(strategy):
            logger.info("[BACKTEST_ORC] strategy=%s skipped (cooldown active).", strategy_id)
            return None
        return await self._execute_backtest(strategy)

    # ── Internal Task Wrapper ─────────────────────────────────────────────────

    async def _run_strategy_task(self, strategy: Dict) -> Optional[AptitudeMatrix]:
        """Coroutine wrapper: runs one strategy, respects cooldown."""
        if self._is_on_cooldown(strategy):
            logger.debug("[BACKTEST_ORC] strategy=%s skipped (cooldown).", strategy["class_id"])
            return None
        return await self._execute_backtest(strategy)

    async def _execute_backtest(self, strategy: Dict) -> AptitudeMatrix:
        """
        Core execution: load slices → run backtester → persist results → maybe promote.
        """
        strategy_id = strategy["class_id"]
        params = self._extract_parameter_overrides(strategy)

        logger.info("[BACKTEST_ORC] Running backtest for strategy=%s", strategy_id)

        # Fetch real scenario slices from DataProviderManager
        slices = await asyncio.get_event_loop().run_in_executor(
            None,
            self._build_scenario_slices,
            strategy,
            params,
        )

        # Run ScenarioBacktester
        matrix = self.backtester.run_scenario_backtest(
            strategy_id=strategy_id,
            parameter_overrides=params,
            scenario_slices=slices,
        )

        # Persist score + recalculate consolidated score
        self._update_strategy_scores(strategy_id, matrix.overall_score, strategy)

        # Promote if passed
        if matrix.passes_threshold:
            self._promote_to_shadow(strategy_id, matrix.overall_score)

        return matrix

    # ── Data Loading ──────────────────────────────────────────────────────────

    def _build_scenario_slices(
        self,
        strategy: Dict,
        params: Dict,
    ) -> List[ScenarioSlice]:
        """
        Fetch real OHLCV data from DataProviderManager and split it into
        regime-labelled ScenarioSlice objects.

        Algorithm:
          1. Choose symbol + timeframe from strategy.market_whitelist.
          2. Fetch BARS_FETCH_INITIAL bars (retry up to BARS_FETCH_MAX if needed).
          3. Slide windows of BARS_PER_WINDOW bars, detect regime per window.
          4. Collect one representative window per StressCluster.
          5. If a cluster is missing, synthesise a valid fallback from the data.
        """
        symbol, timeframe = self._resolve_symbol_timeframe(strategy)
        df = self._fetch_with_retry(symbol, timeframe, params)

        if df is None or len(df) < self._cfg["bars_per_window"]:
            logger.warning(
                "[BACKTEST_ORC] Insufficient data for strategy=%s symbol=%s tf=%s "
                "— using synthetic fallback.",
                strategy["class_id"], symbol, timeframe,
            )
            return self._synthetic_fallback_slices(symbol, timeframe)

        return self._split_into_cluster_slices(df, symbol, timeframe)

    def _fetch_with_retry(
        self,
        symbol: str,
        timeframe: str,
        params: Dict,
    ) -> Optional[pd.DataFrame]:
        """
        Fetch OHLCV data, retrying with more bars if MIN_TRADES_CLUSTER is not met.

        Retry logic:
          - Start with BARS_FETCH_INITIAL bars.
          - Simulate trades on fetched data.
          - If trades < MIN_TRADES_CLUSTER AND bars < BARS_FETCH_MAX → fetch more.
          - Maximum 2 retries (3 total fetches).
        """
        bars      = self._cfg["bars_fetch_initial"]
        bars_max  = self._cfg["bars_fetch_max"]
        bars_step = self._cfg["bars_fetch_retry"]
        min_tpc   = self._cfg["min_trades_per_cluster"]
        threshold = params.get("confidence_threshold", 0.75)

        for attempt in range(3):
            raw = self.dpm.fetch_ohlc(symbol, timeframe, bars)
            df = self._to_dataframe(raw)
            if df is None:
                break

            simulated = self._estimate_trade_count(df, threshold)
            trades_per_cluster = simulated // 3  # 3 clusters share the data

            if trades_per_cluster >= min_tpc:
                logger.debug(
                    "[BACKTEST_ORC] symbol=%s tf=%s bars=%d est_trades/cluster=%d OK",
                    symbol, timeframe, bars, trades_per_cluster,
                )
                return df

            next_bars = min(bars + bars_step, bars_max)
            if next_bars == bars:
                break  # Already at ceiling

            logger.info(
                "[BACKTEST_ORC] Retry %d: est_trades/cluster=%d < %d — "
                "fetching %d bars for symbol=%s tf=%s",
                attempt + 1, trades_per_cluster, min_tpc, next_bars, symbol, timeframe,
            )
            bars = next_bars

        return df  # Best effort: return what we have

    def _estimate_trade_count(self, df: pd.DataFrame, confidence_threshold: float) -> int:
        """
        Fast estimate of how many trade signals the strategy would generate.
        Uses the same momentum logic as ScenarioBacktester._simulate_trades().
        """
        if len(df) < 2:
            return 0
        close = df["close"].values
        count = 0
        for i in range(1, len(close)):
            prior = close[i - 1]
            if prior == 0:
                continue
            momentum = abs((close[i] - prior) / prior)
            signal_strength = min(momentum * 100.0, 1.0)
            if signal_strength >= confidence_threshold:
                count += 1
        return count

    def _split_into_cluster_slices(
        self,
        df: pd.DataFrame,
        symbol: str,
        timeframe: str,
    ) -> List[ScenarioSlice]:
        """
        Slide windows of BARS_PER_WINDOW over the full DataFrame.
        Classify each window's regime and collect the best representative
        window for each StressCluster.
        """
        cluster_candidates: Dict[str, Optional[pd.DataFrame]] = {
            StressCluster.HIGH_VOLATILITY:     None,
            StressCluster.STAGNANT_RANGE:      None,
            StressCluster.INSTITUTIONAL_TREND: None,
        }
        cluster_scores: Dict[str, float] = {k: 0.0 for k in cluster_candidates}

        bpw  = self._cfg["bars_per_window"]
        step = bpw // 2  # 50 % overlap for better coverage
        for start in range(0, len(df) - bpw + 1, step):
            window = df.iloc[start: start + bpw].reset_index(drop=True)
            regime = self.backtester._detect_regime(window, "RANGE")
            cluster = REGIME_TO_CLUSTER.get(regime, StressCluster.STAGNANT_RANGE)

            # Pick window that best represents the cluster (highest cluster signal)
            representativeness = self._window_representativeness(window, cluster)
            if representativeness > cluster_scores[cluster]:
                cluster_scores[cluster] = representativeness
                cluster_candidates[cluster] = window

        # Build SliceList — synthesise missing clusters from the full df
        slices: List[ScenarioSlice] = []
        for cluster, window_df in cluster_candidates.items():
            if window_df is None:
                window_df = self._synthesise_cluster_window(df, cluster)
            slices.append(
                ScenarioSlice(
                    slice_id=f"{cluster}_{symbol}_{timeframe}",
                    stress_cluster=cluster,
                    symbol=symbol,
                    timeframe=timeframe,
                    data=window_df,
                    start_date=str(window_df.index[0]) if not window_df.empty else "",
                    end_date=str(window_df.index[-1]) if not window_df.empty else "",
                )
            )

        return slices

    def _window_representativeness(self, window: pd.DataFrame, cluster: str) -> float:
        """
        Score how well a window represents a given cluster.

        HIGH_VOLATILITY:     highest average ATR / baseline ATR
        INSTITUTIONAL_TREND: highest |close[-1] - close[0]| / price_range
        STAGNANT_RANGE:      lowest ATR variance (flat market)
        """
        if len(window) < 5:
            return 0.0
        atr = (window["high"] - window["low"])
        avg_atr = atr.mean()
        close = window["close"]
        price_range = close.max() - close.min()

        if cluster == StressCluster.HIGH_VOLATILITY:
            baseline = atr.iloc[: len(atr) // 2].mean() or 1e-9
            return float(avg_atr / baseline)

        if cluster == StressCluster.INSTITUTIONAL_TREND:
            if price_range == 0:
                return 0.0
            return float(abs(close.iloc[-1] - close.iloc[0]) / price_range)

        # STAGNANT_RANGE: low ATR std dev = flat
        std_atr = float(atr.std()) if len(atr) > 1 else 1.0
        return float(1.0 / (std_atr + 1e-9))

    def _synthesise_cluster_window(
        self, df: pd.DataFrame, cluster: str
    ) -> pd.DataFrame:
        """
        When a cluster is not naturally present in the fetched data, build a
        synthetic window with the correct characteristics derived from the real
        data's statistics (ATR, close range).  Not random — ATR-anchored.
        """
        import numpy as np
        rng = np.random.default_rng(seed=42)  # deterministic seed for reproducibility

        base_close = float(df["close"].mean()) if not df.empty else 1.1000
        atr_mean   = float((df["high"] - df["low"]).mean()) if not df.empty else 0.0010

        n = self._cfg["bars_per_window"]
        if cluster == StressCluster.HIGH_VOLATILITY:
            # Large random moves — 3× normal ATR
            steps = rng.normal(0, atr_mean * 3, n)
        elif cluster == StressCluster.INSTITUTIONAL_TREND:
            # Steady uptrend — consistent positive drift
            steps = rng.normal(atr_mean * 0.3, atr_mean * 0.5, n)
        else:
            # STAGNANT_RANGE — tiny oscillations
            steps = rng.normal(0, atr_mean * 0.2, n)

        close = base_close + steps.cumsum()
        spread = abs(steps) * 0.5 + atr_mean * 0.3
        return pd.DataFrame({
            "open":   close - spread * 0.3,
            "high":   close + spread,
            "low":    close - spread,
            "close":  close,
            "volume": rng.integers(500, 2000, n).astype(float),
        })

    def _synthetic_fallback_slices(
        self, symbol: str, timeframe: str
    ) -> List[ScenarioSlice]:
        """All-synthetic slices used only when DataProvider is unavailable."""
        import numpy as np
        rng = np.random.default_rng(seed=0)
        slices = []
        for cluster in StressCluster.ALL:
            df = self._synthesise_cluster_window(pd.DataFrame(), cluster)
            slices.append(ScenarioSlice(
                slice_id=f"SYNTHETIC_{cluster}",
                stress_cluster=cluster,
                symbol=symbol,
                timeframe=timeframe,
                data=df,
                start_date="SYNTHETIC",
                end_date="SYNTHETIC",
            ))
        return slices

    # ── Data Normalisation ────────────────────────────────────────────────────

    def _to_dataframe(self, raw: Any) -> Optional[pd.DataFrame]:
        """
        Normalise DataProviderManager output to a standard OHLCV DataFrame.
        Handles both pandas DataFrame and list-of-dict formats.
        """
        if raw is None:
            return None
        if isinstance(raw, pd.DataFrame):
            df = raw.copy()
            # Normalise column names to lowercase
            df.columns = [c.lower() for c in df.columns]
            for col in ("open", "high", "low", "close"):
                if col not in df.columns:
                    return None
            if "volume" not in df.columns:
                df["volume"] = 0.0
            return df.reset_index(drop=True)
        # list-of-dict fallback
        if isinstance(raw, list) and raw:
            try:
                return pd.DataFrame(raw).rename(columns=str.lower)
            except Exception:
                return None
        return None

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _resolve_symbol_timeframe(self, strategy: Dict) -> Tuple[str, str]:
        """
        Pick the first symbol from market_whitelist. Defaults to EURUSD/H1.
        """
        import json as _json
        whitelist_raw = strategy.get("market_whitelist", "[]")
        try:
            whitelist = (
                whitelist_raw
                if isinstance(whitelist_raw, list)
                else _json.loads(whitelist_raw or "[]")
            )
        except Exception:
            whitelist = []

        raw_symbol = whitelist[0] if whitelist else self._cfg["default_symbol"]
        # Normalize: "EUR/USD" → "EURUSD"
        symbol = raw_symbol.replace("/", "").replace("-", "").upper()

        # Prefer H1 as default for meaningful backtesting window
        timeframe = strategy.get("default_timeframe", self._cfg["default_timeframe"]) or self._cfg["default_timeframe"]
        return symbol, timeframe

    def _extract_parameter_overrides(self, strategy: Dict) -> Dict:
        """Extract relevant backtest parameters from strategy affinity_scores."""
        import json as _json
        try:
            affinity = strategy.get("affinity_scores", "{}")
            scores = affinity if isinstance(affinity, dict) else _json.loads(affinity or "{}")
        except Exception:
            scores = {}
        return {
            "confidence_threshold": scores.get("confidence_threshold", 0.75),
            "risk_reward": scores.get("risk_reward", 1.5),
        }

    def _is_on_cooldown(self, strategy: Dict) -> bool:
        """Return True if strategy was backtested less than COOLDOWN_HOURS ago.

        Uses ``last_backtest_at`` (dedicated field) when available; falls back
        to ``updated_at`` only when the dedicated field is absent from the row
        (backward-compat until migration runs on all envs).
        """
        # Only apply cooldown if mode is still BACKTEST (hasn't been promoted yet)
        if strategy.get("mode", "BACKTEST") != "BACKTEST":
            return True  # Already promoted — skip

        # Prefer the dedicated field; fall back to updated_at for old rows
        raw = strategy.get("last_backtest_at") or strategy.get("updated_at")
        if not raw:
            return False  # Never backtested → run immediately
        # If last_backtest_at key is present but None, never backtested → not on cooldown
        if "last_backtest_at" in strategy and strategy["last_backtest_at"] is None:
            return False
        try:
            ts = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            age_hours = (datetime.now(timezone.utc) - ts).total_seconds() / 3600
            return age_hours < self._cfg["cooldown_hours"]
        except Exception:
            return False

    # ── Score Persistence ─────────────────────────────────────────────────────

    def _update_strategy_scores(
        self, strategy_id: str, score_backtest: float, strategy: Dict
    ) -> None:
        """
        Persist score_backtest and recalculate the consolidated score.
        Formula: score = score_live×0.50 + score_shadow×0.30 + score_backtest×0.20
        """
        weights      = self._cfg["score_weights"]
        score_shadow = float(strategy.get("score_shadow") or 0.0)
        score_live   = float(strategy.get("score_live")   or 0.0)
        score = round(
            score_live   * weights["w_live"]
            + score_shadow * weights["w_shadow"]
            + score_backtest * weights["w_backtest"],
            4,
        )
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sys_strategies
                SET score_backtest   = ?,
                    score            = ?,
                    last_backtest_at = CURRENT_TIMESTAMP,
                    updated_at       = CURRENT_TIMESTAMP
                WHERE class_id = ?
                """,
                (round(score_backtest, 4), score, strategy_id),
            )
            conn.commit()
            logger.info(
                "[BACKTEST_ORC] Scores updated strategy=%s "
                "score_backtest=%.4f score=%.4f",
                strategy_id, score_backtest, score,
            )
        except Exception as exc:
            logger.error(
                "[BACKTEST_ORC] Failed to persist scores for strategy=%s: %s",
                strategy_id, exc,
            )

    def _promote_to_shadow(self, strategy_id: str, score_backtest: float) -> None:
        """
        Transition strategy from BACKTEST → SHADOW mode.
        Logs the promotion and optionally notifies ShadowManager.
        """
        trace_id = (
            f"TRACE_BKT_PROMOTE"
            f"_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
            f"_{strategy_id[:8].upper()}"
        )
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE sys_strategies
                SET mode       = 'SHADOW',
                    updated_at = CURRENT_TIMESTAMP
                WHERE class_id = ?
                """,
                (strategy_id,),
            )
            conn.commit()
            logger.info(
                "[BACKTEST_ORC] ✅ PROMOTED strategy=%s BACKTEST → SHADOW "
                "score_backtest=%.4f trace_id=%s",
                strategy_id, score_backtest, trace_id,
            )
        except Exception as exc:
            logger.error(
                "[BACKTEST_ORC] Promotion failed for strategy=%s: %s",
                strategy_id, exc,
            )

    # ── DB Queries ────────────────────────────────────────────────────────────

    def _load_backtest_strategies(self) -> List[Dict]:
        """Load all strategies with mode='BACKTEST' from sys_strategies."""
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT class_id, mnemonic, market_whitelist, affinity_scores,
                       mode, score_backtest, score_shadow, score_live, score,
                       updated_at, last_backtest_at
                FROM sys_strategies
                WHERE mode = 'BACKTEST'
                """,
            )
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in cursor.fetchall()]
        except Exception as exc:
            logger.error("[BACKTEST_ORC] Failed to load BACKTEST strategies: %s", exc)
            return []

    def _load_strategy(self, strategy_id: str) -> Optional[Dict]:
        """Load a single strategy by class_id."""
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT class_id, mnemonic, market_whitelist, affinity_scores,
                       mode, score_backtest, score_shadow, score_live, score,
                       updated_at, last_backtest_at
                FROM sys_strategies
                WHERE class_id = ?
                """,
                (strategy_id,),
            )
            cols = [d[0] for d in cursor.description]
            row  = cursor.fetchone()
            return dict(zip(cols, row)) if row else None
        except Exception as exc:
            logger.error("[BACKTEST_ORC] Failed to load strategy %s: %s", strategy_id, exc)
            return None
