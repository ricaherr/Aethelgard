"""
Tests: SessionExtension0001Strategy._sl_buffer — HU 3.11
  Verifica que el buffer SL/TP sea dinámico por tipo de instrumento.
  Trace_ID: SESS-EXT-SL-BUFFER-2026-03-25
"""
import pytest
from unittest.mock import MagicMock

from core_brain.strategies.session_extension_0001 import SessionExtension0001Strategy


@pytest.fixture
def strategy():
    return SessionExtension0001Strategy(
        storage_manager=MagicMock(),
        session_state_detector=MagicMock(),
    )


class TestSlBuffer:
    def test_sl_buffer_forex_eurusd(self, strategy):
        assert strategy._sl_buffer("EURUSD", 1.10) == pytest.approx(0.0005)

    def test_sl_buffer_forex_gbpusd(self, strategy):
        assert strategy._sl_buffer("GBPUSD", 1.25) == pytest.approx(0.0005)

    def test_sl_buffer_jpy_pair(self, strategy):
        assert strategy._sl_buffer("USDJPY", 150.0) == pytest.approx(0.05)

    def test_sl_buffer_jpy_cross(self, strategy):
        assert strategy._sl_buffer("EURJPY", 160.0) == pytest.approx(0.05)

    def test_sl_buffer_gold(self, strategy):
        assert strategy._sl_buffer("XAUUSD", 2300.0) == pytest.approx(0.50)

    def test_sl_buffer_silver(self, strategy):
        assert strategy._sl_buffer("XAGUSD", 28.0) == pytest.approx(0.50)

    def test_sl_buffer_us30_index(self, strategy):
        assert strategy._sl_buffer("US30", 40000.0) == pytest.approx(5.0)

    def test_sl_buffer_nas100_index(self, strategy):
        assert strategy._sl_buffer("NAS100", 18000.0) == pytest.approx(5.0)

    def test_sl_buffer_spx500_index(self, strategy):
        assert strategy._sl_buffer("SPX500", 5200.0) == pytest.approx(5.0)

    def test_sl_buffer_default_unknown(self, strategy):
        """Instrumento desconocido debe recibir el buffer forex por defecto."""
        assert strategy._sl_buffer("UNKNOWN", 100.0) == pytest.approx(0.0005)

    def test_sl_buffer_is_static(self):
        """_sl_buffer debe poder llamarse sin instancia."""
        result = SessionExtension0001Strategy._sl_buffer("US30", 40000.0)
        assert result == pytest.approx(5.0)


class TestAnalyzeUsesDynamicBuffer:
    """Smoke tests: analyze() aplica el buffer correcto por símbolo."""

    @pytest.mark.asyncio
    async def test_buy_sl_uses_index_buffer_for_us30(self):
        import pandas as pd

        detector = MagicMock()
        detector.get_session_stats.return_value = {"session": "NY", "is_overlap": True}
        strategy = SessionExtension0001Strategy(
            storage_manager=MagicMock(),
            session_state_detector=detector,
        )
        df = pd.DataFrame({
            "open":  [40000.0] * 5,
            "high":  [40050.0] * 5,
            "low":   [39950.0] * 5,
            "close": [40010.0] * 5,
            "volume":[1000.0] * 5,
        })
        signal = await strategy.analyze("US30", df, regime="TREND")
        assert signal is not None
        # SL debe ser low - 5.0 = 39950 - 5 = 39945
        assert signal.stop_loss == pytest.approx(39945.0)

    @pytest.mark.asyncio
    async def test_buy_sl_uses_forex_buffer_for_eurusd(self):
        import pandas as pd

        detector = MagicMock()
        detector.get_session_stats.return_value = {"session": "NY", "is_overlap": True}
        strategy = SessionExtension0001Strategy(
            storage_manager=MagicMock(),
            session_state_detector=detector,
        )
        df = pd.DataFrame({
            "open":  [1.1000] * 5,
            "high":  [1.1050] * 5,
            "low":   [1.0980] * 5,
            "close": [1.1020] * 5,
            "volume":[1000.0] * 5,
        })
        signal = await strategy.analyze("EURUSD", df, regime="TREND")
        assert signal is not None
        # SL debe ser low - 0.0005 = 1.0980 - 0.0005 = 1.0975
        assert signal.stop_loss == pytest.approx(1.0975, abs=1e-5)
