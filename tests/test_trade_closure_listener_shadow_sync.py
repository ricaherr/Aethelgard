"""
test_trade_closure_listener_shadow_sync.py
==========================================
TDD para FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30

Verifica que:
1. instance_id se propaga correctamente a sys_trades para trades SHADOW.
2. La resolución del contexto SHADOW no hace fallback a LIVE cuando falta ranking.
3. calculate_instance_metrics_from_sys_trades() encuentra trades tras el fix.

Sin el fix, instance_id = NULL → 0 filas en la query de métricas → ciclo Darwiniano roto.

Trace_ID: FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30
"""
import asyncio
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core_brain.trade_closure_listener import TradeClosureListener
from data_vault.schema import initialize_schema
from data_vault.shadow_db import ShadowStorageManager
from models.broker_event import BrokerEvent, BrokerTradeClosedEvent, TradeResult
from models.execution_mode import ExecutionMode


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def in_memory_db():
    """DB en memoria con esquema completo (include sys_shadow_instances + sys_trades)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    initialize_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def shadow_instance_id():
    return "SHADOW_LIQ_SWEEP_0001_V0"


@pytest.fixture
def strategy_id():
    return "LIQ_SWEEP_0001"


@pytest.fixture
def db_with_shadow_instance(in_memory_db, shadow_instance_id, strategy_id):
    """DB con instancia SHADOW activa en sys_shadow_instances."""
    in_memory_db.execute(
        """
        INSERT INTO sys_shadow_instances (
            instance_id, strategy_id, account_id, account_type,
            parameter_overrides, regime_filters, birth_timestamp, status,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            shadow_instance_id, strategy_id, "ACC_DEMO_01", "DEMO",
            "{}", "[]",
            datetime.now(timezone.utc).isoformat(),
            "INCUBATING",
            datetime.now(timezone.utc).isoformat(),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    in_memory_db.commit()
    return in_memory_db


def _make_signal_dict(signal_id: str, strategy_id: str) -> dict:
    """Construye un dict de señal con strategy_id en metadata."""
    return {
        "id": signal_id,
        "symbol": "EURUSD",
        "metadata": json.dumps({"strategy_id": strategy_id}),
    }


def _make_trade_event(signal_id: Optional[str] = None) -> BrokerEvent:
    """Construye un BrokerEvent wrapping BrokerTradeClosedEvent mínimo para SHADOW."""
    trade = BrokerTradeClosedEvent(
        ticket=str(uuid.uuid4()),
        symbol="EURUSD",
        entry_price=1.1000,
        exit_price=1.1050,
        entry_time=datetime.now(timezone.utc),
        exit_time=datetime.now(timezone.utc),
        pips=5.0,
        profit_loss=50.0,
        result=TradeResult.WIN,
        exit_reason="TP",
        broker_id="MT5_DEMO",
        signal_id=signal_id,
    )
    return BrokerEvent.from_trade_closed(trade)


def _make_storage_mock(db_conn: sqlite3.Connection, signal_dict: dict, ranking: dict):
    """Crea un StorageManager mock con métodos relevantes apuntando al DB real."""
    storage = MagicMock()
    storage.get_signal_by_id.return_value = signal_dict
    storage.get_signal_ranking.return_value = ranking
    storage.save_trade_result = MagicMock()  # será verificado
    storage._get_conn.return_value = db_conn
    storage._close_conn = MagicMock()
    storage.trade_exists.return_value = False
    return storage


# ── Tests RED (deben fallar antes del fix) ───────────────────────────────────

class TestShadowSyncZeroTrades:
    """
    Suite FIX-SHADOW-SYNC-ZERO-TRADES-2026-03-30

    Valida que instance_id llega a sys_trades correctamente.
    """

    @pytest.mark.asyncio
    async def test_trade_closure_listener_shadow_trade_data_includes_instance_id(
        self, db_with_shadow_instance, shadow_instance_id, strategy_id
    ):
        """
        trade_data enviado a save_trade_result() DEBE contener instance_id.

        Sin el fix: trade_data no tiene 'instance_id' → sys_trades.instance_id = NULL
        Con el fix: trade_data['instance_id'] = shadow_instance_id
        """
        signal_id = str(uuid.uuid4())
        signal_dict = _make_signal_dict(signal_id, strategy_id)
        ranking = {"execution_mode": ExecutionMode.SHADOW.value, "strategy_id": strategy_id}

        storage = _make_storage_mock(db_with_shadow_instance, signal_dict, ranking)
        risk_manager = MagicMock()
        risk_manager.consecutive_losses = 0
        edge_tuner = MagicMock()

        listener = TradeClosureListener(
            storage=storage,
            risk_manager=risk_manager,
            edge_tuner=edge_tuner,
        )

        trade_event = _make_trade_event(signal_id=signal_id)
        await listener.handle_trade_closed_event(trade_event)

        # Verificar que save_trade_result() fue llamado
        assert storage.save_trade_result.called, "save_trade_result() no fue invocado"

        call_args = storage.save_trade_result.call_args[0][0]
        assert "instance_id" in call_args, (
            "trade_data no contiene 'instance_id' — los trades SHADOW llegan con instance_id=NULL"
        )
        assert call_args["instance_id"] == shadow_instance_id, (
            f"instance_id incorrecto: esperado={shadow_instance_id}, "
            f"recibido={call_args.get('instance_id')}"
        )

    @pytest.mark.asyncio
    async def test_trade_closure_listener_shadow_execution_mode_in_trade_data(
        self, db_with_shadow_instance, shadow_instance_id, strategy_id
    ):
        """
        execution_mode DEBE ser 'SHADOW' cuando la estrategia tiene instancia activa.

        Sin el fix (Vector B): si ranking no existe, _get_execution_mode() retorna LIVE
        → trade va a usr_trades, no a sys_trades.
        """
        signal_id = str(uuid.uuid4())
        signal_dict = _make_signal_dict(signal_id, strategy_id)
        # Simulamos que sys_signal_ranking tiene ejecución SHADOW
        ranking = {"execution_mode": ExecutionMode.SHADOW.value, "strategy_id": strategy_id}

        storage = _make_storage_mock(db_with_shadow_instance, signal_dict, ranking)
        risk_manager = MagicMock()
        risk_manager.consecutive_losses = 0
        edge_tuner = MagicMock()

        listener = TradeClosureListener(
            storage=storage,
            risk_manager=risk_manager,
            edge_tuner=edge_tuner,
        )

        trade_event = _make_trade_event(signal_id=signal_id)
        await listener.handle_trade_closed_event(trade_event)

        assert storage.save_trade_result.called
        call_args = storage.save_trade_result.call_args[0][0]
        assert call_args.get("execution_mode") == ExecutionMode.SHADOW.value, (
            f"execution_mode incorrecto: {call_args.get('execution_mode')} (esperado SHADOW)"
        )

    @pytest.mark.asyncio
    async def test_trade_closure_listener_shadow_instance_id_fallback_via_strategy(
        self, db_with_shadow_instance, shadow_instance_id, strategy_id
    ):
        """
        Si sys_signal_ranking no tiene entrada, el listener DEBE resolver instance_id
        vía sys_shadow_instances (fallback por strategy_id), no retornar LIVE.

        Esto cubre el caso donde una estrategia SHADOW no tiene ranking registrado aún.
        """
        signal_id = str(uuid.uuid4())
        signal_dict = _make_signal_dict(signal_id, strategy_id)
        # Ranking devuelve None — simula que no existe entrada en sys_signal_ranking
        storage = _make_storage_mock(db_with_shadow_instance, signal_dict, ranking=None)
        storage.get_signal_ranking.return_value = None

        risk_manager = MagicMock()
        risk_manager.consecutive_losses = 0
        edge_tuner = MagicMock()

        listener = TradeClosureListener(
            storage=storage,
            risk_manager=risk_manager,
            edge_tuner=edge_tuner,
        )

        trade_event = _make_trade_event(signal_id=signal_id)
        await listener.handle_trade_closed_event(trade_event)

        assert storage.save_trade_result.called
        call_args = storage.save_trade_result.call_args[0][0]
        assert call_args.get("instance_id") == shadow_instance_id, (
            "Sin ranking, el listener debe resolver instance_id desde sys_shadow_instances"
        )
        assert call_args.get("execution_mode") == ExecutionMode.SHADOW.value, (
            "Sin ranking pero con instancia SHADOW activa, execution_mode debe ser SHADOW"
        )


class TestShadowMetricsAfterFix:
    """Verifica end-to-end: trade guardado con instance_id → métricas no vacías."""

    def test_shadow_calculate_metrics_finds_trades_with_instance_id(self, db_with_shadow_instance, shadow_instance_id):
        """
        Después del fix, calculate_instance_metrics_from_sys_trades() DEBE encontrar
        los trades guardados con instance_id.
        """
        # Insertar un trade directamente con instance_id correcto
        db_with_shadow_instance.execute(
            """
            INSERT INTO sys_trades (
                id, signal_id, instance_id, account_id, symbol, direction,
                entry_price, exit_price, profit, exit_reason,
                open_time, close_time, execution_mode, strategy_id, order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), None, shadow_instance_id, "ACC_DEMO_01",
                "EURUSD", "BUY",
                1.1000, 1.1050, 50.0, "TP",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                "SHADOW", "LIQ_SWEEP_0001", None,
            ),
        )
        db_with_shadow_instance.commit()

        shadow_storage = ShadowStorageManager(db_with_shadow_instance)
        metrics = shadow_storage.calculate_instance_metrics_from_sys_trades(shadow_instance_id)

        assert metrics.total_trades_executed == 1, (
            f"Se esperaba 1 trade, encontrado {metrics.total_trades_executed}. "
            "Verificar que sys_trades.instance_id no sea NULL."
        )

    def test_shadow_calculate_metrics_empty_when_instance_id_is_null(self, db_with_shadow_instance, shadow_instance_id):
        """
        Confirma que SIN instance_id las métricas son vacías (reproduce el bug original).
        """
        # Insertar trade con instance_id = NULL (bug original)
        db_with_shadow_instance.execute(
            """
            INSERT INTO sys_trades (
                id, signal_id, instance_id, account_id, symbol, direction,
                entry_price, exit_price, profit, exit_reason,
                open_time, close_time, execution_mode, strategy_id, order_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()), None, None, "ACC_DEMO_01",  # instance_id = NULL
                "EURUSD", "BUY",
                1.1000, 1.1050, 50.0, "TP",
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                "SHADOW", "LIQ_SWEEP_0001", None,
            ),
        )
        db_with_shadow_instance.commit()

        shadow_storage = ShadowStorageManager(db_with_shadow_instance)
        metrics = shadow_storage.calculate_instance_metrics_from_sys_trades(shadow_instance_id)

        # Con NULL no encuentra nada — esto documenta el bug original
        assert metrics.total_trades_executed == 0, (
            "Confirma bug: trades con instance_id=NULL no son visibles para la instancia"
        )
