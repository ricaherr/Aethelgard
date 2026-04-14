"""
Signal batch pipeline helpers extracted from SignalFactory.

Keeps SignalFactory lean while preserving the same behavior for batch signal generation.
"""

import asyncio
import logging
from collections import Counter
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd

if TYPE_CHECKING:
    from models.signal import Signal

logger = logging.getLogger(__name__)


async def generate_usr_signals_batch_impl(
    factory: Any,
    scan_results: Dict[str, Dict],
    trace_id: Optional[str] = None,
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
        factory.last_funnel_summary = {
            "trace_id": trace_id,
            "timestamp": pd.Timestamp.utcnow().isoformat(),
            "stages": {
                "STAGE_SCAN_INPUT": {"in": stage_scan_in, "out": 0},
                "STAGE_RAW_SIGNAL_GENERATION": {"in": 0, "out": 0},
            },
            "reasons": {"no_strategy_engines": stage_scan_in},
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
        logger.warning(
            "No tasks created: ningún instrumento elegible para señal. "
            f"scan_results keys: {list(scan_results.keys())}. "
            f"Problemas detectados: {empty_keys if empty_keys else 'Todos los datos faltan o vacíos.'}"
        )
        factory.last_funnel_summary = {
            "trace_id": trace_id,
            "timestamp": pd.Timestamp.utcnow().isoformat(),
            "stages": {
                "STAGE_SCAN_INPUT": {"in": stage_scan_in, "out": stage_scan_out},
                "STAGE_RAW_SIGNAL_GENERATION": {"in": stage_scan_out, "out": 0},
            },
            "reasons": dict(funnel_reasons),
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
    }
    if funnel_reasons:
        logger.info(
            "[FUNNEL][REASONS] trace_id=%s distribution=%s",
            trace_id,
            dict(sorted(funnel_reasons.items(), key=lambda item: item[1], reverse=True)),
        )
    logger.info("[FUNNEL][SIGNAL_FACTORY] %s", factory.last_funnel_summary)

    return all_usr_signals
