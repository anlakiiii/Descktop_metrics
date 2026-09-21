from __future__ import annotations


_FRIENDLY_PROCESS_NAMES = {
    "chrome.exe": "Google Chrome",
    "chrome": "Google Chrome",
    "msedge.exe": "Microsoft Edge",
    "msedge": "Microsoft Edge",
    "firefox.exe": "Mozilla Firefox",
    "firefox": "Mozilla Firefox",
    "explorer.exe": "Windows Explorer",
    "explorer": "Windows Explorer",
    "python.exe": "Python",
    "pythonw.exe": "Python",
    "python": "Python",
    "python3": "Python",
}


def format_bytes(value: float | int, precision: int = 1) -> str:
    """Format a byte count using binary units."""
    amount = float(max(0, value))
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    unit = units[0]
    for unit in units:
        if amount < 1024.0 or unit == units[-1]:
            break
        amount /= 1024.0
    if unit == "B":
        return f"{amount:.0f} {unit}"
    return f"{amount:.{precision}f} {unit}"


def format_rate(bytes_per_second: float | int) -> str:
    """Format storage throughput in bytes per second."""
    return f"{format_bytes(bytes_per_second)}/s"


def format_bit_rate(bytes_per_second: float | int) -> str:
    """Format a byte counter as decimal bits per second, like Task Manager."""
    amount = float(max(0, bytes_per_second)) * 8.0
    units = ("bps", "Kbps", "Mbps", "Gbps", "Tbps")
    unit = units[0]
    for unit in units:
        if amount < 1000.0 or unit == units[-1]:
            break
        amount /= 1000.0

    if unit == "bps" or amount >= 100:
        precision = 0
    elif amount >= 10:
        precision = 1
    else:
        precision = 2
    return f"{amount:.{precision}f} {unit}"


def format_network_rate(bytes_per_second: float | int, unit_mode: str = "bits") -> str:
    return format_rate(bytes_per_second) if unit_mode == "bytes" else format_bit_rate(bytes_per_second)


def format_duration(seconds: float | int) -> str:
    total_seconds = max(0, int(seconds))
    days, remainder = divmod(total_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m {secs}s"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def format_frequency(mhz: float | int | None) -> str:
    if mhz is None or mhz <= 0:
        return "Unavailable"
    if mhz >= 1000:
        return f"{mhz / 1000.0:.2f} GHz"
    return f"{mhz:.0f} MHz"


def friendly_process_name(name: str | None) -> str:
    raw = (name or "Unknown").strip() or "Unknown"
    return _FRIENDLY_PROCESS_NAMES.get(raw.casefold(), raw)


def compact_process_name(name: str | None, max_length: int = 24) -> str:
    text = friendly_process_name(name)
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "..."
