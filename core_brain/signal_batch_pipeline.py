"""
Signal batch pipeline helpers extracted from SignalFactory.

Keeps SignalFactory lean while preserving the same behavior for batch signal generation.

HU 5.5 — FUNNEL OBSERVABILITY
  raw_zero_cause_category classifies WHY STAGE_RAW_SIGNAL_GENERATION == 0:
    INFRA          — upstream infra_skip_reason blocked the scan entirely
    INFRA_FAILURE  — strategy engine exceptions or system-level errors
    LEGIT_SSOT     — business/SSOT filters (affinity, whitelist, no setup, etc.)
    DATA_QUALITY   — missing regime/df/symbol in scan results
"""

import asyncio
import logging
from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd

if TYPE_CHECKING:
    from models.signal import Signal

logger = logging.getLogger(__name__)

# ── Cause classification sets (HU 5.5) ───────────────────────────────────────
# Taxonomy decision (HU 5.5 review fix):
#   strategy_engine_error  → runtime exception in an engine  → INFRA_FAILURE
#   no_strategy_engines    → engines dict empty at start     → LEGIT_SSOT
#     (empty dict is a known configuration state, not a runtime crash;
#      the system is behaving correctly by not generating signals)
_INFRA_FAILURE_CODES = frozenset({
    "strategy_engine_error",
})
_DATA_QUALITY_CODES = frozenset({
    "regime_missing",
    "df_missing",
    "symbol_missing",
})
_LEGIT_SSOT_CODES = frozenset({
    "no_signal_generated",
    "affinity_below_threshold",
    "symbol_not_in_affinity",
    "symbol_not_in_market_whitelist",
    "asset_disabled",
    "factory_duplicate",
    "execution_feedback_suppressed",
    "validator_rejected",
    "no_strategy_engines",  # empty engines dict = config state, not runtime crash
})


def _classify_raw_zero_cause(
    funnel_reasons: Counter,
    infra_skip_reason: Optional[str],
) -> str:
    """
    Return a canonical category explaining why STAGE_RAW_SIGNAL_GENERATION == 0.

    Priority (highest → lowest):
      1. INFRA          — infra_skip_reason present (upstream infra blocked the scan)
      2. INFRA_FAILURE  — any strategy_engine_error or similar runtime crash
      3. DATA_QUALITY   — scan inputs were missing/malformed (regime/df/symbol)
      4. LEGIT_SSOT     — all remaining: business/SSOT filters behaved correctly

    Returns one of: "INFRA" | "INFRA_FAILURE" | "DATA_QUALITY" | "LEGIT_SSOT"
    """
    if infra_skip_reason:
        return "INFRA"

    present_codes = set(funnel_reasons.keys())

    if present_codes & _INFRA_FAILURE_CODES:
        return "INFRA_FAILURE"

    if present_codes & _DATA_QUALITY_CODES:
        return "DATA_QUALITY"

    return "LEGIT_SSOT"


