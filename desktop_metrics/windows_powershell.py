from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import Any


def _powershell_executable() -> str | None:
    if os.name != "nt":
        return None
    for candidate in ("powershell.exe", "pwsh.exe"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def run_powershell_json(script: str, *, timeout: float = 8.0) -> tuple[Any | None, str]:
    """Run a small read-only PowerShell query and decode its JSON output.

    The command is hidden on Windows so periodic sensor refreshes do not flash a
    console window. Callers are expected to cache expensive queries.
    """

    executable = _powershell_executable()
    if executable is None:
        return None, "PowerShell is unavailable"

    prefix = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new($false); "
    )
    creation_flags = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
    try:
        completed = subprocess.run(
            [
                executable,
                "-NoLogo",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                prefix + script,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(1.0, float(timeout)),
            creationflags=creation_flags,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "PowerShell sensor query timed out"
    except OSError as exc:
        return None, str(exc) or "PowerShell could not be started"

    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "PowerShell query failed").strip()
        return None, message[:500]

    output = (completed.stdout or "").strip().lstrip("\ufeff")
    if not output:
        return [], ""
    try:
        return json.loads(output), ""
    except json.JSONDecodeError as exc:
        return None, f"PowerShell returned invalid sensor data: {exc}"
