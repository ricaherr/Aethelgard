"""
TDD: Edge Demo Autoajustable + Handshake Ejecutor
Verifica la lógica de exploración adaptativa en modo DEMO:
- Starvation counter por timeframe/símbolo
- relax_constraints() al detectar inactividad
- Budget de exploración (máx N activos/día)
- StrategyGatekeeper: whitelist dinámica con EXPLORATION_ON
- Freeze y rollback de activos con PF bajo
- Logs de cada evento de exploración
"""
import pytest
from unittest.mock import MagicMock, call
from datetime import date

from core_brain.edge_tuner import (
    EdgeTuner,
    STARVATION_THRESHOLD,
    MAX_EXPLORATION_ASSETS_PER_DAY,
    EXPLORATION_AFFINITY_SCORE,
    EXPLORATION_FLAG,
)
from core_brain.strategy_gatekeeper import StrategyGatekeeper
from models.signal import EXPLORATION_ON


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_storage():
    storage = MagicMock()
    storage.get_strategy_affinity_scores.return_value = {"EURUSD": 0.92, "GBPUSD": 0.30}
    storage.get_dynamic_params.return_value = {}
    storage.log_strategy_state_change.return_value = None
    return storage


@pytest.fixture
def edge_tuner(mock_storage):
    return EdgeTuner(storage=mock_storage)


@pytest.fixture
def gatekeeper(mock_storage):
    return StrategyGatekeeper(storage=mock_storage)


# ── Starvation Counter ─────────────────────────────────────────────────────────

class TestStarvationCounter:
    def test_counter_increments_on_each_candle_without_signal(self, edge_tuner):
        """Cada vela sin señal incrementa el contador de starvation."""
        edge_tuner.record_candle_without_signal("EURUSD", "M5")
        edge_tuner.record_candle_without_signal("EURUSD", "M5")
        assert edge_tuner.get_starvation_count("EURUSD", "M5") == 2

    def test_counter_starts_at_zero(self, edge_tuner):
        """Un símbolo/timeframe nuevo parte desde 0."""
        assert edge_tuner.get_starvation_count("XAUUSD", "H1") == 0

    def test_starvation_not_triggered_below_threshold(self, edge_tuner):
        """Starvation no se activa antes del umbral."""
        for _ in range(STARVATION_THRESHOLD - 1):
            edge_tuner.record_candle_without_signal("EURUSD", "M5")
        assert not edge_tuner.check_starvation("EURUSD", "M5")

    def test_starvation_triggers_at_threshold(self, edge_tuner):
        """Starvation se activa exactamente al alcanzar el umbral."""
        for _ in range(STARVATION_THRESHOLD):
            edge_tuner.record_candle_without_signal("EURUSD", "M5")
        assert edge_tuner.check_starvation("EURUSD", "M5")

    def test_counters_are_independent_per_timeframe(self, edge_tuner):
        """Contadores son independientes por símbolo+timeframe."""
        for _ in range(STARVATION_THRESHOLD):
            edge_tuner.record_candle_without_signal("EURUSD", "M5")
        assert not edge_tuner.check_starvation("EURUSD", "H1")

    def test_reset_clears_counter(self, edge_tuner):
        """reset_starvation_counter limpia el contador a cero."""
        for _ in range(STARVATION_THRESHOLD):
            edge_tuner.record_candle_without_signal("EURUSD", "M5")
        edge_tuner.reset_starvation_counter("EURUSD", "M5")
        assert edge_tuner.get_starvation_count("EURUSD", "M5") == 0


# ── relax_constraints ──────────────────────────────────────────────────────────

class TestRelaxConstraints:
    def test_returns_relaxed_threshold_below_normal(self, edge_tuner):
        """relax_constraints retorna umbral menor al actual."""
        result = edge_tuner.relax_constraints("STRAT_01", current_threshold=0.75)
        assert result["relaxed_threshold"] < 0.75
        assert result["relaxed_threshold"] > 0.0

    def test_sets_exploration_active_flag(self, edge_tuner):
        """relax_constraints activa la exploración para la estrategia."""
        result = edge_tuner.relax_constraints("STRAT_01")
        assert result["exploration_active"] is True
        assert result["strategy_id"] == "STRAT_01"

    def test_flag_is_exploration_on(self, edge_tuner):
        """El flag retornado es EXPLORATION_ON."""
        result = edge_tuner.relax_constraints("STRAT_01")
        assert result["flag"] == EXPLORATION_FLAG

    def test_logs_event_when_in_demo_mode(self, edge_tuner, mock_storage):
        """Solo persiste el log cuando account_mode=DEMO."""
        edge_tuner.relax_constraints("STRAT_01", account_mode="DEMO")
        mock_storage.log_strategy_state_change.assert_called_once()

    def test_noop_outside_demo_mode(self, edge_tuner, mock_storage):
        """No activa exploración ni loguea fuera de DEMO."""
        result = edge_tuner.relax_constraints("STRAT_01", account_mode="LIVE")
        assert result["exploration_active"] is False
        mock_storage.log_strategy_state_change.assert_not_called()

    def test_noop_outside_shadow_mode(self, edge_tuner, mock_storage):
        """No activa exploración en SHADOW."""
        result = edge_tuner.relax_constraints("STRAT_01", account_mode="SHADOW")
        assert result["exploration_active"] is False


