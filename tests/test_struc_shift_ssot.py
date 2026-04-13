"""
Tests TDD — StructureShift0001Strategy: snapshot DB-backed vs constantes locales.

Trace_ID: EDGE-STRATEGY-SSOT-SYNC-2026-04-13

Cubre:
- test_struc_shift_uses_db_market_whitelist:
    whitelist de DB incluye un activo que el hardcode excluye; debe analizarlo.
"""
import asyncio
import logging
import pytest
import pandas as pd
import numpy as np
from unittest.mock import MagicMock, patch

from models.signal import MarketRegime
from core_brain.strategies.struc_shift_0001 import StructureShift0001Strategy


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_storage():
    m = MagicMock()
    m.get_dynamic_params.return_value = {}
    return m


def _make_analyzer(valid=False):
    m = MagicMock()
    m.detect_market_structure.return_value = {
        "is_valid": valid,
        "type": "UPTREND",
        "hh_count": 3,
        "hl_count": 3,
    }
    m.calculate_breaker_block.return_value = {
        "high": 1.26, "low": 1.24, "range_pips": 200, "midpoint": 1.25,
    }
    m.detect_break_of_structure.return_value = {
        "is_break": False, "direction": "UP", "strength": 0.0
    }
    m.calculate_pullback_zone.return_value = {
        "entry_high": 1.255, "entry_low": 1.245, "midpoint": 1.25
    }
    return m


def _make_strategy(analyzer=None):
    return StructureShift0001Strategy(
        storage_manager=_make_storage(),
        market_structure_analyzer=analyzer or _make_analyzer(),
        trace_id="TEST-STRUC-SHIFT",
    )


def _make_df(n=25):
    data = {
        "open":  [1.2500 + i * 0.0001 for i in range(n)],
        "high":  [1.2510 + i * 0.0001 for i in range(n)],
        "low":   [1.2490 + i * 0.0001 for i in range(n)],
        "close": [1.2505 + i * 0.0001 for i in range(n)],
    }
    idx = pd.date_range("2026-01-01", periods=n, freq="h")
    return pd.DataFrame(data, index=idx)


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestStrucShiftSnapshotOverridesClassConstants:
    """
    La estrategia debe usar market_whitelist y affinity_scores del snapshot DB-backed.
    """

    def test_struc_shift_uses_db_market_whitelist(self):
        """
        DADO un snapshot con market_whitelist que incluye GBPUSD
        (excluido del MARKET_WHITELIST hardcodeado de la clase),
        CUANDO analyze recibe GBPUSD,
        ENTONCES debe procesarlo (llegar al analyzer de estructura).
        """
        analyzer = _make_analyzer(valid=False)  # valid=False → retorna None pronto pero pasa whitelist
        strat = _make_strategy(analyzer=analyzer)

        # DB incluye GBPUSD; la clase hardcodeada NO lo incluye en MARKET_WHITELIST
        strat.apply_metadata_snapshot({
            "affinity_scores": {"EURUSD": 0.89, "USDCAD": 0.82, "GBPUSD": 0.75},
            "market_whitelist": ["EURUSD", "USDCAD", "GBPUSD"],
            "execution_params": {},
        })

        df = _make_df()
        asyncio.run(strat.analyze("GBPUSD", df, MarketRegime.TREND))

        analyzer.detect_market_structure.assert_called_once(), (
            "GBPUSD en whitelist DB debe pasar el filtro y llegar al analyzer de estructura"
        )

    def test_struc_shift_blocks_symbol_excluded_from_db_whitelist(self):
        """
        DADO un snapshot con market_whitelist que excluye EURUSD,
        CUANDO analyze recibe EURUSD,
        ENTONCES debe retornar None sin llamar al analyzer.
        """
        analyzer = _make_analyzer()
        strat = _make_strategy(analyzer=analyzer)

        strat.apply_metadata_snapshot({
            "affinity_scores": {"USDCAD": 0.82},
            "market_whitelist": ["USDCAD"],  # EURUSD excluido
            "execution_params": {},
        })

        df = _make_df()
        result = asyncio.run(strat.analyze("EURUSD", df, MarketRegime.TREND))

        assert result is None
        analyzer.detect_market_structure.assert_not_called(), (
            "EURUSD excluido del whitelist DB no debe llegar al analyzer"
        )

    def test_struc_shift_without_snapshot_uses_class_whitelist(self):
        """
        Sin snapshot, la clase usa MARKET_WHITELIST = ["EURUSD", "USDCAD"].
        EURUSD debe procesarse.
        """
        analyzer = _make_analyzer(valid=False)
        strat = _make_strategy(analyzer=analyzer)
        # Sin apply_metadata_snapshot

        df = _make_df()
        asyncio.run(strat.analyze("EURUSD", df, MarketRegime.TREND))

        analyzer.detect_market_structure.assert_called_once(), (
            "Sin snapshot, EURUSD (en whitelist de clase) debe procesarse"
        )

    def test_struc_shift_empty_db_whitelist_passes_all_symbols(self):
        """
        DADO un snapshot con market_whitelist vacía,
        CUANDO analyze recibe cualquier símbolo,
        ENTONCES no debe bloquearse por whitelist (lista vacía = sin restricción).
        """
        analyzer = _make_analyzer(valid=False)
        strat = _make_strategy(analyzer=analyzer)

        strat.apply_metadata_snapshot({
            "affinity_scores": {"XAUUSD": 0.88},
            "market_whitelist": [],  # vacío = sin restricción
            "execution_params": {},
        })

        df = _make_df()
        asyncio.run(strat.analyze("XAUUSD", df, MarketRegime.TREND))

        analyzer.detect_market_structure.assert_called_once(), (
            "Whitelist vacía en snapshot no debe bloquear ningún símbolo"
        )


class TestStrucShiftBlockReasonTraceability:
    """
    El motivo de bloqueo debe quedar distinguible en logs.
    """

    def test_struc_shift_logs_whitelist_block_reason(self, caplog):
        """
        DADO un snapshot que excluye GBPJPY,
        CUANDO analyze retorna None por whitelist,
        ENTONCES el log debe distinguir la razón.
        """
        strat = _make_strategy()
        strat.apply_metadata_snapshot({
            "affinity_scores": {"EURUSD": 0.89},
            "market_whitelist": ["EURUSD"],
            "execution_params": {},
        })

        df = _make_df()
        with caplog.at_level(logging.DEBUG, logger="core_brain.strategies.struc_shift_0001"):
            asyncio.run(strat.analyze("GBPJPY", df, MarketRegime.TREND))

        log_text = caplog.text.lower()
        assert "gbpjpy" in log_text
        assert any(kw in log_text for kw in ("whitelist", "snapshot", "not in", "market")), (
            "El log debe indicar que el bloqueo es por whitelist/snapshot"
        )
