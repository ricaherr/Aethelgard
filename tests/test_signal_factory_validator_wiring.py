"""
ETI-01 / GAP-01 — Wiring de StrategySignalValidator en SignalFactory
====================================================================

TDD: Los 3 tests deben FALLAR antes del fix en signal_factory.py.

AC-1: Con validator inyectado y pilar fallando → señal no se persiste,
      funnel_reasons["validator_rejected"] += 1
AC-2: Con validator inyectado y todos los pilares PASSED → señal pasa al
      flujo normal completo (storage.save_signal llamado)
AC-3: Sin validator (None) → comportamiento actual inalterado
      (señal siempre pasa)
AC-4: El ValidationReport se loguea con trace_id (verificado via AC-1/AC-2)
"""
import pytest
from collections import Counter
from unittest.mock import AsyncMock, MagicMock, patch

import pandas as pd

from core_brain.signal_factory import SignalFactory
from core_brain.strategy_validator_quanter import (
    StrategySignalValidator,
    ValidationReport,
    PillarStatus,
    PillarValidationResult,
)
from models.signal import Signal, SignalType, MarketRegime, ConnectorType
from data_vault.storage import StorageManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(symbol: str = "EURUSD", strategy_id: str = "S-0001") -> Signal:
    """Señal mínima válida para las pruebas."""
    signal = MagicMock(spec=Signal)
    signal.symbol = symbol
    signal.signal_type = SignalType.BUY
    signal.entry_price = 1.08500
    signal.timeframe = "M5"
    signal.trace_id = "trace-test-001"
    signal.provider_source = None
    signal.connector_type = ConnectorType.METATRADER5
    signal.metadata = {
        "strategy_id": strategy_id,
        "score": 75.0,
        "confidence": 0.80,
        "confluence_elements": ["EMA_CROSS", "RSI_OK"],
        "membership_tier": "PREMIUM",
    }
    return signal


def _make_engine_mock(signal: Signal) -> MagicMock:
    """
    Engine mock con solo el método `analyze` visible.
    Usar spec=['analyze'] evita que MagicMock auto-cree `execute_from_registry`,
    lo que forzaría el path JSON_SCHEMA en generate_signal().
    """
    engine = MagicMock(spec=["analyze"])
    engine.analyze = AsyncMock(return_value=signal)
    return engine


def _make_failed_report(strategy_id: str, symbol: str, trace_id: str) -> ValidationReport:
    """ValidationReport con pilar Sensorial fallando."""
    failed_result = PillarValidationResult(
        pillar_name="SensorialPillar",
        status=PillarStatus.FAILED,
        confidence=0.0,
        reason="Sensor data stale (>30s)",
    )
    return ValidationReport(
        strategy_id=strategy_id,
        symbol=symbol,
        overall_status=PillarStatus.FAILED,
        pillars=[failed_result],
        overall_confidence=0.0,
        trace_id=trace_id,
    )


def _make_passed_report(strategy_id: str, symbol: str, trace_id: str) -> ValidationReport:
    """ValidationReport con todos los pilares PASSED."""
    passed_result = PillarValidationResult(
        pillar_name="CoherencePillar",
        status=PillarStatus.PASSED,
        confidence=0.90,
        reason="All checks OK",
    )
    return ValidationReport(
        strategy_id=strategy_id,
        symbol=symbol,
        overall_status=PillarStatus.PASSED,
        pillars=[passed_result],
        overall_confidence=0.90,
        trace_id=trace_id,
    )


def _make_factory(
    mock_storage: MagicMock,
    signal_validator: "StrategySignalValidator | None" = None,
) -> SignalFactory:
    """Construye un SignalFactory con dependencias mínimas mockeadas."""
    with patch("core_brain.signal_factory.get_notifier", return_value=None):
        confluence = MagicMock()
        confluence.enabled = False
        trifecta = MagicMock()

        factory = SignalFactory(
            storage_manager=mock_storage,
            strategy_engines={},
            confluence_analyzer=confluence,
            trifecta_analyzer=trifecta,
            signal_validator=signal_validator,
        )
    return factory


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_storage() -> MagicMock:
    storage = MagicMock(spec=StorageManager)
    storage.save_signal.return_value = "signal-test-001"
    storage.has_recent_signal.return_value = False
    storage.has_open_position.return_value = False
    storage.get_dynamic_params.return_value = {}
    storage.get_signal_ranking.return_value = {"execution_mode": "SHADOW"}
    return storage