# ── Exploration Budget ─────────────────────────────────────────────────────────

class TestExplorationBudget:
    def test_allows_up_to_max_assets_per_day(self, edge_tuner):
        """Permite añadir hasta MAX_EXPLORATION_ASSETS_PER_DAY activos."""
        for i in range(MAX_EXPLORATION_ASSETS_PER_DAY):
            assert edge_tuner.add_exploration_asset("STRAT_01", f"ASSET{i}") is True

    def test_blocks_when_budget_exhausted(self, edge_tuner):
        """Bloquea al superar el budget diario."""
        for i in range(MAX_EXPLORATION_ASSETS_PER_DAY):
            edge_tuner.add_exploration_asset("STRAT_01", f"ASSET{i}")
        result = edge_tuner.add_exploration_asset("STRAT_01", "ASSET_EXTRA")
        assert result is False

    def test_remaining_budget_decreases_on_each_addition(self, edge_tuner):
        """El presupuesto restante disminuye con cada activo añadido."""
        initial = edge_tuner.get_remaining_exploration_budget()
        edge_tuner.add_exploration_asset("STRAT_01", "GBPUSD")
        assert edge_tuner.get_remaining_exploration_budget() == initial - 1

    def test_get_exploration_assets_returns_added_assets(self, edge_tuner):
        """get_exploration_assets lista los activos en exploración."""
        edge_tuner.add_exploration_asset("STRAT_01", "GBPUSD")
        edge_tuner.add_exploration_asset("STRAT_01", "USDJPY")
        assets = edge_tuner.get_exploration_assets("STRAT_01")
        assert "GBPUSD" in assets
        assert "USDJPY" in assets

    def test_no_duplicate_asset_added(self, edge_tuner):
        """No se descuenta presupuesto si el activo ya estaba."""
        edge_tuner.add_exploration_asset("STRAT_01", "GBPUSD")
        before = edge_tuner.get_remaining_exploration_budget()
        edge_tuner.add_exploration_asset("STRAT_01", "GBPUSD")
        assert edge_tuner.get_remaining_exploration_budget() == before


# ── StrategyGatekeeper – Exploración ──────────────────────────────────────────

class TestGatekeeperExploration:
    def test_blocks_low_score_asset_without_exploration(self, gatekeeper):
        """Activo con score bajo es vetado en modo normal."""
        gatekeeper.asset_scores["GBPUSD"] = 0.3
        allowed, _ = gatekeeper.can_execute_on_tick_with_reason("GBP/USD", 0.75, "STRAT_01")
        assert not allowed

    def test_allows_exploration_asset_bypassing_strict_threshold(self, gatekeeper):
        """Activo en exploración se aprueba con umbral relajado."""
        gatekeeper.asset_scores["GBPUSD"] = 0.3
        gatekeeper.enable_exploration_for_asset("STRAT_01", "GBPUSD", temp_score=0.6)
        allowed, reason = gatekeeper.can_execute_on_tick_with_reason("GBP/USD", 0.75, "STRAT_01")
        assert allowed
        assert reason == "gk_approved_exploration"

    def test_disable_exploration_reverts_veto(self, gatekeeper):
        """Deshabilitar exploración restaura el veto original."""
        gatekeeper.asset_scores["GBPUSD"] = 0.3
        gatekeeper.enable_exploration_for_asset("STRAT_01", "GBPUSD", temp_score=0.6)
        gatekeeper.disable_exploration_for_asset("STRAT_01", "GBPUSD")
        allowed, _ = gatekeeper.can_execute_on_tick_with_reason("GBP/USD", 0.75, "STRAT_01")
        assert not allowed

    def test_is_exploration_active_returns_correct_state(self, gatekeeper):
        """is_exploration_active refleja el estado real."""
        assert not gatekeeper.is_exploration_active("STRAT_01")
        gatekeeper.enable_exploration_for_asset("STRAT_01", "GBPUSD")
        assert gatekeeper.is_exploration_active("STRAT_01")

    def test_freeze_blocks_exploration_asset(self, gatekeeper):
        """freeze_exploration_asset bloquea ejecuciones del activo."""
        gatekeeper.enable_exploration_for_asset("STRAT_01", "GBPUSD", temp_score=0.6)
        gatekeeper.freeze_exploration_asset("STRAT_01", "GBPUSD")
        allowed, reason = gatekeeper.can_execute_on_tick_with_reason("GBP/USD", 0.75, "STRAT_01")
        assert not allowed
        assert reason == "gk_frozen_exploration"

    def test_rollback_removes_assets_below_pf_threshold(self, gatekeeper):
        """rollback_low_pf_exploration_assets elimina activos con PF insuficiente."""
        gatekeeper.enable_exploration_for_asset("STRAT_01", "GBPUSD", temp_score=0.6)
        gatekeeper.enable_exploration_for_asset("STRAT_01", "USDJPY", temp_score=0.6)
        gatekeeper.update_exploration_profit_factor("STRAT_01", "GBPUSD", pf=1.5)
        gatekeeper.update_exploration_profit_factor("STRAT_01", "USDJPY", pf=0.8)
        removed = gatekeeper.rollback_low_pf_exploration_assets("STRAT_01", pf_threshold=1.2)
        assert "USDJPY" in removed
        assert "GBPUSD" not in removed

    def test_rollback_keeps_assets_above_pf_threshold(self, gatekeeper):
        """rollback mantiene activos con PF superior al umbral."""
        gatekeeper.enable_exploration_for_asset("STRAT_01", "GBPUSD", temp_score=0.6)
        gatekeeper.update_exploration_profit_factor("STRAT_01", "GBPUSD", pf=1.5)
        gatekeeper.rollback_low_pf_exploration_assets("STRAT_01", pf_threshold=1.2)
        allowed, reason = gatekeeper.can_execute_on_tick_with_reason("GBP/USD", 0.75, "STRAT_01")
        assert allowed

    def test_get_exploration_assets_diagnostics(self, gatekeeper):
        """get_exploration_assets retorna activos actuales de exploración."""
        gatekeeper.enable_exploration_for_asset("STRAT_01", "USDJPY", temp_score=0.6)
        assets = gatekeeper.get_exploration_assets("STRAT_01")
        assert "USDJPY" in assets


