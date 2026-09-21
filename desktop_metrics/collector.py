from __future__ import annotations

import datetime as dt
import os
import re
import time
import warnings
from collections.abc import Iterable
from typing import Any

import psutil

from .constants import DISK_HEALTH_PREFIX, DISK_IO_PREFIX, DISK_USAGE_PREFIX
from .formatting import (
    compact_process_name,
    format_bytes,
    format_duration,
    format_frequency,
    format_network_rate,
    format_rate,
)
from .hardware_sensors import HardwareFanProvider
from .windows_cpu import WindowsCpuFrequencyProvider
from .windows_disks import build_disk_mount_map
from .windows_storage import DiskHealthProvider, disk_health_score
from .windows_wifi import query_wifi_connection

Reading = dict[str, Any]
Snapshot = dict[str, Reading]


def make_reading(
    value: str,
    detail: str = "",
    *,
    progress: float | None = None,
    history: float | None = None,
    available: bool = True,
    label: str | None = None,
    description: str | None = None,
    sort_key: str | None = None,
    tooltip: str | None = None,
) -> Reading:
    reading: Reading = {
        "value": value,
        "detail": detail,
        "progress": progress,
        "history": history,
        "available": available,
    }
    if label:
        reading["label"] = label
    if description:
        reading["description"] = description
    if sort_key:
        reading["sort_key"] = sort_key
    if tooltip:
        reading["tooltip"] = tooltip
    return reading


def unavailable(
    detail: str = "Not available on this system",
    *,
    label: str | None = None,
    description: str | None = None,
    tooltip: str | None = None,
) -> Reading:
    return make_reading(
        "Unavailable",
        detail,
        available=False,
        label=label,
        description=description,
        tooltip=tooltip,
    )


def list_network_interfaces() -> list[str]:
    """Return currently visible network interfaces for the settings window."""
    try:
        counters = psutil.net_io_counters(pernic=True) or {}
    except Exception:
        counters = {}
    try:
        stats = psutil.net_if_stats() or {}
    except Exception:
        stats = {}
    names = set(counters) | set(stats)
    return sorted((str(name) for name in names if str(name).strip()), key=str.casefold)


def _natural_key(text: str) -> tuple[Any, ...]:
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", text))


