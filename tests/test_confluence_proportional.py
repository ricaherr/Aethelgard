"""
test_confluence_proportional.py — Suite TDD para escala proporcional de confluencia.

Componente: core_brain/confluence.py (MultiTimeframeConfluenceAnalyzer)
Trace_ID:   TRACE_TEST_CONFLUENCE_PROP_20260326
Orden S-9:  Dynamic Aggression Engine — Confluencia Proporcional por Nivel de Confianza

Casos de prueba:
  1. Señal confidence=0.35 (<0.40) → bonus escalado = 0 (ningún bono aplicado)
  2. Señal confidence=0.45 ([0.40-0.50]) → bonus escalado = bonus_bruto * 0.5
  3. Señal confidence=0.65 (>0.50) → bonus escalado = bonus_bruto * 1.0
  4. Metadata contiene confluence_scale_factor correcto por tier
  5. Señal confidence=0.40 exacto → tier [0.40, 0.50], aplica 0.5x
  6. Señal confidence=0.50 exacto → tier [0.40, 0.50], aplica 0.5x
  7. Test de Fluidez (S-9 Punto 4.1): señal 0.52 + alta confluencia → Grade B o A
  8. Test de Asimetría (S-9 Punto 4.2): estrategia non-oliver NO pasa por trifecta
"""

from unittest.mock import MagicMock, patch
from typing import Dict

import pytest

from models.signal import SignalType, MarketRegime
from core_brain.confluence import MultiTimeframeConfluenceAnalyzer, ConfluenceAnalysis


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_storage_mock(weights: Dict = None) -> MagicMock:
    """Crea un StorageManager mock con parámetros dinámicos vacíos."""
    storage = MagicMock()
    storage.get_dynamic_params.return_value = (
        {"confluence": {"weights": weights}} if weights else {}
    )
    return storage


class FakeSignal:
    """Señal de prueba simple sin dependencias del modelo complejo."""
    def __init__(self, confidence: float, signal_type: SignalType = SignalType.BUY):
        self.confidence = confidence
        self.signal_type = signal_type
        self.metadata = {}
        self.symbol = "EURUSD"


def _make_signal(confidence: float, signal_type: SignalType = SignalType.BUY) -> FakeSignal:
    """Crea una FakeSignal de prueba con la confianza dada."""
    return FakeSignal(confidence=confidence, signal_type=signal_type)


def _make_all_bullish_regimes() -> Dict[str, MarketRegime]:
    """Todos los timeframes en régimen BULL → máximo bono posible."""
    return {
        "M15": MarketRegime.BULL,
        "H1":  MarketRegime.BULL,
        "H4":  MarketRegime.BULL,
        "D1":  MarketRegime.BULL,
    }


def _make_analyzer(enabled: bool = True, weights: Dict = None) -> MultiTimeframeConfluenceAnalyzer:
    storage = _make_storage_mock(weights)
    analyzer = MultiTimeframeConfluenceAnalyzer(storage=storage, enabled=enabled)
    return analyzer


# ── Tests de escala proporcional ──────────────────────────────────────────────

class TestConfluenciaProporcionalTiers:
    """Verificación de los tres tiers de escala proporcional."""

    def test_confluence_confidence_bajo_040_aplica_bonus_cero(self):
        """Señal con confidence=0.35 (<0.40) → bonus escalado = 0 (ningún bono)."""
        analyzer = _make_analyzer()
        signal = _make_signal(confidence=0.35)
        regimes = _make_all_bullish_regimes()

        result = analyzer.analyze_confluence(signal, regimes)

        assert result.metadata["confluence_bonus"] == pytest.approx(0.0)
        assert result.metadata["confluence_scale_factor"] == pytest.approx(0.0)

    def test_confluence_confidence_040_050_aplica_bonus_mitad(self):
        """Señal con confidence=0.45 ([0.40-0.50]) → bonus = bonus_bruto * 0.5."""
        analyzer = _make_analyzer()
        signal = _make_signal(confidence=0.45)
        regimes = _make_all_bullish_regimes()

        result = analyzer.analyze_confluence(signal, regimes)

        raw_bonus = result.metadata["confluence_bonus_raw"]
        scaled_bonus = result.metadata["confluence_bonus"]
        assert scaled_bonus == pytest.approx(raw_bonus * 0.5, abs=1e-6)
        assert result.metadata["confluence_scale_factor"] == pytest.approx(0.5)

    def test_confluence_confidence_mayor_050_aplica_bonus_completo(self):
        """Señal con confidence=0.65 (>0.50) → bonus escalado = bonus_bruto * 1.0."""
        analyzer = _make_analyzer()
        signal = _make_signal(confidence=0.65)
        regimes = _make_all_bullish_regimes()

        result = analyzer.analyze_confluence(signal, regimes)

        raw_bonus = result.metadata["confluence_bonus_raw"]
        scaled_bonus = result.metadata["confluence_bonus"]
        assert scaled_bonus == pytest.approx(raw_bonus * 1.0, abs=1e-6)
        assert result.metadata["confluence_scale_factor"] == pytest.approx(1.0)

    def test_confluence_boundary_040_exacto_aplica_05x(self):
        """Boundary: confidence=0.40 exacto → tier [0.40, 0.50], aplica 0.5x."""
        analyzer = _make_analyzer()
        signal = _make_signal(confidence=0.40)
        regimes = _make_all_bullish_regimes()

        result = analyzer.analyze_confluence(signal, regimes)

        assert result.metadata["confluence_scale_factor"] == pytest.approx(0.5)

    def test_confluence_boundary_050_exacto_aplica_05x(self):
        """Boundary: confidence=0.50 exacto → tier [0.40, 0.50] inclusive, aplica 0.5x."""
        analyzer = _make_analyzer()
        signal = _make_signal(confidence=0.50)
        regimes = _make_all_bullish_regimes()

        result = analyzer.analyze_confluence(signal, regimes)

        assert result.metadata["confluence_scale_factor"] == pytest.approx(0.5)


