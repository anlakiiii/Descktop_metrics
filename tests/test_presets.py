from desktop_metrics.constants import VALID_METRIC_IDS
from desktop_metrics.presets import PRESETS, matching_preset


def test_named_presets_only_reference_valid_metrics() -> None:
    for name, metrics in PRESETS.items():
        if name == "Custom":
            continue
        assert metrics
        assert set(metrics) <= VALID_METRIC_IDS


def test_matching_preset_detects_named_and_custom_selections() -> None:
    assert matching_preset(PRESETS["Minimal"]) == "Minimal"
    assert matching_preset(["cpu_usage", "clock"]) == "Custom"
