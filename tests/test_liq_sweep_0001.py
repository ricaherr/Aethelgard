"""
Tests TDD — LiquiditySweep0001Strategy: snapshot DB-backed vs constantes locales.

Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13

Cubre:
- test_liq_sweep_uses_db_affinity_scores_not_class_constant:
    affinity en DB distinta a la local; la decisión debe obedecer DB.
"""
import asyncio
import logging
import pytest
import pandas as pd
from unittest.mock import MagicMock

from models.signal import MarketRegime
from core_brain.strategies.liq_sweep_0001 import LiquiditySweep0001Strategy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_storage():
    m = MagicMock()
    m.get_dynamic_params.return_value = {}
    return m


def _make_session_sensor():
    m = MagicMock()
    m.analyze_session_liquidity.return_value = {
        "london_high": 1.2600,
        "london_low": 1.2400,
    }
    return m


def _make_sweep_detector():
    m = MagicMock()
    m.detect_false_breakout_with_reversal.return_value = (False, None, 0.0)
    return m


def _make_fundamental_guard(safe=True):
    m = MagicMock()
    m.is_market_safe.return_value = (safe, "OK")
    return m


def _make_strategy(**kwargs):
    return LiquiditySweep0001Strategy(
        storage_manager=kwargs.get("storage", _make_storage()),
        session_liquidity_sensor=kwargs.get("session", _make_session_sensor()),
        liquidity_sweep_detector=kwargs.get("detector", _make_sweep_detector()),
        fundamental_guard=kwargs.get("guard", _make_fundamental_guard()),
        trace_id="TEST-LIQ-SWEEP",
    )


def _make_df(n=10):
    data = {
        "open":  [1.2500 + i * 0.0001 for i in range(n)],
        "high":  [1.2510 + i * 0.0001 for i in range(n)],
        "low":   [1.2490 + i * 0.0001 for i in range(n)],
        "close": [1.2505 + i * 0.0001 for i in range(n)],
    }
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame(data, index=idx)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestLiqSweepSnapshotOverridesClassConstants:
    """
    La estrategia debe usar affinity_scores del snapshot DB-backed.
    """

    def test_liq_sweep_uses_db_affinity_scores_not_class_constant(self):
        """
        DADO un snapshot con affinity_scores que incluye XAUUSD (no en clase),
        CUANDO analyze recibe XAUUSD,
        ENTONCES debe procesarlo (llegar al detector), no bloquearse por affinity local.
        """
        strat = _make_strategy()

        # XAUUSD no está en AFFINITY_SCORES hardcodeado de la clase
        strat.apply_metadata_snapshot({
            "affinity_scores": {"XAUUSD": 0.92},
            "market_whitelist": [],
            "execution_params": {},
        })

        df = _make_df()
        asyncio.run(strat.analyze("XAUUSD", df, MarketRegime.TREND))

        # El session_liquidity_sensor debe haber sido llamado (pasó el filtro de affinity)
        strat.session_liquidity_sensor.analyze_session_liquidity.assert_called_once(), (
            "XAUUSD con affinity en DB debe pasar el filtro y llegar al sensor de sesión"
        )

    def test_liq_sweep_blocks_symbol_excluded_from_db_snapshot(self):
        """
        DADO un snapshot que excluye EURUSD,
        CUANDO analyze recibe EURUSD (estaba en clase hardcodeada),
        ENTONCES debe retornar None sin llegar al sensor de sesión.
        """
        strat = _make_strategy()

        strat.apply_metadata_snapshot({
            "affinity_scores": {"GBPJPY": 0.70},  # EURUSD excluido
            "market_whitelist": [],
            "execution_params": {},
        })

        df = _make_df()
        result = asyncio.run(strat.analyze("EURUSD", df, MarketRegime.TREND))

        assert result is None
        strat.session_liquidity_sensor.analyze_session_liquidity.assert_not_called(), (
            "EURUSD excluido del snapshot DB no debe llegar al sensor de sesión"
        )

    def test_liq_sweep_without_snapshot_falls_back_to_class_constant(self):
        """
        Sin snapshot, la estrategia usa AFFINITY_SCORES de clase (EURUSD=0.92).
        EURUSD tiene affinity >= min_affinity (0.75), debe procesarse.
        """
        strat = _make_strategy()
        # Sin apply_metadata_snapshot

        df = _make_df()
        asyncio.run(strat.analyze("EURUSD", df, MarketRegime.TREND))

        strat.session_liquidity_sensor.analyze_session_liquidity.assert_called_once(), (
            "Sin snapshot, EURUSD con affinity 0.92 en clase debe procesarse"
        )

    def test_liq_sweep_min_affinity_uses_snapshot_scores(self):
        """
        DADO un snapshot con USDJPY affinity=0.50 y min_affinity=0.75,
        CUANDO analyze recibe USDJPY,
        ENTONCES debe bloquear (0.50 < 0.75).
        """
        strat = _make_strategy()

        strat.apply_metadata_snapshot({
            "affinity_scores": {"USDJPY": 0.50},  # menor que min_affinity default 0.75
            "market_whitelist": [],
            "execution_params": {},
        })

        df = _make_df()
        result = asyncio.run(strat.analyze("USDJPY", df, MarketRegime.TREND))

        assert result is None
        strat.session_liquidity_sensor.analyze_session_liquidity.assert_not_called(), (
            "USDJPY con affinity 0.50 < min_affinity 0.75 debe bloquearse"
        )

    def test_liq_sweep_accepts_enriched_affinity_dict(self):
        """
        DADO un snapshot con affinity enriquecida (dict con effective_score),
        CUANDO analyze recibe el símbolo,
        ENTONCES no debe lanzar TypeError y debe llegar al sensor de sesión.
        """
        strat = _make_strategy()

        strat.apply_metadata_snapshot({
            "affinity_scores": {
                "EURUSD": {
                    "effective_score": 0.91,
                    "raw_score": 0.95,
                    "confidence": 0.7,
                }
            },
            "market_whitelist": [],
            "execution_params": {},
        })

        df = _make_df()
        result = asyncio.run(strat.analyze("EURUSD", df, MarketRegime.TREND))

        assert result is None
        strat.session_liquidity_sensor.analyze_session_liquidity.assert_called_once(), (
            "Affinity enriquecida debe normalizarse y permitir flujo sin crash"
        )
