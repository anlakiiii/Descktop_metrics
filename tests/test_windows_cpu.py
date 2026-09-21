import os

from desktop_metrics.windows_cpu import WindowsCpuFrequencyProvider


def test_non_windows_frequency_provider_falls_back_to_nominal() -> None:
    if os.name == "nt":
        return
    provider = WindowsCpuFrequencyProvider()
    try:
        sample = provider.sample(4300.0)
    finally:
        provider.close()
    assert sample["current_mhz"] == 4300.0
    assert sample["nominal_mhz"] == 4300.0
    assert sample["peak_mhz"] == 4300.0


def test_performance_counter_can_report_boost_above_nominal(monkeypatch) -> None:
    import ctypes
    from ctypes import wintypes

    class FakePdh:
        @staticmethod
        def PdhCollectQueryData(_query):
            return 0

        @staticmethod
        def PdhCloseQuery(_query):
            return 0

    provider = WindowsCpuFrequencyProvider()
    provider._pdh = FakePdh()
    provider._query = wintypes.HANDLE(1)
    provider._performance_counter = wintypes.HANDLE(2)
    provider._frequency_counter = wintypes.HANDLE(3)
    provider._available = True

    def fake_read(counter):
        if ctypes.cast(counter, ctypes.c_void_p).value == 2:
            return 125.0
        return 4300.0

    monkeypatch.setattr(provider, "_read_counter", fake_read)
    try:
        sample = provider.sample(4300.0)
    finally:
        provider.close()

    assert sample["current_mhz"] == 5375.0
    assert sample["nominal_mhz"] == 4300.0
    assert sample["peak_mhz"] == 5375.0
    assert sample["source"] == "Windows performance counter"