def _format_estimated_time(seconds: int | float) -> str:
    total_minutes = max(0, int(float(seconds))) // 60
    days, remaining_minutes = divmod(total_minutes, 24 * 60)
    hours, minutes = divmod(remaining_minutes, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


class NvidiaProvider:
    """Optional NVIDIA GPU provider backed by NVML.

    Every NVML call is isolated because support differs by GPU generation,
    laptop firmware, driver, and virtualized environment. Unsupported fields
    therefore become unavailable cards instead of breaking the collector.
    """

    def __init__(self) -> None:
        self._pynvml: Any | None = None
        self._handles: list[Any] = []
        self._process_timestamps: dict[int, int] = {}
        self._clock_peak_mhz = 0.0
        self.error_message = "No NVIDIA GPU detected"
        try:
            # nvidia-ml-py intentionally exposes the historical ``pynvml``
            # import name. Some environments also contain the obsolete
            # ``pynvml`` distribution, which emits a FutureWarning at import
            # time even though the API remains usable. Do not leak that
            # packaging warning into the application's console.
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message=r"The pynvml package is deprecated\..*",
                    category=FutureWarning,
                )
                import pynvml

            pynvml.nvmlInit()
            count = int(pynvml.nvmlDeviceGetCount())
            self._pynvml = pynvml
            self._handles = [pynvml.nvmlDeviceGetHandleByIndex(index) for index in range(count)]
            if not self._handles:
                self.error_message = "NVML found no NVIDIA devices"
        except Exception as exc:
            self._pynvml = None
            self._handles = []
            text = str(exc).strip()
            if text:
                self.error_message = text

    @property
    def available(self) -> bool:
        return bool(self._pynvml and self._handles)

    @staticmethod
    def _process_name(pid: int) -> str:
        try:
            return compact_process_name(psutil.Process(pid).name() or f"PID {pid}", 30)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, OSError):
            return f"PID {pid}"

    @staticmethod
    def _valid_gpu_memory(value: Any) -> int:
        try:
            number = int(value)
        except (TypeError, ValueError, OverflowError):
            return 0
        # NVML_VALUE_NOT_AVAILABLE is commonly an unsigned all-ones sentinel.
        if number < 0 or number >= (1 << 60):
            return 0
        return number

    def _fan_values(self, handle: Any) -> list[float]:
        pynvml = self._pynvml
        if pynvml is None:
            return []
        values: list[float] = []
        get_count = getattr(pynvml, "nvmlDeviceGetNumFans", None)
        get_v2 = getattr(pynvml, "nvmlDeviceGetFanSpeed_v2", None)
        if callable(get_count) and callable(get_v2):
            try:
                count = max(0, int(get_count(handle)))
            except Exception:
                count = 0
            for index in range(count):
                try:
                    values.append(float(get_v2(handle, index)))
                except Exception:
                    continue
        if not values:
            get_default = getattr(pynvml, "nvmlDeviceGetFanSpeed", None)
            if callable(get_default):
                try:
                    values.append(float(get_default(handle)))
                except Exception:
                    pass
        return [min(100.0, max(0.0, value)) for value in values]

    def _top_process_by_utilization(self) -> dict[str, Any] | None:
        pynvml = self._pynvml
        query = getattr(pynvml, "nvmlDeviceGetProcessUtilization", None) if pynvml else None
        if not callable(query):
            return None

        per_pid: dict[int, float] = {}
        had_supported_query = False
        initial_query = False
        for index, handle in enumerate(self._handles):
            timestamp = int(self._process_timestamps.get(index, 0))
            query_started_us = int(time.time() * 1_000_000)
            initial_query = initial_query or timestamp == 0
            try:
                samples = list(query(handle, timestamp) or [])
                had_supported_query = True
            except Exception:
                continue
            newest = timestamp
            for sample in samples:
                try:
                    pid = int(getattr(sample, "pid"))
                except (TypeError, ValueError, AttributeError):
                    continue
                try:
                    sample_time = int(getattr(sample, "timeStamp", 0) or 0)
                    newest = max(newest, sample_time)
                except (TypeError, ValueError):
                    pass
                engines = []
                for field in ("smUtil", "memUtil", "encUtil", "decUtil"):
                    try:
                        value = float(getattr(sample, field, 0.0) or 0.0)
                    except (TypeError, ValueError):
                        value = 0.0
                    if 0.0 <= value <= 100.0:
                        engines.append(value)
                utilization = max(engines, default=0.0)
                if utilization > 0.0:
                    per_pid[pid] = max(per_pid.get(pid, 0.0), utilization)
            # Establish a baseline even when the query returned no samples.
            # Use the query start time so activity that begins while NVML is
            # answering is not accidentally skipped on the next refresh.
            self._process_timestamps[index] = max(newest, query_started_us)

        grouped: dict[str, dict[str, Any]] = {}
        for pid, utilization in per_pid.items():
            name = self._process_name(pid)
            key = name.casefold()
            group = grouped.setdefault(
                key,
                {"name": name, "utilization": 0.0, "pids": set(), "pid": pid},
            )
            group["utilization"] += utilization
            group["pids"].add(pid)

        if grouped:
            result = max(grouped.values(), key=lambda item: float(item["utilization"]))
            result["utilization"] = min(100.0, float(result["utilization"]))
            result["count"] = len(result.pop("pids"))
            result["source"] = "engine"
            return result
        if had_supported_query:
            return {
                "warming_up": initial_query,
                "idle": not initial_query,
                "source": "engine",
            }
        return None

    def _top_process_by_memory(self) -> dict[str, Any] | None:
        pynvml = self._pynvml
        if pynvml is None:
            return None
        query_names = (
            "nvmlDeviceGetGraphicsRunningProcesses",
            "nvmlDeviceGetComputeRunningProcesses",
        )
        pid_memory: dict[int, int] = {}
        supported = False
        for handle in self._handles:
            per_handle: dict[int, int] = {}
            for name in query_names:
                query = getattr(pynvml, name, None)
                if not callable(query):
                    continue
                try:
                    processes = list(query(handle) or [])
                    supported = True
                except Exception:
                    continue
                for process in processes:
                    try:
                        pid = int(getattr(process, "pid"))
                    except (TypeError, ValueError, AttributeError):
                        continue
                    used = self._valid_gpu_memory(getattr(process, "usedGpuMemory", 0))
                    per_handle[pid] = max(per_handle.get(pid, 0), used)
            for pid, used in per_handle.items():
                pid_memory[pid] = pid_memory.get(pid, 0) + used

        grouped: dict[str, dict[str, Any]] = {}
        for pid, used in pid_memory.items():
            name = self._process_name(pid)
            key = name.casefold()
            group = grouped.setdefault(
                key,
                {"name": name, "memory": 0, "count": 0, "pid": pid},
            )
            group["memory"] += max(0, int(used))
            group["count"] += 1
        if grouped:
            result = max(grouped.values(), key=lambda item: int(item["memory"]))
            result["source"] = "memory"
            return result
        if supported:
            return {"idle": True, "source": "memory"}
        return None

    def collect(self, *, include_processes: bool = False) -> dict[str, Any]:
        if not self.available or self._pynvml is None:
            return {"available": False, "error": self.error_message}

        pynvml = self._pynvml
        usages: list[float] = []
        memory_used = 0
        memory_total = 0
        temperatures: list[float] = []
        power_watts: list[float] = []
        graphics_clocks: list[float] = []
        memory_clocks: list[float] = []
        fan_values: list[float] = []
        names: list[str] = []

        for handle in self._handles:
            try:
                raw_name = pynvml.nvmlDeviceGetName(handle)
                names.append(raw_name.decode(errors="replace") if isinstance(raw_name, bytes) else str(raw_name))
            except Exception:
                names.append("NVIDIA GPU")

            try:
                utilization = pynvml.nvmlDeviceGetUtilizationRates(handle)
                usages.append(float(utilization.gpu))
            except Exception:
                pass

            try:
                memory = pynvml.nvmlDeviceGetMemoryInfo(handle)
                memory_used += int(memory.used)
                memory_total += int(memory.total)
            except Exception:
                pass

            try:
                temperatures.append(float(pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)))
            except Exception:
                pass

            try:
                power_watts.append(float(pynvml.nvmlDeviceGetPowerUsage(handle)) / 1000.0)
            except Exception:
                pass

            try:
                graphics_clocks.append(float(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_GRAPHICS)))
            except Exception:
                pass
            try:
                memory_clocks.append(float(pynvml.nvmlDeviceGetClockInfo(handle, pynvml.NVML_CLOCK_MEM)))
            except Exception:
                pass
            fan_values.extend(self._fan_values(handle))

        graphics_clock = max(graphics_clocks) if graphics_clocks else None
        if graphics_clock is not None:
            self._clock_peak_mhz = max(self._clock_peak_mhz, float(graphics_clock))

        top_process = None
        if include_processes:
            top_process = self._top_process_by_utilization()
            if top_process is None or top_process.get("warming_up"):
                memory_process = self._top_process_by_memory()
                if memory_process and not memory_process.get("warming_up"):
                    top_process = memory_process

        return {
            "available": True,
            "count": len(self._handles),
            "name": names[0] if len(names) == 1 else f"{len(names)} NVIDIA GPUs",
            "usage": max(usages) if usages else None,
            "memory_used": memory_used or None,
            "memory_total": memory_total or None,
            "temperature": max(temperatures) if temperatures else None,
            "power_watts": sum(power_watts) if power_watts else None,
            "graphics_clock_mhz": graphics_clock,
            "graphics_clock_peak_mhz": self._clock_peak_mhz or None,
            "memory_clock_mhz": max(memory_clocks) if memory_clocks else None,
            "fan_percent": max(fan_values) if fan_values else None,
            "fan_count": len(fan_values),
            "top_process": top_process,
        }

    def shutdown(self) -> None:
        if self._pynvml is not None:
            try:
                self._pynvml.nvmlShutdown()
            except Exception:
                pass


