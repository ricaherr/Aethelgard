"""TDD for SHADOW pool bootstrap diagnostics counters and telemetry."""
import asyncio
import logging
from unittest.mock import MagicMock


def _make_active_instances(*strategy_ids: str):
    """Build minimal active-instance objects with strategy_id field."""
    instances = []
    for strategy_id in strategy_ids:
        instance = MagicMock()
        instance.strategy_id = strategy_id
        instances.append(instance)
    return instances


def _make_orchestrator(
    strategies_by_mode: dict,
    raise_on_create: str = None,
    active_strategy_ids=None,
):
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
    sm.storage.list_active_instances.return_value = _make_active_instances(
        *(active_strategy_ids or [])
    )

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

    def test_full_capacity_counts_as_skipped_at_capacity(self):
        """If SHADOW strategies are already at capacity, they must be counted as skipped."""
        orc, _ = _make_orchestrator(
            {
                "STRAT_A": "SHADOW",
                "STRAT_B": "SHADOW",
                "STRAT_C": "SHADOW",
            },
            active_strategy_ids=[
                "STRAT_A",
                "STRAT_A",
                "STRAT_B",
                "STRAT_B",
                "STRAT_C",
                "STRAT_C",
            ],
        )

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {
                    "STRAT_A": MagicMock(),
                    "STRAT_B": MagicMock(),
                    "STRAT_C": MagicMock(),
                },
                account_id="DEMO_001",
                variations_per_strategy=2,
            )
        )

        assert result["created"] == 0
        assert result["skipped"] == 3
        assert result["skipped_at_capacity"] == 3

    def test_not_shadow_counts_skipped_not_shadow(self):
        """Non-SHADOW strategies must increment skipped_not_shadow."""
        orc, _ = _make_orchestrator(
            {
                "STRAT_BACK": "BACKTEST",
                "STRAT_LIVE": "LIVE",
            }
        )

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {
                    "STRAT_BACK": MagicMock(),
                    "STRAT_LIVE": MagicMock(),
                },
                account_id="DEMO_001",
            )
        )

        assert result["created"] == 0
        assert result["skipped"] == 2
        assert result["skipped_not_shadow"] == 2
        assert result["failed"] == 0

    def test_mixed_summary_is_consistent(self):
        """created + skipped + failed must equal evaluated strategies in mixed scenario."""
        orc, _ = _make_orchestrator(
            {
                "STRAT_CREATE": "SHADOW",
                "STRAT_CAP": "SHADOW",
                "STRAT_FILTER": "BACKTEST",
                "STRAT_FAIL": "SHADOW",
            },
            raise_on_create="STRAT_FAIL",
            active_strategy_ids=["STRAT_CAP", "STRAT_CAP"],
        )

        result = asyncio.run(
            orc.initialize_shadow_pool(
                {
                    "STRAT_CREATE": MagicMock(),
                    "STRAT_CAP": MagicMock(),
                    "STRAT_FILTER": MagicMock(),
                    "STRAT_FAIL": MagicMock(),
                },
                account_id="DEMO_001",
                variations_per_strategy=1,
            )
        )

        assert result["created"] == 1
        assert result["skipped"] == 2
        assert result["failed"] == 1
        assert result["skipped_not_shadow"] == 1
        assert result["skipped_at_capacity"] == 1
        assert (result["created"] + result["skipped"] + result["failed"]) == 4

    def test_final_log_includes_skip_breakdown(self, caplog):
        """Final bootstrap log should expose skipped breakdown by reason."""
        orc, _ = _make_orchestrator(
            {
                "STRAT_FILTER": "BACKTEST",
                "STRAT_CAP": "SHADOW",
            },
            active_strategy_ids=["STRAT_CAP", "STRAT_CAP"],
        )

        with caplog.at_level(logging.INFO):
            asyncio.run(
                orc.initialize_shadow_pool(
                    {
                        "STRAT_FILTER": MagicMock(),
                        "STRAT_CAP": MagicMock(),
                    },
                    account_id="DEMO_001",
                    variations_per_strategy=2,
                )
            )

        assert "skipped_not_shadow=" in caplog.text
        assert "skipped_at_capacity=" in caplog.text
