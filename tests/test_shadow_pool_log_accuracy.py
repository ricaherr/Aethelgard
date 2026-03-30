"""
Tests TDD: initialize_shadow_pool debe distinguir skips legítimos de errores reales.

Bug: skipped_count acumula tanto estrategias no-SHADOW (esperado) como excepciones
reales. El log final dice "{skipped_count} failed" mezclando ambos casos.

Fix:
  - failed_count: solo excepciones al crear instancia.
  - skipped_count: solo filtros de modo (not in SHADOW).
  - Log: "{skipped_count} skipped (not SHADOW), {failed_count} failed".
  - Retorno: {"created": N, "skipped": N, "failed": N}.

RED state: falla porque skipped_count mezcla ambos casos.
"""
import asyncio
import pytest
from unittest.mock import MagicMock


def _make_orchestrator(strategies_by_mode: dict, raise_on_create: str = None):
    """
    Crea MainOrchestrator mínimo.
    raise_on_create: strategy_id que lanza excepción al crear instancia.
    """
    from core_brain.main_orchestrator import MainOrchestrator

    orc = object.__new__(MainOrchestrator)

    shadow_ids = {sid for sid, mode in strategies_by_mode.items() if mode == "SHADOW"}

    storage = MagicMock()
    storage.get_shadow_mode_strategy_ids.return_value = shadow_ids
    orc.storage = storage

    sm = MagicMock()
    sm.storage.list_active_instances.return_value = []

    if raise_on_create:
        def _create(**kwargs):
            if raise_on_create in kwargs.get("instance_id", ""):
                raise Exception("DB error")
        sm.storage.create_shadow_instance = MagicMock(side_effect=_create)
    else:
        sm.storage.create_shadow_instance = MagicMock()

    orc.shadow_manager = sm
    return orc, sm


class TestShadowPoolLogAccuracy:
    def test_skipped_does_not_count_mode_filtered_strategies(self):
        """
        Estrategias en BACKTEST que son filtradas por modo NO deben contarse en failed.
        El resultado debe exponer 'skipped' para filtros de modo.
        """
        orc, sm = _make_orchestrator({"STRAT_BACK": "BACKTEST", "STRAT_SHAD": "SHADOW"})

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {"STRAT_BACK": MagicMock(), "STRAT_SHAD": MagicMock()},
                account_id="DEMO_001",
            )
        )

        # STRAT_BACK es filtrado por modo — va a skipped, NO a failed
        assert result.get("skipped", 0) >= 1, (
            "STRAT_BACK (no SHADOW) debe contarse en 'skipped', no en 'failed'"
        )
        assert result.get("failed", 0) == 0, (
            "No hubo excepciones — 'failed' debe ser 0"
        )

    def test_failed_counts_real_exceptions(self):
        """
        Excepciones al crear instancias deben contarse en 'failed', no en 'skipped'.
        """
        orc, sm = _make_orchestrator(
            {"STRAT_SHAD": "SHADOW"},
            raise_on_create="STRAT_SHAD",
        )

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {"STRAT_SHAD": MagicMock()},
                account_id="DEMO_001",
            )
        )

        assert result.get("failed", 0) >= 1, (
            "Una excepción al crear instancia debe contarse en 'failed'"
        )

    def test_all_backtest_zero_failed(self):
        """Si todas las estrategias son BACKTEST (filtradas), failed debe ser 0."""
        orc, sm = _make_orchestrator({"STRAT_X": "BACKTEST", "STRAT_Y": "BACKTEST"})

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {"STRAT_X": MagicMock(), "STRAT_Y": MagicMock()},
                account_id="DEMO_001",
            )
        )

        assert result.get("failed", 0) == 0, (
            "Sin excepciones reales, 'failed' debe ser 0 aunque haya skips de modo"
        )
        assert result.get("skipped", 0) == 2

    def test_result_has_failed_key(self):
        """El dict retornado debe incluir la clave 'failed'."""
        orc, sm = _make_orchestrator({})

        result = asyncio.run(
            orc.initialize_shadow_pool({}, account_id="DEMO_001")
        )

        assert "failed" in result, (
            "initialize_shadow_pool debe retornar dict con clave 'failed'"
        )
