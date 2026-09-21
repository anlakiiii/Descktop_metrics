from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .constants import (
    CONFIG_VERSION,
    DEFAULT_METRICS,
    RATE_UNIT_MODES,
    REFRESH_INTERVALS_MS,
    VALID_METRIC_IDS,
)


def is_portable_mode() -> bool:
    """Return True when the dedicated portable executable/entry point is used."""
    value = os.environ.get("DESKTOP_METRICS_PORTABLE", "").strip().lower()
    return value in {"1", "true", "yes", "on"}


def standard_config_directory() -> Path:
    """Per-user configuration directory used by source and installed builds."""
    if os.name == "nt":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "DesktopMetrics"


def portable_application_directory() -> Path:
    """Directory containing the portable EXE, or the source project while testing."""
    override = os.environ.get("DESKTOP_METRICS_PORTABLE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def default_config_directory() -> Path:
    if is_portable_mode():
        return portable_application_directory() / "DesktopMetricsData"
    return standard_config_directory()


def _normalize_geometry(value: Any, default: list[int]) -> list[int]:
    geometry = list(value) if isinstance(value, (list, tuple)) else []
    if len(geometry) != 4:
        geometry = list(default)
    try:
        x, y, width, height = (int(item) for item in geometry)
    except (TypeError, ValueError):
        x, y, width, height = default
    width = max(320, min(1800, width))
    height = max(200, min(1400, height))
    return [x, y, width, height]


@dataclass(slots=True)
class AppConfig:
    version: int = CONFIG_VERSION
    selected_metrics: list[str] = field(default_factory=lambda: list(DEFAULT_METRICS))
    refresh_ms: int = 1000
    opacity: float = 0.94
    scale: float = 1.0
    locked: bool = False
    always_on_top: bool = False
    click_through: bool = False
    start_with_windows: bool = False
    geometry: list[int] = field(default_factory=lambda: [80, 80, 620, 480])
    separate_widgets: bool = False
    separate_geometries: dict[str, list[int]] = field(default_factory=dict)
    rate_unit: str = "bits"
    network_interface: str = "auto"

    def normalized(self) -> "AppConfig":
        selected: list[str] = []
        seen: set[str] = set()
        for metric_id in self.selected_metrics:
            if metric_id in VALID_METRIC_IDS and metric_id not in seen:
                selected.append(metric_id)
                seen.add(metric_id)
        if not selected:
            selected = list(DEFAULT_METRICS)

        refresh_ms = min(REFRESH_INTERVALS_MS, key=lambda value: abs(value - int(self.refresh_ms)))
        opacity = max(0.45, min(1.0, float(self.opacity)))
        scale = max(0.75, min(1.50, float(self.scale)))
        geometry = _normalize_geometry(self.geometry, [80, 80, 620, 480])

        separate_geometries: dict[str, list[int]] = {}
        if isinstance(self.separate_geometries, dict):
            for raw_key, raw_geometry in list(self.separate_geometries.items())[:128]:
                key = str(raw_key).strip()
                if not key:
                    continue
                separate_geometries[key] = _normalize_geometry(raw_geometry, [80, 80, 360, 240])

        rate_unit = str(self.rate_unit).strip().lower()
        if rate_unit not in RATE_UNIT_MODES:
            rate_unit = "bits"

        network_interface = str(self.network_interface or "auto").strip()
        if not network_interface:
            network_interface = "auto"
        network_interface = network_interface[:256]

        return AppConfig(
            version=CONFIG_VERSION,
            selected_metrics=selected,
            refresh_ms=refresh_ms,
            opacity=opacity,
            scale=scale,
            locked=bool(self.locked),
            always_on_top=bool(self.always_on_top),
            click_through=bool(self.click_through and self.locked and self.always_on_top),
            start_with_windows=bool(self.start_with_windows),
            geometry=geometry,
            separate_widgets=bool(self.separate_widgets),
            separate_geometries=separate_geometries,
            rate_unit=rate_unit,
            network_interface=network_interface,
        )

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "AppConfig":
        known = {field_name for field_name in cls.__dataclass_fields__}
        filtered = {key: value for key, value in data.items() if key in known}
        try:
            return cls(**filtered).normalized()
        except (TypeError, ValueError):
            return cls().normalized()


class ConfigStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_config_directory()
        self.path = self.directory / "config.json"

    def _load_path(self, path: Path) -> AppConfig | None:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return AppConfig.from_mapping(raw)
        except (OSError, json.JSONDecodeError):
            pass
        return None

    def load(self) -> AppConfig:
        loaded = self._load_path(self.path)
        if loaded is not None:
            return loaded

        # A first-run portable build can inherit the user's existing installed/source
        # configuration once. Future changes stay beside the portable executable.
        if is_portable_mode() and self.directory == default_config_directory():
            legacy_path = standard_config_directory() / "config.json"
            migrated = self._load_path(legacy_path)
            if migrated is not None:
                try:
                    self.save(migrated)
                except OSError:
                    # Migration remains usable for this session; portable mode is
                    # intended to be placed in a writable folder for persistence.
                    pass
                return migrated

        return AppConfig().normalized()

    def save(self, config: AppConfig) -> None:
        normalized = config.normalized()
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(asdict(normalized), indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temporary.replace(self.path)