class SystemCollector:
    def __init__(self, *, rate_unit: str = "bits", network_interface: str = "auto") -> None:
        self._last_rate_sample_time: float | None = None
        self._last_net_total: Any | None = None
        self._last_net_per: dict[str, Any] = {}
        self._last_disk_total: Any | None = None
        self._last_disk_per: dict[str, Any] = {}
        self._current_net_total: Any | None = None
        self._current_net_per: dict[str, Any] = {}
        self._net_total_rates = (0.0, 0.0)
        self._net_rates_per: dict[str, tuple[float, float]] = {}
        self._disk_total_rates = (0.0, 0.0)
        self._disk_rates_per: dict[str, tuple[float, float]] = {}
        self._auto_network_interface: str | None = None
        self._rate_unit = "bits"
        self._network_interface = "auto"

        self._last_process_sample_time: float | None = None
        self._process_cpu_state: dict[int, tuple[float, float]] = {}

        self._partition_signature: tuple[tuple[str, str], ...] = ()
        self._disk_mount_map: dict[int, list[str]] = {}

        self._gpu = NvidiaProvider()
        self._windows_cpu = WindowsCpuFrequencyProvider()
        self._fans = HardwareFanProvider()
        self._disk_health = DiskHealthProvider()
        self.update_options(rate_unit=rate_unit, network_interface=network_interface)
        psutil.cpu_percent(interval=None)

    def update_options(self, *, rate_unit: str | None = None, network_interface: str | None = None) -> None:
        if rate_unit is not None:
            normalized = str(rate_unit).strip().lower()
            self._rate_unit = normalized if normalized in {"bits", "bytes"} else "bits"
        if network_interface is not None:
            normalized_interface = str(network_interface or "auto").strip()
            self._network_interface = normalized_interface or "auto"

    @staticmethod
    def _safe_net_total() -> Any | None:
        try:
            return psutil.net_io_counters()
        except Exception:
            return None

    @staticmethod
    def _safe_net_per() -> dict[str, Any]:
        try:
            return dict(psutil.net_io_counters(pernic=True) or {})
        except Exception:
            return {}

    @staticmethod
    def _safe_disk_total() -> Any | None:
        try:
            return psutil.disk_io_counters()
        except Exception:
            return None

    @staticmethod
    def _safe_disk_per() -> dict[str, Any]:
        try:
            return dict(psutil.disk_io_counters(perdisk=True) or {})
        except Exception:
            return {}

    @staticmethod
    def _counter_rate(current: Any, previous: Any, field: str, elapsed: float) -> float:
        try:
            current_value = float(getattr(current, field))
            previous_value = float(getattr(previous, field))
        except (AttributeError, TypeError, ValueError):
            return 0.0
        return max(0.0, (current_value - previous_value) / elapsed)

    def _update_rates(self) -> None:
        now = time.monotonic()
        current_net_total = self._safe_net_total()
        current_net_per = self._safe_net_per()
        current_disk_total = self._safe_disk_total()
        current_disk_per = self._safe_disk_per()
        self._current_net_total = current_net_total
        self._current_net_per = current_net_per

        if self._last_rate_sample_time is None:
            self._last_rate_sample_time = now
            self._last_net_total = current_net_total
            self._last_net_per = current_net_per
            self._last_disk_total = current_disk_total
            self._last_disk_per = current_disk_per
            self._net_total_rates = (0.0, 0.0)
            self._net_rates_per = {name: (0.0, 0.0) for name in current_net_per}
            self._disk_total_rates = (0.0, 0.0)
            self._disk_rates_per = {name: (0.0, 0.0) for name in current_disk_per}
            return

        elapsed = max(0.001, now - self._last_rate_sample_time)
        if current_net_total is not None and self._last_net_total is not None:
            self._net_total_rates = (
                self._counter_rate(current_net_total, self._last_net_total, "bytes_recv", elapsed),
                self._counter_rate(current_net_total, self._last_net_total, "bytes_sent", elapsed),
            )
        else:
            self._net_total_rates = (0.0, 0.0)

        net_rates: dict[str, tuple[float, float]] = {}
        for name, current in current_net_per.items():
            previous = self._last_net_per.get(name)
            if previous is None:
                net_rates[name] = (0.0, 0.0)
            else:
                net_rates[name] = (
                    self._counter_rate(current, previous, "bytes_recv", elapsed),
                    self._counter_rate(current, previous, "bytes_sent", elapsed),
                )
        self._net_rates_per = net_rates

        if current_disk_total is not None and self._last_disk_total is not None:
            self._disk_total_rates = (
                self._counter_rate(current_disk_total, self._last_disk_total, "read_bytes", elapsed),
                self._counter_rate(current_disk_total, self._last_disk_total, "write_bytes", elapsed),
            )
        else:
            self._disk_total_rates = (0.0, 0.0)

        disk_rates: dict[str, tuple[float, float]] = {}
        for name, current in current_disk_per.items():
            previous = self._last_disk_per.get(name)
            if previous is None:
                disk_rates[name] = (0.0, 0.0)
            else:
                disk_rates[name] = (
                    self._counter_rate(current, previous, "read_bytes", elapsed),
                    self._counter_rate(current, previous, "write_bytes", elapsed),
                )
        self._disk_rates_per = disk_rates

        self._last_rate_sample_time = now
        self._last_net_total = current_net_total
        self._last_net_per = current_net_per
        self._last_disk_total = current_disk_total
        self._last_disk_per = current_disk_per

    @staticmethod
    def _system_disk_path() -> str:
        if os.name == "nt":
            drive = os.environ.get("SystemDrive", "C:")
            return drive.rstrip("\\/") + "\\"
        return "/"

    @staticmethod
    def _cpu_temperature() -> tuple[float | None, str]:
        sensor_function = getattr(psutil, "sensors_temperatures", None)
        if not callable(sensor_function):
            return None, "Temperature sensors are not exposed by this operating system"
        try:
            groups = sensor_function(fahrenheit=False) or {}
        except Exception as exc:
            return None, str(exc) or "Temperature sensor query failed"

        candidates: list[tuple[float, str]] = []
        preferred_keys = ("coretemp", "k10temp", "cpu_thermal", "acpitz")
        ordered_keys = list(preferred_keys) + [key for key in groups if key not in preferred_keys]
        for key in ordered_keys:
            for entry in groups.get(key, []):
                current = getattr(entry, "current", None)
                if current is None:
                    continue
                try:
                    value = float(current)
                except (TypeError, ValueError):
                    continue
                if -20.0 <= value <= 150.0:
                    label = (getattr(entry, "label", "") or key).strip()
                    candidates.append((value, label))
            if candidates and key in preferred_keys:
                break

        if not candidates:
            return None, "No compatible CPU temperature sensor was found"
        value, label = max(candidates, key=lambda item: item[0])
        return value, label

    @staticmethod
    def _is_idle_process(pid: int, name: str) -> bool:
        lowered = name.casefold().strip()
        return pid == 0 or lowered in {"system idle process", "idle", "idle.exe"}

    def _process_snapshot(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
        now = time.monotonic()
        elapsed = None if self._last_process_sample_time is None else max(0.001, now - self._last_process_sample_time)
        logical_count = max(1, psutil.cpu_count(logical=True) or 1)
        current_state: dict[int, tuple[float, float]] = {}
        groups: dict[str, dict[str, Any]] = {}
        process_count = 0

        attributes = ["pid", "name", "cpu_times", "memory_info", "create_time"]
        for process in psutil.process_iter(attributes):
            try:
                pid = int(process.info.get("pid", process.pid))
                raw_name = str(process.info.get("name") or "Unknown")
                if self._is_idle_process(pid, raw_name):
                    continue
                process_count += 1

                cpu_times = process.info.get("cpu_times")
                cpu_total = float(getattr(cpu_times, "user", 0.0)) + float(getattr(cpu_times, "system", 0.0))
                create_time = float(process.info.get("create_time") or 0.0)
                current_state[pid] = (create_time, cpu_total)

                memory_info = process.info.get("memory_info")
                # Task Manager's Processes view is much closer to the current
                # working set than to committed private bytes. Summing RSS by
                # executable also makes multi-process browsers compare as one app.
                rss_memory = getattr(memory_info, "rss", None) if memory_info is not None else None
                private_memory = getattr(memory_info, "private", 0) if memory_info is not None else 0
                memory_bytes = int(rss_memory if rss_memory is not None else private_memory or 0)
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess, TypeError, ValueError):
                continue

            key = raw_name.casefold().strip() or f"unknown:{pid}"
            group = groups.setdefault(
                key,
                {
                    "name": compact_process_name(raw_name, 30),
                    "raw_name": raw_name,
                    "count": 0,
                    "memory": 0,
                    "cpu": 0.0,
                    "representative_pid": pid,
                },
            )
            group["count"] += 1
            group["memory"] += max(0, memory_bytes)

            previous = self._process_cpu_state.get(pid)
            if elapsed is not None and elapsed >= 0.05 and previous is not None:
                previous_create, previous_total = previous
                if abs(previous_create - create_time) < 0.001 and cpu_total >= previous_total:
                    delta = cpu_total - previous_total
                    # Normalize across all logical processors to match Task Manager's
                    # 0-100% process scale rather than psutil's per-core scale.
                    cpu_percent = delta / elapsed * 100.0 / logical_count
                    if 0.0 <= cpu_percent < 1000.0:
                        group["cpu"] += cpu_percent

        self._process_cpu_state = current_state
        self._last_process_sample_time = now

        top_memory = None
        memory_groups = [group for group in groups.values() if int(group["memory"]) > 0]
        if memory_groups:
            top_memory = max(memory_groups, key=lambda group: int(group["memory"]))

        top_cpu = None
        if elapsed is not None and elapsed >= 0.05:
            cpu_groups = [group for group in groups.values() if float(group["cpu"]) > 0.0001]
            if cpu_groups:
                top_cpu = max(cpu_groups, key=lambda group: float(group["cpu"]))

        return top_cpu, top_memory, process_count

    @staticmethod
    def _mounted_partitions() -> list[Any]:
        try:
            partitions = list(psutil.disk_partitions(all=False) or [])
        except Exception:
            partitions = []
        unique: dict[str, Any] = {}
        for partition in partitions:
            mountpoint = str(getattr(partition, "mountpoint", "") or "").strip()
            if mountpoint and mountpoint not in unique:
                unique[mountpoint] = partition
        return sorted(unique.values(), key=lambda item: _natural_key(str(getattr(item, "mountpoint", ""))))

    def _refresh_disk_mount_map(self, partitions: list[Any]) -> None:
        signature = tuple(
            (str(getattr(partition, "device", "")), str(getattr(partition, "mountpoint", "")))
            for partition in partitions
        )
        if signature == self._partition_signature:
            return
        self._partition_signature = signature
        self._disk_mount_map = build_disk_mount_map(partitions)

    @staticmethod
    def _drive_label(mountpoint: str) -> str:
        text = str(mountpoint or "").strip()
        if os.name == "nt" and len(text) >= 2 and text[1] == ":":
            return text[:2].upper()
        stripped = text.rstrip("/\\")
        return stripped or text or "/"

    def _disk_io_label(self, key: str) -> tuple[str, str, str]:
        text = str(key)
        number_match = re.search(r"(\d+)$", text)
        if os.name == "nt" and number_match:
            number = int(number_match.group(1))
            mounts = self._disk_mount_map.get(number, [])
            mount_text = ", ".join(mounts)
            base = f"Disk {number}"
            if mount_text:
                base += f" ({mount_text})"
            return f"{base} read / write", f"PhysicalDrive{number}", f"{number:08d}"
        return f"{text} read / write", text, text

    @staticmethod
    def _is_loopback_interface(name: str) -> bool:
        lowered = name.casefold()
        return lowered in {"lo", "loopback"} or "loopback" in lowered

    @staticmethod
    def _looks_virtual_interface(name: str) -> bool:
        lowered = name.casefold()
        virtual_tokens = (
            "vethernet",
            "hyper-v",
            "vmware",
            "virtualbox",
            "docker",
            "wsl",
            "npcap",
            "tap-",
            "tunnel",
            "bluetooth",
        )
        return any(token in lowered for token in virtual_tokens)

    @staticmethod
    def _is_pseudo_disk_counter(name: str) -> bool:
        lowered = str(name).casefold()
        return lowered.startswith(("loop", "ram", "zram", "fd"))

    def _choose_network_interface(self) -> str:
        requested = self._network_interface
        if requested not in {"auto", "all"} and requested in self._current_net_per:
            return requested
        if requested == "all":
            return "all"

        try:
            stats = psutil.net_if_stats() or {}
        except Exception:
            stats = {}
        candidates = [
            name
            for name in self._current_net_per
            if not self._is_loopback_interface(name)
            and (name not in stats or bool(getattr(stats[name], "isup", True)))
        ]
        if not candidates:
            candidates = [name for name in self._current_net_per if not self._is_loopback_interface(name)]
        if not candidates:
            return "all"

        # Prefer ordinary Ethernet/Wi-Fi adapters for automatic mode. A VPN or
        # virtual switch remains selectable explicitly in Settings.
        physical_candidates = [name for name in candidates if not self._looks_virtual_interface(name)]
        if physical_candidates:
            candidates = physical_candidates

        def score(name: str) -> float:
            receive, send = self._net_rates_per.get(name, (0.0, 0.0))
            return receive + send

        busiest = max(candidates, key=lambda name: (score(name), name.casefold()))
        busiest_score = score(busiest)
        current = self._auto_network_interface
        if current in candidates:
            current_score = score(current)
            # Avoid jumping between adapters when all of them are nearly idle.
            if busiest_score < 2048.0 or current_score >= busiest_score * 0.35:
                busiest = current
        self._auto_network_interface = busiest
        return busiest

    def _network_values(self) -> tuple[str, float, float, Any | None]:
        interface = self._choose_network_interface()
        if interface == "all":
            receive, send = self._net_total_rates
            return "All adapters", receive, send, self._current_net_total
        receive, send = self._net_rates_per.get(interface, (0.0, 0.0))
        return interface, receive, send, self._current_net_per.get(interface)

    def collect(
        self,
        selected_metrics: Iterable[str],
        *,
        rate_unit: str | None = None,
        network_interface: str | None = None,
    ) -> Snapshot:
        self.update_options(rate_unit=rate_unit, network_interface=network_interface)
        selected = set(selected_metrics)
        snapshot: Snapshot = {metric_id: unavailable("Waiting for a sample") for metric_id in selected}

        try:
            self._update_rates()
        except Exception:
            self._net_total_rates = (0.0, 0.0)
            self._net_rates_per = {}
            self._disk_total_rates = (0.0, 0.0)
            self._disk_rates_per = {}

        if "clock" in selected:
            now = dt.datetime.now().astimezone()
            snapshot["clock"] = make_reading(now.strftime("%H:%M:%S"), now.strftime("%A, %d %B %Y"))

        if "uptime" in selected:
            try:
                boot_time = psutil.boot_time()
                uptime_seconds = time.time() - boot_time
                boot = dt.datetime.fromtimestamp(boot_time).astimezone()
                snapshot["uptime"] = make_reading(
                    format_duration(uptime_seconds),
                    f"Booted {boot.strftime('%d %b %Y at %H:%M')}",
                    history=uptime_seconds,
                )
            except Exception as exc:
                snapshot["uptime"] = unavailable(str(exc) or "Boot time unavailable")

        cpu_percent: float | None = None
        cpu_frequency = None
        clock_sample: dict[str, Any] = {}
        if {"cpu_usage", "cpu_frequency"} & selected:
            try:
                cpu_percent = float(psutil.cpu_percent(interval=None))
            except Exception:
                cpu_percent = None
            try:
                cpu_frequency = psutil.cpu_freq()
            except Exception:
                cpu_frequency = None

            ps_current = getattr(cpu_frequency, "current", None)
            ps_maximum = getattr(cpu_frequency, "max", None)
            if os.name == "nt":
                candidates = [
                    float(value)
                    for value in (ps_current, ps_maximum)
                    if value is not None and float(value) > 0.0
                ]
                nominal = max(candidates) if candidates else None
                clock_sample = self._windows_cpu.sample(nominal)
            else:
                current = float(ps_current) if ps_current else None
                maximum = float(ps_maximum) if ps_maximum else None
                clock_sample = {
                    "current_mhz": current,
                    "nominal_mhz": maximum,
                    "peak_mhz": maximum,
                    "source": "psutil",
                }

        if "cpu_usage" in selected:
            if cpu_percent is None:
                snapshot["cpu_usage"] = unavailable("CPU utilization query failed")
            else:
                frequency_detail = format_frequency(clock_sample.get("current_mhz"))
                logical = psutil.cpu_count(logical=True) or 0
                snapshot["cpu_usage"] = make_reading(
                    f"{cpu_percent:.0f}%",
                    f"{frequency_detail} | {logical} logical processors",
                    progress=cpu_percent,
                    history=cpu_percent,
                )

        if "cpu_frequency" in selected:
            current = clock_sample.get("current_mhz")
            nominal = clock_sample.get("nominal_mhz")
            peak = clock_sample.get("peak_mhz")
            if current is None:
                snapshot["cpu_frequency"] = unavailable("CPU frequency is not exposed")
            else:
                if os.name == "nt":
                    details: list[str] = []
                    if nominal:
                        details.append(f"Nominal {format_frequency(nominal)}")
                    if peak:
                        details.append(f"session peak {format_frequency(peak)}")
                    detail = " | ".join(details) or str(clock_sample.get("source") or "Windows live clock")
                    ceiling = max(float(value) for value in (current, peak or 0.0, nominal or 0.0))
                else:
                    detail = f"Maximum {format_frequency(nominal)}" if nominal else "Current average clock"
                    ceiling = float(nominal or current)
                progress = float(current) / ceiling * 100.0 if ceiling > 0 else None
                snapshot["cpu_frequency"] = make_reading(
                    format_frequency(current),
                    detail,
                    progress=min(100.0, progress) if progress is not None else None,
                    history=float(current),
                )

        if "cpu_temperature" in selected:
            value, label = self._cpu_temperature()
            snapshot["cpu_temperature"] = (
                make_reading(
                    f"{value:.0f} C",
                    label,
                    progress=min(100.0, max(0.0, value)),
                    history=value,
                )
                if value is not None
                else unavailable(label)
            )

        if "cpu_fan" in selected:
            try:
                fan = self._fans.cpu_fan()
                if not fan.get("available"):
                    reason = str(fan.get("error") or "CPU fan speed is not exposed").strip()
                    lowered = reason.casefold()
                    if "starting" in lowered or "next refresh" in lowered:
                        short_reason = "Detecting fan sensor..."
                    elif "none was labelled" in lowered or "none was labeled" in lowered:
                        short_reason = "CPU fan not identified"
                    else:
                        short_reason = "Fan sensor not detected"
                    snapshot["cpu_fan"] = unavailable(
                        short_reason,
                        tooltip=reason or "CPU fan speed is not exposed",
                    )
                else:
                    rpm = max(0.0, float(fan.get("rpm") or 0.0))
                    details = [str(fan.get("name") or "CPU fan")]
                    source = str(fan.get("source") or "").strip()
                    note = str(fan.get("note") or "").strip()
                    if source:
                        details.append(source)
                    if note:
                        details.append(note)
                    snapshot["cpu_fan"] = make_reading(
                        f"{rpm:,.0f} RPM",
                        " | ".join(details),
                        history=rpm,
                    )
            except Exception as exc:
                reason = str(exc).strip() or "CPU fan query failed"
                snapshot["cpu_fan"] = unavailable("Fan query failed", tooltip=reason)

        if "memory" in selected:
            try:
                memory = psutil.virtual_memory()
                snapshot["memory"] = make_reading(
                    f"{memory.percent:.0f}%",
                    f"{format_bytes(memory.used)} used | {format_bytes(memory.available)} available",
                    progress=float(memory.percent),
                    history=float(memory.percent),
                )
            except Exception as exc:
                snapshot["memory"] = unavailable(str(exc) or "Memory query failed")

        if "swap" in selected:
            try:
                swap = psutil.swap_memory()
                snapshot["swap"] = make_reading(
                    f"{swap.percent:.0f}%",
                    f"{format_bytes(swap.used)} used of {format_bytes(swap.total)}",
                    progress=float(swap.percent),
                    history=float(swap.percent),
                )
            except Exception as exc:
                snapshot["swap"] = unavailable(str(exc) or "Swap query failed")

        gpu_metric_ids = {
            "gpu_usage",
            "gpu_memory",
            "gpu_temperature",
            "gpu_power",
            "gpu_clock",
            "gpu_fan",
            "top_gpu_process",
        }
        if gpu_metric_ids & selected:
            gpu = self._gpu.collect(include_processes="top_gpu_process" in selected)
            if not gpu.get("available"):
                reason = str(gpu.get("error") or "NVML is unavailable")
                for metric_id in gpu_metric_ids & selected:
                    snapshot[metric_id] = unavailable(reason)
            else:
                gpu_name = str(gpu.get("name") or "NVIDIA GPU")
                usage = gpu.get("usage")
                used = gpu.get("memory_used")
                total = gpu.get("memory_total")
                temperature = gpu.get("temperature")
                power = gpu.get("power_watts")
                graphics_clock = gpu.get("graphics_clock_mhz")
                clock_peak = gpu.get("graphics_clock_peak_mhz")
                memory_clock = gpu.get("memory_clock_mhz")
                fan_percent = gpu.get("fan_percent")

                if "gpu_usage" in selected:
                    snapshot["gpu_usage"] = (
                        make_reading(
                            f"{float(usage):.0f}%",
                            gpu_name,
                            progress=float(usage),
                            history=float(usage),
                        )
                        if usage is not None
                        else unavailable("GPU utilization is not exposed")
                    )
                if "gpu_memory" in selected:
                    if used is not None and total:
                        percent = float(used) / float(total) * 100.0
                        snapshot["gpu_memory"] = make_reading(
                            f"{percent:.0f}%",
                            f"{format_bytes(used)} used of {format_bytes(total)}",
                            progress=percent,
                            history=percent,
                        )
                    else:
                        snapshot["gpu_memory"] = unavailable("GPU memory information is not exposed")
                if "gpu_temperature" in selected:
                    snapshot["gpu_temperature"] = (
                        make_reading(
                            f"{float(temperature):.0f} C",
                            gpu_name,
                            progress=min(100.0, float(temperature)),
                            history=float(temperature),
                        )
                        if temperature is not None
                        else unavailable("GPU temperature is not exposed")
                    )
                if "gpu_power" in selected:
                    snapshot["gpu_power"] = (
                        make_reading(f"{float(power):.1f} W", gpu_name, history=float(power))
                        if power is not None
                        else unavailable("GPU power draw is not exposed")
                    )
                if "gpu_clock" in selected:
                    if graphics_clock is None:
                        snapshot["gpu_clock"] = unavailable("NVIDIA graphics clock is not exposed")
                    else:
                        details = []
                        if clock_peak:
                            details.append(f"session peak {format_frequency(clock_peak)}")
                        if memory_clock:
                            details.append(f"memory {format_frequency(memory_clock)}")
                        details.append(gpu_name)
                        ceiling = max(float(graphics_clock), float(clock_peak or 0.0))
                        progress = float(graphics_clock) / ceiling * 100.0 if ceiling > 0 else None
                        snapshot["gpu_clock"] = make_reading(
                            format_frequency(graphics_clock),
                            " | ".join(details),
                            progress=min(100.0, progress) if progress is not None else None,
                            history=float(graphics_clock),
                        )
                if "gpu_fan" in selected:
                    if fan_percent is None:
                        snapshot["gpu_fan"] = unavailable(
                            "GPU fan sensor unavailable",
                            tooltip=(
                                "NVIDIA fan duty is not exposed; some laptops and "
                                "passively cooled cards do not report it"
                            ),
                        )
                    else:
                        fan_count = max(1, int(gpu.get("fan_count") or 1))
                        fan_label = "fan" if fan_count == 1 else "fans"
                        snapshot["gpu_fan"] = make_reading(
                            f"{float(fan_percent):.0f}%",
                            f"Highest of {fan_count} {fan_label} | {gpu_name}",
                            progress=float(fan_percent),
                            history=float(fan_percent),
                        )
                if "top_gpu_process" in selected:
                    process = gpu.get("top_process")
                    if not process:
                        snapshot["top_gpu_process"] = unavailable(
                            "Per-process NVIDIA GPU utilization and VRAM data are not exposed"
                        )
                    elif process.get("warming_up"):
                        snapshot["top_gpu_process"] = unavailable(
                            "GPU process data is warming up; wait one refresh"
                        )
                    elif process.get("idle"):
                        snapshot["top_gpu_process"] = make_reading(
                            "None",
                            "No active NVIDIA GPU process in this sample",
                        )
                    elif process.get("source") == "engine":
                        amount = min(100.0, max(0.0, float(process.get("utilization") or 0.0)))
                        count = max(1, int(process.get("count") or 1))
                        target = f"{count} processes" if count > 1 else f"PID {int(process.get('pid') or 0)}"
                        snapshot["top_gpu_process"] = make_reading(
                            str(process.get("name") or "Unknown"),
                            f"{amount:.1f}% NVIDIA engine | {target}",
                            progress=amount,
                            history=amount,
                        )
                    else:
                        memory_bytes = max(0, int(process.get("memory") or 0))
                        count = max(1, int(process.get("count") or 1))
                        target = f"{count} processes" if count > 1 else f"PID {int(process.get('pid') or 0)}"
                        snapshot["top_gpu_process"] = make_reading(
                            str(process.get("name") or "Unknown"),
                            f"{format_bytes(memory_bytes)} VRAM | fallback ranking | {target}",
                            history=float(memory_bytes),
                        )

        partitions: list[Any] = []
        if {"disk_usage_all", "disk_io_all", "disk_health"} & selected:
            partitions = self._mounted_partitions()
            self._refresh_disk_mount_map(partitions)

        if "disk_usage" in selected:
            try:
                path = self._system_disk_path()
                usage = psutil.disk_usage(path)
                drive_label = path[:2] if os.name == "nt" else path
                snapshot["disk_usage"] = make_reading(
                    f"{usage.percent:.0f}%",
                    f"{drive_label} | {format_bytes(usage.free)} free of {format_bytes(usage.total)}",
                    progress=float(usage.percent),
                    history=float(usage.percent),
                )
            except Exception as exc:
                snapshot["disk_usage"] = unavailable(str(exc) or "Disk usage query failed")

        if "disk_usage_all" in selected:
            added = 0
            for partition in partitions:
                mountpoint = str(getattr(partition, "mountpoint", "") or "")
                try:
                    usage = psutil.disk_usage(mountpoint)
                except Exception:
                    continue
                drive_label = self._drive_label(mountpoint)
                fstype = str(getattr(partition, "fstype", "") or "").strip()
                detail = f"{format_bytes(usage.free)} free of {format_bytes(usage.total)}"
                if fstype:
                    detail += f" | {fstype}"
                metric_id = f"{DISK_USAGE_PREFIX}{mountpoint}"
                snapshot[metric_id] = make_reading(
                    f"{usage.percent:.0f}% used",
                    detail,
                    progress=float(usage.percent),
                    history=float(usage.percent),
                    label=f"{drive_label} storage",
                    description=f"Used and free space on {mountpoint}.",
                    sort_key=drive_label,
                )
                added += 1
            if added:
                snapshot.pop("disk_usage_all", None)
            else:
                snapshot["disk_usage_all"] = unavailable("No accessible mounted disks were found")

        if "disk_io" in selected:
            read_rate, write_rate = self._disk_total_rates
            snapshot["disk_io"] = make_reading(
                f"Read {format_rate(read_rate)}",
                f"Write {format_rate(write_rate)} | all physical disks",
                history=read_rate + write_rate,
            )

        if "disk_io_all" in selected:
            keys = [key for key in self._disk_rates_per if not self._is_pseudo_disk_counter(key)]
            if os.name == "nt":
                physical = [key for key in keys if re.search(r"(?:physicaldrive)?\d+$", key, re.IGNORECASE)]
                if physical:
                    keys = physical
            added = 0
            for key in sorted(keys, key=_natural_key):
                read_rate, write_rate = self._disk_rates_per.get(key, (0.0, 0.0))
                label, technical_name, sort_key = self._disk_io_label(key)
                metric_id = f"{DISK_IO_PREFIX}{key}"
                snapshot[metric_id] = make_reading(
                    f"Read {format_rate(read_rate)}",
                    f"Write {format_rate(write_rate)} | {technical_name}",
                    history=read_rate + write_rate,
                    label=label,
                    description=f"Live read and write throughput for {technical_name}.",
                    sort_key=sort_key,
                )
                added += 1
            if added:
                snapshot.pop("disk_io_all", None)
            else:
                detail = "No per-disk I/O counters were found"
                if os.name == "nt":
                    detail += "; Windows may require 'diskperf -y' in an Administrator terminal"
                snapshot["disk_io_all"] = unavailable(detail)

        if "disk_health" in selected:
            try:
                disks, health_error = self._disk_health.collect()
                added = 0
                for index, disk in enumerate(disks):
                    device_id = str(disk.get("device_id") or index)
                    name = str(disk.get("name") or f"Physical disk {device_id}")
                    health = str(disk.get("health") or "Unknown")
                    operational = str(disk.get("operational") or "").strip()
                    media_type = str(disk.get("media_type") or "").strip()
                    size = max(0, int(disk.get("size") or 0))
                    details = [name]
                    if media_type and media_type.casefold() not in {"unspecified", "unknown"}:
                        details.append(media_type)
                    if size:
                        details.append(format_bytes(size))
                    if operational and operational.casefold() != health.casefold():
                        details.append(operational)
                    score = disk_health_score(health)
                    metric_id = f"{DISK_HEALTH_PREFIX}{device_id}"
                    mounts: list[str] = []
                    try:
                        mounts = self._disk_mount_map.get(int(device_id), [])
                    except (TypeError, ValueError):
                        mounts = []
                    mount_text = ", ".join(mounts)
                    display_disk = f"Disk {device_id}"
                    if mount_text:
                        display_disk += f" ({mount_text})"
                    snapshot[metric_id] = make_reading(
                        health,
                        " | ".join(details),
                        progress=score,
                        history=score,
                        label=f"{display_disk} health",
                        description=f"Windows physical-disk health status for {name}.",
                        sort_key=f"{index:08d}",
                    )
                    added += 1
                if added:
                    snapshot.pop("disk_health", None)
                else:
                    snapshot["disk_health"] = unavailable(health_error or "No physical-disk health data was found")
            except Exception as exc:
                snapshot["disk_health"] = unavailable(str(exc) or "Disk health query failed")

        interface_name = "All adapters"
        receive_rate = send_rate = 0.0
        interface_totals = None
        if {"network_speed", "network_total"} & selected:
            interface_name, receive_rate, send_rate, interface_totals = self._network_values()

        if "network_speed" in selected:
            snapshot["network_speed"] = make_reading(
                f"Receive {format_network_rate(receive_rate, self._rate_unit)}",
                f"Send {format_network_rate(send_rate, self._rate_unit)} | {interface_name}",
                history=receive_rate + send_rate,
            )

        if "network_total" in selected:
            if interface_totals is None:
                snapshot["network_total"] = unavailable("No network counters were found")
            else:
                try:
                    snapshot["network_total"] = make_reading(
                        f"Receive {format_bytes(interface_totals.bytes_recv)}",
                        f"Send {format_bytes(interface_totals.bytes_sent)} since boot | {interface_name}",
                    )
                except Exception as exc:
                    snapshot["network_total"] = unavailable(str(exc) or "Network counters failed")

        if "wifi_signal" in selected:
            try:
                wifi = query_wifi_connection()
                if not wifi.get("available"):
                    snapshot["wifi_signal"] = unavailable(str(wifi.get("error") or "No connected Wi-Fi interface was found"))
                else:
                    quality = min(100.0, max(0.0, float(wifi.get("quality") or 0.0)))
                    dbm = float(wifi.get("dbm") or -100.0)
                    ssid = str(wifi.get("ssid") or "Connected Wi-Fi")
                    rx = max(0.0, float(wifi.get("rx_mbps") or 0.0))
                    tx = max(0.0, float(wifi.get("tx_mbps") or 0.0))
                    interface = str(wifi.get("interface") or "Wi-Fi")
                    snapshot["wifi_signal"] = make_reading(
                        f"{quality:.0f}%",
                        f"{ssid} | {dbm:.0f} dBm | link Rx {rx:g} / Tx {tx:g} Mbps",
                        progress=quality,
                        history=quality,
                        description=f"Signal and negotiated link rates for {interface}.",
                    )
            except Exception as exc:
                snapshot["wifi_signal"] = unavailable(str(exc) or "Wi-Fi signal query failed")

        process_metrics = {"process_count", "top_cpu_process", "top_memory_process"} & selected
        if process_metrics:
            try:
                top_cpu, top_memory, process_count = self._process_snapshot()
                if "process_count" in selected:
                    snapshot["process_count"] = make_reading(
                        str(process_count),
                        "Running processes",
                        history=float(process_count),
                    )
                if "top_cpu_process" in selected:
                    if top_cpu is None:
                        snapshot["top_cpu_process"] = unavailable("Process CPU data is warming up; wait one refresh")
                    else:
                        count = int(top_cpu["count"])
                        cpu = min(100.0, max(0.0, float(top_cpu["cpu"])))
                        if count > 1:
                            target = f"{count} processes"
                        else:
                            target = f"PID {int(top_cpu['representative_pid'])}"
                        snapshot["top_cpu_process"] = make_reading(
                            str(top_cpu["name"]),
                            f"{cpu:.1f}% total CPU | {target}",
                            progress=cpu,
                            history=cpu,
                        )
                if "top_memory_process" in selected:
                    if top_memory is None:
                        snapshot["top_memory_process"] = unavailable("Process memory data is unavailable")
                    else:
                        count = int(top_memory["count"])
                        memory_bytes = int(top_memory["memory"])
                        if count > 1:
                            target = f"{count} processes combined"
                        else:
                            target = f"PID {int(top_memory['representative_pid'])}"
                        memory_kind = "working set" if os.name == "nt" else "resident memory"
                        snapshot["top_memory_process"] = make_reading(
                            str(top_memory["name"]),
                            f"{format_bytes(memory_bytes)} {memory_kind} | {target}",
                            history=float(memory_bytes),
                        )
            except Exception as exc:
                for metric_id in process_metrics:
                    snapshot[metric_id] = unavailable(str(exc) or "Process query failed")

        if {"battery", "battery_time"} & selected:
            try:
                battery = psutil.sensors_battery()
                if battery is None:
                    if "battery" in selected:
                        snapshot["battery"] = unavailable("No battery was detected")
                    if "battery_time" in selected:
                        snapshot["battery_time"] = unavailable("No battery was detected")
                else:
                    plugged = bool(battery.power_plugged)
                    if "battery" in selected:
                        snapshot["battery"] = make_reading(
                            f"{battery.percent:.0f}%",
                            "Plugged in" if plugged else "Running on battery",
                            progress=float(battery.percent),
                            history=float(battery.percent),
                        )
                    if "battery_time" in selected:
                        if plugged:
                            snapshot["battery_time"] = make_reading(
                                "Plugged in",
                                "The runtime estimate resumes when the PC is using battery power",
                            )
                        elif battery.secsleft in (psutil.POWER_TIME_UNKNOWN, psutil.POWER_TIME_UNLIMITED):
                            snapshot["battery_time"] = unavailable("Windows did not provide a remaining-time estimate")
                        else:
                            seconds = max(0, int(battery.secsleft))
                            snapshot["battery_time"] = make_reading(
                                _format_estimated_time(seconds),
                                f"Estimated at {battery.percent:.0f}% charge",
                                history=float(seconds),
                            )
            except Exception as exc:
                for metric_id in {"battery", "battery_time"} & selected:
                    snapshot[metric_id] = unavailable(str(exc) or "Battery query failed")

        if "clipboard_history" in selected:
            snapshot["clipboard_history"] = unavailable(
                "Session clipboard history is collected by the UI and never written to disk"
            )

        return snapshot

    def shutdown(self) -> None:
        self._gpu.shutdown()
        self._windows_cpu.close()
