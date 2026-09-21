from desktop_metrics.constants import DISK_HEALTH_PREFIX, DISK_IO_PREFIX, DISK_USAGE_PREFIX
from desktop_metrics.metric_layout import expand_metric_ids, metric_display_label


def test_dynamic_disk_metrics_expand_in_selected_order() -> None:
    usage_c = f"{DISK_USAGE_PREFIX}C:\\"
    usage_d = f"{DISK_USAGE_PREFIX}D:\\"
    io_0 = f"{DISK_IO_PREFIX}PhysicalDrive0"
    snapshot = {
        usage_d: {"label": "D: storage", "sort_key": "D:"},
        usage_c: {"label": "C: storage", "sort_key": "C:"},
        io_0: {"label": "Disk 0 (C:) read / write", "sort_key": "00000000"},
    }
    expanded = expand_metric_ids(
        ["cpu_usage", "disk_usage_all", "disk_io_all", "memory"],
        snapshot,
    )
    assert expanded == ["cpu_usage", usage_c, usage_d, io_0, "memory"]
    assert metric_display_label(io_0, snapshot) == "Disk 0 (C:) read / write"


def test_dynamic_parent_remains_until_children_exist() -> None:
    assert expand_metric_ids(["disk_usage_all"], {}) == ["disk_usage_all"]


def test_dynamic_disk_health_expands() -> None:
    health = f"{DISK_HEALTH_PREFIX}0"
    snapshot = {health: {"label": "Disk 0 health", "sort_key": "00000000"}}
    assert expand_metric_ids(["disk_health"], snapshot) == [health]
    assert metric_display_label(health, snapshot) == "Disk 0 health"
