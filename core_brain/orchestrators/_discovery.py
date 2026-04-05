"""
Discovery and session-helper implementations extracted from MainOrchestrator.

Covers: broker discovery/provisioning, config loading, sleep interval,
shadow pool bootstrap, demo-account provisioning, and session helpers.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from core_brain.main_orchestrator import MainOrchestrator

logger = logging.getLogger(__name__)


def discover_brokers(orch: "MainOrchestrator") -> List[Dict]:
    """Discover all sys_brokers registered in the database."""
    try:
        return orch.storage.get_brokers()
    except Exception as e:
        logger.error(f"Error discovering sys_brokers: {e}")
        return []


def classify_brokers(orch: "MainOrchestrator", sys_brokers: List[Dict]) -> Dict[str, Dict]:
    """Classify brokers by auto-provision capability."""
    status: Dict[str, Dict] = {}
    for broker in sys_brokers:
        broker_id = broker.get("broker_id")
        auto = broker.get("auto_provision_available", False)
        status[broker_id] = {
            "name": broker.get("name"),
            "auto_provision": bool(auto),
            "manual_required": not bool(auto),
            "sys_platforms": broker.get("platforms_available"),
            "website": broker.get("website"),
            "status": "pending",
        }
    return status


async def provision_all_demo_accounts_impl(orch: "MainOrchestrator") -> None:
    """Provision master demo accounts for all auto-provision brokers."""
    from connectors.auto_provisioning import BrokerProvisioner
    from models.signal import MarketRegime
    from core_brain.coherence_monitor import CoherenceMonitor

    provisioner = BrokerProvisioner(storage=orch.storage)
    for broker_id, info in orch.broker_status.items():
        if info["auto_provision"]:
            logger.info(f"[EDGE] Provisionando cuenta demo para broker: {broker_id}")
            success, result = await provisioner.ensure_demo_account(broker_id)
            if success:
                orch.broker_status[broker_id]["status"] = "demo_ready"
                logger.info(f"[OK] Cuenta demo lista para {broker_id}")
            else:
                orch.broker_status[broker_id]["status"] = (
                    f"error: {result.get('error', 'unknown')}"
                )
                logger.warning(f"[ERROR] Error al provisionar demo {broker_id}: {result}")
        else:
            orch.broker_status[broker_id]["status"] = "manual_required"
            logger.info(f"[WARNING] {broker_id} requiere provisión manual")

    # NOTE: This block re-initializes runtime state — preserved for backward compatibility.
    from core_brain.main_orchestrator import SessionStats
    orch.stats = SessionStats.from_storage(orch.storage)
    orch.current_regime = MarketRegime.RANGE
    orch._shutdown_requested = False
    orch._active_usr_signals = []
    orch.coherence_monitor = CoherenceMonitor(storage=orch.storage)
    orchestrator_config = orch.config.get("orchestrator", {})
    orch.intervals = {
        MarketRegime.TREND: orchestrator_config.get("loop_interval_trend", 5),
        MarketRegime.RANGE: orchestrator_config.get("loop_interval_range", 30),
        MarketRegime.VOLATILE: orchestrator_config.get("loop_interval_volatile", 15),
        MarketRegime.SHOCK: orchestrator_config.get("loop_interval_shock", 60),
    }
    logger.info(
        f"MainOrchestrator initialized with intervals: "
        f"TREND={orch.intervals[MarketRegime.TREND]}s, "
        f"RANGE={orch.intervals[MarketRegime.RANGE]}s, "
        f"VOLATILE={orch.intervals[MarketRegime.VOLATILE]}s, "
        f"SHOCK={orch.intervals[MarketRegime.SHOCK]}s"
    )
    logger.info(f"Adaptive heartbeat: MIN={orch.MIN_SLEEP_INTERVAL}s when usr_signals active")


def load_config(orch: "MainOrchestrator", config_path: Optional[str]) -> Dict:
    """Load config: DB as SSOT, optional file merge for legacy compatibility."""
    config: Dict[str, Any] = {}
    try:
        db_config = orch.storage.get_dynamic_params()
        if isinstance(db_config, dict):
            config.update(db_config)
    except Exception as e:
        logger.warning("Failed to load dynamic params from DB: %s", e)

    if config_path:
        try:
            cfg_path = Path(config_path)
            if cfg_path.exists():
                with open(cfg_path, "r", encoding="utf-8") as f:
                    file_cfg = json.load(f)
                if isinstance(file_cfg, dict):
                    config.update(file_cfg)
        except Exception as e:
            logger.warning("Failed loading legacy config files: %s", e)

    return config


def get_sleep_interval_impl(orch: "MainOrchestrator") -> int:
    """Get sleep interval based on current regime with adaptive heartbeat."""
    base_interval = orch.intervals.get(orch.current_regime, 30)
    if orch._active_usr_signals:
        adaptive_interval = min(base_interval, orch.MIN_SLEEP_INTERVAL)
        logger.debug(
            f"Adaptive heartbeat active: {len(orch._active_usr_signals)} usr_signals, "
            f"interval reduced to {adaptive_interval}s"
        )
        return adaptive_interval
    return base_interval


async def initialize_shadow_pool_impl(
    orch: "MainOrchestrator",
    strategy_engines: Dict[str, Any],
    account_id: str = "DEMO_MT5_001",
    variations_per_strategy: int = 2,
) -> Dict[str, Any]:
    """Bootstrap SHADOW pool with automatic instance creation."""
    import uuid as _uuid

    if not orch.shadow_manager:
        logger.warning("[SHADOW] ShadowManager not initialized, skipping pool bootstrap")
        return {"created": 0, "skipped": len(strategy_engines)}

    param_variations = [
        {"risk_pct": 0.01, "regime_filters": ["TREND_UP", "EXPANSION"]},
        {"risk_pct": 0.015, "regime_filters": ["TREND_UP"]},
        {"risk_pct": 0.02, "regime_filters": []},
    ][:variations_per_strategy]

    created_count = 0
    skipped_count = 0
    failed_count = 0

    shadow_strategy_ids = orch.storage.get_shadow_mode_strategy_ids()
    existing_active = orch.shadow_manager.storage.list_active_instances()
    active_per_strategy: Dict[str, int] = {}
    for inst in existing_active:
        active_per_strategy[inst.strategy_id] = (
            active_per_strategy.get(inst.strategy_id, 0) + 1
        )

    for strategy_id, engine in strategy_engines.items():
        if strategy_id not in shadow_strategy_ids:
            logger.debug("[SHADOW] Skipping %s — not in SHADOW mode", strategy_id)
            skipped_count += 1
            continue

        already_active = active_per_strategy.get(strategy_id, 0)
        if already_active >= variations_per_strategy:
            logger.debug(
                f"[SHADOW] Skipping {strategy_id}: {already_active} active instances exist"
            )
            continue

        for variation_idx, params in enumerate(param_variations):
            try:
                instance_id = f"SHADOW_{strategy_id}_V{variation_idx}_{_uuid.uuid4().hex[:8]}"
                orch.shadow_manager.storage.create_shadow_instance(
                    instance_id=instance_id,
                    strategy_id=strategy_id,
                    account_id=account_id,
                    account_type="DEMO",
                    parameter_overrides={"risk_pct": params["risk_pct"]},
                    regime_filters=params.get("regime_filters", []),
                )
                logger.info(
                    f"[SHADOW] Created pool instance {strategy_id} "
                    f"(V{variation_idx}, risk={params['risk_pct']:.2%})"
                )
                created_count += 1
            except Exception as e:
                logger.error(f"[SHADOW] Failed to create instance for {strategy_id}: {e}")
                failed_count += 1

    logger.info(
        f"[SHADOW] Pool bootstrap complete: {created_count} created, "
        f"{skipped_count} skipped, {failed_count} failed"
    )
    return {"created": created_count, "skipped": skipped_count, "failed": failed_count}


async def ensure_optimal_demo_accounts_impl(orch: "MainOrchestrator") -> None:
    """Provision demo accounts only when needed (optimal provisioning)."""
    from connectors.auto_provisioning import BrokerProvisioner

    provisioner = BrokerProvisioner(storage=orch.storage)
    for broker_id, info in orch.broker_status.items():
        if info["auto_provision"]:
            if not provisioner.has_demo_account(broker_id):
                logger.info(f"[EDGE] No existe cuenta demo válida para {broker_id}. Provisionando...")
                success, result = await provisioner.ensure_demo_account(broker_id)
                if success:
                    orch.broker_status[broker_id]["status"] = "demo_ready"
                    logger.info(f"[OK] Cuenta demo lista para {broker_id}")
                else:
                    orch.broker_status[broker_id]["status"] = (
                        f"error: {result.get('error', 'unknown')}"
                    )
                    logger.warning(f"[ERROR] Error al provisionar demo {broker_id}: {result}")
            else:
                logger.info(f"[EDGE] Ya existe cuenta demo válida para {broker_id}.")
        else:
            orch.broker_status[broker_id]["status"] = "manual_required"
            logger.info(f"[WARNING] {broker_id} requiere provisión manual")
