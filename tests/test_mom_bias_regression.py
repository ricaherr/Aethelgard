"""
Tests de regresión: MOM_BIAS_0001 + MovingAverageSensor.

P5 — El error 'get_sma' fue corregido en código pero sin test de regresión.
Este test evita que el bug regrese en futuros refactors.

Expected state: GREEN desde el inicio (el fix ya está en producción).
"""
import pytest
from core_brain.sensors.moving_average_sensor import MovingAverageSensor


class TestMovingAverageSensorInterface:
    def test_has_calculate_sma(self):
        """MovingAverageSensor debe exponer calculate_sma (método correcto)."""
        assert hasattr(MovingAverageSensor, "calculate_sma"), (
            "calculate_sma debe existir — si falla, alguien lo renombró sin actualizar mom_bias_0001"
        )
        assert callable(getattr(MovingAverageSensor, "calculate_sma"))

    def test_does_not_have_get_sma(self):
        """get_sma NO debe existir — fue el nombre incorrecto que causó el bug."""
        assert not hasattr(MovingAverageSensor, "get_sma"), (
            "get_sma no debe existir en MovingAverageSensor — si aparece, revisar mom_bias_0001"
        )

    def test_mom_bias_calls_calculate_sma_not_get_sma(self):
        """El source de mom_bias_0001 debe usar calculate_sma, no get_sma."""
        import inspect
        from core_brain.strategies import mom_bias_0001
        source = inspect.getsource(mom_bias_0001)
        assert "get_sma" not in source, (
            "mom_bias_0001 contiene 'get_sma' — usar 'calculate_sma'"
        )
        assert "calculate_sma" in source, (
            "mom_bias_0001 debe llamar 'calculate_sma' en MovingAverageSensor"
        )
