import math

import pytest

from core_brain.orchestrators._cycle_scan import _normalize_ui_structure_confidence


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
