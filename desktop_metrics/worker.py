from __future__ import annotations

import threading
import time
from collections.abc import Iterable
from typing import Any

from PySide6.QtCore import QThread, Signal

from .collector import SystemCollector


class MetricsWorker(QThread):
    """Continuously sample selected metrics without blocking the UI thread."""

    snapshot_ready = Signal(dict)
    collection_error = Signal(str)

    def __init__(
        self,
        selected_metrics: Iterable[str],
        refresh_ms: int,
        *,
        rate_unit: str = "bits",
        network_interface: str = "auto",
        parent: Any | None = None,
    ) -> None:
        super().__init__(parent)
        self._selected_metrics = list(selected_metrics)
        self._refresh_ms = max(250, int(refresh_ms))
        self._rate_unit = str(rate_unit)
        self._network_interface = str(network_interface)
        self._state_lock = threading.Lock()
        self._stop_event = threading.Event()
        self._wake_event = threading.Event()

    def update_preferences(
        self,
        selected_metrics: Iterable[str],
        refresh_ms: int,
        *,
        rate_unit: str = "bits",
        network_interface: str = "auto",
    ) -> None:
        with self._state_lock:
            self._selected_metrics = list(selected_metrics)
            self._refresh_ms = max(250, int(refresh_ms))
            self._rate_unit = str(rate_unit)
            self._network_interface = str(network_interface)
        self._wake_event.set()

    def stop(self) -> None:
        self._stop_event.set()
        self._wake_event.set()

    def run(self) -> None:
        collector = SystemCollector()
        try:
            while not self._stop_event.is_set():
                with self._state_lock:
                    selected = tuple(self._selected_metrics)
                    refresh_ms = self._refresh_ms
                    rate_unit = self._rate_unit
                    network_interface = self._network_interface

                started = time.monotonic()
                try:
                    self.snapshot_ready.emit(
                        collector.collect(
                            selected,
                            rate_unit=rate_unit,
                            network_interface=network_interface,
                        )
                    )
                except Exception as exc:
                    self.collection_error.emit(str(exc) or exc.__class__.__name__)

                elapsed = time.monotonic() - started
                delay = max(0.05, refresh_ms / 1000.0 - elapsed)
                self._wake_event.wait(delay)
                self._wake_event.clear()
        finally:
            collector.shutdown()
