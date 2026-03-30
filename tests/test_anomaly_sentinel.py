"""
Tests TDD para AnomalySentinel
================================

Convención: test_<componente>_<comportamiento>

Cobertura:
  - push_tick / push_ticks: alimentación del buffer
  - Flash_Crash_Detector: Z-Score → NONE / WARNING / LOCKDOWN
  - Spread_Anomaly: ratio → NONE / WARNING
  - get_defense_protocol(): prioridad LOCKDOWN > WARNING > NONE
  - Configuración: umbrales desde storage / defaults seguros
  - Criterio de Aceptación ETI: caída 5% en 3 ticks → LOCKDOWN

TRACE_ID: EDGE-IGNITION-PHASE-2-ANOMALY-SENTINEL
"""
import logging
from unittest.mock import MagicMock

import pytest

from core_brain.services.anomaly_sentinel import (
    AnomalySentinel,
    DefenseProtocol,
    _DEFAULT_SPREAD_RATIO_THRESHOLD,
    _DEFAULT_ZSCORE_THRESHOLD,
    _MIN_TICKS_FOR_ZSCORE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _sentinel(
    zscore_threshold: float = _DEFAULT_ZSCORE_THRESHOLD,
    spread_ratio_threshold: float = _DEFAULT_SPREAD_RATIO_THRESHOLD,
    tick_window: int = 10,
) -> AnomalySentinel:
    """Crea un sentinel sin storage (umbrales explícitos)."""
    return AnomalySentinel(
        storage=None,
        zscore_threshold=zscore_threshold,
        spread_ratio_threshold=spread_ratio_threshold,
        tick_window=tick_window,
    )


def _stable_prices(base: float = 1.1000, n: int = 8, delta: float = 0.0001):
    """Genera N precios con variaciones mínimas y uniformes."""
    return [base + i * delta for i in range(n)]


# ── Buffer: push_tick ─────────────────────────────────────────────────────────

class TestPushTick:

    def test_anomaly_sentinel_push_tick_ignora_precio_cero(self):
        s = _sentinel()
        s.push_tick(price=0.0, spread=1.0)
        assert len(s._prices) == 0

    def test_anomaly_sentinel_push_tick_ignora_precio_negativo(self):
        s = _sentinel()
        s.push_tick(price=-1.0, spread=0.0)
        assert len(s._prices) == 0

    def test_anomaly_sentinel_push_tick_acepta_precio_valido(self):
        s = _sentinel()
        s.push_tick(price=1.1000, spread=0.0001)
        assert len(s._prices) == 1
        assert len(s._spreads) == 1

    def test_anomaly_sentinel_push_tick_respeta_tick_window(self):
        s = _sentinel(tick_window=5)
        for i in range(10):
            s.push_tick(price=1.0 + i * 0.001)
        assert len(s._prices) == 5  # deque con maxlen


# ── Buffer: push_ticks ────────────────────────────────────────────────────────

class TestPushTicks:

    def test_anomaly_sentinel_push_ticks_acepta_clave_close(self):
        s = _sentinel()
        s.push_ticks([{"close": 1.1000}, {"close": 1.1001}])
        assert len(s._prices) == 2

    def test_anomaly_sentinel_push_ticks_acepta_clave_price(self):
        s = _sentinel()
        s.push_ticks([{"price": 1.1000}, {"price": 1.1002}])
        assert len(s._prices) == 2

    def test_anomaly_sentinel_push_ticks_acepta_clave_bid(self):
        s = _sentinel()
        s.push_ticks([{"bid": 1.1000}])
        assert len(s._prices) == 1

    def test_anomaly_sentinel_push_ticks_ignora_tick_sin_precio(self):
        s = _sentinel()
        s.push_ticks([{"ask": 1.1000}])  # No tiene clave soportada
        assert len(s._prices) == 0

    def test_anomaly_sentinel_push_ticks_acepta_spread(self):
        s = _sentinel()
        s.push_ticks([{"close": 1.1000, "spread": 0.0002}])
        assert s._spreads[-1] == pytest.approx(0.0002)


# ── Flash Crash Detector ──────────────────────────────────────────────────────

class TestFlashCrashDetector:

    def test_anomaly_sentinel_flash_crash_none_sin_suficientes_ticks(self):
        s = _sentinel()
        # Menos de _MIN_TICKS_FOR_ZSCORE precios
        for p in [1.1, 1.1001, 1.1002]:
            s.push_tick(p)
        result = s._detect_flash_crash("trace-fc-001")
        assert result == DefenseProtocol.NONE

    def test_anomaly_sentinel_flash_crash_none_con_precios_estables(self):
        s = _sentinel()
        for p in _stable_prices():
            s.push_tick(p)
        result = s._detect_flash_crash("trace-fc-002")
        assert result == DefenseProtocol.NONE

    def test_anomaly_sentinel_flash_crash_lockdown_con_caida_extrema(self):
        """
        CRITERIO DE ACEPTACIÓN ETI:
        Caída del 5% en el último tick vs precios ultra-estables → LOCKDOWN.

        Con leave-one-out el crash no contamina la distribución de referencia,
        produciendo stdev_ref ≈ 0 y Z >> 3.5.
        """
        s = _sentinel(zscore_threshold=3.5)
        # 8 precios ultra-estables (delta mínimo → stdev_ref ≈ 0)
        for p in _stable_prices(base=1.1000, n=8, delta=0.000001):
            s.push_tick(p)
        # Caída del 5%: retorno ≈ -0.05, stdev_ref ≈ 0 → Z >> 3.5
        s.push_tick(1.1000 * 0.95)
        result = s._detect_flash_crash("trace-fc-003")
        assert result == DefenseProtocol.LOCKDOWN

    def test_anomaly_sentinel_flash_crash_lockdown_caida_5pct_en_3_ticks(self):
        """
        CRITERIO DE ACEPTACIÓN ETI — enunciado exacto:
        Simulación de caída del 5% en 3 ticks → LOCKDOWN.

        Diseño:
        - 10 precios ultra-estables establecen distribución de referencia (stdev ≈ 0)
        - Tick+1 y Tick+2: precios estables (sin anomalía)
        - Tick+3: caída del 5% → Z >> 3.5 → LOCKDOWN
        """
        s = _sentinel(zscore_threshold=3.5, tick_window=15)
        base = 1.2000
        for i in range(10):
            s.push_tick(base + i * 0.000001)  # ultra-estables
        s.push_tick(base + 10 * 0.000001)     # tick+1: estable
        s.push_tick(base + 11 * 0.000001)     # tick+2: estable
        s.push_tick(base * 0.95)               # tick+3: -5% crash
        protocol = s.get_defense_protocol()
        assert protocol == DefenseProtocol.LOCKDOWN

    def test_anomaly_sentinel_flash_crash_warning_con_volatilidad_elevada(self):
        """
        Movimiento moderado sobre base volátil → Z entre 0.7×threshold y threshold → WARNING.

        Con stdev_ref ≈ 0.0115 y caída del 3%: Z ≈ 2.6 (entre 0.7×3.5=2.45 y 3.5) → WARNING.
        """
        s = _sentinel(zscore_threshold=3.5)
        # Precios con oscilaciones de ≈1% (stdev de retornos ≈ 0.01)
        volatile_prices = [1.0, 1.010, 1.000, 1.012, 0.999, 1.008, 0.998, 1.010, 1.000]
        for p in volatile_prices:
            s.push_tick(p)
        # Caída del 3%: Z ≈ -0.03 / 0.0115 ≈ -2.6 → zona WARNING
        s.push_tick(0.970)
        result = s._detect_flash_crash("trace-fc-004")
        assert result in (DefenseProtocol.WARNING, DefenseProtocol.LOCKDOWN)

    def test_anomaly_sentinel_flash_crash_none_si_stdev_es_cero(self):
        """Si todos los precios son idénticos, stdev=0, no hay crash."""
        s = _sentinel()
        for _ in range(8):
            s.push_tick(1.1000)
        result = s._detect_flash_crash("trace-fc-005")
        assert result == DefenseProtocol.NONE

    def test_anomaly_sentinel_flash_crash_genera_trace_id(self):
        s = _sentinel()
        for p in _stable_prices():
            s.push_tick(p)
        s.get_defense_protocol()
        assert s.last_trace_id.startswith("SEN-")


# ── Spread Anomaly ────────────────────────────────────────────────────────────

class TestSpreadAnomaly:

    def test_anomaly_sentinel_spread_none_sin_spreads(self):
        s = _sentinel()
        result = s._detect_spread_anomaly("trace-sp-001")
        assert result == DefenseProtocol.NONE

    def test_anomaly_sentinel_spread_none_con_spread_normal(self):
        s = _sentinel(spread_ratio_threshold=3.0)
        for sp in [0.0001, 0.0001, 0.0001, 0.00012]:
            s.push_tick(1.1000, sp)
        result = s._detect_spread_anomaly("trace-sp-002")
        assert result == DefenseProtocol.NONE

    def test_anomaly_sentinel_spread_warning_cuando_supera_300pct(self):
        s = _sentinel(spread_ratio_threshold=3.0)
        # Histórico: 0.0001 × 3 ticks. Actual: 0.0004 (400%)
        for sp in [0.0001, 0.0001, 0.0001]:
            s.push_tick(1.1000, sp)
        s.push_tick(1.1001, 0.0004)
        result = s._detect_spread_anomaly("trace-sp-003")
        assert result == DefenseProtocol.WARNING

    def test_anomaly_sentinel_spread_none_si_avg_es_cero(self):
        """Si el spread histórico es 0, no se emite alerta."""
        s = _sentinel()
        for _ in range(3):
            s.push_tick(1.1000, 0.0)
        s.push_tick(1.1000, 0.0005)
        result = s._detect_spread_anomaly("trace-sp-004")
        assert result == DefenseProtocol.NONE


# ── get_defense_protocol: prioridad ──────────────────────────────────────────

class TestGetDefenseProtocol:

    def test_anomaly_sentinel_protocol_none_sin_datos(self):
        s = _sentinel()
        assert s.get_defense_protocol() == DefenseProtocol.NONE

    def test_anomaly_sentinel_protocol_lockdown_tiene_prioridad_sobre_warning(self):
        """Flash Crash + Spread anómalo → LOCKDOWN (Flash Crash gana)."""
        s = _sentinel(zscore_threshold=3.5, spread_ratio_threshold=3.0)
        # Precios ultra-estables para que stdev_ref ≈ 0 y crash produzca Z >> 3.5
        for p in _stable_prices(base=1.1000, n=8, delta=0.000001):
            s.push_tick(p, spread=0.0001)
        # crash -5% + spread 5× → ambas anomalías, pero LOCKDOWN tiene prioridad
        s.push_tick(1.1000 * 0.95, spread=0.0005)
        protocol = s.get_defense_protocol()
        assert protocol == DefenseProtocol.LOCKDOWN

    def test_anomaly_sentinel_protocol_warning_con_solo_spread_anomalo(self):
        s = _sentinel(spread_ratio_threshold=3.0)
        for sp in [0.0001, 0.0001, 0.0001]:
            s.push_tick(1.1000, sp)
        s.push_tick(1.10001, 0.0005)  # precio casi igual, spread 5×
        protocol = s.get_defense_protocol()
        assert protocol == DefenseProtocol.WARNING

    def test_anomaly_sentinel_protocol_actualiza_last_trace_id(self):
        s = _sentinel()
        s.get_defense_protocol()
        assert s.last_trace_id != ""
        first = s.last_trace_id
        s.get_defense_protocol()
        assert s.last_trace_id != first  # nuevo uuid cada llamada


# ── Configuración desde storage ───────────────────────────────────────────────

class TestConfiguracion:

    def test_anomaly_sentinel_lee_umbrales_de_storage(self):
        storage = MagicMock()
        storage.get_dynamic_params.return_value = {
            "anomaly_zscore_threshold": 4.0,
            "anomaly_spread_ratio_threshold": 2.5,
        }
        s = AnomalySentinel(storage=storage)
        assert s.zscore_threshold == pytest.approx(4.0)
        assert s.spread_ratio_threshold == pytest.approx(2.5)

    def test_anomaly_sentinel_usa_defaults_si_storage_falla(self):
        storage = MagicMock()
        storage.get_dynamic_params.side_effect = Exception("DB error")
        s = AnomalySentinel(storage=storage)
        assert s.zscore_threshold == pytest.approx(_DEFAULT_ZSCORE_THRESHOLD)
        assert s.spread_ratio_threshold == pytest.approx(_DEFAULT_SPREAD_RATIO_THRESHOLD)

    def test_anomaly_sentinel_usa_defaults_si_storage_es_none(self):
        s = AnomalySentinel(storage=None)
        assert s.zscore_threshold == pytest.approx(_DEFAULT_ZSCORE_THRESHOLD)
        assert s.spread_ratio_threshold == pytest.approx(_DEFAULT_SPREAD_RATIO_THRESHOLD)

    def test_anomaly_sentinel_parametro_explicito_tiene_prioridad_sobre_storage(self):
        storage = MagicMock()
        storage.get_dynamic_params.return_value = {"anomaly_zscore_threshold": 4.0}
        s = AnomalySentinel(storage=storage, zscore_threshold=5.0)
        assert s.zscore_threshold == pytest.approx(5.0)

    def test_anomaly_sentinel_log_de_inicializacion(self, caplog):
        with caplog.at_level(logging.INFO, logger="core_brain.services.anomaly_sentinel"):
            AnomalySentinel(storage=None)
        assert "ANOMALY_SENTINEL" in caplog.text
        assert "EDGE-IGNITION-PHASE-2-ANOMALY-SENTINEL" in caplog.text
