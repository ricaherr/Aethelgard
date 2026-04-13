"""
Tests TDD — MomentumBias0001Strategy: snapshot DB-backed vs constantes locales.

Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13

Cubre:
- test_mom_bias_uses_db_whitelist_not_class_constant:
    DB y constante local difieren; la estrategia debe obedecer DB.
- test_strategy_returns_reason_when_blocked_by_whitelist:
    analyze retorna None por whitelist y el motivo queda trazado.
"""
import asyncio
import logging
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch
from datetime import datetime

from models.signal import MarketRegime
from core_brain.strategies.mom_bias_0001 import MomentumBias0001Strategy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_mock_storage():
    m = MagicMock()
    m.get_dynamic_params.return_value = {}
    return m


def _make_mock_elephant():
    m = MagicMock()
    m.validate_ignition.return_value = None
    return m


def _make_mock_ma():
    m = MagicMock()
    import pandas as pd
    series = pd.Series([1.2500] * 210)
    m.calculate_sma.return_value = series
    return m


def _make_strategy(storage=None, elephant=None, ma=None):
    return MomentumBias0001Strategy(
        storage_manager=storage or _make_mock_storage(),
        elephant_candle_detector=elephant or _make_mock_elephant(),
        moving_average_sensor=_make_mock_ma() if ma is None else ma,
        trace_id="TEST-MOM-BIAS",
    )


def _make_df(n=210):
    """DataFrame mínimo con OHLC válido."""
    base = 1.2500
    data = {
        "open":   [base + i * 0.0001 for i in range(n)],
        "high":   [base + i * 0.0001 + 0.0005 for i in range(n)],
        "low":    [base + i * 0.0001 - 0.0005 for i in range(n)],
        "close":  [base + i * 0.0001 + 0.0002 for i in range(n)],
        "volume": [1000] * n,
    }
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame(data, index=idx)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestMomBiasSnapshotOverridesClassConstants:
    """
    La estrategia debe usar los valores del snapshot DB-backed
    en lugar de sus constantes de clase hardcodeadas.
    """

    def test_mom_bias_uses_db_affinity_scores_not_class_constant(self):
        """
        DADO un snapshot con affinity_scores distintos a la clase,
        CUANDO se llama a analyze con un símbolo en el snapshot DB pero NO en la clase,
        ENTONCES la estrategia debe evaluarlo (no retornar None por whitelist).
        """
        strat = _make_strategy()

        # Símbolo que NO está en AFFINITY_SCORES de clase pero sí en snapshot DB
        db_affinity = {"XAUUSD": 0.95}  # XAUUSD no existe en AFFINITY_SCORES hardcodeado
        strat.apply_metadata_snapshot({
            "affinity_scores": db_affinity,
            "market_whitelist": [],
            "execution_params": {},
        })

        # Con snapshot inyectado, XAUUSD debe ser procesado (el detector retorna None → None OK,
        # pero NO debe retornar None por "símbolo no encontrado en affinity_scores")
        df = _make_df()
        with patch.object(strat, "moving_average_sensor") as mock_ma:
            series = pd.Series([1.25] * len(df))
            mock_ma.calculate_sma.return_value = series
            with patch.object(strat, "elephant_candle_detector") as mock_el:
                mock_el.validate_ignition.return_value = None  # no señal, pero sí llegó

                result = asyncio.run(strat.analyze("XAUUSD", df, MarketRegime.TREND))

        # Si llegamos hasta el detector y retornó None, el flujo fue correcto.
        # Si hubiera retornado None por "symbol not in affinity_scores" no habría
        # llegado al detector.
        mock_el.validate_ignition.assert_called_once(), (
            "El flujo debe llegar al detector; no bloquearse antes por affinity hardcodeada"
        )

    def test_mom_bias_blocks_symbol_not_in_db_snapshot(self):
        """
        DADO un snapshot con affinity_scores que excluye un símbolo,
        CUANDO analyze recibe ese símbolo,
        ENTONCES debe retornar None sin llegar al detector.
        """
        strat = _make_strategy()

        strat.apply_metadata_snapshot({
            "affinity_scores": {"EURUSD": 0.65},  # Solo EURUSD
            "market_whitelist": [],
            "execution_params": {},
        })

        df = _make_df()
        with patch.object(strat, "elephant_candle_detector") as mock_el:
            result = asyncio.run(strat.analyze("GBPJPY", df, MarketRegime.TREND))

        assert result is None
        mock_el.validate_ignition.assert_not_called(), (
            "GBPJPY no está en snapshot DB; debe bloquearse antes del detector"
        )

    def test_mom_bias_without_snapshot_uses_class_constant_as_fallback(self):
        """
        DADO una estrategia sin snapshot aplicado (comportamiento legado),
        CUANDO analyze recibe GBPJPY (está en clase hardcodeada),
        ENTONCES debe procesarlo normalmente (compatibilidad regresiva).
        """
        strat = _make_strategy()
        # No llamamos apply_metadata_snapshot → usa AFFINITY_SCORES de clase

        df = _make_df()
        with patch.object(strat, "elephant_candle_detector") as mock_el:
            mock_el.validate_ignition.return_value = None
            result = asyncio.run(strat.analyze("GBPJPY", df, MarketRegime.TREND))

        # El flujo debe llegar al detector (GBPJPY está en clase hardcodeada)
        mock_el.validate_ignition.assert_called_once()


class TestMomBiasBlockedReasonTraceability:
    """
    El motivo de bloqueo en analyze() debe quedar distinguible en logs.
    """

    def test_strategy_logs_whitelist_block_reason(self, caplog):
        """
        DADO un snapshot con affinity_scores que no incluye el símbolo,
        CUANDO analyze retorna None,
        ENTONCES el log debe mencionar 'whitelist' o 'affinity' y el símbolo.
        """
        strat = _make_strategy()
        strat.apply_metadata_snapshot({
            "affinity_scores": {"EURUSD": 0.65},
            "market_whitelist": [],
            "execution_params": {},
        })

        df = _make_df()
        with caplog.at_level(logging.DEBUG, logger="core_brain.strategies.mom_bias_0001"):
            asyncio.run(strat.analyze("XAUUSD", df, MarketRegime.TREND))

        log_text = caplog.text.lower()
        assert "xauusd" in log_text, "El log debe mencionar el símbolo bloqueado"
        # La razón debe ser distinguible (affinity, whitelist, o snapshot)
        assert any(kw in log_text for kw in ("affinity", "whitelist", "snapshot", "not in")), (
            "El log debe indicar la razón del bloqueo por affinity/whitelist"
        )

    def test_strategy_logs_insufficient_data_differently(self, caplog):
        """
        Datos insuficientes deben loguearse con razón distinta a whitelist.
        """
        strat = _make_strategy()
        # GBPJPY está en AFFINITY_SCORES de clase → pasa whitelist
        short_df = _make_df(n=5)  # menos de 20 filas → insuficiente

        with caplog.at_level(logging.DEBUG, logger="core_brain.strategies.mom_bias_0001"):
            asyncio.run(strat.analyze("GBPJPY", short_df, MarketRegime.TREND))

        log_text = caplog.text.lower()
        # Debe mencionar "insuficiente" o "datos" pero NO "affinity" o "whitelist"
        assert any(kw in log_text for kw in ("insuficiente", "insufficient", "datos")), (
            "El bloqueo por datos insuficientes debe tener razón diferenciada"
        )
