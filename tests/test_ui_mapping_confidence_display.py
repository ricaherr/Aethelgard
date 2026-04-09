import math
import re
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from core_brain.orchestrators._cycle_scan import _normalize_ui_structure_confidence, run_scan_phase
from core_brain.services.ui_mapping_service import (
    UIMappingService,
    _normalize_structure_confidence,
)


def test_orchestrator_confidence_normalizer_is_canonical() -> None:
    """Orchestrator must reuse service canonical confidence normalizer (single SSOT)."""
    assert _normalize_ui_structure_confidence is _normalize_structure_confidence


def test_ui_mapping_keeps_percent_scale_without_double_scaling() -> None:
    """Given confidence=55.8 from sensor, UI should keep ~56% and not 558%."""
    assert _normalize_ui_structure_confidence(55.8) == pytest.approx(55.8, abs=0.1)


def test_ui_mapping_normalizes_ratio_scale_to_percent() -> None:
    """Given confidence in ratio scale, UI normalizes it to percentage once."""
    assert _normalize_ui_structure_confidence(0.558) == pytest.approx(55.8, abs=0.1)


@pytest.mark.parametrize(
    "invalid_value, expected",
    [
        (None, 0.0),
        (float("nan"), 0.0),
        (-12.0, 0.0),
        (447.0, 100.0),
        (558.0, 100.0),
    ],
)
def test_ui_mapping_confidence_is_always_bounded(invalid_value: float, expected: float) -> None:
    """UI confidence display must always remain inside 0-100 range."""
    value = _normalize_ui_structure_confidence(invalid_value)
    assert math.isfinite(value)
    assert value == pytest.approx(expected, abs=0.1)


def test_ui_service_clamps_overflow_confidence_for_persisted_state_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    """Service must clamp overflow confidence before persisting and logging."""
    service = UIMappingService()

    with caplog.at_level("INFO"):
        service.add_structure_signal(
            asset="EURUSD",
            structure_data={
                "hh_indices": [1, 2],
                "hl_indices": [3],
                "lh_indices": [],
                "ll_indices": [],
                "structure_type": "UPTREND",
                "is_valid": True,
                "validation_level": "STRONG",
                "confidence": 664.0,
            },
        )

    signal = service.trader_page_state.analysis_usr_signals["EURUSD_structure"]
    assert signal["confidence"] == pytest.approx(100.0, abs=0.1)
    assert "Confidence: 100.0%" in caplog.text


def test_ui_service_normalizes_legacy_ratio_confidence() -> None:
    """Legacy ratio-scale confidence must be converted to percentage once."""
    service = UIMappingService()
    service.add_structure_signal(
        asset="GBPUSD",
        structure_data={
            "hh_indices": [1],
            "hl_indices": [2],
            "lh_indices": [],
            "ll_indices": [],
            "structure_type": "UPTREND",
            "is_valid": True,
            "validation_level": "PARTIAL",
            "confidence": 0.638,
        },
    )

    signal = service.trader_page_state.analysis_usr_signals["GBPUSD_structure"]
    assert signal["confidence"] == pytest.approx(63.8, abs=0.1)


@pytest.mark.parametrize("invalid_confidence", [None, float("nan")])
def test_ui_service_invalid_confidence_falls_back_to_zero(invalid_confidence: float) -> None:
    """Service must persist 0.0 when confidence is None or NaN."""
    service = UIMappingService()
    service.add_structure_signal(
        asset="USDJPY",
        structure_data={
            "hh_indices": [1],
            "hl_indices": [2],
            "lh_indices": [],
            "ll_indices": [],
            "structure_type": "RANGE",
            "is_valid": False,
            "validation_level": "INSUFFICIENT",
            "confidence": invalid_confidence,
        },
    )

    signal = service.trader_page_state.analysis_usr_signals["USDJPY_structure"]
    assert signal["confidence"] == pytest.approx(0.0, abs=0.1)


@pytest.mark.asyncio
async def test_orchestrator_to_service_confidence_consistency_runtime(caplog: pytest.LogCaptureFixture) -> None:
    """Orchestrator and service must expose the same bounded confidence at runtime."""
    df = pd.DataFrame(
        [
            {"open": 1.0, "high": 1.1, "low": 0.9, "close": 1.05},
            {"open": 1.05, "high": 1.12, "low": 1.0, "close": 1.1},
        ]
    )

    storage = MagicMock()
    storage.update_module_heartbeat.return_value = None

    async def _request_scan(_assets):
        return {
            "EURUSD|M5": {
                "symbol": "EURUSD",
                "timeframe": "M5",
                "regime": "TREND",
                "provider_source": "test",
                "df": df,
            }
        }

    ui_service = UIMappingService()
    captured_payload: dict = {}
    original_add = ui_service.add_structure_signal

    def _spy_add_structure_signal(asset: str, structure_data: dict) -> None:
        captured_payload["asset"] = asset
        captured_payload["confidence"] = structure_data.get("confidence")
        original_add(asset, structure_data)

    ui_service.add_structure_signal = _spy_add_structure_signal

    orch = SimpleNamespace(
        thought_callback=None,
        _get_scan_schedule=lambda: {"EURUSD|M5": 1.0},
        _should_scan_now=lambda _schedule: [("EURUSD", "M5")],
        _request_scan=_request_scan,
        scanner=SimpleNamespace(last_results={}),
        stats=SimpleNamespace(scans_total=0),
        anomaly_sentinel=SimpleNamespace(push_ticks=MagicMock()),
        _update_regime_from_scan=MagicMock(),
        storage=storage,
        _persist_scan_telemetry=MagicMock(),
        market_structure_analyzer=SimpleNamespace(
            detect_market_structure=lambda _symbol, _df: {
                "hh_indices": [1, 2],
                "hl_indices": [1],
                "lh_indices": [],
                "ll_indices": [],
                "hh_count": 2,
                "hl_count": 1,
                "lh_count": 0,
                "ll_count": 0,
                "type": "UPTREND",
                "is_valid": True,
                "validation_level": "STRONG",
                "confidence": 664.0,
            }
        ),
        ui_mapping_service=ui_service,
        _consecutive_empty_structure_cycles=0,
        _max_consecutive_empty_cycles=3,
    )

    with caplog.at_level("INFO"):
        bundle = await run_scan_phase(orch)

    assert bundle is not None
    assert captured_payload["asset"] == "EURUSD"
    assert captured_payload["confidence"] == pytest.approx(100.0, abs=0.1)

    signal = ui_service.trader_page_state.analysis_usr_signals["EURUSD_structure"]
    persisted_confidence = signal["confidence"]
    assert persisted_confidence == pytest.approx(100.0, abs=0.1)

    orchestrator_match = re.search(r"\[Conf:\s*([0-9]+(?:\.[0-9]+)?)%\]", caplog.text)
    service_match = re.search(r"Confidence:\s*([0-9]+(?:\.[0-9]+)?)%", caplog.text)

    assert orchestrator_match is not None
    assert service_match is not None

    assert "[Conf: 100.0%]" in caplog.text
    assert "Confidence: 100.0%" in caplog.text

    orchestrator_conf = float(orchestrator_match.group(1))
    service_conf = float(service_match.group(1))

    assert orchestrator_conf == pytest.approx(persisted_confidence, abs=0.1)
    assert service_conf == pytest.approx(persisted_confidence, abs=0.1)
