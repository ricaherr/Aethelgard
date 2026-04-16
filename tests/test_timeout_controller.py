"""
Tests TDD: TimeoutController dinámico para operaciones EDGE.

Criterios de aceptación:
- Timeout se ajusta por modo operacional.
- Timeout lee el valor base desde sys_config en BD.
- Timeout se ajusta dinámicamente con latencia registrada.
- Si BD no está disponible, usa defaults de código.
- Valores acotados a [_MIN_TIMEOUT, _MAX_TIMEOUT].
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from core_brain.timeout_controller import TimeoutController


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage(config: dict | None = None) -> MagicMock:
    storage = MagicMock()
    storage.get_sys_config.return_value = config or {}
    return storage


# ---------------------------------------------------------------------------
# Test: defaults por modo cuando BD no tiene valor
# ---------------------------------------------------------------------------

class TestDefaultsPorModo:
    """Sin valor en BD, deben usarse defaults según contexto/modo."""

    def test_default_live_active(self):
        tc = TimeoutController(storage=_make_storage({}))
        assert tc.get_timeout("LIVE_ACTIVE") == 30

    def test_default_shadow_active(self):
        tc = TimeoutController(storage=_make_storage({}))
        assert tc.get_timeout("SHADOW_ACTIVE") == 60

    def test_default_backtest_only(self):
        tc = TimeoutController(storage=_make_storage({}))
        assert tc.get_timeout("BACKTEST_ONLY") == 120

    def test_default_contexto_desconocido(self):
        tc = TimeoutController(storage=_make_storage({}))
        # Contexto desconocido → DEFAULT = 30
        assert tc.get_timeout("UNKNOWN_MODE") == 30

    def test_sin_storage_usa_defaults(self):
        tc = TimeoutController(storage=None)
        assert tc.get_timeout("LIVE_ACTIVE") == 30
        assert tc.get_timeout("SHADOW_ACTIVE") == 60


# ---------------------------------------------------------------------------
# Test: lectura desde BD (sys_config)
# ---------------------------------------------------------------------------

class TestLecturaDesdeDB:
    """El valor de BD debe tener precedencia sobre el default de código."""

    def test_timeout_desde_bd_live_active(self):
        storage = _make_storage({"edge_timeout_live_active": 45})
        tc = TimeoutController(storage=storage)
        assert tc.get_timeout("LIVE_ACTIVE") == 45

    def test_timeout_desde_bd_shadow_active(self):
        storage = _make_storage({"edge_timeout_shadow_active": 90})
        tc = TimeoutController(storage=storage)
        assert tc.get_timeout("SHADOW_ACTIVE") == 90

    def test_timeout_desde_bd_backtest_only(self):
        storage = _make_storage({"edge_timeout_backtest_only": 180})
        tc = TimeoutController(storage=storage)
        assert tc.get_timeout("BACKTEST_ONLY") == 180

    def test_valor_bd_como_string_se_convierte_a_int(self):
        """BD puede retornar valores como strings — deben convertirse."""
        storage = _make_storage({"edge_timeout_live_active": "55"})
        tc = TimeoutController(storage=storage)
        assert tc.get_timeout("LIVE_ACTIVE") == 55

    def test_fallo_bd_usa_default(self):
        """Si la BD lanza excepción, se usa el default de código."""
        storage = MagicMock()
        storage.get_sys_config.side_effect = Exception("DB locked")
        tc = TimeoutController(storage=storage)
        assert tc.get_timeout("LIVE_ACTIVE") == 30


# ---------------------------------------------------------------------------
# Test: ajuste dinámico por latencia
# ---------------------------------------------------------------------------

class TestAjustePorLatencia:
    """La latencia registrada debe escalar el timeout de forma proporcional."""

    def test_sin_latencia_timeout_sin_cambio(self):
        tc = TimeoutController(storage=_make_storage({}))
        base = tc.get_timeout("LIVE_ACTIVE")
        tc.record_latency(0)
        assert tc.get_timeout("LIVE_ACTIVE") == base

    def test_latencia_baja_ajuste_minimo(self):
        """500 ms → factor ~1.05 → cambio mínimo."""
        tc = TimeoutController(storage=_make_storage({}))
        tc.record_latency(500)
        # 30 * 1.05 = 31 (int)
        result = tc.get_timeout("LIVE_ACTIVE")
        assert result >= 30  # nunca baja del base

    def test_latencia_alta_escala_timeout(self):
        """10 000 ms (10s) → factor 2.0 → timeout doble."""
        tc = TimeoutController(storage=_make_storage({}))
        tc.record_latency(10_000)
        result = tc.get_timeout("LIVE_ACTIVE")
        # 30 * 2.0 = 60
        assert result == 60

    def test_latencia_muy_alta_acotada_a_triple(self):
        """Latencias extremas → máximo factor 3x."""
        tc = TimeoutController(storage=_make_storage({}))
        tc.record_latency(100_000)  # 100 s
        result = tc.get_timeout("LIVE_ACTIVE")
        # 30 * 3 = 90 (max factor)
        assert result == 90

    def test_timeout_no_supera_max(self):
        """El timeout siempre debe ser ≤ _MAX_TIMEOUT."""
        storage = _make_storage({"edge_timeout_backtest_only": 200})
        tc = TimeoutController(storage=storage)
        tc.record_latency(100_000)
        result = tc.get_timeout("BACKTEST_ONLY")
        # 200 * 3 = 600 → acotado a 300
        assert result == tc._MAX_TIMEOUT

    def test_timeout_no_baja_de_min(self):
        """El timeout siempre debe ser ≥ _MIN_TIMEOUT."""
        storage = _make_storage({"edge_timeout_live_active": 1})
        tc = TimeoutController(storage=storage)
        result = tc.get_timeout("LIVE_ACTIVE")
        assert result >= tc._MIN_TIMEOUT

    def test_latencia_negativa_ignorada(self):
        """Latencias negativas no deben afectar el timeout."""
        tc = TimeoutController(storage=_make_storage({}))
        tc.record_latency(-500)
        assert tc.get_current_latency_ms() == 0.0
        assert tc.get_timeout("LIVE_ACTIVE") == 30


# ---------------------------------------------------------------------------
# Test: API de registro y lectura de latencia
# ---------------------------------------------------------------------------

class TestRegistroLatencia:

    def test_record_latency_persiste(self):
        tc = TimeoutController()
        tc.record_latency(1234.5)
        assert tc.get_current_latency_ms() == 1234.5

    def test_latencia_inicial_es_cero(self):
        tc = TimeoutController()
        assert tc.get_current_latency_ms() == 0.0

    def test_latencia_se_actualiza_con_nueva_llamada(self):
        tc = TimeoutController()
        tc.record_latency(100)
        tc.record_latency(500)
        assert tc.get_current_latency_ms() == 500.0
