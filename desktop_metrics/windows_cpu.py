from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Any


class _PdhValueUnion(ctypes.Union):
    _fields_ = [
        ("long_value", wintypes.LONG),
        ("double_value", ctypes.c_double),
        ("large_value", ctypes.c_longlong),
        ("ansi_string_value", ctypes.c_char_p),
        ("wide_string_value", ctypes.c_wchar_p),
    ]


class _PdhFormattedCounterValue(ctypes.Structure):
    _anonymous_ = ("value",)
    _fields_ = [
        ("status", wintypes.DWORD),
        ("value", _PdhValueUnion),
    ]


class _ProcessorPowerInformation(ctypes.Structure):
    _fields_ = [
        ("number", wintypes.ULONG),
        ("max_mhz", wintypes.ULONG),
        ("current_mhz", wintypes.ULONG),
        ("mhz_limit", wintypes.ULONG),
        ("max_idle_state", wintypes.ULONG),
        ("current_idle_state", wintypes.ULONG),
    ]


class WindowsCpuFrequencyProvider:
    """Read a boost-aware Windows CPU clock without extra Python packages.

    psutil's Windows frequency is normally the nominal fixed clock. Windows'
    ``% Processor Performance`` counter can exceed 100 while boost is active;
    multiplying it by the nominal clock gives a much closer match to the live
    Speed value shown by Task Manager.
    """

    PDH_FMT_DOUBLE = 0x00000200
    VALID_STATUSES = {0, 1}
    PROCESSOR_INFORMATION_LEVEL = 11

    def __init__(self) -> None:
        self._pdh: Any | None = None
        self._query = wintypes.HANDLE()
        self._performance_counter = wintypes.HANDLE()
        self._frequency_counter = wintypes.HANDLE()
        self._session_peak_mhz = 0.0
        self._available = False
        self.error_message = "Windows performance counters are unavailable"

        if os.name != "nt":
            return
        self._open_pdh_query()

    def _open_pdh_query(self) -> None:
        try:
            pdh = ctypes.WinDLL("pdh.dll")
            pdh.PdhOpenQueryW.argtypes = [
                wintypes.LPCWSTR,
                ctypes.c_size_t,
                ctypes.POINTER(wintypes.HANDLE),
            ]
            pdh.PdhOpenQueryW.restype = wintypes.LONG
            pdh.PdhAddEnglishCounterW.argtypes = [
                wintypes.HANDLE,
                wintypes.LPCWSTR,
                ctypes.c_size_t,
                ctypes.POINTER(wintypes.HANDLE),
            ]
            pdh.PdhAddEnglishCounterW.restype = wintypes.LONG
            pdh.PdhCollectQueryData.argtypes = [wintypes.HANDLE]
            pdh.PdhCollectQueryData.restype = wintypes.LONG
            pdh.PdhGetFormattedCounterValue.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                ctypes.POINTER(wintypes.DWORD),
                ctypes.POINTER(_PdhFormattedCounterValue),
            ]
            pdh.PdhGetFormattedCounterValue.restype = wintypes.LONG
            pdh.PdhCloseQuery.argtypes = [wintypes.HANDLE]
            pdh.PdhCloseQuery.restype = wintypes.LONG

            status = int(pdh.PdhOpenQueryW(None, 0, ctypes.byref(self._query)))
            if status != 0:
                self.error_message = f"PdhOpenQueryW failed (0x{status & 0xFFFFFFFF:08X})"
                return

            performance_status = int(
                pdh.PdhAddEnglishCounterW(
                    self._query,
                    r"\Processor Information(_Total)\% Processor Performance",
                    0,
                    ctypes.byref(self._performance_counter),
                )
            )
            frequency_status = int(
                pdh.PdhAddEnglishCounterW(
                    self._query,
                    r"\Processor Information(_Total)\Processor Frequency",
                    0,
                    ctypes.byref(self._frequency_counter),
                )
            )
            if performance_status != 0:
                self._performance_counter = wintypes.HANDLE()
            if frequency_status != 0:
                self._frequency_counter = wintypes.HANDLE()
            if not self._performance_counter.value and not self._frequency_counter.value:
                self.error_message = "Processor Information counters were not found"
                self.close()
                return

            self._pdh = pdh
            self._available = True
            # Prime counters which need two samples before they become valid.
            pdh.PdhCollectQueryData(self._query)
        except Exception as exc:
            self.error_message = str(exc) or exc.__class__.__name__
            self.close()

    @property
    def available(self) -> bool:
        return self._available and self._pdh is not None and bool(self._query.value)

    @staticmethod
    def _power_frequencies() -> tuple[float | None, float | None]:
        if os.name != "nt":
            return None, None
        try:
            count = max(1, os.cpu_count() or 1)
            entries_type = _ProcessorPowerInformation * count
            entries = entries_type()
            powrprof = ctypes.WinDLL("powrprof.dll")
            powrprof.CallNtPowerInformation.argtypes = [
                ctypes.c_int,
                ctypes.c_void_p,
                wintypes.ULONG,
                ctypes.c_void_p,
                wintypes.ULONG,
            ]
            powrprof.CallNtPowerInformation.restype = wintypes.LONG
            status = int(
                powrprof.CallNtPowerInformation(
                    WindowsCpuFrequencyProvider.PROCESSOR_INFORMATION_LEVEL,
                    None,
                    0,
                    ctypes.byref(entries),
                    ctypes.sizeof(entries),
                )
            )
            if status != 0:
                return None, None
            currents = [float(entry.current_mhz) for entry in entries if entry.current_mhz > 0]
            maximums = [float(entry.max_mhz) for entry in entries if entry.max_mhz > 0]
            current = sum(currents) / len(currents) if currents else None
            nominal = max(maximums) if maximums else None
            return current, nominal
        except Exception:
            return None, None

    def _read_counter(self, counter: wintypes.HANDLE) -> float | None:
        if not self.available or not counter.value or self._pdh is None:
            return None
        value = _PdhFormattedCounterValue()
        counter_type = wintypes.DWORD()
        status = int(
            self._pdh.PdhGetFormattedCounterValue(
                counter,
                self.PDH_FMT_DOUBLE,
                ctypes.byref(counter_type),
                ctypes.byref(value),
            )
        )
        if status != 0 or int(value.status) not in self.VALID_STATUSES:
            return None
        result = float(value.double_value)
        return result if result > 0.0 else None

    def sample(self, nominal_mhz: float | None) -> dict[str, float | str | None]:
        power_current, power_nominal = self._power_frequencies()
        nominal_candidates = [
            float(value)
            for value in (nominal_mhz, power_nominal)
            if value is not None and 100.0 <= float(value) <= 20000.0
        ]
        nominal = max(nominal_candidates) if nominal_candidates else None

        performance_percent: float | None = None
        direct_frequency: float | None = None
        if self.available and self._pdh is not None:
            status = int(self._pdh.PdhCollectQueryData(self._query))
            if status == 0:
                performance_percent = self._read_counter(self._performance_counter)
                direct_frequency = self._read_counter(self._frequency_counter)

        current: float | None = None
        source = "nominal fallback"
        if nominal and performance_percent and 0.0 < performance_percent < 1000.0:
            current = nominal * performance_percent / 100.0
            source = "Windows performance counter"
        elif direct_frequency and 100.0 <= direct_frequency <= 20000.0:
            current = direct_frequency
            source = "Windows frequency counter"
        elif power_current and 100.0 <= power_current <= 20000.0:
            current = power_current
            source = "Windows power information"
        elif nominal:
            current = nominal

        if current and 100.0 <= current <= 20000.0:
            self._session_peak_mhz = max(self._session_peak_mhz, current)
        return {
            "current_mhz": current,
            "nominal_mhz": nominal,
            "peak_mhz": self._session_peak_mhz or current or nominal,
            "performance_percent": performance_percent,
            "source": source,
        }

    def close(self) -> None:
        if self._pdh is not None and self._query.value:
            try:
                self._pdh.PdhCloseQuery(self._query)
            except Exception:
                pass
        self._query = wintypes.HANDLE()
        self._performance_counter = wintypes.HANDLE()
        self._frequency_counter = wintypes.HANDLE()
        self._available = False
