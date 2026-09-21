from __future__ import annotations

import os
import threading
import time
from typing import Any

from .windows_powershell import run_powershell_json


def _as_list(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


class DiskHealthProvider:
    """Cached physical-disk health query for Windows.

    Get-PhysicalDisk provides the same high-level Healthy/Warning/Unhealthy
    status Windows Storage exposes. A Win32_DiskDrive fallback is used on
    systems where the Storage module is unavailable.
    """

    def __init__(self, cache_seconds: float = 60.0) -> None:
        self._cache_seconds = max(5.0, float(cache_seconds))
        self._last_query = 0.0
        self._items: list[dict[str, Any]] = []
        self._error = "Disk health has not been queried yet"
        self._lock = threading.Lock()
        self._query_in_progress = False

    @staticmethod
    def _normalize(item: dict[str, Any], index: int) -> dict[str, Any]:
        raw_id = item.get("device_id", index)
        device_id = str(raw_id if raw_id not in (None, "") else index)
        name = str(item.get("name") or item.get("model") or f"Physical disk {device_id}").strip()
        health = str(item.get("health") or item.get("status") or "Unknown").strip()
        operational = item.get("operational") or item.get("operational_status") or ""
        if isinstance(operational, list):
            operational = ", ".join(str(value) for value in operational if value is not None)
        operational_text = str(operational or "").strip()
        media_type = str(item.get("media_type") or item.get("media") or "").strip()
        serial = str(item.get("serial") or "").strip()
        try:
            size = max(0, int(item.get("size") or 0))
        except (TypeError, ValueError):
            size = 0
        return {
            "device_id": device_id,
            "name": name,
            "health": health or "Unknown",
            "operational": operational_text,
            "media_type": media_type,
            "serial": serial,
            "size": size,
        }

    def _query_windows(self) -> tuple[list[dict[str, Any]], str]:
        primary_script = r"""
$items = @(Get-PhysicalDisk | Sort-Object DeviceId | ForEach-Object {
    [pscustomobject]@{
        device_id = [string]$_.DeviceId
        name = [string]$_.FriendlyName
        serial = [string]$_.SerialNumber
        media_type = [string]$_.MediaType
        health = [string]$_.HealthStatus
        operational = [string](($_.OperationalStatus | ForEach-Object { [string]$_ }) -join ', ')
        size = [int64]$_.Size
    }
})
ConvertTo-Json -InputObject $items -Compress -Depth 4
"""
        data, error = run_powershell_json(primary_script, timeout=9.0)
        items = _as_list(data)
        if items:
            return [self._normalize(item, index) for index, item in enumerate(items)], ""

        fallback_script = r"""
$items = @(Get-CimInstance -ClassName Win32_DiskDrive | Sort-Object Index | ForEach-Object {
    [pscustomobject]@{
        device_id = [string]$_.Index
        name = [string]$_.Model
        serial = [string]$_.SerialNumber
        media_type = [string]$_.MediaType
        health = [string]$_.Status
        operational = [string]$_.Status
        size = [int64]$_.Size
    }
})
ConvertTo-Json -InputObject $items -Compress -Depth 4
"""
        fallback_data, fallback_error = run_powershell_json(fallback_script, timeout=9.0)
        fallback_items = _as_list(fallback_data)
        if fallback_items:
            return [self._normalize(item, index) for index, item in enumerate(fallback_items)], ""
        return [], fallback_error or error or "Windows returned no physical-disk health information"

    def _store_result(self, items: list[dict[str, Any]], error: str) -> None:
        self._items = items if items else []
        self._error = "" if items else error
        self._last_query = time.monotonic()
        self._query_in_progress = False

    def _background_query(self) -> None:
        try:
            items, error = self._query_windows()
        except Exception as exc:  # Defensive: Storage/CIM providers vary by system.
            items, error = [], str(exc) or "Disk health query failed"
        with self._lock:
            self._store_result(items, error)

    def collect(self, *, force: bool = False) -> tuple[list[dict[str, Any]], str]:
        if os.name != "nt":
            return [], "Disk health cards currently use the Windows Storage provider"

        if force:
            items, error = self._query_windows()
            with self._lock:
                self._store_result(items, error)
                return list(self._items), self._error

        now = time.monotonic()
        with self._lock:
            due = not self._last_query or now - self._last_query >= self._cache_seconds
            if due and not self._query_in_progress:
                self._query_in_progress = True
                threading.Thread(
                    target=self._background_query,
                    name="DesktopMetricsDiskHealthQuery",
                    daemon=True,
                ).start()
            items = list(self._items)
            error = self._error
            in_progress = self._query_in_progress

        if not items and in_progress:
            return [], "Disk health query is starting; wait for the next refresh"
        return items, error


_HEALTH_SCORES = {
    # More-specific negative states must precede "healthy" because the word
    # "unhealthy" contains "healthy".
    "unhealthy": 10.0,
    "pred fail": 5.0,
    "failed": 5.0,
    "degraded": 25.0,
    "warning": 55.0,
    "caution": 55.0,
    "healthy": 100.0,
    "ok": 100.0,
}


def disk_health_score(status: str) -> float | None:
    lowered = str(status or "").strip().casefold()
    if not lowered or lowered == "unknown":
        return None
    for token, score in _HEALTH_SCORES.items():
        if token in lowered:
            return score
    return None
