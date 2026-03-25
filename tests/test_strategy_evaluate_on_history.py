"""
test_strategy_evaluate_on_history.py

Verifica el contrato evaluate_on_history() en las 6 estrategias del sistema.
Cada estrategia debe producir trades distintos al evaluar los mismos datos OHLCV,
reflejando su lógica real de señales en lugar de un modelo genérico.
"""
import inspect
from dataclasses import fields
from typing import Dict, List
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from models.trade_result import TradeResult
from core_brain.strategies.base_strategy import BaseStrategy


# ─────────────────────────────────────────────────────────────────────────────
# Helpers de fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """DataFrame OHLCV con valores realistas para tests de backtesting."""
    rng = np.random.default_rng(seed)
    close = 1.1000 + rng.normal(0, 0.0008, n).cumsum()
    spread = abs(rng.normal(0, 0.0004, n)) + 0.0003
    return pd.DataFrame({
        "open":   close - spread * rng.uniform(0.2, 0.6, n),
        "high":   close + spread,
        "low":    close - spread,
        "close":  close,
        "volume": rng.integers(500, 3000, n).astype(float),
    })


def _mock_storage() -> MagicMock:
    s = MagicMock()
    s.get_dynamic_params.return_value = {}
    return s


def _mom_bias_instance():
    from core_brain.strategies.mom_bias_0001 import MomentumBias0001Strategy
    return MomentumBias0001Strategy(
        storage_manager=_mock_storage(),
        elephant_candle_detector=MagicMock(),
        moving_average_sensor=MagicMock(),
    )


def _liq_sweep_instance():
    from core_brain.strategies.liq_sweep_0001 import LiquiditySweep0001Strategy
    return LiquiditySweep0001Strategy(
        storage_manager=_mock_storage(),
        session_liquidity_sensor=MagicMock(),
        liquidity_sweep_detector=MagicMock(),
        fundamental_guard=MagicMock(),
    )


def _sess_ext_instance():
    from core_brain.strategies.session_extension_0001 import SessionExtension0001Strategy
    return SessionExtension0001Strategy(
        storage_manager=_mock_storage(),
        session_state_detector=MagicMock(),
    )


def _struc_shift_instance():
    from core_brain.strategies.struc_shift_0001 import StructureShift0001Strategy
    return StructureShift0001Strategy(
        storage_manager=_mock_storage(),
        market_structure_analyzer=MagicMock(),
    )


def _oliver_velez_instance():
    from core_brain.strategies.oliver_velez import OliverVelezStrategy
    im = MagicMock()
    im.get_enabled_symbols.return_value = []
    return OliverVelezStrategy(config={}, instrument_manager=im)


def _trifecta_instance():
    from core_brain.strategies.trifecta_logic import TrifectaAnalyzer
    return TrifectaAnalyzer(storage=_mock_storage(), auto_enable_tfs=False)


ALL_INSTANCES = [
    ("MOM_BIAS_0001",    _mom_bias_instance),
    ("LIQ_SWEEP_0001",   _liq_sweep_instance),
    ("SESS_EXT_0001",    _sess_ext_instance),
    ("STRUC_SHIFT_0001", _struc_shift_instance),
    ("OLIVER_VELEZ",     _oliver_velez_instance),
    ("TRIFECTA",         _trifecta_instance),
]


# ─────────────────────────────────────────────────────────────────────────────
# TradeResult
# ─────────────────────────────────────────────────────────────────────────────

class TestTradeResultModel:

    def test_trade_result_has_all_required_fields(self):
        """TradeResult debe tener los 8 campos especificados en HU 7.6."""
        required = {
            "entry_price", "exit_price", "pnl", "direction",
            "bars_held", "regime_at_entry", "sl_distance", "tp_distance",
        }
        actual = {f.name for f in fields(TradeResult)}
        assert required.issubset(actual), f"Campos faltantes: {required - actual}"

    def test_trade_result_is_instantiable(self):
        t = TradeResult(
            entry_price=1.1000,
            exit_price=1.1020,
            pnl=0.0020,
            direction=1,
            bars_held=3,
            regime_at_entry="TREND",
            sl_distance=0.0010,
            tp_distance=0.0020,
        )
        assert t.direction == 1
        assert t.regime_at_entry == "TREND"

    def test_pnl_sign_consistent_with_direction_for_winning_long(self):
        """LONG con exit > entry → pnl positivo."""
        t = TradeResult(
            entry_price=1.1000, exit_price=1.1020, pnl=0.0020,
            direction=1, bars_held=2, regime_at_entry="TREND",
            sl_distance=0.0010, tp_distance=0.0020,
        )
        assert t.pnl > 0

    def test_pnl_sign_consistent_with_direction_for_winning_short(self):
        """SHORT con exit < entry → pnl positivo."""
        t = TradeResult(
            entry_price=1.1000, exit_price=1.0980, pnl=0.0020,
            direction=-1, bars_held=2, regime_at_entry="RANGE",
            sl_distance=0.0010, tp_distance=0.0020,
        )
        assert t.pnl > 0


# ─────────────────────────────────────────────────────────────────────────────
# BaseStrategy — contrato abstracto
# ─────────────────────────────────────────────────────────────────────────────

