from __future__ import annotations

import os

# The portable build keeps configuration, logs, and the lock file in a
# DesktopMetricsData folder beside DesktopMetrics-Portable.exe.
os.environ["DESKTOP_METRICS_PORTABLE"] = "1"

from main import main  # noqa: E402  (portable mode must be selected first)


if __name__ == "__main__":
    raise SystemExit(main())