async def generate_usr_signals_batch_impl(
    factory: Any,
    scan_results: Dict[str, Dict],
    trace_id: Optional[str] = None,
    infra_skip_reason: Optional[str] = None,
) -> List["Signal"]:
    """
    Process scanner batch data and return flattened generated signals.

    This function intentionally receives `factory` to reuse injected collaborators
    and avoid duplicating orchestration logic.
    """
    logger.info(f"DEBUG: generate_usr_signals_batch called with {len(scan_results)} items")
    tasks = []
    funnel_reasons: Counter = Counter()
    stage_scan_in = len(scan_results)
    stage_scan_out = 0

    if not factory.strategy_engines:
        logger.error("DEBUG: No strategy engines in SignalFactory!")
        _no_engine_reasons: Counter = Counter({"no_strategy_engines": stage_scan_in})
        factory.last_funnel_summary = {
            "trace_id": trace_id,
            "timestamp": pd.Timestamp.utcnow().isoformat(),
            "stages": {
                "STAGE_SCAN_INPUT": {"in": stage_scan_in, "out": 0},
                "STAGE_RAW_SIGNAL_GENERATION": {"in": 0, "out": 0},
            },
            "reasons": dict(_no_engine_reasons),
            "infra_skip_reason": infra_skip_reason,
            "raw_zero_cause_category": _classify_raw_zero_cause(_no_engine_reasons, infra_skip_reason),
        }
        return []
    logger.info(f"DEBUG: Engines available: {list(factory.strategy_engines.keys())}")

    # FASE 4: Enabled symbol filter — SSOT via InstrumentManager (HU 3.9)
    if factory.instrument_manager is not None:
        try:
            enabled_symbols = factory.instrument_manager.get_enabled_symbols()
            logger.info(f"[FASE4] Enabled symbols (InstrumentManager): {len(enabled_symbols)}")
        except Exception as e:
            logger.warning(f"[FASE4] InstrumentManager.get_enabled_symbols() failed: {e} — no filter")
            enabled_symbols = None
    else:
        enabled_symbols = None  # No filter — generate for all scanned symbols

    skipped_count = 0

    for key, data in scan_results.items():
        regime = data.get("regime")
        df = data.get("df")
        symbol = data.get("symbol")
        timeframe = data.get("timeframe")

        if df is not None:
            logger.debug(
                f"[DEBUG][DF] {symbol}|{timeframe}: df.shape={getattr(df, 'shape', 'N/A')}, "
                f"columns={list(df.columns) if hasattr(df, 'columns') else 'N/A'}"
            )
        else:
            logger.debug(f"[DEBUG][DF] {symbol}|{timeframe}: df=None")

        if enabled_symbols is not None and symbol not in enabled_symbols:
            logger.debug(f"[FASE4] Skipping {symbol}: not in enabled asset config")
            skipped_count += 1
            funnel_reasons["asset_disabled"] += 1
            continue

        if regime and df is not None and symbol:
            stage_scan_out += 1
            provider_source = data.get("provider_source", "UNKNOWN")
            tasks.append(
                factory.generate_signal(
                    symbol,
                    df,
                    regime,
                    timeframe,
                    trace_id,
                    provider_source,
                    funnel_reasons,
                )
            )
        else:
            if not regime:
                funnel_reasons["regime_missing"] += 1
            if df is None:
                funnel_reasons["df_missing"] += 1
            if not symbol:
                funnel_reasons["symbol_missing"] += 1

    if skipped_count > 0:
        logger.info(f"[FASE4] Skipped {skipped_count} symbols not in asset configuration")

    if not tasks:
        empty_keys = []
        for key, data in scan_results.items():
            regime = data.get("regime")
            df = data.get("df")
            symbol = data.get("symbol")
            if not regime:
                empty_keys.append(f"{key}: regime=None")
            elif df is None:
                empty_keys.append(f"{key}: df=None")
            elif not symbol:
                empty_keys.append(f"{key}: symbol=None")

        raw_zero_cat = _classify_raw_zero_cause(funnel_reasons, infra_skip_reason)
        if infra_skip_reason:
            logger.warning(
                "[INFRA_CAUSE] STAGE_RAW_SIGNAL_GENERATION=0 — infra_skip_reason=%s "
                "cause_category=%s. Ciclo silenciado por infra, no por lógica de negocio.",
                infra_skip_reason,
                raw_zero_cat,
            )
        else:
            logger.warning(
                "[FUNNEL][RAW_ZERO] cause_category=%s. "
                "No tasks created: ningún instrumento elegible para señal. "
                "scan_results keys: %s. Problemas: %s",
                raw_zero_cat,
                list(scan_results.keys()),
                empty_keys if empty_keys else "Todos los datos faltan o vacíos.",
            )
        factory.last_funnel_summary = {
            "trace_id": trace_id,
            "timestamp": pd.Timestamp.utcnow().isoformat(),
            "stages": {
                "STAGE_SCAN_INPUT": {"in": stage_scan_in, "out": stage_scan_out},
                "STAGE_RAW_SIGNAL_GENERATION": {"in": stage_scan_out, "out": 0},
            },
            "reasons": dict(funnel_reasons),
            "infra_skip_reason": infra_skip_reason,
            "raw_zero_cause_category": raw_zero_cat,
        }
        return []

    results = await asyncio.gather(*tasks)

    all_usr_signals = []
    for batch in results:
        all_usr_signals.extend(batch)

    raw_generated_count = len(all_usr_signals)
    logger.info(
        "[FUNNEL][RAW] trace_id=%s raw_usr_signals_generated=%d",
        trace_id,
        raw_generated_count,
    )

    if all_usr_signals and factory.confluence_analyzer.enabled:
        all_usr_signals = factory.signal_conflict_analyzer.apply_confluence(
            all_usr_signals, scan_results
        )

    if all_usr_signals:
        all_usr_signals = factory.signal_trifecta_optimizer.optimize(
            all_usr_signals, scan_results
        )

    if all_usr_signals and factory.execution_feedback_collector:
        before_suppression = len(all_usr_signals)
        all_usr_signals = [s for s in all_usr_signals if not factory._should_suppress_signal(s)]
        if before_suppression > len(all_usr_signals):
            logger.info(
                f"[EXEC-FEEDBACK] Suppressed {before_suppression - len(all_usr_signals)} signals "
                "based on execution feedback learning"
            )

    if all_usr_signals:
        logger.info(
            f"Batch completado. {len(all_usr_signals)} señales generadas de "
            f"{len(scan_results)} instrumentos analizados (multi-timeframe)."
        )

    # Classify cause even when signals were generated (partial zero stages may exist)
    final_raw_zero_cat = (
        _classify_raw_zero_cause(funnel_reasons, infra_skip_reason)
        if raw_generated_count == 0
        else None
    )

    factory.last_funnel_summary = {
        "trace_id": trace_id,
        "timestamp": pd.Timestamp.utcnow().isoformat(),
        "stages": {
            "STAGE_SCAN_INPUT": {"in": stage_scan_in, "out": stage_scan_out},
            "STAGE_RAW_SIGNAL_GENERATION": {
                "in": stage_scan_out,
                "out": raw_generated_count,
            },
            "STAGE_POST_PROCESSING": {
                "in": raw_generated_count,
                "out": len(all_usr_signals),
            },
        },
        "reasons": dict(funnel_reasons),
        "infra_skip_reason": infra_skip_reason,
        "raw_zero_cause_category": final_raw_zero_cat,
    }
    if funnel_reasons:
        logger.info(
            "[FUNNEL][REASONS] trace_id=%s distribution=%s",
            trace_id,
            dict(sorted(funnel_reasons.items(), key=lambda item: item[1], reverse=True)),
        )
    logger.info("[FUNNEL][SIGNAL_FACTORY] %s", factory.last_funnel_summary)

    return all_usr_signals
