"""
OperationalModeManager — Adaptive Resource & Context Manager
=============================================================

Detecta el contexto operacional del sistema leyendo los modos activos en
sys_strategies y ajusta las frecuencias/activación de componentes en consecuencia.
Evalúa los recursos del servidor (psutil) para autorizar el presupuesto de backtest.

Contextos:
  BACKTEST_ONLY  — Todas las estrategias están en modo BACKTEST.
  SHADOW_ACTIVE  — Al menos 1 estrategia en SHADOW (ninguna en LIVE).
  LIVE_ACTIVE    — Al menos 1 estrategia en LIVE.

Presupuesto de backtest:
  AGGRESSIVE    — BACKTEST_ONLY + recursos OK → máxima velocidad de evaluación.
  MODERATE      — SHADOW_ACTIVE + recursos OK.
  CONSERVATIVE  — LIVE_ACTIVE + recursos OK → no robar CPU a la ejecución real.
  DEFERRED      — Recursos insuficientes (CPU > threshold o RAM > threshold).

Tabla de frecuencias de componentes:

  Componente            | BACKTEST_ONLY     | SHADOW_ACTIVE | LIVE_ACTIVE
  ----------------------|-------------------|---------------|------------
  Scanner               | 1/5 min (mínima)  | Normal        | Normal
  SignalFactory         | Suspendido        | Normal        | Normal
  ClosingMonitor        | Suspendido        | Normal        | Normal
  EdgeMonitor           | Reducida          | Normal        | Normal
  OperationalEdgeMonitor| Reducida          | Normal        | Normal
  BacktestOrchestrator  | Agresivo          | Moderado      | Conservador
  ConnectivityOrchest.  | Normal (siempre)  | Normal        | Normal
  AutonomousHealth      | Normal (siempre)  | Normal        | Normal

Trace_ID: EDGE-BKT-107-OPERATIONAL-MODE-MANAGER-2026-03-24
"""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

import psutil

from data_vault.storage import StorageManager

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────────────

class OperationalContext(str, Enum):
    BACKTEST_ONLY = "BACKTEST_ONLY"
    SHADOW_ACTIVE = "SHADOW_ACTIVE"
    LIVE_ACTIVE   = "LIVE_ACTIVE"


class BacktestBudget(str, Enum):
    AGGRESSIVE   = "AGGRESSIVE"
    MODERATE     = "MODERATE"
    CONSERVATIVE = "CONSERVATIVE"
    DEFERRED     = "DEFERRED"


# ── Default thresholds (overrideable via sys_config) ──────────────────────────

_DEFAULT_CPU_THRESHOLD  = 80.0   # % — above this → DEFERRED
_DEFAULT_RAM_THRESHOLD  = 90.0   # % — above this → DEFERRED

# Normal scanner interval (seconds) — used as baseline in frequency table
_SCANNER_INTERVAL_NORMAL_S = 60   # 1 minute
_SCANNER_INTERVAL_REDUCED_S = 300 # 5 minutes (BACKTEST_ONLY)


# ── OperationalModeManager ────────────────────────────────────────────────────

