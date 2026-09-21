from desktop_metrics.formatting import (
    compact_process_name,
    format_bit_rate,
    format_bytes,
    format_duration,
    format_frequency,
    format_network_rate,
    format_rate,
)


def test_format_bytes() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(1024**3) == "1.0 GB"


def test_format_rate() -> None:
    assert format_rate(1024) == "1.0 KB/s"


def test_format_network_rate_uses_bits_for_task_manager_style() -> None:
    assert format_bit_rate(1_000_000) == "8.00 Mbps"
    assert format_bit_rate(13_000) == "104 Kbps"
    assert format_network_rate(1_000_000, "bits") == "8.00 Mbps"
    assert format_network_rate(1024, "bytes") == "1.0 KB/s"


def test_format_duration() -> None:
    assert format_duration(5) == "5s"
    assert format_duration(65) == "1m 5s"
    assert format_duration(3665) == "1h 1m 5s"
    assert format_duration(90061) == "1d 1h 1m"


def test_format_frequency() -> None:
    assert format_frequency(None) == "Unavailable"
    assert format_frequency(800) == "800 MHz"
    assert format_frequency(4200) == "4.20 GHz"


def test_friendly_process_names() -> None:
    assert compact_process_name("chrome.exe") == "Google Chrome"
    assert compact_process_name("pythonw.exe") == "Python"
