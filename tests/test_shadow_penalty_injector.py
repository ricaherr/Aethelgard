"""
ETI-02 / GAP-02 — Shadow Reality Engine: ShadowPenaltyInjector
==============================================================

TDD: Los 4 tests deben FALLAR antes de crear shadow_penalty_injector.py.

AC-1: Señal SHADOW → sys_trades recibe entrada con precio degradado
      (entry_price + spread_pips * pip_size para BUY)
AC-2: Instancia con ≥1 shadow trade → métricas no-cero desde sys_trades
AC-3: simulate_and_record() es idempotente (mismo signal_id → 1 sola entrada)
AC-4: Sin spread explícito → usa fallback DEFAULT_SPREAD_BY_PREFIX
"""
import pytest
import sqlite3
from datetime import datetime, timezone
from unittest.mock import MagicMock

from core_brain.services.shadow_penalty_injector import ShadowPenaltyInjector
from data_vault.shadow_db import ShadowStorageManager
from models.signal import Signal, SignalType, ConnectorType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_buy_signal(
    symbol: str = "EURUSD",
    entry_price: float = 1.08500,
    stop_loss: float = 1.08000,
    take_profit: float = 1.09500,
    score: float = 75.0,
    signal_id: str = "sig-001",
    strategy_id: str = "S-0001",
) -> Signal:
    return Signal(
        symbol=symbol,
        signal_type=SignalType.BUY,
        confidence=0.80,
        connector_type=ConnectorType.METATRADER5,
        entry_price=entry_price,
        stop_loss=stop_loss,
        take_profit=take_profit,
        metadata={
            "signal_id": signal_id,
            "strategy_id": strategy_id,
            "score": score,
        },
    )


def _insert_shadow_instance(conn: sqlite3.Connection, instance_id: str, strategy_id: str) -> None:
    """Inserta una instancia SHADOW mínima para que el lookup de instance_id funcione."""
    conn.execute(
        """INSERT OR IGNORE INTO sys_shadow_instances
           (instance_id, strategy_id, account_id, account_type,
            parameter_overrides, regime_filters, birth_timestamp, status,
            created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            instance_id, strategy_id, "acct-001", "DEMO",
            "{}", "[]",
            datetime.now(timezone.utc).isoformat(),
            "INCUBATING",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# AC-1: entrada en sys_trades con precio degradado por spread
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_penalty_injector_escribe_entrada_con_spread_degradado(storage):
    """
    AC-1: Para una señal BUY, simulate_and_record() debe escribir en sys_trades
    un entry_price >= signal.entry_price + spread * pip_size (precio degradado hacia arriba).
    """
    signal = _make_buy_signal(entry_price=1.08500, symbol="EURUSD")
    SPREAD_PIPS = 1.5
    PIP_SIZE = 0.0001
    expected_degraded = 1.08500 + SPREAD_PIPS * PIP_SIZE  # 1.08515

    injector = ShadowPenaltyInjector(storage_manager=storage)

    trade_id = await injector.simulate_and_record(signal, spread_pips=SPREAD_PIPS)

    assert trade_id is not None, "simulate_and_record() debe retornar un trade_id"

    conn = storage._get_conn()
    row = conn.execute(
        "SELECT entry_price FROM sys_trades WHERE id = ?", (trade_id,)
    ).fetchone()

    assert row is not None, f"No se encontró trade {trade_id} en sys_trades"
    assert row[0] >= expected_degraded - 1e-9, (
        f"entry_price={row[0]:.5f} debe ser >= {expected_degraded:.5f} (degradado por spread)"
    )


# ---------------------------------------------------------------------------
# AC-2: instancia con ≥1 shadow trade → métricas no-cero
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_penalty_injector_instancia_evalua_con_metricas_no_cero(storage):
    """
    AC-2: Después de simulate_and_record(), la instancia SHADOW debe producir
    métricas con total_trades_executed > 0 al consultar sys_trades.
    """
    instance_id = "inst-test-0001"
    strategy_id = "S-0002"

    signal = _make_buy_signal(
        signal_id="sig-ac2-001",
        strategy_id=strategy_id,
        score=80.0,
    )

    conn = storage._get_conn()
    _insert_shadow_instance(conn, instance_id, strategy_id)

    injector = ShadowPenaltyInjector(storage_manager=storage)
    await injector.simulate_and_record(signal, spread_pips=1.5)

    shadow_storage = ShadowStorageManager(storage)
    metrics = shadow_storage.calculate_instance_metrics_from_sys_trades(instance_id)

    assert metrics.total_trades_executed > 0, (
        f"Después de simulate_and_record(), total_trades_executed debe ser > 0, "
        f"fue {metrics.total_trades_executed}"
    )


# ---------------------------------------------------------------------------
# AC-3: idempotencia — mismo signal_id no genera entrada duplicada
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_penalty_injector_es_idempotente(storage):
    """
    AC-3: Llamar simulate_and_record() dos veces con el mismo signal_id
    debe resultar en exactamente 1 fila en sys_trades, no 2.
    """
    signal = _make_buy_signal(signal_id="sig-idem-001", strategy_id="S-0003")

    injector = ShadowPenaltyInjector(storage_manager=storage)

    trade_id_1 = await injector.simulate_and_record(signal, spread_pips=1.5)
    trade_id_2 = await injector.simulate_and_record(signal, spread_pips=1.5)

    assert trade_id_1 is not None, "Primera llamada debe retornar trade_id"
    assert trade_id_2 is None, (
        "Segunda llamada con mismo signal_id debe retornar None (idempotente)"
    )

    conn = storage._get_conn()
    count = conn.execute(
        "SELECT COUNT(*) FROM sys_trades WHERE signal_id = ?", ("sig-idem-001",)
    ).fetchone()[0]

    assert count == 1, f"Debe existir exactamente 1 fila en sys_trades, encontradas: {count}"


# ---------------------------------------------------------------------------
# AC-4: fallback de spread cuando no hay instrument_manager ni override
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_shadow_penalty_injector_usa_fallback_spread_si_no_disponible(storage):
    """
    AC-4: Sin instrument_manager y sin spread_pips explícito, el injector
    debe usar DEFAULT_SPREAD_BY_PREFIX y aún así registrar el trade con éxito.
    """
    signal = _make_buy_signal(
        symbol="GBPUSD",
        signal_id="sig-fallback-001",
        strategy_id="S-0004",
    )

    # Sin instrument_manager inyectado — debe usar fallback interno
    injector = ShadowPenaltyInjector(storage_manager=storage, instrument_manager=None)

    trade_id = await injector.simulate_and_record(signal)  # sin spread_pips

    assert trade_id is not None, (
        "El injector debe registrar el trade incluso sin spread explícito (fallback)"
    )

    conn = storage._get_conn()
    row = conn.execute(
        "SELECT entry_price, execution_mode FROM sys_trades WHERE id = ?", (trade_id,)
    ).fetchone()

    assert row is not None, "El trade debe existir en sys_trades"
    assert row[1] == "SHADOW", "execution_mode debe ser 'SHADOW'"
    # entry_price debe ser >= entry original (BUY degrada hacia arriba)
    assert row[0] > signal.entry_price, (
        f"entry_price={row[0]:.5f} debe ser > {signal.entry_price:.5f} (spread aplicado)"
    )