# ---------------------------------------------------------------------------
# AC-1: Validator inyectado + pilar FAILING → señal rechazada
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signal_factory_validator_rechaza_cuando_pilar_falla(mock_storage):
    """
    AC-1: Si el validator devuelve un report FAILED, la señal NO debe
    persistirse y funnel_reasons["validator_rejected"] debe incrementarse.
    """
    signal = _make_signal()
    strategy_id = signal.metadata["strategy_id"]
    trace_id = signal.trace_id

    mock_validator = AsyncMock(spec=StrategySignalValidator)
    mock_validator.validate.return_value = _make_failed_report(
        strategy_id, signal.symbol, trace_id
    )

    factory = _make_factory(mock_storage, signal_validator=mock_validator)
    factory.signal_deduplicator.is_duplicate = MagicMock(return_value=False)
    factory.strategy_engines = {strategy_id: _make_engine_mock(signal)}

    funnel_reasons: Counter = Counter()

    with patch(
        "core_brain.signal_factory.StrategySignalConverter.convert_from_python_class",
        return_value=signal,
    ):
        result = await factory.generate_signal(
            symbol=signal.symbol,
            df=pd.DataFrame(),
            regime=MarketRegime.TREND,
            trace_id=trace_id,
            funnel_reasons=funnel_reasons,
        )

    mock_storage.save_signal.assert_not_called()
    assert funnel_reasons["validator_rejected"] >= 1, (
        "funnel_reasons['validator_rejected'] debe incrementarse al rechazar la señal"
    )
    assert result == [], "No debe haber señales cuando el validator rechaza"


# ---------------------------------------------------------------------------
# AC-2: Validator inyectado + todos los pilares PASSED → señal persiste
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signal_factory_validator_aprueba_cuando_todos_pilares_pasan(mock_storage):
    """
    AC-2: Si el validator devuelve un report PASSED, la señal DEBE
    persistirse y aparecer en el resultado.
    """
    signal = _make_signal()
    strategy_id = signal.metadata["strategy_id"]
    trace_id = signal.trace_id

    mock_validator = AsyncMock(spec=StrategySignalValidator)
    mock_validator.validate.return_value = _make_passed_report(
        strategy_id, signal.symbol, trace_id
    )

    factory = _make_factory(mock_storage, signal_validator=mock_validator)
    factory.signal_deduplicator.is_duplicate = MagicMock(return_value=False)
    factory.signal_enricher.enrich = AsyncMock()
    factory._should_suppress_signal = MagicMock(return_value=False)
    factory.strategy_engines = {strategy_id: _make_engine_mock(signal)}

    funnel_reasons: Counter = Counter()

    with patch(
        "core_brain.signal_factory.StrategySignalConverter.convert_from_python_class",
        return_value=signal,
    ):
        result = await factory.generate_signal(
            symbol=signal.symbol,
            df=pd.DataFrame(),
            regime=MarketRegime.TREND,
            trace_id=trace_id,
            funnel_reasons=funnel_reasons,
        )

    mock_storage.save_signal.assert_called_once()
    assert len(result) == 1, "La señal aprobada debe aparecer en el resultado"
    assert funnel_reasons["validator_rejected"] == 0


# ---------------------------------------------------------------------------
# AC-3: Sin validator (None) → flujo actual inalterado
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_signal_factory_sin_validator_pasa_todas_las_señales(mock_storage):
    """
    AC-3: Cuando signal_validator=None, todas las señales válidas pasan
    sin ninguna validación adicional de pilares.
    """
    signal = _make_signal()
    strategy_id = signal.metadata["strategy_id"]

    factory = _make_factory(mock_storage, signal_validator=None)
    factory.signal_deduplicator.is_duplicate = MagicMock(return_value=False)
    factory.signal_enricher.enrich = AsyncMock()
    factory._should_suppress_signal = MagicMock(return_value=False)
    factory.strategy_engines = {strategy_id: _make_engine_mock(signal)}

    funnel_reasons: Counter = Counter()

    with patch(
        "core_brain.signal_factory.StrategySignalConverter.convert_from_python_class",
        return_value=signal,
    ):
        result = await factory.generate_signal(
            symbol=signal.symbol,
            df=pd.DataFrame(),
            regime=MarketRegime.TREND,
            funnel_reasons=funnel_reasons,
        )

    mock_storage.save_signal.assert_called_once()
    assert len(result) == 1, "Sin validator, la señal debe pasar normalmente"
    assert funnel_reasons["validator_rejected"] == 0
