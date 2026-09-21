import sys
import warnings
from types import SimpleNamespace

from desktop_metrics import collector as collector_module
from desktop_metrics.collector import NvidiaProvider, SystemCollector
from desktop_metrics.constants import DISK_IO_PREFIX, DISK_USAGE_PREFIX


def test_basic_snapshot() -> None:
    collector = SystemCollector()
    try:
        first = collector.collect(["cpu_usage", "memory", "disk_usage", "network_speed", "uptime"])
        second = collector.collect(["cpu_usage", "memory", "disk_usage", "network_speed", "uptime"])
    finally:
        collector.shutdown()
    assert set(second) == {"cpu_usage", "memory", "disk_usage", "network_speed", "uptime"}
    assert second["memory"]["available"] is True
    assert second["disk_usage"]["available"] is True
    assert "value" in first["cpu_usage"]


def test_process_snapshot_excludes_idle_and_groups_browser_processes(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, pid: int, name: str, cpu_total: float, memory: int, created: float = 1.0) -> None:
            self.pid = pid
            self.info = {
                "pid": pid,
                "name": name,
                "cpu_times": SimpleNamespace(user=cpu_total, system=0.0),
                "memory_info": SimpleNamespace(rss=memory, private=memory),
                "create_time": created,
            }

    processes = [
        FakeProcess(0, "System Idle Process", 900.0, 0),
        FakeProcess(10, "python.exe", 3.4, 200),
        FakeProcess(20, "chrome.exe", 1.1, 800),
        FakeProcess(21, "chrome.exe", 1.1, 700),
        FakeProcess(30, "explorer.exe", 1.05, 1000),
    ]

    instance = SystemCollector()
    try:
        instance._last_process_sample_time = 100.0
        instance._process_cpu_state = {
            0: (1.0, 1.0),
            10: (1.0, 1.0),
            20: (1.0, 1.0),
            21: (1.0, 1.0),
            30: (1.0, 1.0),
        }
        monkeypatch.setattr(collector_module.time, "monotonic", lambda: 101.0)
        monkeypatch.setattr(collector_module.psutil, "cpu_count", lambda logical=True: 8)
        monkeypatch.setattr(collector_module.psutil, "process_iter", lambda _attrs: processes)

        top_cpu, top_memory, count = instance._process_snapshot()
    finally:
        instance.shutdown()

    assert count == 4
    assert top_cpu is not None
    assert top_cpu["name"] == "Python"
    assert top_memory is not None
    assert top_memory["name"] == "Google Chrome"
    assert top_memory["count"] == 2
    assert top_memory["memory"] == 1500


def test_all_disk_space_expands_to_a_card(monkeypatch) -> None:
    partition = SimpleNamespace(device="/dev/test", mountpoint="/test", fstype="TESTFS")
    instance = SystemCollector()
    try:
        monkeypatch.setattr(instance, "_update_rates", lambda: None)
        monkeypatch.setattr(instance, "_mounted_partitions", lambda: [partition])
        monkeypatch.setattr(
            collector_module.psutil,
            "disk_usage",
            lambda _path: SimpleNamespace(percent=25.0, free=750, total=1000),
        )
        snapshot = instance.collect(["disk_usage_all"])
    finally:
        instance.shutdown()

    dynamic_ids = [metric_id for metric_id in snapshot if metric_id.startswith(DISK_USAGE_PREFIX)]
    assert len(dynamic_ids) == 1
    reading = snapshot[dynamic_ids[0]]
    assert reading["available"] is True
    assert "free of" in reading["detail"]


def test_per_disk_io_includes_read_and_write(monkeypatch) -> None:
    instance = SystemCollector()
    try:
        monkeypatch.setattr(instance, "_update_rates", lambda: None)
        monkeypatch.setattr(instance, "_mounted_partitions", lambda: [])
        instance._disk_rates_per = {"testdisk0": (2048.0, 4096.0)}
        snapshot = instance.collect(["disk_io_all"])
    finally:
        instance.shutdown()

    dynamic_ids = [metric_id for metric_id in snapshot if metric_id.startswith(DISK_IO_PREFIX)]
    assert dynamic_ids == [f"{DISK_IO_PREFIX}testdisk0"]
    reading = snapshot[dynamic_ids[0]]
    assert reading["value"] == "Read 2.0 KB/s"
    assert "Write 4.0 KB/s" in reading["detail"]


