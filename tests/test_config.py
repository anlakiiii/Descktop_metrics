import json
from pathlib import Path

from desktop_metrics.config import AppConfig, ConfigStore
from desktop_metrics.constants import CONFIG_VERSION, DEFAULT_METRICS


def test_config_normalization() -> None:
    config = AppConfig(
        selected_metrics=["invalid"],
        refresh_ms=1400,
        opacity=3.0,
        scale=0.1,
        geometry=[1, 2, 10, 20],
        rate_unit="wrong",
        network_interface="",
    ).normalized()
    assert config.selected_metrics == list(DEFAULT_METRICS)
    assert config.refresh_ms == 1000
    assert config.opacity == 1.0
    assert config.scale == 0.75
    assert config.geometry == [1, 2, 320, 200]
    assert config.rate_unit == "bits"
    assert config.network_interface == "auto"


def test_config_round_trip(tmp_path: Path) -> None:
    store = ConfigStore(tmp_path)
    original = AppConfig(
        selected_metrics=["cpu_usage", "memory"],
        geometry=[10, 20, 500, 400],
        separate_widgets=True,
        separate_geometries={"cpu_usage": [-1200, 20, 360, 240]},
        locked=True,
        always_on_top=True,
        click_through=True,
        rate_unit="bytes",
        network_interface="Ethernet",
    )
    store.save(original)
    loaded = store.load()
    assert loaded.selected_metrics == ["cpu_usage", "memory"]
    assert loaded.geometry == [10, 20, 500, 400]
    assert loaded.separate_widgets is True
    assert loaded.separate_geometries["cpu_usage"] == [-1200, 20, 360, 240]
    assert loaded.locked is True
    assert loaded.always_on_top is True
    assert loaded.click_through is True
    assert loaded.rate_unit == "bytes"
    assert loaded.network_interface == "Ethernet"
    parsed = json.loads((tmp_path / "config.json").read_text(encoding="utf-8"))
    assert parsed["version"] == CONFIG_VERSION


def test_config_removes_duplicate_metrics() -> None:
    config = AppConfig(selected_metrics=["cpu_usage", "memory", "cpu_usage"]).normalized()
    assert config.selected_metrics == ["cpu_usage", "memory"]


def test_portable_config_directory_uses_executable_sidecar(monkeypatch, tmp_path: Path) -> None:
    from desktop_metrics.config import default_config_directory

    monkeypatch.setenv("DESKTOP_METRICS_PORTABLE", "1")
    monkeypatch.setenv("DESKTOP_METRICS_PORTABLE_ROOT", str(tmp_path))
    assert default_config_directory() == tmp_path.resolve() / "DesktopMetricsData"


def test_click_through_requires_topmost_and_locked() -> None:
    assert AppConfig(always_on_top=True, locked=False, click_through=True).normalized().click_through is False
    assert AppConfig(always_on_top=False, locked=True, click_through=True).normalized().click_through is False
    enabled = AppConfig(always_on_top=True, locked=True, click_through=True).normalized()
    assert enabled.always_on_top is True
    assert enabled.locked is True
    assert enabled.click_through is True
