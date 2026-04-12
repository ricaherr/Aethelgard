"""
ShadowPenaltyInjector — Shadow Reality Engine (ETI-02/GAP-02)
=============================================================

Simula la ejecución de señales SHADOW con penalidad de spread dinámico
y persiste el resultado sintético en sys_trades (execution_mode='SHADOW').

Esto alimenta el pipeline de métricas de ShadowManager (3 Pilares) que
anteriormente quedaba vacío al no haber trades reales para instancias SHADOW.

Flujo:
  signal generada (SHADOW) → simulate_and_record(signal) →
  sys_trades[execution_mode='SHADOW'] → calculate_instance_metrics_from_sys_trades()
  → evaluate_all_instances() con métricas no-cero → Darwinismo activo.

Trace_ID: SHADOW-PENALTY-INJECTOR-2026-001
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class ShadowPenaltyInjector:
    """
    Simula ejecución de señales SHADOW con penalidad de spread.

    Responsabilidades:
    1. Calcular el precio de entrada degradado por el spread actual.
    2. Simular el resultado del trade basado en score de la señal.
    3. Persistir en sys_trades con execution_mode='SHADOW'.
    4. Garantizar idempotencia por signal_id (AC-3).

    Dependency Injection:
    - storage_manager: StorageManager (NO self-instantiated).
    - instrument_manager: Opcional, para spread máximo configurable por par.
    """

    # Fallback de spread en pips por prefijo de par (AC-4)
    DEFAULT_SPREAD_BY_PREFIX: Dict[str, float] = {
        "GBP": 2.5,
        "EUR": 1.5,
        "JPY": 2.0,
        "USD": 1.5,
        "XAU": 3.0,
        "BTC": 50.0,
    }
    DEFAULT_SPREAD_FALLBACK: float = 2.0

    # Umbral de score para simular WIN vs LOSS
    SCORE_WIN_THRESHOLD: float = 70.0

    def __init__(
        self,
        storage_manager: Any,
        instrument_manager: Optional[Any] = None,
    ) -> None:
        """
        Args:
            storage_manager: StorageManager con acceso a sys_trades y
                             sys_shadow_instances.
            instrument_manager: Opcional, para leer max_spread por par.
        """
        self.storage = storage_manager
        self.instrument_manager = instrument_manager

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers privados
    # ──────────────────────────────────────────────────────────────────────────

    def _resolve_spread_pips(
        self, symbol: str, spread_override: Optional[float]
    ) -> float:
        """
        Cadena de fallback para obtener el spread en pips:
          1. Override explícito (parámetro de la llamada).
          2. instrument_manager.get_max_spread(symbol).
          3. DEFAULT_SPREAD_BY_PREFIX según el prefijo del par.
          4. DEFAULT_SPREAD_FALLBACK (2.0 pips).
        """
        if spread_override is not None:
            return float(spread_override)

        if self.instrument_manager is not None:
            try:
                max_spread = self.instrument_manager.get_max_spread(symbol)
                if max_spread:
                    return float(max_spread)
            except Exception as e:
                logger.debug(f"[SHADOW-PENALTY] instrument_manager.get_max_spread failed: {e}")

        symbol_upper = symbol.upper()
        for prefix, pips in self.DEFAULT_SPREAD_BY_PREFIX.items():
            if prefix in symbol_upper:
                return pips

        return self.DEFAULT_SPREAD_FALLBACK

    def _pip_size(self, symbol: str) -> float:
        """Devuelve el tamaño del pip para el símbolo."""
        return 0.01 if "JPY" in symbol.upper() else 0.0001

    def _degraded_entry_price(
        self, entry_price: float, signal_type_value: str, spread_pips: float, symbol: str
    ) -> float:
        """
        Calcula el precio de entrada degradado por el spread.

        BUY:  el trader paga el ASK → precio sube (degradación hacia arriba).
        SELL: el trader vende al BID → precio baja (degradación hacia abajo).
        """
        pip = self._pip_size(symbol)
        if signal_type_value.upper() in ("BUY",):
            return entry_price + spread_pips * pip
        return entry_price - spread_pips * pip

    def _simulate_profit(
        self,
        signal: Any,
        degraded_entry: float,
    ) -> float:
        """
        Simula el resultado del trade basado en score y niveles SL/TP.

        - score >= SCORE_WIN_THRESHOLD → WIN (usa TP si está disponible)
        - score <  SCORE_WIN_THRESHOLD → LOSS (usa SL si está disponible)

        Usa múltiplos R fijos (1.5 / -1.0) cuando no hay SL/TP válidos.
        """
        score = float(signal.metadata.get("score", 60.0)) if signal.metadata else 60.0
        is_buy = signal.signal_type.value.upper() == "BUY"

        if score >= self.SCORE_WIN_THRESHOLD:
            # Simular WIN
            if signal.take_profit > 0:
                if is_buy:
                    return abs(signal.take_profit - degraded_entry)
                else:
                    return abs(degraded_entry - signal.take_profit)
            return 1.5  # R fijo

        else:
            # Simular LOSS
            if signal.stop_loss > 0:
                if is_buy:
                    return -abs(degraded_entry - signal.stop_loss)
                else:
                    return -abs(signal.stop_loss - degraded_entry)
            return -1.0  # R fijo

    def _get_instance_id_for_strategy(self, strategy_id: str) -> Optional[str]:
        """
        Busca el instance_id SHADOW activo para una estrategia dada.
        Retorna None si no existe ninguna instancia activa.
        """
        if not strategy_id:
            return None
        try:
            conn = self.storage._get_conn()
            row = conn.execute(
                """SELECT instance_id FROM sys_shadow_instances
                   WHERE strategy_id = ?
                     AND status NOT IN ('DEAD', 'PROMOTED_TO_REAL')
                   LIMIT 1""",
                (strategy_id,),
            ).fetchone()
            return row[0] if row else None
        except Exception as e:
            logger.debug(f"[SHADOW-PENALTY] instance_id lookup failed: {e}")
            return None

    def _is_already_recorded(self, signal_id: str) -> bool:
        """Comprueba si la señal ya tiene un trade simulado en sys_trades (AC-3)."""
        try:
            conn = self.storage._get_conn()
            row = conn.execute(
                """SELECT id FROM sys_trades
                   WHERE signal_id = ? AND execution_mode = 'SHADOW'
                   LIMIT 1""",
                (signal_id,),
            ).fetchone()
            return row is not None
        except Exception:
            return False

    # ──────────────────────────────────────────────────────────────────────────
    # API pública
    # ──────────────────────────────────────────────────────────────────────────

    async def simulate_and_record(
        self,
        signal: Any,
        spread_pips: Optional[float] = None,
    ) -> Optional[str]:
        """
        Simula la ejecución de una señal SHADOW y persiste en sys_trades.

        Args:
            signal: Signal object (SHADOW) generado por SignalFactory.
            spread_pips: Spread en pips. Si None, usa cadena de fallback.

        Returns:
            trade_id (str) si se registró correctamente.
            None si ya existía un registro para este signal_id (idempotencia).
        """
        metadata = signal.metadata or {}
        signal_id: Optional[str] = metadata.get("signal_id")
        strategy_id: str = metadata.get("strategy_id", "")

        # AC-3: Idempotencia
        if signal_id and self._is_already_recorded(signal_id):
            logger.debug(
                f"[SHADOW-PENALTY] signal_id={signal_id} ya registrado — skip"
            )
            return None

        spread = self._resolve_spread_pips(signal.symbol, spread_pips)
        degraded_entry = self._degraded_entry_price(
            signal.entry_price, signal.signal_type.value, spread, signal.symbol
        )
        profit = self._simulate_profit(signal, degraded_entry)
        instance_id = self._get_instance_id_for_strategy(strategy_id)

        uid = signal_id or uuid4().hex[:12]
        trade_id = f"SIM_{strategy_id}_{uid}"
        now = datetime.now(timezone.utc).isoformat()

        try:
            self.storage.save_sys_trade(
                {
                    "id": trade_id,
                    "signal_id": signal_id,
                    "instance_id": instance_id,
                    "account_id": None,  # no aplica a simulación shadow
                    "symbol": signal.symbol,
                    "direction": signal.signal_type.value,
                    "entry_price": degraded_entry,
                    "exit_price": degraded_entry,  # snapshot puntual
                    "profit": profit,
                    "exit_reason": "SHADOW_SIM",
                    "open_time": now,
                    "close_time": now,
                    "execution_mode": "SHADOW",
                    "strategy_id": strategy_id,
                    "order_id": None,
                }
            )
            logger.info(
                "[SHADOW-PENALTY] sim trade registrado: id=%s symbol=%s "
                "spread=%.1fpips degraded_entry=%.5f profit=%.5f",
                trade_id, signal.symbol, spread, degraded_entry, profit,
            )
            return trade_id

        except Exception as e:
            logger.error(f"[SHADOW-PENALTY] Error al persistir sim trade: {e}")
            return None
