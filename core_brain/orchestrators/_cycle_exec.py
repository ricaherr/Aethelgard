"""
Economic veto phase and signal filter phase extracted from MainOrchestrator.run_single_cycle().

run_econ_phase   → check economic calendar, set veto/caution symbols → False to abort
run_signal_filter → generate, validate, filter signals → None to abort
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, List, Optional

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

from core_brain.orchestrators._types import ScanBundle

logger = logging.getLogger(__name__)


async def run_econ_phase(orch: "MainOrchestrator", bundle: ScanBundle) -> bool:
    """
    PHASE 8: Economic Calendar Veto.

    Sets orch._econ_veto_symbols and orch._econ_caution_symbols.
    Returns False (with stats.cycles_completed incremented) if all symbols are vetoed.
    Returns True to continue into signal generation.
    """
    import asyncio

    trace_id = bundle.trace_id
    scan_results = bundle.scan_results

    if not orch.economic_integration:
        orch._econ_veto_symbols = set()
        orch._econ_caution_symbols = set()
        await orch._sync_economic_caution_state(set(), trace_id)  # thin wrapper
        return True

    try:
        current_time = datetime.now(timezone.utc)
        veto_symbols: set = set()
        caution_symbols: set = set()

        for symbol in scan_results.keys():
            status = await orch.economic_integration.get_trading_status(symbol, current_time)
            if not status.get("is_tradeable", True):
                veto_symbols.add(symbol)
                reason = status.get("reason", "Economic veto")
                logger.warning(
                    f"[ECON-VETO] {symbol}: {reason} "
                    f"(Next: {status.get('next_event')} @ {status.get('time_to_event', 0):.0f}s)"
                )
                if status.get("restriction_level") == "BLOCK":
                    logger.warning(
                        f"[ECON-VETO] HIGH IMPACT: Adjusting open positions for {symbol} to Break-Even"
                    )
                    try:
                        await orch.risk_manager.activate_lockdown(
                            symbol=symbol,
                            reason=f'ECON_VETO: {status.get("next_event", "UNKNOWN")}',
                            trace_id=trace_id,
                        )
                        logger.info(f"[ECON-VETO] Lockdown activated for {symbol}")
                    except Exception as e:
                        logger.error(
                            f"[ECON-VETO] Failed to activate lockdown for {symbol}: {e}",
                            exc_info=True,
                        )
            elif status.get("restriction_level") == "CAUTION":
                caution_symbols.add(symbol)
                logger.info(
                    f"[ECON-VETO] {symbol}: MEDIUM impact (unit R @ 50%). "
                    f"Next: {status.get('next_event')}"
                )

        # If ALL symbols are vetoed: sleep and abort cycle
        if veto_symbols and len(veto_symbols) == len(scan_results):
            earliest_recovery = None
            for symbol in veto_symbols:
                status = await orch.economic_integration.get_trading_status(symbol, current_time)
                if status.get("time_to_event") is not None:
                    post_buffer_secs = status.get("buffer_post_minutes", 0) * 60
                    time_to_tradeable = status.get("time_to_event", 0) + post_buffer_secs
                    if earliest_recovery is None or time_to_tradeable < earliest_recovery:
                        earliest_recovery = time_to_tradeable

            if earliest_recovery and earliest_recovery > 0:
                sleep_duration = min(earliest_recovery, 60)
                logger.info(
                    f"[ECON-VETO] SYSTEM_IDLE: All symbols vetoed. "
                    f"Sleeping {sleep_duration:.0f}s."
                )
                if orch.thought_callback:
                    await orch.thought_callback(
                        f"Pausa prevista por evento económico. Reanudando en {int(sleep_duration)}s.",
                        module="ECON",
                        level="info",
                    )
                await asyncio.sleep(min(sleep_duration, orch.MIN_SLEEP_INTERVAL))
            orch.stats.cycles_completed += 1
            return False

        orch._econ_veto_symbols = veto_symbols
        orch._econ_caution_symbols = caution_symbols
        await orch._sync_economic_caution_state(caution_symbols, trace_id)  # thin wrapper

    except Exception as e:
        logger.error(f"[ECON-VETO] Error in economic check: {e}", exc_info=True)
        # Fail-open: continue trading
        orch._econ_veto_symbols = set()
        orch._econ_caution_symbols = set()
        await orch._sync_economic_caution_state(set(), trace_id)  # thin wrapper

    return True


async def run_signal_filter(
    orch: "MainOrchestrator", bundle: ScanBundle
) -> Optional[List[Any]]:
    """
    Generate signals, validate with risk manager, apply module toggles and filters.

    Returns a list of validated signals, or None (with cycles_completed incremented)
    to abort the cycle before execution.
    """
    # HU 5.5 — Defensive reset: clear GK veto reasons at start of every filter phase
    # so early-return paths (risk, lockdown, econ-veto) never bleed reasons into the
    # next cycle's funnel (fixes stale-state bug when execute phase is skipped).
    orch._gk_veto_reasons = {}

    scan_results_with_data = bundle.scan_results_with_data
    trace_id = bundle.trace_id

    # Generate signals — propagate infra cause from scan phase for funnel observability
    usr_signals = await orch.signal_factory.generate_usr_signals_batch(
        scan_results_with_data,
        trace_id,
        infra_skip_reason=getattr(bundle, "infra_skip_reason", None),
    )
    orch.storage.update_module_heartbeat("signal_factory")

    if not usr_signals:
        logger.debug("No usr_signals generated")
        if orch.thought_callback:
            await orch.thought_callback(
                "Silencio en el mercado. No se detectan setups institucionales.",
                module="ALPHA",
            )
        orch._active_usr_signals.clear()
        orch.stats.cycles_completed += 1
        return None

    if orch.thought_callback:
        await orch.thought_callback(
            f"Setup detectado: {len(usr_signals)} señales en pipeline alpha.", module="ALPHA"
        )
    logger.info(f"Generated {len(usr_signals)} usr_signals")
    orch.stats.usr_signals_processed += len(usr_signals)
    orch.stats.usr_signals_generated += len(usr_signals)

    # Risk validation
    validated: List[Any] = []
    for signal in usr_signals:
        is_valid = True
        if hasattr(orch.risk_manager, "validate_signal"):
            is_valid = bool(orch.risk_manager.validate_signal(signal))
        if is_valid:
            validated.append(signal)
        else:
            logger.info(
                f"Signal {signal.symbol} rejected by risk manager (Trace: {signal.trace_id})"
            )

    if not validated:
        logger.info("No usr_signals passed risk validation")
        orch._active_usr_signals.clear()
        orch.stats.cycles_completed += 1
        return None

    logger.info(f"{len(validated)} usr_signals passed risk validation")
    orch.stats.usr_signals_risk_passed += len(validated)
    orch.stats.usr_signals_vetoed += len(usr_signals) - len(validated)
    orch.storage.update_module_heartbeat("risk_manager")
    orch._active_usr_signals = validated

    # MODULE TOGGLE: Executor
    if not orch.modules_enabled_global.get("executor", True):
        logger.info(
            f"[TOGGLE] executor deshabilitado — "
            f"{len(validated)} señales aprobadas NO ejecutadas"
        )
        orch.stats.cycles_completed += 1
        orch._active_usr_signals.clear()
        return None

    # EDGE Auto-Correction every 10 cycles
    if orch.stats.cycles_completed % 10 == 0:
        from core_brain.health import HealthManager
        lockdown_check = HealthManager().auto_correct_lockdown(orch.storage, orch.risk_manager)
        if lockdown_check.get("action_taken") == "LOCKDOWN_DEACTIVATED":
            logger.warning(f"[AUTO] EDGE AUTO-CORRECTION: {lockdown_check['reason']}")

    # Lockdown guard
    if orch.risk_manager.is_lockdown_active():
        logger.warning("Lockdown mode active. Skipping signal execution.")
        orch.stats.cycles_completed += 1
        return None

    # Economic veto filter
    econ_veto_symbols = getattr(orch, "_econ_veto_symbols", set())
    filtered: List[Any] = []
    for signal in validated:
        if signal.symbol in econ_veto_symbols:
            logger.info(
                f"[ECON-VETO-EXEC] Signal for {signal.symbol} blocked: Economic veto active"
            )
            orch.stats.usr_signals_vetoed += 1
            if orch.economic_integration:
                try:
                    current_status = await orch.economic_integration.get_trading_status(
                        signal.symbol, datetime.now(timezone.utc)
                    )
                    if current_status.get("restriction_level") == "BLOCK":
                        logger.warning(
                            f"[ECON-VETO-EXEC] HIGH IMPACT: adjusting positions for {signal.symbol}"
                        )
                        try:
                            await orch.risk_manager.activate_lockdown(
                                symbol=signal.symbol,
                                reason=f'ECON_VETO: {current_status.get("next_event", "UNKNOWN")}',
                                trace_id=getattr(signal, "trace_id", None),
                            )
                        except Exception as e:
                            logger.error(f"[ECON-VETO-EXEC] Failed to activate lockdown: {e}", exc_info=True)
                        breakeven_result = await orch.risk_manager.adjust_stops_to_breakeven(
                            symbol=signal.symbol,
                            reason=f"HIGH impact: {current_status.get('next_event', 'UNKNOWN')}",
                        )
                        if breakeven_result.get("adjusted", 0) > 0:
                            logger.info(
                                f"[ECON-VETO-EXEC] Adjusted {breakeven_result['adjusted']} positions to BE"
                            )
                except Exception as e:
                    logger.error(f"[ECON-VETO-EXEC] Error adjusting SL to BE: {e}")
        else:
            filtered.append(signal)
    validated = filtered

    # CAUTION volume reduction (MEDIUM impact)
    econ_caution_symbols = getattr(orch, "_econ_caution_symbols", set())
    if econ_caution_symbols:
        caution_multipliers: dict = {}
        try:
            caution_multipliers = orch.storage.get_sys_config()
        except Exception as e:
            logger.warning(f"[ECON-CAUTION] Failed loading risk multipliers: {e}")

        for i, sig in enumerate(validated):
            if sig.symbol in econ_caution_symbols and sig.signal_type.value in ("BUY", "SELL"):
                old_vol = sig.volume
                multiplier_key = f"econ_risk_multiplier_{sig.symbol}"
                try:
                    risk_multiplier = float(caution_multipliers.get(multiplier_key, 0.5))
                except (TypeError, ValueError):
                    risk_multiplier = 0.5
                if risk_multiplier <= 0.0 or risk_multiplier > 1.0:
                    risk_multiplier = 0.5
                new_vol = max(round(old_vol * risk_multiplier, 2), 0.01)
                validated[i] = sig.model_copy(update={"volume": new_vol})
                logger.info(
                    f"[ECON-CAUTION] {sig.symbol} volume {old_vol}→{new_vol} "
                    f"(MEDIUM impact, multiplier={risk_multiplier})"
                )

    if not validated:
        logger.info("All usr_signals filtered by economic veto")
        orch.stats.cycles_completed += 1
        return None

    # StrategyGatekeeper pre-execution filter
    if orch.strategy_gatekeeper is not None:
        _gk_min = orch.config.get("gatekeeper_min_threshold", 0.0)
        gatekeeper_passed: List[Any] = []
        gk_veto_reasons: dict = {}
        for signal in validated:
            strategy_id = getattr(signal, "strategy_id", None) or "default"
            allowed, gk_reason = orch.strategy_gatekeeper.can_execute_on_tick_with_reason(
                asset=signal.symbol,
                min_threshold=_gk_min,
                strategy_id=strategy_id,
            )
            if allowed:
                gatekeeper_passed.append(signal)
            else:
                logger.info(
                    "[GATEKEEPER] Signal vetoed: %s strategy=%s reason=%s",
                    signal.symbol,
                    strategy_id,
                    gk_reason,
                )
                orch.stats.usr_signals_vetoed += 1
                gk_veto_reasons[gk_reason] = gk_veto_reasons.get(gk_reason, 0) + 1

        vetoed_count = len(validated) - len(gatekeeper_passed)
        if vetoed_count:
            logger.info("[GATEKEEPER] %d signal(s) vetoed reasons=%s", vetoed_count, gk_veto_reasons)

        # Propagate gatekeeper reason codes so _cycle_trade can merge them into funnel
        orch._gk_veto_reasons = gk_veto_reasons
        validated = gatekeeper_passed

    if not validated:
        logger.info("[GATEKEEPER] All signals vetoed by StrategyGatekeeper")
        orch.stats.cycles_completed += 1
        return None

    return validated