class TestBaseStrategyContract:

    def test_evaluate_on_history_is_defined_in_base_strategy(self):
        """BaseStrategy debe declarar evaluate_on_history."""
        assert hasattr(BaseStrategy, "evaluate_on_history")

    def test_evaluate_on_history_is_abstract(self):
        """evaluate_on_history debe ser abstracto (no instanciable directamente)."""
        abstract_methods = getattr(BaseStrategy, "__abstractmethods__", frozenset())
        assert "evaluate_on_history" in abstract_methods, (
            "evaluate_on_history no está marcado como abstractmethod en BaseStrategy"
        )

    def test_evaluate_on_history_signature_has_df_and_params(self):
        """La firma debe aceptar df y params."""
        sig = inspect.signature(BaseStrategy.evaluate_on_history)
        param_names = list(sig.parameters.keys())
        assert "df" in param_names
        assert "params" in param_names


# ─────────────────────────────────────────────────────────────────────────────
# Cada estrategia implementa evaluate_on_history
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("name,factory", ALL_INSTANCES)
class TestEveryStrategyImplementsInterface:

    def test_method_exists(self, name, factory):
        inst = factory()
        assert hasattr(inst, "evaluate_on_history"), (
            f"{name} no tiene el método evaluate_on_history()"
        )

    def test_method_is_callable(self, name, factory):
        inst = factory()
        assert callable(inst.evaluate_on_history)

    def test_returns_list_on_empty_df(self, name, factory):
        inst = factory()
        result = inst.evaluate_on_history(pd.DataFrame(), {})
        assert isinstance(result, list), f"{name} debe retornar una lista"

    def test_returns_list_on_real_data(self, name, factory):
        inst = factory()
        df = _make_ohlcv(300)
        result = inst.evaluate_on_history(df, {})
        assert isinstance(result, list), f"{name} debe retornar una lista con datos reales"

    def test_returns_trade_result_objects(self, name, factory):
        inst = factory()
        df = _make_ohlcv(300)
        result = inst.evaluate_on_history(df, {})
        for trade in result:
            assert isinstance(trade, TradeResult), (
                f"{name}: el elemento {trade!r} no es un TradeResult"
            )

    def test_trade_results_have_valid_direction(self, name, factory):
        inst = factory()
        df = _make_ohlcv(300)
        for trade in inst.evaluate_on_history(df, {}):
            assert trade.direction in (1, -1), (
                f"{name}: direction debe ser 1 (LONG) o -1 (SHORT)"
            )

    def test_trade_results_have_positive_sl_and_tp_distance(self, name, factory):
        inst = factory()
        df = _make_ohlcv(300)
        for trade in inst.evaluate_on_history(df, {}):
            assert trade.sl_distance >= 0, f"{name}: sl_distance debe ser >= 0"
            assert trade.tp_distance >= 0, f"{name}: tp_distance debe ser >= 0"

    def test_trade_results_have_valid_bars_held(self, name, factory):
        inst = factory()
        df = _make_ohlcv(300)
        for trade in inst.evaluate_on_history(df, {}):
            assert trade.bars_held >= 1, f"{name}: bars_held debe ser >= 1"


# ─────────────────────────────────────────────────────────────────────────────
# Las 6 estrategias producen trades DIFERENTES sobre los mismos datos
# ─────────────────────────────────────────────────────────────────────────────

class TestStrategiesProduceDifferentResults:

    def _collect_all(self) -> Dict[str, List[TradeResult]]:
        df = _make_ohlcv(400)
        results = {}
        for name, factory in ALL_INSTANCES:
            inst = factory()
            results[name] = inst.evaluate_on_history(df, {})
        return results

    def test_strategies_do_not_all_produce_identical_entry_prices(self):
        """No todas las estrategias deben producir las mismas entradas."""
        all_results = self._collect_all()
        entry_sets = []
        for name, trades in all_results.items():
            if trades:
                entry_sets.append(frozenset(round(t.entry_price, 5) for t in trades))
        # Al menos 2 de las estrategias que generan señales deben tener entradas distintas
        if len(entry_sets) >= 2:
            assert not all(es == entry_sets[0] for es in entry_sets), (
                "Todas las estrategias producen exactamente las mismas entradas — "
                "los evaluate_on_history() no son distintos entre sí"
            )

    def test_at_least_two_strategies_generate_trades(self):
        """Al menos 2 estrategias deben generar trades con 400 barras de datos."""
        all_results = self._collect_all()
        strategies_with_trades = [n for n, t in all_results.items() if len(t) > 0]
        assert len(strategies_with_trades) >= 2, (
            f"Solo {len(strategies_with_trades)} estrategias generan trades en 400 barras. "
            f"Se esperan al menos 2. Resultados: {[(n, len(t)) for n, t in all_results.items()]}"
        )

    def test_mom_bias_and_liq_sweep_produce_different_trade_counts(self):
        """MOM_BIAS y LIQ_SWEEP deben diferir en número de trades o en precios."""
        df = _make_ohlcv(400)
        mom = _mom_bias_instance().evaluate_on_history(df, {})
        liq = _liq_sweep_instance().evaluate_on_history(df, {})
        # Si ambos generan trades, sus conteos o primeras entradas deben ser distintos
        if mom and liq:
            counts_differ = len(mom) != len(liq)
            entries_differ = round(mom[0].entry_price, 5) != round(liq[0].entry_price, 5)
            assert counts_differ or entries_differ, (
                "MOM_BIAS y LIQ_SWEEP produjeron exactamente los mismos trades"
            )
