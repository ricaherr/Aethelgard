"""
Tests TDD: Filtro de modo en initialize_shadow_pool.

P4 — initialize_shadow_pool() debe ignorar estrategias que NO están en modo SHADOW.
Solo las estrategias con mode='SHADOW' en sys_strategies deben recibir instancias.

RED state: falla porque la función itera strategy_engines sin filtrar por modo DB.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


def _make_orchestrator(strategies_by_mode: dict):
    """
    Crea un MainOrchestrator mínimo con:
      - shadow_manager con storage que expone list_active_instances y create_shadow_instance
      - storage que responde get_strategies_by_mode({'SHADOW'}) con los de mode=SHADOW
    """
    from core_brain.main_orchestrator import MainOrchestrator

    orc = object.__new__(MainOrchestrator)

    # shadow_manager mock
    sm = MagicMock()
    sm.storage.list_active_instances.return_value = []
    sm.storage.create_shadow_instance = MagicMock()
    orc.shadow_manager = sm

    # storage principal — debe devolver qué strategies están en SHADOW
    shadow_ids = {sid for sid, mode in strategies_by_mode.items() if mode == "SHADOW"}
    storage = MagicMock()
    storage.get_shadow_mode_strategy_ids.return_value = shadow_ids
    orc.storage = storage

    return orc, sm


class TestShadowPoolModeFilter:
    def test_skips_backtest_strategies(self):
        """Estrategias en BACKTEST no deben recibir instancias shadow."""
        orc, sm = _make_orchestrator({"STRAT_BACK": "BACKTEST", "STRAT_SHAD": "SHADOW"})

        strategy_engines = {
            "STRAT_BACK": MagicMock(),
            "STRAT_SHAD": MagicMock(),
        }

        asyncio.run(
            orc.initialize_shadow_pool(strategy_engines, account_id="DEMO_001")
        )

        # Solo STRAT_SHAD debe haber tenido instancias creadas
        calls = sm.storage.create_shadow_instance.call_args_list
        strategy_ids_created = {c.kwargs.get("strategy_id") or c.args[0] for c in calls}
        assert "STRAT_BACK" not in strategy_ids_created, (
            "STRAT_BACK está en BACKTEST mode — no debe recibir instancias shadow"
        )

    def test_creates_instances_only_for_shadow_mode_strategies(self):
        """Solo estrategias en SHADOW mode deben tener instancias creadas."""
        orc, sm = _make_orchestrator({
            "STRAT_A": "BACKTEST",
            "STRAT_B": "SHADOW",
            "STRAT_C": "LIVE",
        })

        strategy_engines = {
            "STRAT_A": MagicMock(),
            "STRAT_B": MagicMock(),
            "STRAT_C": MagicMock(),
        }

        asyncio.run(
            orc.initialize_shadow_pool(strategy_engines, account_id="DEMO_001")
        )

        calls = sm.storage.create_shadow_instance.call_args_list
        strategy_ids_created = {c.kwargs.get("strategy_id") or c.args[0] for c in calls}
        assert strategy_ids_created == {"STRAT_B"}, (
            f"Solo STRAT_B (SHADOW) debería tener instancias. Obtenido: {strategy_ids_created}"
        )

    def test_all_backtest_returns_zero_created(self):
        """Si todas las estrategias están en BACKTEST, created=0."""
        orc, sm = _make_orchestrator({"STRAT_X": "BACKTEST", "STRAT_Y": "BACKTEST"})

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {"STRAT_X": MagicMock(), "STRAT_Y": MagicMock()},
                account_id="DEMO_001",
            )
        )

        assert result["created"] == 0
        sm.storage.create_shadow_instance.assert_not_called()

    def test_empty_engines_returns_zero(self):
        """Sin estrategias no debe fallar."""
        orc, sm = _make_orchestrator({})

        result = asyncio.run(
            orc.initialize_shadow_pool({}, account_id="DEMO_001")
        )

        assert result["created"] == 0