class TestConfluenciaMetadata:
    """Verificación de los campos de metadata generados."""

    def test_confluence_metadata_contiene_scale_factor(self):
        """Metadata debe contener 'confluence_scale_factor' en todos los casos."""
        analyzer = _make_analyzer()
        for conf in [0.30, 0.45, 0.55, 0.80]:
            signal = _make_signal(confidence=conf)
            result = analyzer.analyze_confluence(signal, _make_all_bullish_regimes())
            assert "confluence_scale_factor" in result.metadata, (
                f"Falta confluence_scale_factor para confidence={conf}"
            )

    def test_confluence_metadata_contiene_bonus_raw(self):
        """Metadata debe contener 'confluence_bonus_raw' (bonus antes de escalar)."""
        analyzer = _make_analyzer()
        signal = _make_signal(confidence=0.60)
        result = analyzer.analyze_confluence(signal, _make_all_bullish_regimes())

        assert "confluence_bonus_raw" in result.metadata
        assert isinstance(result.metadata["confluence_bonus_raw"], (int, float))


class TestConfluenciaValidacionS9:
    """Tests de validación del protocolo S-9 (Orden de Ingeniería)."""

    def test_confluence_fluency_signal_052_alta_confluencia_alcanza_grade_b(self):
        """
        S-9 Punto 4.1 - Test de Fluidez:
        Señal con confidence=0.52 + alta confluencia → Grade B (>0.60) o Grade A (>0.75).
        (confidence=0.52 > 0.50 → full bonus aplicado)
        """
        # Pesos con H1=20, H4=15 → bono fuerte
        analyzer = _make_analyzer(weights={"M15": 15.0, "H1": 20.0, "H4": 15.0, "D1": 10.0})
        signal = _make_signal(confidence=0.52)
        regimes = {
            "M15": MarketRegime.BULL,
            "H1":  MarketRegime.BULL,
            "H4":  MarketRegime.BULL,
            "D1":  MarketRegime.BULL,
        }

        result = analyzer.analyze_confluence(signal, regimes)

        # Grade A: >0.75 | Grade B: >0.60
        final_confidence = result.confidence
        assert final_confidence > 0.60, (
            f"Se esperaba Grade B (>0.60) pero confidence final = {final_confidence:.4f}"
        )

    def test_confluence_asymmetry_non_oliver_bypasses_trifecta(self):
        """
        S-9 Punto 4.2 - Test de Asimetría:
        Una estrategia de 'Ruptura' (no-oliver) sin flag requires_trifecta
        NO es evaluada por el módulo Trifecta.
        """
        from core_brain.signal_trifecta_optimizer import SignalTrifectaOptimizer

        mock_trifecta_analyzer = MagicMock()
        optimizer = SignalTrifectaOptimizer(trifecta_analyzer=mock_trifecta_analyzer)

        signal = _make_signal(confidence=0.70)
        signal.metadata = {"strategy_id": "brk_open_ruptura"}  # non-oliver, sin flag

        result_signals = optimizer.optimize([signal], scan_results={})

        # La señal debe pasar sin ser evaluada por trifecta
        assert len(result_signals) == 1
        assert result_signals[0] is signal
        # El analizador trifecta nunca debe haber sido llamado
        mock_trifecta_analyzer.analyze.assert_not_called()
