from __future__ import annotations

import os
import threading
import time
from typing import Any

import psutil

from .windows_powershell import run_powershell_json


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


class HardwareFanProvider:
    """Read fan RPM where the platform exposes it.

    On Windows, generic fan RPM is vendor-specific. Desktop Metrics supports
    LibreHardwareMonitor/OpenHardwareMonitor WMI sensors when either monitor is
    running, then falls back to the rarely-populated Win32_Fan class.
    """

    def __init__(self, cache_seconds: float = 15.0) -> None:
        self._cache_seconds = max(1.0, float(cache_seconds))
        self._last_query = 0.0
        self._fans: list[dict[str, Any]] = []
        self._error = "Fan sensors have not been queried yet"
        self._lock = threading.Lock()
        self._query_in_progress = False

    @staticmethod
    def _normalize(item: dict[str, Any], index: int) -> dict[str, Any] | None:
        try:
            rpm = float(item.get("rpm") if item.get("rpm") is not None else item.get("value"))
        except (TypeError, ValueError):
            return None
        if not 0.0 <= rpm < 100_000.0:
            return None
        name = str(item.get("name") or f"Fan {index + 1}").strip()
        identifier = str(item.get("identifier") or "").strip()
        parent = str(item.get("parent") or "").strip()
        source = str(item.get("source") or "Hardware sensor").strip()
        return {
            "name": name,
            "identifier": identifier,
            "parent": parent,
            "source": source,
            "rpm": rpm,
        }

    @staticmethod
    def _query_psutil() -> tuple[list[dict[str, Any]], str]:
        function = getattr(psutil, "sensors_fans", None)
        if not callable(function):
            return [], "Fan sensors are not exposed by this operating system"
        try:
            groups = function() or {}
        except Exception as exc:
            return [], str(exc) or "Fan sensor query failed"

        fans: list[dict[str, Any]] = []
        for group_name, entries in groups.items():
            for index, entry in enumerate(entries):
                current = getattr(entry, "current", None)
                if current is None:
                    continue
                item = HardwareFanProvider._normalize(
                    {
                        "name": getattr(entry, "label", "") or f"{group_name} fan {index + 1}",
                        "identifier": group_name,
                        "parent": group_name,
                        "source": "psutil",
                        "rpm": current,
                    },
                    index,
                )
                if item is not None:
                    fans.append(item)
        return fans, "" if fans else "No compatible fan sensor was found"

    @staticmethod
    def _query_windows() -> tuple[list[dict[str, Any]], str]:
        script = r"""
$items = @()
foreach ($namespace in @('root/LibreHardwareMonitor', 'root/OpenHardwareMonitor')) {
    try {
        $rows = @(Get-CimInstance -Namespace $namespace -ClassName Sensor -ErrorAction Stop |
            Where-Object { [string]$_.SensorType -eq 'Fan' -and $_.Value -ne $null })
        if ($rows.Count -gt 0) {
            $items = @($rows | ForEach-Object {
                [pscustomobject]@{
                    name = [string]$_.Name
                    identifier = [string]$_.Identifier
                    parent = [string]$_.Parent
                    source = [string]$namespace
                    rpm = [double]$_.Value
                }
            })
            break
        }
    } catch {}
}
if ($items.Count -eq 0) {
    try {
        $items = @(Get-CimInstance -ClassName Win32_Fan -ErrorAction Stop |
            Where-Object { $_.DesiredSpeed -ne $null -and [double]$_.DesiredSpeed -gt 0 } |
            ForEach-Object {
                [pscustomobject]@{
                    name = [string]$_.Name
                    identifier = [string]$_.DeviceID
                    parent = ''
                    source = 'Win32_Fan reported speed'
                    rpm = [double]$_.DesiredSpeed
                }
            })
    } catch {}
}
ConvertTo-Json -InputObject $items -Compress -Depth 4
"""
        data, error = run_powershell_json(script, timeout=8.0)
        fans: list[dict[str, Any]] = []
        for index, raw in enumerate(_as_list(data)):
            item = HardwareFanProvider._normalize(raw, index)
            if item is not None:
                fans.append(item)
        if fans:
            return fans, ""
        guidance = (
            "No CPU fan RPM was exposed. On Windows, run LibreHardwareMonitor "
            "or OpenHardwareMonitor with its WMI sensors enabled."
        )
        return [], error or guidance

    def _perform_query(self) -> tuple[list[dict[str, Any]], str]:
        return self._query_windows() if os.name == "nt" else self._query_psutil()

    def _background_query(self) -> None:
        try:
            fans, error = self._perform_query()
        except Exception as exc:  # Defensive: sensor backends are vendor-specific.
            fans, error = [], str(exc) or "Fan sensor query failed"
        with self._lock:
            self._fans = fans
            self._error = error
            self._last_query = time.monotonic()
            self._query_in_progress = False

    def collect(self, *, force: bool = False) -> tuple[list[dict[str, Any]], str]:
        if force:
            fans, error = self._perform_query()
            with self._lock:
                self._fans = fans
                self._error = error
                self._last_query = time.monotonic()
                self._query_in_progress = False
                return list(self._fans), self._error

        now = time.monotonic()
        with self._lock:
            due = not self._last_query or now - self._last_query >= self._cache_seconds
            if due and not self._query_in_progress:
                self._query_in_progress = True
                threading.Thread(
                    target=self._background_query,
                    name="DesktopMetricsFanQuery",
                    daemon=True,
                ).start()
            fans = list(self._fans)
            error = self._error
            in_progress = self._query_in_progress

        if not fans and in_progress:
            return [], "Fan sensor query is starting; wait for the next refresh"
        return fans, error

    def cpu_fan(self) -> dict[str, Any]:
        fans, error = self.collect()
        if not fans:
            return {"available": False, "error": error}

        cpu_tokens = ("cpu", "processor", "package", "socket")
        gpu_tokens = ("gpu", "graphics", "video")
        candidates: list[dict[str, Any]] = []
        for fan in fans:
            searchable = " ".join(
                str(fan.get(key) or "") for key in ("name", "identifier", "parent")
            ).casefold()
            if any(token in searchable for token in gpu_tokens):
                continue
            if any(token in searchable for token in cpu_tokens):
                candidates.append(fan)

        note = ""
        if not candidates and len(fans) == 1:
            candidates = fans
            note = "Only detected fan; the board did not label it as CPU"
        if not candidates:
            return {
                "available": False,
                "error": "Fan sensors were found, but none was labelled as the CPU fan",
            }

        selected = max(candidates, key=lambda item: float(item.get("rpm") or 0.0))
        return {
            "available": True,
            "rpm": float(selected["rpm"]),
            "name": str(selected.get("name") or "CPU fan"),
            "source": str(selected.get("source") or "Hardware sensor"),
            "note": note,
        }
