from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from .autostart import get_start_with_windows, set_start_with_windows
from .clipboard_history import ClipboardHistoryDialog, ClipboardHistoryTracker
from .config import AppConfig, ConfigStore
from .constants import APP_DISPLAY_NAME, APP_VERSION
from .desktop_widget import DesktopWidget
from .icon import create_app_icon
from .settings_window import SettingsWindow
from .metric_layout import expand_metric_ids, metric_display_label
from .worker import MetricsWorker


class DesktopMetricsController(QObject):
    """Own the tray icon, settings window, collector thread, and widget windows."""

    shutdown_complete = Signal()

    def __init__(self, app: QApplication, entry_script: Path) -> None:
        super().__init__()
        self.app = app
        self.entry_script = entry_script
        self.store = ConfigStore()
        self._first_run = not self.store.path.exists()
        self.config = self.store.load()
        self._shutting_down = False
        self._last_snapshot: dict[str, dict] = {}
        self._widgets_should_be_visible = True
        self._syncing_widgets = False
        self.widgets: dict[str, DesktopWidget] = {}

        self.icon: QIcon = create_app_icon()
        self.app.setWindowIcon(self.icon)
        self.settings = SettingsWindow(self.config)
        self.settings.setWindowIcon(self.icon)
        self.clipboard_tracker = ClipboardHistoryTracker(self)
        self.clipboard_tracker.set_enabled("clipboard_history" in self.config.selected_metrics)
        self.clipboard_dialog = ClipboardHistoryDialog(self.clipboard_tracker)
        self.clipboard_dialog.setWindowIcon(self.icon)
        self.worker = MetricsWorker(
            self.config.selected_metrics,
            self.config.refresh_ms,
            rate_unit=self.config.rate_unit,
            network_interface=self.config.network_interface,
            parent=self,
        )
        self.worker.snapshot_ready.connect(self._handle_snapshot)
        self.worker.collection_error.connect(self._handle_collection_error)

        self._build_tray()
        self._connect_signals()
        self._reconcile_startup_setting()
        self._sync_widgets()
        self.worker.start()
        self.show_widgets(activate=False)
        self.tray.show()
        if self._first_run:
            QTimer.singleShot(350, self.open_settings)

    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip(f"{APP_DISPLAY_NAME} v{APP_VERSION}")
        self.tray_menu = QMenu()
        menu = self.tray_menu
        self.settings_action = QAction("Settings...", menu)
        self.toggle_widget_action = QAction("Hide widget", menu)
        self.lock_action = QAction("Lock position and size", menu)
        self.lock_action.setCheckable(True)
        self.lock_action.setChecked(self.config.locked)
        self.topmost_action = QAction("Always on top", menu)
        self.topmost_action.setCheckable(True)
        self.topmost_action.setChecked(self.config.always_on_top)
        self.click_through_action = QAction("Click through", menu)
        self.click_through_action.setCheckable(True)
        self.click_through_action.setChecked(self.config.click_through)
        self.clipboard_action = QAction("Clipboard history...", menu)
        self.clear_clipboard_action = QAction("Clear clipboard history", menu)
        self.reset_action = QAction("Reset widget position", menu)
        self.startup_action = QAction("Start with Windows", menu)
        self.startup_action.setCheckable(True)
        self.startup_action.setChecked(self.config.start_with_windows)
        self.startup_action.setEnabled(os.name == "nt")
        self.quit_action = QAction("Quit", menu)
        menu.addAction(self.settings_action)
        menu.addAction(self.toggle_widget_action)
        menu.addSeparator()
        menu.addAction(self.lock_action)
        menu.addAction(self.topmost_action)
        menu.addAction(self.click_through_action)
        menu.addAction(self.reset_action)
        menu.addSeparator()
        menu.addAction(self.clipboard_action)
        menu.addAction(self.clear_clipboard_action)
        menu.addSeparator()
        menu.addAction(self.startup_action)
        menu.addSeparator()
        menu.addAction(self.quit_action)
        self.tray.setContextMenu(menu)

    def _connect_signals(self) -> None:
        self.settings_action.triggered.connect(self.open_settings)
        self.toggle_widget_action.triggered.connect(self.toggle_widgets)
        self.lock_action.toggled.connect(self.set_locked)
        self.topmost_action.toggled.connect(self.set_always_on_top)
        self.click_through_action.toggled.connect(self.set_click_through)
        self.reset_action.triggered.connect(self.reset_widget_positions)
        self.clipboard_action.triggered.connect(self.open_clipboard_history)
        self.clear_clipboard_action.triggered.connect(self.clipboard_tracker.clear)
        self.clipboard_tracker.history_changed.connect(self._clipboard_history_changed)
        self.startup_action.toggled.connect(self.set_startup)
        self.quit_action.triggered.connect(self.shutdown)
        self.tray.activated.connect(self._tray_activated)
        self.settings.config_applied.connect(self.apply_config)
        self.app.aboutToQuit.connect(self._cleanup)

    def _connect_widget(self, key: str, widget: DesktopWidget) -> None:
        widget.settings_requested.connect(self.open_settings)
        widget.quit_requested.connect(self.shutdown)
        widget.reset_position_requested.connect(
            lambda widget_key=key: self.reset_widget_position(widget_key)
        )
        widget.lock_toggled.connect(self.set_locked)
        widget.always_on_top_toggled.connect(self.set_always_on_top)
        widget.click_through_toggled.connect(self.set_click_through)
        widget.metric_activated.connect(self._metric_activated)
        widget.geometry_changed.connect(
            lambda geometry, widget_key=key: self._save_geometry(widget_key, geometry)
        )
        widget.visibility_changed.connect(
            lambda _visible, widget_key=key: self._widget_visibility_changed(widget_key)
        )

    def _tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings()
        elif reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_widgets()

    def _expanded_metric_ids(self) -> list[str]:
        return expand_metric_ids(self.config.selected_metrics, self._last_snapshot)

    def _desired_layout(self) -> dict[str, list[str]]:
        expanded = self._expanded_metric_ids()
        if not self.config.separate_widgets:
            return {"combined": expanded}
        return {metric_id: [metric_id] for metric_id in expanded}

    @staticmethod
    def _primary_available_geometry() -> tuple[int, int, int, int]:
        screen = QApplication.primaryScreen()
        if screen is None:
            return 0, 0, 1920, 1080
        area = screen.availableGeometry()
        return area.left(), area.top(), area.width(), area.height()

    def _default_combined_geometry(self) -> list[int]:
        left, top, available_width, available_height = self._primary_available_geometry()
        width = min(620, max(420, available_width - 80))
        height = min(480, max(300, available_height - 80))
        return [left + 40, top + 40, width, height]

    def _default_separate_geometry(self, index: int) -> list[int]:
        left, top, available_width, available_height = self._primary_available_geometry()
        width = min(390, max(320, available_width - 40))
        height = min(255, max(210, available_height - 40))
        gap = 14
        columns = max(1, (available_width - 30) // (width + gap))
        rows = max(1, (available_height - 30) // (height + gap))
        slot_count = max(1, columns * rows)
        slot = index % slot_count
        column = slot % columns
        row = slot // columns
        cycle = index // slot_count
        offset = min(60, cycle * 18)
        x = left + 15 + column * (width + gap) + offset
        y = top + 15 + row * (height + gap) + offset
        return [x, y, width, height]

    def _geometry_for_widget(self, key: str, index: int) -> list[int]:
        if key == "combined":
            return list(self.config.geometry)
        return list(self.config.separate_geometries.get(key, self._default_separate_geometry(index)))

    def _header_for_widget(self, key: str) -> str:
        if key == "combined":
            return "Desktop Metrics"
        return metric_display_label(key, self._last_snapshot)

    def _sync_widgets(self, *, config_changed: bool = False) -> None:
        """Create/remove windows so they match combined or separate layout mode."""
        desired = self._desired_layout()
        desired_keys = set(desired)
        visibility_intent = self._widgets_should_be_visible
        self._syncing_widgets = True
        try:
            for key in list(self.widgets):
                if key in desired_keys:
                    continue
                widget = self.widgets.pop(key)
                widget.hide_widget()
                widget.deleteLater()

            for index, (key, metric_ids) in enumerate(desired.items()):
                header = self._header_for_widget(key)
                widget = self.widgets.get(key)
                if widget is None:
                    widget = DesktopWidget(
                        self.config,
                        metric_ids=metric_ids,
                        widget_key=key,
                        header_title=header,
                        initial_geometry=self._geometry_for_widget(key, index),
                    )
                    widget.setWindowIcon(self.icon)
                    self._connect_widget(key, widget)
                    self.widgets[key] = widget
                    if visibility_intent:
                        widget.show_widget(activate=False)
                else:
                    if config_changed:
                        widget.apply_config(
                            self.config,
                            metric_ids=metric_ids,
                            header_title=header,
                            metadata=self._last_snapshot,
                        )
                    else:
                        widget.set_metrics(metric_ids, self._last_snapshot)
                        widget.set_header_title(header)
        finally:
            self._syncing_widgets = False
            self._widgets_should_be_visible = visibility_intent

        self._update_tray_state()

    def _refresh_widgets_from_snapshot(self) -> None:
        if not self._last_snapshot:
            return
        for widget in tuple(self.widgets.values()):
            widget.update_snapshot(self._last_snapshot)

    def _handle_snapshot(self, snapshot: dict[str, dict]) -> None:
        if "clipboard_history" in self.config.selected_metrics:
            snapshot["clipboard_history"] = self.clipboard_tracker.reading()
        self._last_snapshot = snapshot
        # All-disk selections can expand into a different set of cards at run
        # time, so both combined and separate modes resync after every sample.
        self._sync_widgets()
        self._refresh_widgets_from_snapshot()

    def _clipboard_history_changed(self) -> None:
        if self._shutting_down or "clipboard_history" not in self.config.selected_metrics:
            return
        self._last_snapshot["clipboard_history"] = self.clipboard_tracker.reading()
        self._sync_widgets()
        self._refresh_widgets_from_snapshot()
        self._update_tray_state()

    def _metric_activated(self, metric_id: str) -> None:
        if metric_id == "clipboard_history":
            self.open_clipboard_history()

    def open_clipboard_history(self) -> None:
        if "clipboard_history" not in self.config.selected_metrics:
            QMessageBox.information(
                self.settings,
                "Clipboard history",
                "Enable Clipboard history (session) in Settings first.",
            )
            return
        self.clipboard_dialog.show_history()

    def _handle_collection_error(self, message: str) -> None:
        for widget in tuple(self.widgets.values()):
            widget.set_collection_error(message)

    def open_settings(self) -> None:
        self.settings.show_with_config(self.config)

    def any_widget_visible(self) -> bool:
        return any(widget.isVisible() for widget in self.widgets.values())

    def show_widgets(self, *, activate: bool = True) -> None:
        self._widgets_should_be_visible = True
        self._sync_widgets()
        self._refresh_widgets_from_snapshot()
        first = True
        for widget in self.widgets.values():
            widget.show_widget(activate=activate and first)
            first = False
        self._update_tray_state()

    def hide_widgets(self) -> None:
        self._widgets_should_be_visible = False
        for widget in self.widgets.values():
            widget.hide_widget()
        self._update_tray_state()

    def toggle_widgets(self) -> None:
        if self.any_widget_visible():
            self.hide_widgets()
        else:
            self.show_widgets(activate=True)

    def _widget_visibility_changed(self, _widget_key: str) -> None:
        if self._syncing_widgets:
            return
        # Closing one separate card should not make it reappear on the next
        # refresh. The tray can still reveal every card again in one action.
        self._widgets_should_be_visible = self.any_widget_visible()
        self._update_tray_state()

    def _update_tray_state(self) -> None:
        visible = self.any_widget_visible()
        noun = "widgets" if self.config.separate_widgets else "widget"
        self.toggle_widget_action.setText(f"Hide {noun}" if visible else f"Show {noun}")
        self.reset_action.setText(
            "Reset widget positions" if self.config.separate_widgets else "Reset widget position"
        )
        self.lock_action.blockSignals(True)
        self.lock_action.setChecked(self.config.locked)
        self.lock_action.blockSignals(False)
        self.topmost_action.blockSignals(True)
        self.topmost_action.setChecked(self.config.always_on_top)
        self.topmost_action.blockSignals(False)
        self.click_through_action.blockSignals(True)
        self.click_through_action.setChecked(self.config.click_through)
        self.click_through_action.setEnabled(self.config.locked and self.config.always_on_top)
        self.click_through_action.blockSignals(False)
        clipboard_enabled = "clipboard_history" in self.config.selected_metrics
        self.clipboard_action.setEnabled(clipboard_enabled)
        self.clear_clipboard_action.setEnabled(clipboard_enabled and bool(self.clipboard_tracker.items))
        self.startup_action.blockSignals(True)
        self.startup_action.setChecked(self.config.start_with_windows)
        self.startup_action.blockSignals(False)

    def apply_config(self, config: AppConfig, *, show_widget: bool = True) -> None:
        new_config = config.normalized()
        if new_config.start_with_windows != self.config.start_with_windows:
            success, message = set_start_with_windows(new_config.start_with_windows, self.entry_script)
            if not success:
                QMessageBox.warning(self.settings, "Startup setting", message)
                new_config = replace(
                    new_config,
                    start_with_windows=self.config.start_with_windows,
                ).normalized()

        self.config = new_config
        self.clipboard_tracker.set_enabled("clipboard_history" in self.config.selected_metrics)
        if "clipboard_history" not in self.config.selected_metrics:
            self.clipboard_dialog.hide()
        self.store.save(self.config)
        self.worker.update_preferences(
            self.config.selected_metrics,
            self.config.refresh_ms,
            rate_unit=self.config.rate_unit,
            network_interface=self.config.network_interface,
        )
        self.settings.set_config(self.config)
        self._sync_widgets(config_changed=True)

        if show_widget:
            self.show_widgets(activate=False)
        else:
            self._update_tray_state()

    def set_locked(self, locked: bool) -> None:
        if bool(locked) == self.config.locked:
            self._update_tray_state()
            return
        self.apply_config(
            replace(
                self.config,
                locked=bool(locked),
                click_through=self.config.click_through if locked else False,
            ),
            show_widget=False,
        )

    def set_always_on_top(self, enabled: bool) -> None:
        if bool(enabled) == self.config.always_on_top:
            self._update_tray_state()
            return
        self.apply_config(
            replace(
                self.config,
                always_on_top=bool(enabled),
                click_through=self.config.click_through if enabled else False,
            ),
            show_widget=False,
        )

    def set_click_through(self, enabled: bool) -> None:
        requested = bool(enabled)
        if requested and not (self.config.locked and self.config.always_on_top):
            QMessageBox.information(
                self.settings,
                "Click-through",
                "Enable Always on top and Lock position and size before enabling click-through.",
            )
            self._update_tray_state()
            return
        if requested == self.config.click_through:
            self._update_tray_state()
            return
        self.apply_config(replace(self.config, click_through=requested), show_widget=False)

    def set_startup(self, enabled: bool) -> None:
        if bool(enabled) == self.config.start_with_windows:
            self._update_tray_state()
            return
        self.apply_config(replace(self.config, start_with_windows=bool(enabled)), show_widget=False)

    def reset_widget_position(self, key: str) -> None:
        """Reset the requested card; the tray action resets every card."""
        if key == "combined" or not self.config.separate_widgets:
            geometry = self._default_combined_geometry()
            self.config = replace(self.config, geometry=geometry).normalized()
            widget = self.widgets.get("combined")
            if widget is not None:
                widget.set_screen_geometry(geometry)
                widget.ensure_visible()
                widget.show_widget(activate=True)
        else:
            keys = list(self.widgets)
            index = keys.index(key) if key in keys else 0
            geometry = self._default_separate_geometry(index)
            geometries = dict(self.config.separate_geometries)
            geometries[key] = geometry
            self.config = replace(self.config, separate_geometries=geometries).normalized()
            widget = self.widgets.get(key)
            if widget is not None:
                widget.set_screen_geometry(geometry)
                widget.ensure_visible()
                widget.show_widget(activate=True)
        self.store.save(self.config)
        self._update_tray_state()

    def reset_widget_positions(self) -> None:
        self._sync_widgets()
        if not self.config.separate_widgets:
            self.reset_widget_position("combined")
            return

        geometries = dict(self.config.separate_geometries)
        for index, (key, widget) in enumerate(self.widgets.items()):
            geometry = self._default_separate_geometry(index)
            geometries[key] = geometry
            widget.set_screen_geometry(geometry)
            widget.ensure_visible()
        self.config = replace(self.config, separate_geometries=geometries).normalized()
        self.store.save(self.config)
        self.show_widgets(activate=True)

    def _save_geometry(self, key: str, geometry: list[int]) -> None:
        if len(geometry) != 4:
            return
        cleaned = [int(value) for value in geometry]
        if key == "combined":
            self.config = replace(self.config, geometry=cleaned).normalized()
        else:
            geometries = dict(self.config.separate_geometries)
            geometries[key] = cleaned
            self.config = replace(self.config, separate_geometries=geometries).normalized()
        self.store.save(self.config)

    def _reconcile_startup_setting(self) -> None:
        if os.name != "nt":
            return
        actual, _message = get_start_with_windows(self.entry_script)
        if actual is None or actual == self.config.start_with_windows:
            return
        # The registry is the source of truth at startup. This keeps the Settings
        # checkbox synchronized with an installer-created startup entry and also
        # notices when the user removes the entry through Windows Settings.
        self.config = replace(self.config, start_with_windows=actual).normalized()
        self.store.save(self.config)
        self.settings.set_config(self.config)

    def _cleanup(self) -> None:
        if self.worker.isRunning():
            self.worker.stop()
            self.worker.wait(4000)
        for widget in tuple(self.widgets.values()):
            widget.hide_widget()
        self.clipboard_dialog.hide()
        self.clipboard_tracker.set_enabled(False)
        self.tray.hide()

    def shutdown(self) -> None:
        if self._shutting_down:
            return
        self._shutting_down = True
        self.hide_widgets()
        self.settings.hide()
        self._cleanup()
        self.shutdown_complete.emit()
        self.app.quit()
