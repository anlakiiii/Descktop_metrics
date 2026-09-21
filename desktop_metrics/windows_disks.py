from __future__ import annotations

import ctypes
import os
import re
from collections.abc import Iterable
from ctypes import wintypes
from typing import Any


class _StorageDeviceNumber(ctypes.Structure):
    _fields_ = [
        ("device_type", wintypes.DWORD),
        ("device_number", wintypes.DWORD),
        ("partition_number", wintypes.DWORD),
    ]


# CTL_CODE(FILE_DEVICE_MASS_STORAGE, 0x420, METHOD_BUFFERED, FILE_ANY_ACCESS)
_IOCTL_STORAGE_GET_DEVICE_NUMBER = 0x002D1080
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_OPEN_EXISTING = 3
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def volume_device_number(mountpoint: str) -> int | None:
    """Return the Windows physical device number backing a drive-letter volume."""
    if os.name != "nt":
        return None

    text = str(mountpoint or "")
    match = _DRIVE_RE.match(text)
    if not match:
        return None
    drive = match.group(0).upper()
    path = rf"\\.\{drive}"

    try:
        kernel32 = ctypes.WinDLL("kernel32.dll", use_last_error=True)
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            wintypes.HANDLE,
        ]
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.DeviceIoControl.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        kernel32.DeviceIoControl.restype = wintypes.BOOL
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL

        handle = kernel32.CreateFileW(
            path,
            0,
            _FILE_SHARE_READ | _FILE_SHARE_WRITE,
            None,
            _OPEN_EXISTING,
            0,
            None,
        )
        handle_value = getattr(handle, "value", handle)
        if handle_value in (None, _INVALID_HANDLE_VALUE):
            return None

        try:
            result = _StorageDeviceNumber()
            returned = wintypes.DWORD()
            ok = kernel32.DeviceIoControl(
                handle,
                _IOCTL_STORAGE_GET_DEVICE_NUMBER,
                None,
                0,
                ctypes.byref(result),
                ctypes.sizeof(result),
                ctypes.byref(returned),
                None,
            )
            return int(result.device_number) if ok else None
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def build_disk_mount_map(partitions: Iterable[Any]) -> dict[int, list[str]]:
    """Map physical disk numbers to visible drive letters on Windows."""
    mapping: dict[int, list[str]] = {}
    if os.name != "nt":
        return mapping

    for partition in partitions:
        mountpoint = str(getattr(partition, "mountpoint", "") or "")
        match = _DRIVE_RE.match(mountpoint)
        if not match:
            continue
        drive = match.group(0).upper()
        number = volume_device_number(drive)
        if number is None:
            continue
        values = mapping.setdefault(number, [])
        if drive not in values:
            values.append(drive)

    for values in mapping.values():
        values.sort()
    return mapping
