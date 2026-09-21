from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any


WLAN_INTERFACE_STATE_CONNECTED = 1
WLAN_INTF_OPCODE_CURRENT_CONNECTION = 7
ERROR_SUCCESS = 0
WLAN_MAX_NAME_LENGTH = 256
DOT11_SSID_MAX_LENGTH = 32


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class DOT11_SSID(ctypes.Structure):
    _fields_ = [
        ("uSSIDLength", wintypes.ULONG),
        ("ucSSID", ctypes.c_ubyte * DOT11_SSID_MAX_LENGTH),
    ]


class WLAN_ASSOCIATION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("dot11Ssid", DOT11_SSID),
        ("dot11BssType", wintypes.DWORD),
        ("dot11Bssid", ctypes.c_ubyte * 6),
        ("dot11PhyType", wintypes.DWORD),
        ("uDot11PhyIndex", wintypes.ULONG),
        ("wlanSignalQuality", wintypes.ULONG),
        ("ulRxRate", wintypes.ULONG),
        ("ulTxRate", wintypes.ULONG),
    ]


class WLAN_SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("bSecurityEnabled", wintypes.BOOL),
        ("bOneXEnabled", wintypes.BOOL),
        ("dot11AuthAlgorithm", wintypes.DWORD),
        ("dot11CipherAlgorithm", wintypes.DWORD),
    ]


class WLAN_CONNECTION_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("isState", wintypes.DWORD),
        ("wlanConnectionMode", wintypes.DWORD),
        ("strProfileName", ctypes.c_wchar * WLAN_MAX_NAME_LENGTH),
        ("wlanAssociationAttributes", WLAN_ASSOCIATION_ATTRIBUTES),
        ("wlanSecurityAttributes", WLAN_SECURITY_ATTRIBUTES),
    ]


class WLAN_INTERFACE_INFO(ctypes.Structure):
    _fields_ = [
        ("InterfaceGuid", GUID),
        ("strInterfaceDescription", ctypes.c_wchar * WLAN_MAX_NAME_LENGTH),
        ("isState", wintypes.DWORD),
    ]


class WLAN_INTERFACE_INFO_LIST(ctypes.Structure):
    _fields_ = [
        ("dwNumberOfItems", wintypes.DWORD),
        ("dwIndex", wintypes.DWORD),
        ("InterfaceInfo", WLAN_INTERFACE_INFO * 1),
    ]


def signal_quality_to_dbm(quality: float | int) -> float:
    """Convert Windows' 0-100 WLAN quality to its documented RSSI estimate."""
    clamped = max(0.0, min(100.0, float(quality)))
    return -100.0 + clamped * 0.5


def _decode_ssid(ssid: DOT11_SSID) -> str:
    length = max(0, min(DOT11_SSID_MAX_LENGTH, int(ssid.uSSIDLength)))
    raw = bytes(ssid.ucSSID[:length])
    for encoding in ("utf-8", "mbcs" if os.name == "nt" else "latin-1"):
        try:
            return raw.decode(encoding).strip("\x00")
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("latin-1", errors="replace").strip("\x00")


def query_wifi_connection() -> dict[str, Any]:
    if os.name != "nt":
        return {"available": False, "error": "Wi-Fi signal is currently implemented for Windows"}

    try:
        wlan = ctypes.WinDLL("wlanapi.dll")
    except OSError as exc:
        return {"available": False, "error": str(exc) or "Windows WLAN API is unavailable"}

    wlan.WlanOpenHandle.argtypes = [
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.HANDLE),
    ]
    wlan.WlanOpenHandle.restype = wintypes.DWORD
    wlan.WlanEnumInterfaces.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    wlan.WlanEnumInterfaces.restype = wintypes.DWORD
    wlan.WlanQueryInterface.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(GUID),
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(wintypes.DWORD),
    ]
    wlan.WlanQueryInterface.restype = wintypes.DWORD
    wlan.WlanFreeMemory.argtypes = [ctypes.c_void_p]
    wlan.WlanFreeMemory.restype = None
    wlan.WlanCloseHandle.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    wlan.WlanCloseHandle.restype = wintypes.DWORD

    negotiated = wintypes.DWORD()
    handle = wintypes.HANDLE()
    result = wlan.WlanOpenHandle(2, None, ctypes.byref(negotiated), ctypes.byref(handle))
    if result != ERROR_SUCCESS:
        return {"available": False, "error": f"WlanOpenHandle failed with Windows error {result}"}

    interface_list_ptr = ctypes.c_void_p()
    connections: list[dict[str, Any]] = []
    try:
        result = wlan.WlanEnumInterfaces(handle, None, ctypes.byref(interface_list_ptr))
        if result != ERROR_SUCCESS or not interface_list_ptr.value:
            return {"available": False, "error": f"WlanEnumInterfaces failed with Windows error {result}"}

        info_list = ctypes.cast(
            interface_list_ptr,
            ctypes.POINTER(WLAN_INTERFACE_INFO_LIST),
        ).contents
        base_address = (
            int(interface_list_ptr.value) + WLAN_INTERFACE_INFO_LIST.InterfaceInfo.offset
        )
        for index in range(int(info_list.dwNumberOfItems)):
            interface = WLAN_INTERFACE_INFO.from_address(
                base_address + index * ctypes.sizeof(WLAN_INTERFACE_INFO)
            )
            if int(interface.isState) != WLAN_INTERFACE_STATE_CONNECTED:
                continue

            data_size = wintypes.DWORD()
            data_ptr = ctypes.c_void_p()
            opcode_type = wintypes.DWORD()
            query_result = wlan.WlanQueryInterface(
                handle,
                ctypes.byref(interface.InterfaceGuid),
                WLAN_INTF_OPCODE_CURRENT_CONNECTION,
                None,
                ctypes.byref(data_size),
                ctypes.byref(data_ptr),
                ctypes.byref(opcode_type),
            )
            if query_result != ERROR_SUCCESS or not data_ptr.value:
                continue
            try:
                attributes = ctypes.cast(
                    data_ptr,
                    ctypes.POINTER(WLAN_CONNECTION_ATTRIBUTES),
                ).contents
                association = attributes.wlanAssociationAttributes
                quality = max(0.0, min(100.0, float(association.wlanSignalQuality)))
                connections.append(
                    {
                        "available": True,
                        "quality": quality,
                        "dbm": signal_quality_to_dbm(quality),
                        "ssid": _decode_ssid(association.dot11Ssid) or "Connected Wi-Fi",
                        "profile": str(attributes.strProfileName or "").strip(),
                        "interface": str(interface.strInterfaceDescription or "Wi-Fi").strip(),
                        # Native WLAN rates are reported in kilobits per second.
                        "rx_mbps": float(association.ulRxRate) / 1000.0,
                        "tx_mbps": float(association.ulTxRate) / 1000.0,
                    }
                )
            finally:
                wlan.WlanFreeMemory(data_ptr)
    finally:
        if interface_list_ptr.value:
            wlan.WlanFreeMemory(interface_list_ptr)
        wlan.WlanCloseHandle(handle, None)

    if not connections:
        return {"available": False, "error": "No connected Wi-Fi interface was found"}
    return max(connections, key=lambda item: float(item.get("quality") or 0.0))
