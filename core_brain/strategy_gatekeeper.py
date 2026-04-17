"""
strategy_gatekeeper.py — In-Memory Asset Efficiency Filter

Responsibility:
  - Pre-tick validation of asset affinity scores
  - Fail-fast execution abort (< 1ms)
  - Market whitelist enforcement
  - Performance learning integration

Architecture:
  - Resides entirely in memory (Python dict cache)
  - No DB queries during tick processing (ultra-fast)
  - Periodic refresh from StorageManager for score updates
  - Single Source of Truth (SSOT): scores originate from usr_strategy_logs in DB

Dependency Injection: StorageManager (provided by caller)

TRACE_ID: EXEC-EFFICIENCY-SCORE-001
"""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _normalize_symbol(symbol: str) -> str:
    """Normalize asset symbol to broker format (no slash). EUR/USD → EURUSD."""
    return symbol.replace("/", "").upper()


class StrategyGatekeeper:
    """
    In-memory asset efficiency validator.
    
    Before a strategy processes any tick, StrategyGatekeeper validates:
      1. Asset is in market_whitelist (if defined)
      2. Asset affinity_score >= min_threshold
      
    If both conditions fail, execution aborts instantly (< 1ms).
    """

    def __init__(self, storage: Any) -> None:
        """
        Initialize the Gatekeeper with dependency injection.

        Args:
            storage: StorageManager instance (for affinity score queries)
        """
        self.storage = storage
        self.asset_scores: Dict[str, float] = {}
        self.market_whitelists: Dict[str, List[str]] = {}

        # Exploración adaptativa (solo DEMO)
        self._exploration_scores: Dict[str, Dict[str, float]] = {}  # strategy_id → {asset: score}
        self._frozen_exploration: Dict[str, set] = {}               # strategy_id → {asset}
        self._exploration_pf: Dict[str, Dict[str, float]] = {}      # strategy_id → {asset: PF}

        # Load initial affinity scores from DB
        try:
            if hasattr(self.storage, "get_strategy_affinity_scores"):
                self.asset_scores = self.storage.get_strategy_affinity_scores() or {}
                logger.info(f"[GATEKEEPER] Loaded {len(self.asset_scores)} asset scores into memory cache.")
            else:
                self.asset_scores = {}
                logger.info(
                    "[GATEKEEPER] Storage has no get_strategy_affinity_scores(); "
                    "starting with empty cache."
                )
        except Exception as e:
            logger.warning(f"[GATEKEEPER] Failed to load initial scores: {e}")
            self.asset_scores = {}

    # ── Pre-Tick Validation (Core Function) ────────────────────────────────────

    def can_execute_on_tick(
        self,
        asset: str,
        min_threshold: float,
        strategy_id: str
    ) -> bool:
        """
        Fast path: Validate if strategy can execute on this asset for this tick.
        
        CRITICAL: This method must complete in < 1ms (in-memory only, no DB calls).
        
        Args:
            asset: Asset symbol (e.g., 'EUR/USD')
            min_threshold: Minimum affinity score required (0-1)
            strategy_id: Strategy class_id for whitelist lookup
            
        Returns:
            True if execution allowed, False if blocked (veto)
        """
        # Check market whitelist first (if defined for this strategy)
        normalized_asset = _normalize_symbol(asset)
        if strategy_id in self.market_whitelists:
            if normalized_asset not in self.market_whitelists[strategy_id]:
                logger.debug(f"[GATEKEEPER] Veto: {asset} not in whitelist for {strategy_id}")
                return False

        # Check affinity score
        asset_score = self.asset_scores.get(normalized_asset, self.asset_scores.get(asset, 0.0))
        
        if asset_score < min_threshold:
            logger.debug(
                f"[GATEKEEPER] Veto: {asset} score {asset_score:.2f} < threshold {min_threshold:.2f}"
            )
            return False
        
        return True

    def can_execute_on_tick_with_reason(
        self,
        asset: str,
        min_threshold: float,
        strategy_id: str,
    ) -> tuple[bool, str]:
        """
        Fast path validation identical to can_execute_on_tick() but returns a
        deterministic reason code alongside the boolean decision.

        Reason codes (canonical — HU 5.5 + exploración):
          - ``gk_approved``              — all checks passed
          - ``gk_approved_exploration``  — aprobado vía exploración adaptativa
          - ``gk_whitelist_reject``      — asset not in strategy whitelist
          - ``gk_score_below_threshold`` — affinity score below minimum
          - ``gk_frozen_exploration``    — activo congelado por bajo PF en exploración

        Returns:
            Tuple (allowed: bool, reason_code: str)
        """
        normalized_asset = _normalize_symbol(asset)

        if strategy_id in self.market_whitelists:
            if normalized_asset not in self.market_whitelists[strategy_id]:
                logger.debug("[GATEKEEPER] Veto: %s not in whitelist for %s", asset, strategy_id)
                return False, "gk_whitelist_reject"

        asset_score = self.asset_scores.get(normalized_asset, self.asset_scores.get(asset, 0.0))
        if asset_score >= min_threshold:
            return True, "gk_approved"

        # Fallback: verificar activos en exploración adaptativa
        exploration = self._exploration_scores.get(strategy_id, {})
        if normalized_asset in exploration:
            frozen = self._frozen_exploration.get(strategy_id, set())
            if normalized_asset in frozen:
                logger.debug("[GATEKEEPER] Frozen exploration asset: %s", asset)
                return False, "gk_frozen_exploration"
            logger.debug("[GATEKEEPER] Approved via exploration: %s", asset)
            return True, "gk_approved_exploration"

        logger.debug(
            "[GATEKEEPER] Veto: %s score %.2f < threshold %.2f", asset, asset_score, min_threshold
        )
        return False, "gk_score_below_threshold"

    def validate_asset_score(
        self,
        asset: str,
        min_threshold: float,
        strategy_id: str
    ) -> bool:
        """
        Explicit score validation (same as can_execute_on_tick but clearer naming).

        Args:
            asset: Asset symbol
            min_threshold: Minimum score required (0-1)
            strategy_id: Strategy identifier

        Returns:
            True if score passes, False otherwise
        """
        return self.can_execute_on_tick(asset, min_threshold, strategy_id)

    # ── Market Whitelist Management ─────────────────────────────────────────────

    def set_market_whitelist(
        self,
        strategy_id: str,
        whitelist: List[str]
    ) -> None:
        """
        Set allowed markets for a strategy.
        
        Args:
            strategy_id: Strategy class_id
            whitelist: List of allowed asset symbols
        """
        self.market_whitelists[strategy_id] = [_normalize_symbol(s) for s in whitelist]
        logger.info(f"[GATEKEEPER] Whitelist set for {strategy_id}: {self.market_whitelists[strategy_id]}")

    def get_market_whitelist(self, strategy_id: str) -> List[str]:
        """Retrieve market whitelist for a strategy."""
        return self.market_whitelists.get(strategy_id, [])

    def clear_market_whitelist(self, strategy_id: str) -> None:
        """Remove whitelist restrictions for a strategy."""
        if strategy_id in self.market_whitelists:
            del self.market_whitelists[strategy_id]
            logger.info(f"[GATEKEEPER] Whitelist cleared for {strategy_id}")

    # ── Performance Logging (Learning) ──────────────────────────────────────────

    def log_asset_performance(
        self,
        strategy_id: str,
        asset: str,
        pnl: float,
        usr_trades_count: int,
        win_rate: float,
        profit_factor: float,
        trace_id: Optional[str] = None
    ) -> bool:
        """
        Log strategy performance for an asset.
        Called after each trade or batch completes.
        
        This data feeds the learning system that recalculates affinity_scores.
        
        Args:
            strategy_id: Strategy class_id
            asset: Asset symbol
            pnl: Profit/Loss amount
            usr_trades_count: Number of usr_trades in this batch
            win_rate: Win rate (0-1)
            profit_factor: Profit Factor (wins / losses)
            trace_id: Optional trace ID for auditing
            
        Returns:
            True if logged successfully
        """
        try:
            result = self.storage.save_strategy_performance_log(
                strategy_id=strategy_id,
                asset=asset,
                pnl=pnl,
                usr_trades_count=usr_trades_count,
                win_rate=win_rate,
                profit_factor=profit_factor,
                trace_id=trace_id
            )
            if result:
                logger.debug(
                    f"[GATEKEEPER] Performance logged for {strategy_id}@{asset}: "
                    f"PnL={pnl:.2f}, WR={win_rate:.2%}, PF={profit_factor:.2f}"
                )
            return bool(result)
        except Exception as e:
            logger.error(f"[GATEKEEPER] Error logging performance: {e}")
            return False

    # ── Sync from Strategy Specs (Alignment with analyze() snapshot) ────────────

    def sync_from_strategy_specs(
        self,
        strategy_specs: List[Dict[str, Any]]
    ) -> None:
        """
        Sincroniza market_whitelists con los datos de sys_strategies (SSOT).

        Garantiza que las whitelists del Gatekeeper sean coherentes con las que
        analyze() recibe vía snapshot DB-backed, eliminando el riesgo de
        contradicción entre las dos capas de filtrado.

        Debe llamarse después de cargar estrategias desde la factory para que
        ambas capas (analyze snapshot y Gatekeeper) usen la misma noción de
        whitelist por estrategia.

        Args:
            strategy_specs: Lista de dicts de sys_strategies con market_whitelist.

        Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13
        """
        synced = 0
        for spec in strategy_specs:
            strategy_id = spec.get("class_id") or spec.get("strategy_id")
            whitelist = spec.get("market_whitelist")
            if not strategy_id:
                continue
            if whitelist:
                self.market_whitelists[strategy_id] = [_normalize_symbol(s) for s in whitelist]
                synced += 1
            elif strategy_id in self.market_whitelists:
                # Lista vacía en DB = sin restricción → limpiar whitelist del gatekeeper
                del self.market_whitelists[strategy_id]
                synced += 1
        logger.info(
            f"[GATEKEEPER] Whitelists sincronizadas con sys_strategies: {synced} estrategias"
        )

    # ── Cache Refresh (Reload from DB) ──────────────────────────────────────────

    def refresh_affinity_scores(self) -> bool:
        """
        Refresh in-memory affinity scores from database.
        
        Called periodically (e.g., between trading sessions) to pick up
        updated scores from usr_strategy_logs aggregation.
        
        Returns:
            True if successful
        """
        try:
            new_scores = self.storage.get_strategy_affinity_scores() or {}
            self.asset_scores = new_scores
            logger.info(f"[GATEKEEPER] Affinity scores refreshed: {len(new_scores)} assets")
            return True
        except Exception as e:
            logger.error(f"[GATEKEEPER] Error refreshing scores: {e}")
            return False

    # ── Diagnostics ─────────────────────────────────────────────────────────────

    def get_asset_score(self, asset: str) -> float:
        """Get current cached affinity score for an asset."""
        return self.asset_scores.get(asset, 0.0)

    def get_all_scores(self) -> Dict[str, float]:
        """Get all cached affinity scores (snapshot)."""
        return self.asset_scores.copy()

    def get_cache_stats(self) -> Dict[str, int]:
        """Return cache state for diagnostics."""
        return {
            'cached_assets': len(self.asset_scores),
            'whitelisted_usr_strategies': len(self.market_whitelists),
            'total_whitelist_entries': sum(len(v) for v in self.market_whitelists.values())
        }

    # ── Exploración Adaptativa (solo DEMO) ──────────────────────────────────────

    def enable_exploration_for_asset(
        self, strategy_id: str, asset: str, temp_score: float = 0.6
    ) -> None:
        """Añade un activo al pool de exploración con score temporal relajado."""
        normalized = _normalize_symbol(asset)
        self._exploration_scores.setdefault(strategy_id, {})[normalized] = temp_score
        logger.info(
            "[GATEKEEPER] Exploración habilitada: %s@%s (score=%.2f)",
            strategy_id, normalized, temp_score,
        )

    def disable_exploration_for_asset(self, strategy_id: str, asset: str) -> None:
        """Elimina un activo del pool de exploración."""
        normalized = _normalize_symbol(asset)
        scores = self._exploration_scores.get(strategy_id, {})
        scores.pop(normalized, None)
        self._frozen_exploration.get(strategy_id, set()).discard(normalized)
        self._exploration_pf.get(strategy_id, {}).pop(normalized, None)
        logger.info("[GATEKEEPER] Exploración deshabilitada: %s@%s", strategy_id, normalized)

    def is_exploration_active(self, strategy_id: str) -> bool:
        """Retorna True si la estrategia tiene activos en exploración."""
        return bool(self._exploration_scores.get(strategy_id))

    def freeze_exploration_asset(self, strategy_id: str, asset: str) -> None:
        """Congela un activo en exploración: bloquea ejecuciones futuras."""
        normalized = _normalize_symbol(asset)
        self._frozen_exploration.setdefault(strategy_id, set()).add(normalized)
        logger.info("[GATEKEEPER] Activo congelado (bajo PF): %s@%s", strategy_id, normalized)

    def update_exploration_profit_factor(
        self, strategy_id: str, asset: str, pf: float
    ) -> None:
        """Registra o actualiza el Profit Factor de un activo en exploración."""
        normalized = _normalize_symbol(asset)
        self._exploration_pf.setdefault(strategy_id, {})[normalized] = pf

    def rollback_low_pf_exploration_assets(
        self, strategy_id: str, pf_threshold: float = 1.2
    ) -> List[str]:
        """
        Elimina activos en exploración cuyo PF no supera el umbral.
        Retorna la lista de activos eliminados.
        """
        pf_map = self._exploration_pf.get(strategy_id, {})
        exploration = self._exploration_scores.get(strategy_id, {})
        removed: List[str] = []

        for asset in list(exploration.keys()):
            asset_pf = pf_map.get(asset, 0.0)
            if asset_pf < pf_threshold:
                self.disable_exploration_for_asset(strategy_id, asset)
                removed.append(asset)
                logger.info(
                    "[GATEKEEPER] Rollback exploración: %s eliminado (PF=%.2f < %.2f)",
                    asset, asset_pf, pf_threshold,
                )
        return removed

    def get_exploration_assets(self, strategy_id: str) -> List[str]:
        """Retorna los activos activos de exploración para la estrategia."""
        return list(self._exploration_scores.get(strategy_id, {}).keys())

    def log_state(self) -> None:
        """Log current state (for debugging)."""
        logger.info(f"[GATEKEEPER] Asset Scores (top 10):")
        sorted_scores = sorted(self.asset_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        for asset, score in sorted_scores:
            logger.info(f"  {asset}: {score:.2f}")
        
        if self.market_whitelists:
            logger.info(f"[GATEKEEPER] Market Whitelists:")
            for strategy_id, whitelist in self.market_whitelists.items():
                logger.info(f"  {strategy_id}: {whitelist}")