def test_process_ranking_groups_apps_and_excludes_idle(monkeypatch) -> None:
    from types import SimpleNamespace

    import desktop_metrics.collector as collector_module

    class FakeProcess:
        def __init__(self, pid: int, name: str, cpu_total: float, memory: int) -> None:
            self.pid = pid
            self.info = {
                "pid": pid,
                "name": name,
                "cpu_times": SimpleNamespace(user=cpu_total, system=0.0),
                "memory_info": SimpleNamespace(rss=memory),
                "create_time": float(pid + 100),
            }

    samples = [
        [
            FakeProcess(0, "System Idle Process", 50.0, 10_000_000_000),
            FakeProcess(10, "chrome.exe", 1.0, 100),
            FakeProcess(11, "chrome.exe", 2.0, 200),
            FakeProcess(12, "explorer.exe", 0.5, 250),
            FakeProcess(13, "python.exe", 1.0, 150),
        ],
        [
            FakeProcess(0, "System Idle Process", 54.0, 10_000_000_000),
            FakeProcess(10, "chrome.exe", 1.4, 100),
            FakeProcess(11, "chrome.exe", 2.4, 200),
            FakeProcess(12, "explorer.exe", 0.6, 250),
            FakeProcess(13, "python.exe", 2.2, 150),
        ],
    ]
    iterator_call = {"index": 0}

    def fake_process_iter(_attributes):
        index = iterator_call["index"]
        iterator_call["index"] += 1
        return iter(samples[index])

    monotonic_values = iter((100.0, 101.0))
    monkeypatch.setattr(collector_module.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(collector_module.psutil, "process_iter", fake_process_iter)
    monkeypatch.setattr(collector_module.psutil, "cpu_count", lambda logical=True: 4)

    collector = SystemCollector()
    try:
        collector._process_snapshot()
        top_cpu, top_memory, _process_count = collector._process_snapshot()
    finally:
        collector.shutdown()

    assert top_cpu is not None
    assert top_cpu["name"] == "Python"
    assert round(float(top_cpu["cpu"]), 1) == 30.0
    assert top_memory is not None
    assert top_memory["name"] == "Google Chrome"
    assert int(top_memory["memory"]) == 300
    assert int(top_memory["count"]) == 2


def test_new_gpu_cards(monkeypatch) -> None:
    class FakeGpu:
        def collect(self, *, include_processes=False):
            assert include_processes is True
            return {
                "available": True,
                "name": "Example GPU",
                "graphics_clock_mhz": 2800.0,
                "graphics_clock_peak_mhz": 2850.0,
                "memory_clock_mhz": 10500.0,
                "fan_percent": 42.0,
                "fan_count": 2,
                "top_process": {
                    "name": "Python",
                    "source": "engine",
                    "utilization": 61.5,
                    "count": 1,
                    "pid": 123,
                },
            }

        def shutdown(self):
            pass

    instance = SystemCollector()
    instance._gpu.shutdown()
    instance._gpu = FakeGpu()
    try:
        monkeypatch.setattr(instance, "_update_rates", lambda: None)
        snapshot = instance.collect(["gpu_clock", "gpu_fan", "top_gpu_process"])
    finally:
        instance.shutdown()

    assert snapshot["gpu_clock"]["value"] == "2.80 GHz"
    assert snapshot["gpu_fan"]["value"] == "42%"
    assert snapshot["top_gpu_process"]["value"] == "Python"
    assert "61.5%" in snapshot["top_gpu_process"]["detail"]


def test_cpu_fan_disk_health_wifi_and_battery_time(monkeypatch) -> None:
    class FakeFans:
        def cpu_fan(self):
            return {
                "available": True,
                "rpm": 1450.0,
                "name": "CPU Fan",
                "source": "test sensor",
                "note": "",
            }

    class FakeDiskHealth:
        def collect(self):
            return (
                [
                    {
                        "device_id": "0",
                        "name": "Example SSD",
                        "health": "Healthy",
                        "operational": "OK",
                        "media_type": "SSD",
                        "size": 1_000_000,
                    }
                ],
                "",
            )

    instance = SystemCollector()
    instance._fans = FakeFans()
    instance._disk_health = FakeDiskHealth()
    try:
        monkeypatch.setattr(instance, "_update_rates", lambda: None)
        monkeypatch.setattr(
            collector_module,
            "query_wifi_connection",
            lambda: {
                "available": True,
                "quality": 80.0,
                "dbm": -60.0,
                "ssid": "Example Wi-Fi",
                "rx_mbps": 866.7,
                "tx_mbps": 866.7,
                "interface": "Wi-Fi Adapter",
            },
        )
        monkeypatch.setattr(
            collector_module.psutil,
            "sensors_battery",
            lambda: SimpleNamespace(
                percent=75.0,
                power_plugged=False,
                secsleft=7200,
            ),
        )
        snapshot = instance.collect(["cpu_fan", "disk_health", "wifi_signal", "battery_time"])
    finally:
        instance.shutdown()

    assert snapshot["cpu_fan"]["value"] == "1,450 RPM"
    health_ids = [key for key in snapshot if key.startswith("disk_health|")]
    assert health_ids == ["disk_health|0"]
    assert snapshot[health_ids[0]]["value"] == "Healthy"
    assert snapshot["wifi_signal"]["value"] == "80%"
    assert snapshot["battery_time"]["value"] == "2h 0m"


def test_unavailable_cpu_fan_uses_compact_card_text_and_full_tooltip(monkeypatch) -> None:
    class FakeFans:
        def cpu_fan(self):
            return {
                "available": False,
                "error": (
                    "No CPU fan RPM was exposed. On Windows, run "
                    "LibreHardwareMonitor with its WMI sensors enabled."
                ),
            }

    instance = SystemCollector()
    instance._fans = FakeFans()
    try:
        monkeypatch.setattr(instance, "_update_rates", lambda: None)
        snapshot = instance.collect(["cpu_fan"])
    finally:
        instance.shutdown()

    reading = snapshot["cpu_fan"]
    assert reading["value"] == "Unavailable"
    assert reading["detail"] == "Fan sensor not detected"
    assert "LibreHardwareMonitor" in reading["tooltip"]


def test_nvidia_provider_suppresses_obsolete_pynvml_future_warning(monkeypatch, tmp_path) -> None:
    fake_module = tmp_path / "pynvml.py"
    fake_module.write_text(
        """
import warnings
warnings.warn(
    'The pynvml package is deprecated. Please install nvidia-ml-py instead.',
    FutureWarning,
    stacklevel=2,
)
def nvmlInit(): pass
def nvmlDeviceGetCount(): return 0
def nvmlShutdown(): pass
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "pynvml", raising=False)

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        provider = NvidiaProvider()
        provider.shutdown()

    assert not [item for item in captured if issubclass(item.category, FutureWarning)]
