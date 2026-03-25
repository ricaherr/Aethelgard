"""
test_symbol_format_strategies.py — RED phase

Verifica que las estrategias LIQ_SWEEP_0001, MOM_BIAS_0001 y STRUC_SHIFT_0001
aceptan símbolos en formato sin barra ("EURUSD") que es el formato producido
por el scanner.

Problema detectado: las constantes AFFINITY_SCORES y MARKET_WHITELIST usaban
formato "EUR/USD" (con barra), mientras que el scanner pasa "EURUSD".
Resultado: las 3 estrategias nunca generaban señales.

Trace_ID: FIX-SYMBOL-FORMAT-2026-03-25
"""
import pytest
from unittest.mock import MagicMock


def _mock_storage():
    s = MagicMock()
    s.get_dynamic_params.return_value = {}
    return s


# ─────────────────────────────────────────────────────────────────────────────
# LIQ_SWEEP_0001
# ─────────────────────────────────────────────────────────────────────────────

class TestLiqSweepSymbolFormat:
    def setup_method(self):
        from core_brain.strategies.liq_sweep_0001 import LiquiditySweep0001Strategy
        self.strategy = LiquiditySweep0001Strategy(
            storage_manager=_mock_storage(),
            session_liquidity_sensor=MagicMock(),
            liquidity_sweep_detector=MagicMock(),
            fundamental_guard=MagicMock(),
        )

    def test_affinity_scores_use_no_slash_format(self):
        """EURUSD (sin barra) debe estar en AFFINITY_SCORES, no EUR/USD."""
        assert "EURUSD" in self.strategy.AFFINITY_SCORES
        assert "EUR/USD" not in self.strategy.AFFINITY_SCORES

    def test_all_affinity_keys_are_no_slash(self):
        """Ninguna clave de AFFINITY_SCORES debe contener barra."""
        for key in self.strategy.AFFINITY_SCORES:
            assert "/" not in key, f"Clave con barra encontrada: '{key}'"

    def test_affinity_covers_major_pairs(self):
        """Los pares principales del scanner deben estar cubiertos."""
        for symbol in ("EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "USDCAD"):
            assert symbol in self.strategy.AFFINITY_SCORES, f"{symbol} no en AFFINITY_SCORES"


# ─────────────────────────────────────────────────────────────────────────────
# MOM_BIAS_0001
# ─────────────────────────────────────────────────────────────────────────────

class TestMomBiasSymbolFormat:
    def setup_method(self):
        from core_brain.strategies.mom_bias_0001 import MomentumBias0001Strategy
        self.strategy = MomentumBias0001Strategy(
            storage_manager=_mock_storage(),
            elephant_candle_detector=MagicMock(),
            moving_average_sensor=MagicMock(),
        )

    def test_affinity_scores_use_no_slash_format(self):
        """EURUSD (sin barra) debe estar en AFFINITY_SCORES."""
        assert "EURUSD" in self.strategy.AFFINITY_SCORES
        assert "EUR/USD" not in self.strategy.AFFINITY_SCORES

    def test_all_affinity_keys_are_no_slash(self):
        """Ninguna clave debe contener barra."""
        for key in self.strategy.AFFINITY_SCORES:
            assert "/" not in key, f"Clave con barra encontrada: '{key}'"

    def test_enabled_symbols_are_no_slash(self):
        """enabled_symbols (derivado de AFFINITY_SCORES) tampoco debe tener barras."""
        for sym in self.strategy.enabled_symbols:
            assert "/" not in sym, f"enabled_symbol con barra: '{sym}'"


# ─────────────────────────────────────────────────────────────────────────────
# STRUC_SHIFT_0001
# ─────────────────────────────────────────────────────────────────────────────

class TestStrucShiftSymbolFormat:
    def setup_method(self):
        from core_brain.strategies.struc_shift_0001 import StructureShift0001Strategy
        self.strategy = StructureShift0001Strategy(
            storage_manager=_mock_storage(),
            market_structure_analyzer=MagicMock(),
        )

    def test_market_whitelist_uses_no_slash_format(self):
        """MARKET_WHITELIST debe usar formato sin barra."""
        assert "EURUSD" in self.strategy.MARKET_WHITELIST
        assert "EUR/USD" not in self.strategy.MARKET_WHITELIST

    def test_affinity_scores_use_no_slash_format(self):
        """AFFINITY_SCORES también debe usar formato sin barra."""
        assert "EURUSD" in self.strategy.AFFINITY_SCORES
        assert "EUR/USD" not in self.strategy.AFFINITY_SCORES

    def test_all_whitelist_entries_are_no_slash(self):
        """Ninguna entrada del whitelist debe contener barra."""
        for sym in self.strategy.MARKET_WHITELIST:
            assert "/" not in sym, f"Whitelist entry con barra: '{sym}'"

    def test_whitelist_symbols_are_in_affinity_scores(self):
        """Todos los símbolos del whitelist deben tener score de afinidad."""
        for sym in self.strategy.MARKET_WHITELIST:
            assert sym in self.strategy.AFFINITY_SCORES, f"{sym} en whitelist pero no en AFFINITY_SCORES"