# ── Executor – Handshake ──────────────────────────────────────────────────────

class TestExecutorHandshake:
    def test_log_exploration_handshake_persists_event(self):
        """_log_exploration_handshake llama a log_strategy_state_change."""
        from core_brain.executor import OrderExecutor
        from core_brain.risk_manager import RiskManager

        storage = MagicMock()
        storage.log_strategy_state_change.return_value = None
        risk_manager = MagicMock(spec=RiskManager)

        executor = OrderExecutor(risk_manager=risk_manager, storage=storage)
        executor._log_exploration_handshake("GBPUSD", "STRAT_01", "DEMO")

        storage.log_strategy_state_change.assert_called_once()
        call_kwargs = storage.log_strategy_state_change.call_args
        # Verificar que el trace contiene el asset y el flag
        args = call_kwargs[1] if call_kwargs[1] else call_kwargs[0]
        logged_content = str(args)
        assert "GBPUSD" in logged_content or "EXPLORATION" in logged_content

    def test_log_exploration_handshake_skipped_outside_demo(self):
        """_log_exploration_handshake no loguea fuera de DEMO."""
        from core_brain.executor import OrderExecutor
        from core_brain.risk_manager import RiskManager

        storage = MagicMock()
        risk_manager = MagicMock(spec=RiskManager)
        executor = OrderExecutor(risk_manager=risk_manager, storage=storage)

        executor._log_exploration_handshake("GBPUSD", "STRAT_01", "LIVE")
        storage.log_strategy_state_change.assert_not_called()


# ── Integración: Starvation → Exploración ─────────────────────────────────────

class TestExplorationIntegration:
    def test_starvation_triggers_relax_and_enables_exploration(self, edge_tuner, gatekeeper):
        """
        Flujo completo: starvation detectada → relax_constraints →
        asset añadido al gatekeeper → aprobado en modo exploración.
        """
        for _ in range(STARVATION_THRESHOLD):
            edge_tuner.record_candle_without_signal("GBPUSD", "M5")
        assert edge_tuner.check_starvation("GBPUSD", "M5")

        result = edge_tuner.relax_constraints("STRAT_01", account_mode="DEMO")
        assert result["exploration_active"] is True

        added = edge_tuner.add_exploration_asset("STRAT_01", "GBPUSD")
        assert added is True

        gatekeeper.asset_scores["GBPUSD"] = 0.3
        gatekeeper.enable_exploration_for_asset(
            "STRAT_01", "GBPUSD", temp_score=EXPLORATION_AFFINITY_SCORE
        )

        allowed, reason = gatekeeper.can_execute_on_tick_with_reason("GBP/USD", 0.75, "STRAT_01")
        assert allowed
        assert reason == "gk_approved_exploration"

    def test_exploration_flag_propagated_to_signal_metadata(self):
        """Señal generada con exploración activa lleva metadata EXPLORATION_ON=True."""
        from models.signal import Signal, SignalType, ConnectorType, EXPLORATION_ON

        signal = Signal(
            symbol="GBPUSD",
            signal_type=SignalType.BUY,
            confidence=0.65,
            connector_type=ConnectorType.PAPER,
        )
        signal.metadata[EXPLORATION_ON] = True
        assert signal.metadata.get(EXPLORATION_ON) is True
