from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .constants import APP_NAME

_REGISTRY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _startup_command(entry_script: Path) -> str:
    if getattr(sys, "frozen", False):
        return subprocess.list2cmdline([sys.executable])

    executable = Path(sys.executable)
    pythonw = executable.with_name("pythonw.exe") if os.name == "nt" else executable
    if os.name == "nt" and not pythonw.exists():
        pythonw = executable
    return subprocess.list2cmdline([str(pythonw), str(entry_script.resolve())])


def _commands_match(actual: str, expected: str) -> bool:
    # Registry command lines are case-insensitive on Windows. Whitespace and
    # optional outer quoting are normalized enough for paths written by this app
    # or by the Inno Setup installer.
    def normalize(value: str) -> str:
        normalized = " ".join(str(value).strip().split())
        if len(normalized) >= 2 and normalized.startswith('"') and normalized.endswith('"'):
            # Inno Setup always quotes the executable. subprocess.list2cmdline
            # omits quotes when a path contains no spaces; both forms are valid.
            if normalized.count('"') == 2:
                normalized = normalized[1:-1]
        return normalized.casefold()

    return normalize(actual) == normalize(expected)


def get_start_with_windows(entry_script: Path) -> tuple[bool | None, str]:
    """Read the real per-user startup state.

    Returns ``None`` when the registry cannot be queried, so callers do not
    overwrite a saved preference because of a temporary permissions problem.
    """
    if os.name != "nt":
        return None, "Start with Windows is available only on Windows"

    try:
        import winreg

        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                _REGISTRY_PATH,
                0,
                winreg.KEY_QUERY_VALUE,
            ) as key:
                actual, _value_type = winreg.QueryValueEx(key, APP_NAME)
        except FileNotFoundError:
            return False, "Startup entry is not present"

        expected = _startup_command(entry_script)
        enabled = _commands_match(str(actual), expected)
        if enabled:
            return True, "Startup entry matches this application"
        return False, "A stale startup entry points to a different application path"
    except Exception as exc:
        return None, str(exc) or "Could not read the Windows startup registry"


def set_start_with_windows(enabled: bool, entry_script: Path) -> tuple[bool, str]:
    if os.name != "nt":
        return False, "Start with Windows is available only on Windows"

    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _REGISTRY_PATH,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enabled:
                winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _startup_command(entry_script))
            else:
                try:
                    winreg.DeleteValue(key, APP_NAME)
                except FileNotFoundError:
                    pass
        return True, "Startup setting updated"
    except Exception as exc:
        return False, str(exc) or "Could not update the Windows startup registry"
