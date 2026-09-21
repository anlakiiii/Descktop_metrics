from __future__ import annotations

import ctypes
import logging
import os
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QLockFile, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

from desktop_metrics.app import DesktopMetricsController
from desktop_metrics.config import ConfigStore
from desktop_metrics.constants import APP_DISPLAY_NAME, APP_NAME, APP_VERSION, ORGANIZATION_NAME


_WINDOWS_MUTEX_HANDLE: int | None = None
_WINDOWS_MUTEX_NAME = "DesktopMetrics.DesktopMetrics.AppMutex"


def configure_high_dpi() -> None:
    """Keep Qt in per-monitor DPI mode and preserve fractional Windows scaling."""
    try:
        QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except (AttributeError, RuntimeError):
        # Qt 6 already enables high-DPI scaling by default. This fallback keeps
        # source compatibility with older compatible PySide6 builds.
        pass


def create_windows_app_mutex() -> None:
    """Expose a named mutex so the installer can detect a running tray app."""
    global _WINDOWS_MUTEX_HANDLE
    if os.name != "nt" or _WINDOWS_MUTEX_HANDLE:
        return
    try:
        function = ctypes.windll.kernel32.CreateMutexW
        function.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        function.restype = ctypes.c_void_p
        handle = function(None, False, _WINDOWS_MUTEX_NAME)
        if handle:
            _WINDOWS_MUTEX_HANDLE = int(handle)
    except Exception:
        pass


def configure_logging() -> Path:
    directory = ConfigStore().directory
    directory.mkdir(parents=True, exist_ok=True)
    log_path = directory / "desktop_metrics.log"
    logging.basicConfig(
        filename=log_path,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return log_path


def set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        function = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID
        function.argtypes = [ctypes.c_wchar_p]
        function.restype = ctypes.c_long
        function("DesktopMetrics.DesktopMetrics.1")
    except Exception:
        pass


def main() -> int:
    set_windows_app_id()
    create_windows_app_mutex()
    configure_high_dpi()
    log_path = configure_logging()
    app = QApplication(sys.argv)
    # Use Qt's built-in Fusion style so portable Python/Windows themes cannot
    # make controls or selection indicators disappear.
    app.setStyle("Fusion")
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setOrganizationName(ORGANIZATION_NAME)
    app.setQuitOnLastWindowClosed(False)

    lock_path = ConfigStore().directory / "DesktopMetrics.lock"
    lock = QLockFile(str(lock_path))
    lock.setStaleLockTime(30000)
    if not lock.tryLock(100):
        if not (lock.removeStaleLockFile() and lock.tryLock(100)):
            QMessageBox.information(
                None,
                APP_DISPLAY_NAME,
                f"Desktop Metrics is already running in the system tray.\n\nQuit the old tray instance before starting v{APP_VERSION}.",
            )
            return 0

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(
            None,
            APP_DISPLAY_NAME,
            "A system tray is required to run Desktop Metrics.",
        )
        return 1

    try:
        controller = DesktopMetricsController(app, Path(sys.argv[0]).resolve())
        app._desktop_metrics_controller = controller
        return app.exec()
    except Exception as exc:
        logging.exception("Fatal startup error")
        details = "".join(traceback.format_exception(exc))
        QMessageBox.critical(
            None,
            APP_DISPLAY_NAME,
            f"Desktop Metrics could not start.\n\n{exc}\n\nDetails were written to:\n{log_path}",
        )
        logging.error(details)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
