"""
Scan orchestration methods extracted from MainOrchestrator.

TRACE_ID: OPTION-A-SCAN-ORCHESTRATION-2026-03-11
Extracted to comply with .ai_rules.md §4 (500-line limit).
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

logger = logging.getLogger(__name__)


def update_regime_from_scan(
    orch: "MainOrchestrator",
    scan_results: Dict[str, Any],
) -> None:
    """Update current regime to the most aggressive found across all symbols."""
    if not scan_results:
        return

    from models.signal import MarketRegime

    regime_priority: Dict[Any, int] = {
        MarketRegime.SHOCK: 4,
        MarketRegime.VOLATILE: 3,
        MarketRegime.TREND: 2,
        MarketRegime.RANGE: 1,
    }

    max_priority = 0
    new_regime = MarketRegime.RANGE

    for _, regime in scan_results.items():
        priority = regime_priority.get(regime, 1)
        if priority > max_priority:
            max_priority = priority
            new_regime = regime

    if new_regime != orch.current_regime:
        logger.info(f"Regime changed: {orch.current_regime} -> {new_regime}")
        orch.current_regime = new_regime


def persist_tick_timestamp(orch: "MainOrchestrator", tick_ts: str) -> None:
    """Persist last_market_tick_ts to sys_config with retry on DB lock."""
    max_retries = 3
    for attempt in range(max_retries):
        try:
            orch.storage.update_sys_config({"last_market_tick_ts": tick_ts})
            logger.debug(f"[TELEMETRY] last_market_tick_ts persisted: {tick_ts}")
            return
        except Exception as exc:
            if "locked" in str(exc).lower() and attempt < max_retries - 1:
                sleep_time = 0.5 * (attempt + 1)
                logger.warning(
                    f"[TELEMETRY] DB locked on retry {attempt+1}/{max_retries}, "
                    f"sleeping {sleep_time}s..."
                )
                time.sleep(sleep_time)
            else:
                logger.warning(
                    f"[TELEMETRY] Could not write last_market_tick_ts after "
                    f"{attempt+1} attempts: {exc}"
                )


def persist_scan_telemetry(
    orch: "MainOrchestrator",
    scan_results_with_data: Dict,
) -> None:
    """Persist scan telemetry (tick timestamp + ADX) required by IntegrityGuard."""
    persist_tick_timestamp(orch, datetime.now(timezone.utc).isoformat())

    valid_adx_values = [
        float(data["metrics"].get("adx") or 0)
        for data in scan_results_with_data.values()
        if isinstance(data.get("metrics"), dict) and (data["metrics"].get("adx") or 0) > 0
    ]
    if not valid_adx_values:
        return
    try:
        dynamic_params = orch.storage.get_dynamic_params() or {}
        dynamic_params["adx"] = max(valid_adx_values)
        orch.storage.update_dynamic_params(dynamic_params)
        logger.debug(f"[TELEMETRY] ADX updated: {dynamic_params['adx']}")
    except Exception as exc:
        logger.warning(f"[TELEMETRY] Could not write adx to dynamic_params: {exc}")


def get_scan_schedule(orch: "MainOrchestrator") -> Dict[str, float]:
    """Build per-symbol|timeframe scan intervals based on current regimes."""
    from models.signal import MarketRegime

    schedule: Dict[str, float] = {}
    try:
        for symbol in orch.scanner.assets:
            for tf in orch.scanner.active_timeframes:
                key = f"{symbol}|{tf}"
                regime = orch.scanner.last_regime.get(key, MarketRegime.NORMAL)
                if regime in [MarketRegime.TREND, MarketRegime.CRASH]:
                    interval = 1.0
                elif regime in [MarketRegime.RANGE, MarketRegime.NORMAL]:
                    interval = 10.0
                elif regime == MarketRegime.VOLATILE:
                    interval = 5.0
                else:
                    interval = 10.0
                schedule[key] = interval
    except Exception as e:
        logger.warning(f"[OPTION-A] Error building scan schedule: {e}")
        for symbol in getattr(orch.scanner, "assets", []):
            for tf in getattr(orch.scanner, "active_timeframes", []):
                schedule[f"{symbol}|{tf}"] = 10.0
    return schedule


def should_scan_now(
    orch: "MainOrchestrator",
    schedule: Dict[str, float],
) -> List[Tuple[str, str]]:
    """Determine which assets need scanning based on schedule and last scan time."""
    to_scan: List[Tuple[str, str]] = []
    now = time.monotonic()
    try:
        for key, interval in schedule.items():
            symbol, tf = key.split("|")
            last_scan_time = orch.scanner.last_scan_time.get(key, 0.0)
            if now - last_scan_time >= interval:
                to_scan.append((symbol, tf))
    except Exception as e:
        logger.warning(f"[OPTION-A] Error checking scan readiness: {e}")
    return to_scan


async def request_scan(
    orch: "MainOrchestrator",
    assets_to_scan: List[Tuple[str, str]],
) -> Dict[str, Dict[str, Any]]:
    """Request ScannerEngine to execute a scan for specific assets."""
    if not assets_to_scan:
        return {}

    logger.info(f"[OPTION-A] Requesting scan for {len(assets_to_scan)} asset-timeframe pairs")
    try:
        new_results = await asyncio.to_thread(orch.scanner.execute_scan, assets_to_scan)
        logger.info(f"[OPTION-A] Scan completed: {len(new_results)} results")
        return new_results
    except Exception as e:
        logger.error(f"[OPTION-A] Error requesting scan: {e}")
        return {}
