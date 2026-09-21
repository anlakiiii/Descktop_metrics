from __future__ import annotations

from dataclasses import dataclass

APP_NAME = "DesktopMetrics"
APP_DISPLAY_NAME = "Desktop Metrics"
APP_VERSION = "1.8.1"
ORGANIZATION_NAME = "DesktopMetrics"
CONFIG_VERSION = 3


@dataclass(frozen=True, slots=True)
class MetricSpec:
    metric_id: str
    label: str
    category: str
    description: str


CATEGORY_ORDER = (
    "System",
    "CPU",
    "Memory",
    "GPU",
    "Storage",
    "Network",
    "Processes",
    "Power",
    "Privacy",
)

DISK_USAGE_PREFIX = "disk_usage|"
DISK_IO_PREFIX = "disk_io|"
DISK_HEALTH_PREFIX = "disk_health|"

METRIC_SPECS = (
    MetricSpec("clock", "Date and time", "System", "Current local date and time."),
    MetricSpec("uptime", "PC uptime", "System", "Time since the last system boot."),
    MetricSpec("cpu_usage", "CPU usage", "CPU", "Total CPU load with a short history graph."),
    MetricSpec(
        "cpu_frequency",
        "CPU frequency",
        "CPU",
        "Live Windows performance clock, including CPU boost when Windows exposes it.",
    ),
    MetricSpec(
        "cpu_temperature",
        "CPU temperature",
        "CPU",
        "Temperature when the operating system exposes a supported sensor.",
    ),
    MetricSpec(
        "cpu_fan",
        "CPU fan speed",
        "CPU",
        "CPU fan RPM when a compatible hardware sensor is exposed; Windows can use LibreHardwareMonitor/OpenHardwareMonitor WMI.",
    ),
    MetricSpec("memory", "Memory usage", "Memory", "RAM used, available, and total."),
    MetricSpec("swap", "Swap / page file", "Memory", "Swap or Windows page file usage."),
    MetricSpec("gpu_usage", "GPU usage", "GPU", "NVIDIA GPU utilization through NVML."),
    MetricSpec("gpu_memory", "GPU memory", "GPU", "VRAM usage for detected NVIDIA GPUs."),
    MetricSpec("gpu_temperature", "GPU temperature", "GPU", "Highest detected NVIDIA GPU temperature."),
    MetricSpec("gpu_power", "GPU power", "GPU", "Combined NVIDIA GPU power draw when available."),
    MetricSpec("gpu_clock", "GPU graphics clock", "GPU", "Current NVIDIA graphics clock and session peak."),
    MetricSpec("gpu_fan", "GPU fan speed", "GPU", "NVIDIA fan duty percentage when the board exposes it through NVML."),
    MetricSpec(
        "top_gpu_process",
        "Top GPU app",
        "GPU",
        "Highest NVIDIA GPU engine use when process utilization is exposed; falls back to highest VRAM use.",
    ),
    MetricSpec("disk_usage", "System disk space", "Storage", "Used and free space on the Windows system drive."),
    MetricSpec(
        "disk_usage_all",
        "All disk space",
        "Storage",
        "Creates one used/free-space card for every accessible mounted disk or volume.",
    ),
    MetricSpec("disk_io", "Total disk read / write", "Storage", "Combined transfer speed across all physical disks."),
    MetricSpec(
        "disk_io_all",
        "Per-disk read / write",
        "Storage",
        "Creates one read/write-speed card for every physical disk reported by the operating system.",
    ),
    MetricSpec(
        "disk_health",
        "Physical disk health",
        "Storage",
        "Creates one Windows health-status card for every physical disk. This is a high-level status, not a full SMART attribute viewer.",
    ),
    MetricSpec(
        "network_speed",
        "Network speed",
        "Network",
        "Current receive and send rate for an automatically selected or chosen network adapter.",
    ),
    MetricSpec(
        "network_total",
        "Network totals",
        "Network",
        "Data received and sent through the selected adapter since boot.",
    ),
    MetricSpec(
        "wifi_signal",
        "Wi-Fi signal strength",
        "Network",
        "Connected Windows Wi-Fi signal quality, estimated dBm, SSID, and link rates.",
    ),
    MetricSpec("process_count", "Process count", "Processes", "Number of currently running processes."),
    MetricSpec(
        "top_cpu_process",
        "Top CPU app",
        "Processes",
        "Highest combined CPU use grouped by executable; System Idle Process is excluded.",
    ),
    MetricSpec(
        "top_memory_process",
        "Top memory app",
        "Processes",
        "Highest combined working set grouped by executable, including multi-process browsers.",
    ),
    MetricSpec("battery", "Battery", "Power", "Charge percentage and plugged-in state."),
    MetricSpec(
        "battery_time",
        "Battery time remaining",
        "Power",
        "Estimated remaining runtime reported by the operating system when running on battery.",
    ),
    MetricSpec(
        "clipboard_history",
        "Clipboard history (session)",
        "Privacy",
        "Private in-memory text history captured only while Desktop Metrics runs; double-click the card to open it.",
    ),
)

METRIC_SPEC_BY_ID = {spec.metric_id: spec for spec in METRIC_SPECS}
VALID_METRIC_IDS = frozenset(METRIC_SPEC_BY_ID)

DEFAULT_METRICS = (
    "cpu_usage",
    "memory",
    "gpu_usage",
    "gpu_memory",
    "disk_usage_all",
    "network_speed",
    "uptime",
)

REFRESH_INTERVALS_MS = (500, 1000, 2000, 5000)
RATE_UNIT_MODES = ("bits", "bytes")
