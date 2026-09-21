from __future__ import annotations

from collections.abc import Iterable

from .constants import METRIC_SPECS


PRESETS: dict[str, tuple[str, ...]] = {
    "Custom": (),
    "Minimal": ("cpu_usage", "memory", "network_speed", "uptime"),
    "Gaming": (
        "cpu_usage",
        "cpu_frequency",
        "memory",
        "gpu_usage",
        "gpu_memory",
        "gpu_temperature",
        "gpu_clock",
        "gpu_fan",
        "top_gpu_process",
        "network_speed",
        "uptime",
    ),
    "Workstation": (
        "cpu_usage",
        "cpu_frequency",
        "memory",
        "gpu_usage",
        "gpu_memory",
        "disk_usage_all",
        "disk_io_all",
        "disk_health",
        "network_speed",
        "top_cpu_process",
        "top_memory_process",
        "uptime",
    ),
    "Everything": tuple(spec.metric_id for spec in METRIC_SPECS),
}


def matching_preset(selected_metrics: Iterable[str]) -> str:
    """Return the named preset that exactly matches a selection, or Custom."""
    selected = set(selected_metrics)
    for name, metrics in PRESETS.items():
        if name != "Custom" and selected == set(metrics):
            return name
    return "Custom"