class OperationalModeManager:
    """
    Detects operational context from DB and exposes adaptive configuration
    to BacktestOrchestrator, MainOrchestrator, and AdaptiveBacktestScheduler.

    Usage::

        mgr = OperationalModeManager(storage=storage_manager)
        ctx = mgr.detect_context()           # OperationalContext
        budget = mgr.get_backtest_budget()   # BacktestBudget
        freqs = mgr.get_component_frequencies(ctx)
    """

    def __init__(
        self,
        storage: StorageManager,
        cpu_threshold: float = _DEFAULT_CPU_THRESHOLD,
        ram_threshold: float = _DEFAULT_RAM_THRESHOLD,
    ) -> None:
        self.storage       = storage
        self.cpu_threshold = cpu_threshold
        self.ram_threshold = ram_threshold
        self._current_context: Optional[OperationalContext] = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def current_context(self) -> OperationalContext:
        """Current cached context. Calls detect_context() if not yet set."""
        if self._current_context is None:
            return self.detect_context()
        return self._current_context

    def detect_context(self) -> OperationalContext:
        """
        Query sys_strategies and determine the current operational context.

        Priority: LIVE_ACTIVE > SHADOW_ACTIVE > BACKTEST_ONLY.
        Persists a MODE_TRANSITION event to sys_audit_logs when context changes.
        """
        modes = self._load_strategy_modes()

        if any(m == "LIVE" for m in modes):
            new_ctx = OperationalContext.LIVE_ACTIVE
        elif any(m == "SHADOW" for m in modes):
            new_ctx = OperationalContext.SHADOW_ACTIVE
        else:
            new_ctx = OperationalContext.BACKTEST_ONLY

        if new_ctx != self._current_context:
            self._persist_transition(self._current_context, new_ctx)
            self._current_context = new_ctx
            logger.info(
                "[MODE_MGR] Context transition: %s → %s",
                self._current_context, new_ctx,
            )

        return new_ctx

    def get_backtest_budget(self) -> BacktestBudget:
        """
        Evaluate CPU + RAM via psutil and return authorized backtest aggressiveness.

        Returns DEFERRED if resources are above configured thresholds,
        regardless of operational context.
        """
        cpu = psutil.cpu_percent(interval=None)
        ram = psutil.virtual_memory().percent

        if cpu > self.cpu_threshold or ram > self.ram_threshold:
            logger.debug(
                "[MODE_MGR] Resources constrained (CPU=%.1f%% RAM=%.1f%%) — DEFERRED.",
                cpu, ram,
            )
            return BacktestBudget.DEFERRED

        ctx = self._current_context or self.detect_context()
        if ctx == OperationalContext.BACKTEST_ONLY:
            return BacktestBudget.AGGRESSIVE
        if ctx == OperationalContext.SHADOW_ACTIVE:
            return BacktestBudget.MODERATE
        return BacktestBudget.CONSERVATIVE  # LIVE_ACTIVE

    def get_component_frequencies(self, context: OperationalContext) -> Dict[str, Any]:
        """
        Return a configuration dict that MainOrchestrator uses to set component
        intervals and enable/disable flags.

        Keys:
          scanner_interval_s          — polling interval for ScannerEngine
          scanner_interval_s_normal   — baseline (for comparison in tests)
          signal_factory_enabled      — bool
          closing_monitor_enabled     — bool
          edge_monitor_interval_s     — polling interval for EdgeMonitor
          operational_edge_interval_s — polling interval for OperationalEdgeMonitor
          backtest_cooldown_h         — cooldown hours for BacktestOrchestrator
          connectivity_enabled        — always True
        """
        normal = _SCANNER_INTERVAL_NORMAL_S
        reduced = _SCANNER_INTERVAL_REDUCED_S

        if context == OperationalContext.BACKTEST_ONLY:
            return {
                "scanner_interval_s":          reduced,
                "scanner_interval_s_normal":    normal,
                "signal_factory_enabled":       False,
                "closing_monitor_enabled":      False,
                "edge_monitor_interval_s":      120,   # reduced: 2 min
                "operational_edge_interval_s":  120,
                "backtest_cooldown_h":           1,    # aggressive: 1h cooldown
                "connectivity_enabled":         True,
                "autonomous_health_enabled":    True,
            }

        if context == OperationalContext.SHADOW_ACTIVE:
            return {
                "scanner_interval_s":          normal,
                "scanner_interval_s_normal":   normal,
                "signal_factory_enabled":      True,
                "closing_monitor_enabled":     True,
                "edge_monitor_interval_s":     60,
                "operational_edge_interval_s": 60,
                "backtest_cooldown_h":         12,   # moderate
                "connectivity_enabled":        True,
                "autonomous_health_enabled":   True,
            }

        # LIVE_ACTIVE
        return {
            "scanner_interval_s":          normal,
            "scanner_interval_s_normal":   normal,
            "signal_factory_enabled":      True,
            "closing_monitor_enabled":     True,
            "edge_monitor_interval_s":     60,
            "operational_edge_interval_s": 60,
            "backtest_cooldown_h":         24,   # conservative: standard 24h
            "connectivity_enabled":        True,
            "autonomous_health_enabled":   True,
        }

    # ── Internals ─────────────────────────────────────────────────────────────

    def _load_strategy_modes(self) -> list:
        """Return list of mode strings from sys_strategies."""
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute("SELECT mode FROM sys_strategies")
            return [row[0] for row in cursor.fetchall()]
        except Exception as exc:
            logger.warning("[MODE_MGR] Could not load strategy modes: %s", exc)
            return []

    def _persist_transition(
        self,
        from_ctx: Optional[OperationalContext],
        to_ctx: OperationalContext,
    ) -> None:
        """Insert a MODE_TRANSITION event into sys_audit_logs."""
        payload = json.dumps({
            "from": from_ctx.value if from_ctx else None,
            "to":   to_ctx.value,
            "ts":   datetime.now(timezone.utc).isoformat(),
        })
        try:
            conn   = self.storage._get_conn()
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO sys_audit_logs (event_type, payload) VALUES (?, ?)",
                ("MODE_TRANSITION", payload),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("[MODE_MGR] Could not persist mode transition: %s", exc)
