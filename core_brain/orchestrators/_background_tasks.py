"""
Background task implementations for MainOrchestrator.

Extracted to comply with .ai_rules.md §4 (500-line limit).
All functions receive `orch: MainOrchestrator` as first parameter (explicit DI).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

logger = logging.getLogger(__name__)


async def check_closed_usr_positions(orch: "MainOrchestrator") -> None:
    """Check connectors for newly closed positions and process via TradeClosureListener."""
    try:
        from datetime import datetime
        from models.broker_event import BrokerEvent, BrokerEventType, BrokerTradeClosedEvent
        from models.signal import ConnectorType

        if not hasattr(orch.executor, "connectors"):
            return

        mt5_connector = orch.executor.connectors.get(ConnectorType.METATRADER5)
        if not mt5_connector or not mt5_connector.is_connected:
            return

        closed_usr_positions = mt5_connector.get_closed_usr_positions(hours=24)
        if not closed_usr_positions:
            return

        new_usr_positions = [
            p for p in closed_usr_positions
            if p["ticket"] > orch._last_checked_deal_ticket
        ]
        if not new_usr_positions:
            return

        logger.info(f"Found {len(new_usr_positions)} new closed usr_positions to process via Listener")

        for pos in new_usr_positions:
            signal_id = pos.get("signal_id")
            matching_signal = None

            if signal_id:
                matching_signal = orch.storage.get_signal_by_id(signal_id)

            if not matching_signal:
                sys_signals = orch.storage.get_sys_signals(limit=100)
                for sig in sys_signals:
                    if sig.get("order_id") == str(pos["ticket"]):
                        matching_signal = sig
                        break

            if not matching_signal:
                continue

            entry_time = (
                datetime.fromisoformat(matching_signal["timestamp"])
                if "timestamp" in matching_signal
                else datetime.now(timezone.utc)
            )
            if entry_time.tzinfo is None:
                entry_time = entry_time.replace(tzinfo=timezone.utc)

            exit_time = pos["close_time"]
            if isinstance(exit_time, datetime) and exit_time.tzinfo is None:
                exit_time = exit_time.replace(tzinfo=timezone.utc)

            trade_event = BrokerTradeClosedEvent(
                ticket=pos["ticket"],
                signal_id=matching_signal.get("id"),
                symbol=pos["symbol"],
                entry_price=pos.get("entry_price") or matching_signal.get("entry_price", 0.0),
                exit_price=pos["exit_price"],
                profit_loss=pos["profit"],
                pips=0.0,
                exit_reason=pos.get("exit_reason", "MT5_CLOSE"),
                entry_time=entry_time,
                exit_time=exit_time,
                broker_id="MT5",
                metadata={"ticket": pos["ticket"]},
            )
            event = BrokerEvent(
                event_type=BrokerEventType.TRADE_CLOSED,
                data=trade_event,
                timestamp=datetime.now(timezone.utc),
            )
            await orch.trade_closure_listener.handle_trade_closed_event(event)
            orch._last_checked_deal_ticket = max(orch._last_checked_deal_ticket, pos["ticket"])

    except Exception as e:
        logger.error(f"Error checking closed usr_positions: {e}")


async def check_and_run_weekly_dedup_learning(orch: "MainOrchestrator") -> None:
    """PHASE 3: Weekly dedup window auto-calibration (Sundays 23:00 UTC)."""
    try:
        now_utc = datetime.now(timezone.utc)
        is_sunday = now_utc.weekday() == 6
        is_learning_hour = now_utc.hour == 23
        hours_since_last = (now_utc - orch._last_dedup_learning).total_seconds() / 3600
        enough_time_passed = hours_since_last >= 24

        if is_sunday and is_learning_hour and enough_time_passed:
            logger.info("[PHASE3-DEDUP] Starting weekly dedup window learning cycle...")
            results = await orch.dedup_learner.run_weekly_learning_cycle()
            learned_count = len(results.get("learned", []))
            blocked_count = len(results.get("blocked", []))
            skipped_count = len(results.get("skipped", []))
            logger.info(
                f"[PHASE3-DEDUP] Learning cycle complete: "
                f"{learned_count} adaptations applied, "
                f"{blocked_count} blocked by governance, "
                f"{skipped_count} skipped"
            )
            orch._last_dedup_learning = now_utc
            for result in results.get("learned", []):
                logger.info(
                    f"[PHASE3-DEDUP] LEARNED: {result.symbol} {result.timeframe} "
                    f"({result.strategy}): {result.window_old}→{result.window_new} min"
                )
    except Exception as e:
        logger.error(f"[PHASE3-DEDUP] Error in weekly learning: {e}", exc_info=False)


async def check_and_run_weekly_shadow_evolution(orch: "MainOrchestrator") -> None:
    """SHADOW Feedback Loop — hourly evaluation of all active instances."""
    if not orch.shadow_manager:
        return

    try:
        now_utc = datetime.now(timezone.utc)
        if orch.last_shadow_evolution:
            hours_since_last = (now_utc - orch.last_shadow_evolution).total_seconds() / 3600
            enough_time_passed = hours_since_last >= 1.0
        else:
            enough_time_passed = True

        if not enough_time_passed:
            return

        logger.info("[SHADOW] Starting hourly SHADOW feedback loop cycle...")
        trace_base = f"TRACE_EVOLUTION_HOURLY_{now_utc.strftime('%Y%m%d_%H%M%S')}"
        try:
            results = orch.shadow_manager.evaluate_all_instances()
            promotions = results.get("promotions", [])
            kills = results.get("kills", [])
            quarantines = results.get("quarantines", [])
            monitors = results.get("monitors", [])
            total_evaluated = len(promotions) + len(kills) + len(quarantines) + len(monitors)
            logger.info(
                f"[SHADOW] Hourly cycle complete: "
                f"{len(promotions)} promoted, {len(kills)} DEAD, "
                f"{len(quarantines)} QUARANTINED, {len(monitors)} MONITOR "
                f"({total_evaluated} total) | {trace_base}"
            )
            orch.last_shadow_evolution = now_utc

            for promo in promotions:
                instance_id = promo.get("instance_id", "UNKNOWN")
                trace_id = promo.get("trace_id", "")
                logger.info(f"[SHADOW] PROMOTED: {instance_id} → REAL ({trace_id})")
                await emit_shadow_status_update(
                    orch, instance_id, "HEALTHY", "PASS", "PASS", "PASS",
                    {"profit_factor": 0, "win_rate": 0, "max_drawdown_pct": 0,
                     "consecutive_losses_max": 0, "trade_count": 0},
                    trace_id, "PROMOTE",
                )
            for kill in kills:
                instance_id = kill.get("instance_id", "UNKNOWN")
                trace_id = kill.get("trace_id", "")
                logger.warning(f"[SHADOW] DEAD: {instance_id} → {kill.get('reason')} ({trace_id})")
                await emit_shadow_status_update(
                    orch, instance_id, "DEAD", "FAIL", "UNKNOWN", "UNKNOWN",
                    {"profit_factor": 0, "win_rate": 0, "max_drawdown_pct": 0,
                     "consecutive_losses_max": 0, "trade_count": 0},
                    trace_id, "DEMOTE",
                )
            for quar in quarantines:
                instance_id = quar.get("instance_id", "UNKNOWN")
                trace_id = quar.get("trace_id", "")
                logger.warning(f"[SHADOW] QUARANTINED: {instance_id} ({trace_id})")
                await emit_shadow_status_update(
                    orch, instance_id, "QUARANTINED", "PASS", "FAIL", "UNKNOWN",
                    {"profit_factor": 0, "win_rate": 0, "max_drawdown_pct": 0,
                     "consecutive_losses_max": 0, "trade_count": 0},
                    trace_id, "QUARANTINE",
                )
            for mon in monitors:
                instance_id = mon.get("instance_id", "UNKNOWN")
                trace_id = mon.get("trace_id", "")
                logger.info(f"[SHADOW] MONITOR: {instance_id} ({trace_id})")
                await emit_shadow_status_update(
                    orch, instance_id, "MONITOR", "PASS", "PASS", "FAIL",
                    {"profit_factor": 0, "win_rate": 0, "max_drawdown_pct": 0,
                     "consecutive_losses_max": 0, "trade_count": 0},
                    trace_id, "MONITOR",
                )
            if orch.thought_callback:
                await orch.thought_callback(
                    f"Evolución SHADOW: {len(promotions)} promovidas, "
                    f"{len(kills)} eliminadas, {len(quarantines)} cuarentena, "
                    f"{len(monitors)} monitoreo.",
                    level="info",
                    module="SHADOW",
                )
        except Exception as e:
            logger.error(f"[SHADOW] Error during evolution: {e}", exc_info=True)

    except Exception as e:
        logger.error(f"[SHADOW] Error checking schedule: {e}", exc_info=False)


async def check_and_run_daily_backtest(orch: "MainOrchestrator") -> None:
    """EXEC-V5: Daily BacktestOrchestrator → SHADOW pipeline."""
    if not getattr(orch, "backtest_orchestrator", None):
        return

    try:
        now_utc = datetime.now(timezone.utc)
        if getattr(orch, "operational_mode_manager", None):
            from core_brain.operational_mode_manager import BacktestBudget
            budget = orch.operational_mode_manager.get_backtest_budget()
            if budget == BacktestBudget.DEFERRED:
                logger.info("[BACKTEST] Skipped — resources constrained (DEFERRED budget).")
                return
            ctx = orch.operational_mode_manager.current_context
            freqs = orch.operational_mode_manager.get_component_frequencies(ctx)
            cooldown_h = freqs.get("backtest_cooldown_h", 24.0)
        else:
            cooldown_h = 24.0

        if orch._last_backtest_run:
            hours_since = (now_utc - orch._last_backtest_run).total_seconds() / 3600
            if hours_since < cooldown_h:
                return

        logger.info("[BACKTEST] Starting daily BACKTEST → SHADOW pipeline...")
        summary = await orch.backtest_orchestrator.run_pending_strategies()
        orch._last_backtest_run = now_utc
        logger.info(
            "[BACKTEST] Daily cycle complete — evaluated=%d promoted=%d failed=%d skipped=%d",
            summary.get("evaluated", 0),
            summary.get("promoted", 0),
            summary.get("failed", 0),
            summary.get("skipped", 0),
        )
    except Exception as exc:
        logger.error("[BACKTEST] Error during daily backtest cycle: %s", exc, exc_info=False)


async def consume_oem_repair_flags(orch: "MainOrchestrator") -> None:
    """Consume and execute OEM repair flags from sys_config."""
    try:
        from datetime import timedelta
        sys_config = orch.storage.get_sys_config()
        consumed: Dict[str, Any] = {}

        if sys_config.get("oem_repair_force_backtest"):
            logger.info("[OEM-REPAIR] Flag force_backtest — reseteando cooldown")
            orch._last_backtest_run = None
            orch.storage.reset_backtest_cooldown_for_pending()
            consumed["oem_repair_force_backtest"] = None

        if sys_config.get("oem_repair_force_ohlc_reload") and orch.scanner:
            logger.info("[OEM-REPAIR] Flag force_ohlc_reload — reseteando tiempos de scan")
            orch.scanner.last_scan_time.clear()
            consumed["oem_repair_force_ohlc_reload"] = None

        if sys_config.get("oem_repair_force_ranking"):
            logger.info("[OEM-REPAIR] Flag force_ranking — forzando ciclo de ranking inmediato")
            orch._last_ranking_cycle = (
                datetime.now(timezone.utc) - timedelta(seconds=orch._ranking_interval + 10)
            )
            consumed["oem_repair_force_ranking"] = None

        if consumed:
            orch.storage.update_sys_config(consumed)
            logger.info("[OEM-REPAIR] %d flag(s) consumido(s): %s", len(consumed), list(consumed.keys()))

    except Exception as exc:
        logger.warning("[OEM-REPAIR] Error consumiendo repair flags (no bloquea ciclo): %s", exc)


async def emit_shadow_status_update(
    orch: "MainOrchestrator",
    instance_id: str,
    health_status: str,
    pilar1_status: str,
    pilar2_status: str,
    pilar3_status: str,
    metrics: dict,
    trace_id: str,
    action: str,
) -> None:
    """Broadcast SHADOW_STATUS_UPDATE WebSocket event to registered clients."""
    try:
        from core_brain.api.routers.shadow_ws import broadcast_shadow_update

        payload = {
            "event_type": "SHADOW_STATUS_UPDATE",
            "instance_id": instance_id,
            "health_status": health_status,
            "pilar1_status": pilar1_status,
            "pilar2_status": pilar2_status,
            "pilar3_status": pilar3_status,
            "metrics": metrics,
            "action": action,
            "trace_id": trace_id,
        }
        await broadcast_shadow_update(orch.user_id, payload)
        logger.debug(
            "[SHADOW_WS] Emitted SHADOW_STATUS_UPDATE for %s (%s), %s",
            instance_id, action, trace_id,
        )
    except Exception as e:
        logger.error(f"[SHADOW_WS] Error emitting shadow status update: {e}")
