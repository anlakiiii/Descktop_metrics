from __future__ import annotations

import ast
import re
import struct
from pathlib import Path

from desktop_metrics.constants import APP_VERSION

ROOT = Path(__file__).resolve().parent


def require_text(path: Path, text: str) -> None:
    content = path.read_text(encoding="utf-8")
    if text not in content:
        raise SystemExit(f"{path.relative_to(ROOT)} does not contain {text!r}")


def ico_sizes(path: Path) -> set[tuple[int, int]]:
    raw = path.read_bytes()
    reserved, image_type, count = struct.unpack_from("<HHH", raw, 0)
    if reserved != 0 or image_type != 1 or count < 1:
        raise SystemExit(f"Invalid ICO header: {path}")
    sizes: set[tuple[int, int]] = set()
    offset = 6
    for _ in range(count):
        width, height = struct.unpack_from("<BB", raw, offset)
        sizes.add((width or 256, height or 256))
        offset += 16
    return sizes


def main() -> int:
    dotted = APP_VERSION
    quad = f"{APP_VERSION}.0"
    require_text(ROOT / "build_release.bat", f'set "APP_VERSION={dotted}"')
    require_text(ROOT / "installer" / "DesktopMetrics.iss", f'#define MyAppVersion "{dotted}"')
    require_text(ROOT / "README.md", f"v{dotted}")
    require_text(ROOT / "CHANGELOG.md", f"## {dotted}")

    for version_file in (ROOT / "packaging").glob("version_info_*.txt"):
        ast.parse(version_file.read_text(encoding="utf-8"))
        require_text(version_file, f"'{quad}'")

    required_sizes = {(16, 16), (32, 32), (48, 48), (64, 64), (256, 256)}
    sizes = ico_sizes(ROOT / "assets" / "desktop_metrics.ico")
    missing = required_sizes - sizes
    if missing:
        raise SystemExit(f"Application ICO is missing sizes: {sorted(missing)}")

    for required in (
        "main.py",
        "portable_main.py",
        "build_release.bat",
        "build_installer.bat",
        "installer/DesktopMetrics.iss",
        "packaging/version_info_installed.txt",
        "packaging/version_info_portable.txt",
        "assets/desktop_metrics.ico",
    ):
        if not (ROOT / required).is_file():
            raise SystemExit(f"Missing release file: {required}")

    # Confirm both PyInstaller targets and Setup point to the same ICO.
    for path in (
        ROOT / "build_release.bat",
        ROOT / "installer" / "DesktopMetrics.iss",
    ):
        require_text(path, "desktop_metrics.ico")

    print(f"Desktop Metrics v{APP_VERSION} release files are internally consistent.")
    print("ICO sizes:", ", ".join(f"{w}x{h}" for w, h in sorted(sizes)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
