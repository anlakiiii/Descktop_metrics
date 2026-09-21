from __future__ import annotations

import os
from dataclasses import replace

import psutil

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .constants import APP_VERSION, CATEGORY_ORDER, METRIC_SPECS, REFRESH_INTERVALS_MS
from .presets import PRESETS, matching_preset


class MetricSelector(QPushButton):
    """A large, explicitly drawn checkable row.

    Native checkbox indicators can disappear with some portable Qt/theme
    combinations. This control always shows an ASCII [ ] or [x] marker and a
    checked background, so the selection state stays visible on every theme.
    """

    def __init__(self, label: str, description: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._label = label
        self.setObjectName("metricSelector")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(description)
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.toggled.connect(self.sync_text)
        self.sync_text(False)

    def sync_text(self, checked: bool | None = None) -> None:
        state = self.isChecked() if checked is None else bool(checked)
        self.setText(f"[x]  {self._label}" if state else f"[ ]  {self._label}")
        self.setAccessibleName(self._label)
        self.setAccessibleDescription("Selected" if state else "Not selected")


class SettingsWindow(QDialog):
    config_applied = Signal(object)

    def __init__(self, config: AppConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._config = config.normalized()
        self._selectors: dict[str, MetricSelector] = {}
        self._selection_sync = False
        self.setWindowTitle(f"Desktop Metrics Settings - v{APP_VERSION}")
        self.setMinimumSize(720, 650)
        self.resize(820, 790)
        self.setModal(False)
        self._build_ui()
        self._apply_stylesheet()
        self.set_config(self._config)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 16)
        root.setSpacing(12)

        title = QLabel(f"Desktop Metrics v{APP_VERSION}")
        title.setObjectName("settingsTitle")
        subtitle = QLabel(
            "Choose the cards shown on the desktop. Presets update the selections immediately, and storage cards can expand per disk."
        )
        subtitle.setObjectName("settingsSubtitle")
        subtitle.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(subtitle)

        self.tabs = QTabWidget()
        self.tabs.setObjectName("settingsTabs")
        self.tabs.addTab(self._build_metrics_tab(), "Metrics")
        self.tabs.addTab(self._build_appearance_tab(), "Appearance and behavior")
        self.tabs.setCurrentIndex(0)
        root.addWidget(self.tabs, 1)

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Apply
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.RestoreDefaults
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Save).setText("Save and close")
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).setText("Reset defaults")
        self.buttons.button(QDialogButtonBox.StandardButton.Save).clicked.connect(
            lambda: self._apply(close_after=True)
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(
            lambda: self._apply(close_after=False)
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Cancel).clicked.connect(self.reject)
        self.buttons.button(QDialogButtonBox.StandardButton.RestoreDefaults).clicked.connect(
            self._reset_defaults
        )
        root.addWidget(self.buttons)

    def _build_metrics_tab(self) -> QWidget:
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(2, 12, 2, 2)
        tab_layout.setSpacing(10)

        preset_frame = QFrame()
        preset_frame.setObjectName("presetFrame")
        preset_layout = QGridLayout(preset_frame)
        preset_layout.setContentsMargins(12, 10, 12, 10)
        preset_layout.setHorizontalSpacing(10)
        preset_layout.setVerticalSpacing(6)

        preset_layout.addWidget(QLabel("Preset:"), 0, 0)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(list(PRESETS))
        self.preset_combo.currentTextChanged.connect(self._preset_changed)
        preset_layout.addWidget(self.preset_combo, 0, 1)

        preset_help = QLabel(
            "Choose Minimal, Gaming, Workstation, or Everything and the rows below are selected immediately."
        )
        preset_help.setObjectName("presetHelp")
        preset_help.setWordWrap(True)
        preset_layout.addWidget(preset_help, 1, 0, 1, 2)
        tab_layout.addWidget(preset_frame)

        controls = QHBoxLayout()
        controls.setSpacing(8)
        selection_hint = QLabel("Click a [ ] row to select it.")
        selection_hint.setObjectName("selectionHint")
        controls.addWidget(selection_hint)
        controls.addStretch(1)
        select_all = QPushButton("Select all")
        select_all.clicked.connect(lambda: self._set_selected_metrics(spec.metric_id for spec in METRIC_SPECS))
        clear_all = QPushButton("Clear all")
        clear_all.clicked.connect(lambda: self._set_selected_metrics(()))
        controls.addWidget(select_all)
        controls.addWidget(clear_all)
        tab_layout.addLayout(controls)

        scroll = QScrollArea()
        scroll.setObjectName("metricsScroll")
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMinimumHeight(390)

        content = QWidget()
        content.setObjectName("metricsContent")
        content.setMinimumWidth(600)
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content_layout = QVBoxLayout(content)
        content_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        content_layout.setContentsMargins(0, 0, 8, 0)
        content_layout.setSpacing(10)

        by_category = {category: [] for category in CATEGORY_ORDER}
        for spec in METRIC_SPECS:
            by_category.setdefault(spec.category, []).append(spec)

        for category in CATEGORY_ORDER:
            specs = by_category.get(category) or []
            if not specs:
                continue
            group = QGroupBox(category)
            group.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            grid = QGridLayout(group)
            grid.setContentsMargins(12, 16, 12, 12)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(8)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            for index, spec in enumerate(specs):
                selector = MetricSelector(spec.label, spec.description)
                selector.toggled.connect(self._metric_selection_changed)
                self._selectors[spec.metric_id] = selector
                row, column = divmod(index, 2)
                grid.addWidget(selector, row, column)
            content_layout.addWidget(group)

        content_layout.addStretch(1)
        scroll.setWidget(content)
        tab_layout.addWidget(scroll, 1)

        self.selection_summary = QLabel()
        self.selection_summary.setObjectName("selectionSummary")
        tab_layout.addWidget(self.selection_summary)
        return tab

    def _build_appearance_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 16, 4, 4)
        layout.setSpacing(14)

        appearance_group = QGroupBox("Appearance")
        appearance_form = QFormLayout(appearance_group)
        appearance_form.setContentsMargins(14, 18, 14, 14)
        appearance_form.setSpacing(13)

        opacity_row = QWidget()
        opacity_layout = QHBoxLayout(opacity_row)
        opacity_layout.setContentsMargins(0, 0, 0, 0)
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(45, 100)
        self.opacity_value = QLabel()
        self.opacity_value.setMinimumWidth(46)
        self.opacity_slider.valueChanged.connect(
            lambda value: self.opacity_value.setText(f"{value}%")
        )
        opacity_layout.addWidget(self.opacity_slider, 1)
        opacity_layout.addWidget(self.opacity_value)
        appearance_form.addRow("Window opacity", opacity_row)

        scale_row = QWidget()
        scale_layout = QHBoxLayout(scale_row)
        scale_layout.setContentsMargins(0, 0, 0, 0)
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(75, 150)
        self.scale_slider.setSingleStep(5)
        self.scale_slider.setToolTip(
            "Extra application scaling applied after Windows per-monitor display scaling. "
            "Use 75-90% for a more compact widget on a Full HD screen."
        )
        self.scale_value = QLabel()
        self.scale_value.setMinimumWidth(46)
        self.scale_slider.valueChanged.connect(lambda value: self.scale_value.setText(f"{value}%"))
        scale_layout.addWidget(self.scale_slider, 1)
        scale_layout.addWidget(self.scale_value)
        appearance_form.addRow("Interface scale", scale_row)
        layout.addWidget(appearance_group)

        behavior_group = QGroupBox("Behavior")
        behavior_form = QFormLayout(behavior_group)
        behavior_form.setContentsMargins(14, 18, 14, 14)
        behavior_form.setSpacing(13)
        self.refresh_combo = QComboBox()
        for interval in REFRESH_INTERVALS_MS:
            self.refresh_combo.addItem(f"{interval / 1000.0:g} seconds", interval)
        behavior_form.addRow("Refresh every", self.refresh_combo)
        self.separate_widgets_checkbox = QCheckBox("Show every metric in its own movable and resizable widget")
        self.separate_widgets_checkbox.setToolTip(
            "Unchecked: all selected metrics share one window. Checked: every metric gets a separate window and saved position."
        )
        behavior_form.addRow("Widget layout", self.separate_widgets_checkbox)
        self.always_on_top_checkbox = QCheckBox("Keep the widget(s) above normal application windows")
        self.always_on_top_checkbox.setToolTip(
            "Optional. Leave this unchecked for normal desktop-window behavior."
        )
        behavior_form.addRow("Always on top", self.always_on_top_checkbox)
        self.lock_checkbox = QCheckBox("Prevent moving and resizing the widget(s)")
        behavior_form.addRow("Lock widgets", self.lock_checkbox)
        self.click_through_checkbox = QCheckBox(
            "Pass mouse clicks through the widget to windows underneath"
        )
        self.click_through_checkbox.setToolTip(
            "For safety, click-through is available only while Always on top and Lock widgets are both enabled. "
            "The tray menu remains usable."
        )
        behavior_form.addRow("Click-through", self.click_through_checkbox)
        self.always_on_top_checkbox.toggled.connect(self._update_click_through_availability)
        self.lock_checkbox.toggled.connect(self._update_click_through_availability)
        self.startup_checkbox = QCheckBox("Launch Desktop Metrics when I sign in")
        self.startup_checkbox.setEnabled(os.name == "nt")
        if os.name != "nt":
            self.startup_checkbox.setToolTip("This option is available on Windows only")
        behavior_form.addRow("Startup", self.startup_checkbox)
        layout.addWidget(behavior_group)

        network_group = QGroupBox("Network display")
        network_form = QFormLayout(network_group)
        network_form.setContentsMargins(14, 18, 14, 14)
        network_form.setSpacing(13)
        self.rate_unit_combo = QComboBox()
        self.rate_unit_combo.addItem("Mbps / Kbps (Task Manager style)", "bits")
        self.rate_unit_combo.addItem("MB/s / KB/s (byte units)", "bytes")
        network_form.addRow("Speed units", self.rate_unit_combo)
        self.network_interface_combo = QComboBox()
        self._populate_network_interfaces("auto")
        network_form.addRow("Network adapter", self.network_interface_combo)
        layout.addWidget(network_group)

        desktop_note = QLabel(
            "The X button hides a widget without stopping monitoring. The app keeps refreshing in the tray. "
            "Click-through is intentionally restricted to locked, always-on-top widgets; use the tray menu to turn it off. "
            "Separate mode saves a different position and size for every metric. Qt follows the Windows scale of each monitor automatically; "
            "Interface scale is an additional personal size adjustment."
        )
        desktop_note.setObjectName("desktopNote")
        desktop_note.setWordWrap(True)
        layout.addWidget(desktop_note)
        layout.addStretch(1)
        return tab

    def _update_click_through_availability(self, _checked: bool | None = None) -> None:
        enabled = self.always_on_top_checkbox.isChecked() and self.lock_checkbox.isChecked()
        self.click_through_checkbox.setEnabled(enabled)
        if not enabled and self.click_through_checkbox.isChecked():
            self.click_through_checkbox.setChecked(False)

    def _populate_network_interfaces(self, selected: str) -> None:
        current = selected or "auto"
        self.network_interface_combo.blockSignals(True)
        try:
            self.network_interface_combo.clear()
            self.network_interface_combo.addItem("Automatic (most active physical adapter)", "auto")
            self.network_interface_combo.addItem("All adapters combined", "all")
            try:
                stats = psutil.net_if_stats()
            except Exception:
                stats = {}
            for name in sorted(stats, key=str.casefold):
                status = stats[name]
                state = "up" if status.isup else "down"
                speed = f", {status.speed} Mbps link" if getattr(status, "speed", 0) else ""
                self.network_interface_combo.addItem(f"{name} ({state}{speed})", name)
            index = self.network_interface_combo.findData(current)
            if index < 0 and current.casefold() != "auto":
                self.network_interface_combo.addItem(f"{current} (currently unavailable)", current)
                index = self.network_interface_combo.count() - 1
            self.network_interface_combo.setCurrentIndex(max(0, index))
        finally:
            self.network_interface_combo.blockSignals(False)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #F8FAFC; color: #0F172A; font-family: "Segoe UI"; }
            QDialog QWidget { color: #0F172A; }
            QLabel { color: #0F172A; background: transparent; }
            QLabel#settingsTitle { font-size: 24px; font-weight: 700; color: #0F172A; }
            QLabel#settingsSubtitle, QLabel#desktopNote, QLabel#presetHelp, QLabel#selectionHint {
                color: #475569; font-size: 10pt;
            }
            QLabel#selectionSummary { color: #1E3A8A; font-weight: 600; padding: 3px 2px; }
            QLabel#desktopNote {
                background-color: #EFF6FF; border: 1px solid #BFDBFE;
                border-radius: 7px; padding: 12px;
            }
            QTabWidget::pane {
                border: 1px solid #CBD5E1; border-radius: 8px; background-color: #FFFFFF;
            }
            QTabWidget QWidget { color: #0F172A; }
            QTabBar::tab {
                padding: 9px 15px; margin-right: 3px; color: #475569; background: #F8FAFC;
            }
            QTabBar::tab:selected {
                color: #0F172A; font-weight: 600; border-bottom: 2px solid #2563EB;
            }
            QScrollArea#metricsScroll, QWidget#metricsContent {
                background-color: #FFFFFF; border: none;
            }
            QGroupBox {
                border: 1px solid #E2E8F0; border-radius: 8px; margin-top: 8px;
                padding-top: 8px; font-weight: 600; background-color: #FFFFFF;
            }
            QGroupBox::title {
                subcontrol-origin: margin; left: 10px; padding: 0 5px;
                color: #0F172A; background-color: #FFFFFF;
            }
            QFrame#presetFrame {
                background-color: #F1F5F9; border: 1px solid #E2E8F0; border-radius: 8px;
            }
            QCheckBox { spacing: 8px; padding: 4px; color: #0F172A; background: transparent; }
            QCheckBox:disabled { color: #94A3B8; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border: 1px solid #64748B;
                border-radius: 3px; background-color: #FFFFFF;
            }
            QCheckBox::indicator:checked { border-color: #1D4ED8; background-color: #2563EB; }
            QComboBox, QPushButton {
                min-height: 28px; border: 1px solid #CBD5E1; border-radius: 5px;
                background-color: #FFFFFF; color: #0F172A; padding: 2px 9px;
            }
            QComboBox QAbstractItemView {
                background-color: #FFFFFF; color: #0F172A; selection-background-color: #DBEAFE;
                selection-color: #0F172A; border: 1px solid #CBD5E1;
            }
            QPushButton:hover { background-color: #F1F5F9; color: #0F172A; }
            QPushButton:pressed { background-color: #E2E8F0; color: #0F172A; }
            QPushButton:disabled { background-color: #F1F5F9; color: #94A3B8; }
            QPushButton#metricSelector {
                min-height: 36px; text-align: left; padding: 3px 12px;
                border: 1px solid #CBD5E1; border-radius: 7px;
                background-color: #FFFFFF; color: #0F172A; font-weight: 500;
            }
            QPushButton#metricSelector:hover { border-color: #60A5FA; background-color: #F8FAFC; }
            QPushButton#metricSelector:checked {
                border: 2px solid #2563EB; background-color: #DBEAFE;
                color: #1E3A8A; font-weight: 700; padding-left: 11px;
            }
            QDialogButtonBox QPushButton { min-width: 98px; }
            QSlider::groove:horizontal {
                height: 5px; background: #E2E8F0; border-radius: 2px;
            }
            QSlider::sub-page:horizontal { background: #3B82F6; border-radius: 2px; }
            QSlider::handle:horizontal {
                width: 15px; margin: -5px 0; border-radius: 7px; background: #2563EB;
            }
            QScrollBar:vertical { width: 10px; background: #F8FAFC; margin: 2px; }
            QScrollBar::handle:vertical { background: #CBD5E1; border-radius: 4px; min-height: 30px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            """
        )

    def _selected_metric_ids(self) -> list[str]:
        return [
            spec.metric_id
            for spec in METRIC_SPECS
            if self._selectors[spec.metric_id].isChecked()
        ]

    def _set_selected_metrics(self, metric_ids) -> None:
        selected = set(metric_ids)
        self._selection_sync = True
        try:
            for metric_id, selector in self._selectors.items():
                selector.blockSignals(True)
                try:
                    selector.setChecked(metric_id in selected)
                    selector.sync_text()
                finally:
                    selector.blockSignals(False)
        finally:
            self._selection_sync = False
        self._update_selection_summary()
        self._select_matching_preset()

    def set_config(self, config: AppConfig) -> None:
        self._config = config.normalized()
        self._set_selected_metrics(self._config.selected_metrics)
        refresh_index = self.refresh_combo.findData(self._config.refresh_ms)
        self.refresh_combo.setCurrentIndex(max(0, refresh_index))
        self.opacity_slider.setValue(round(self._config.opacity * 100))
        self.scale_slider.setValue(round(self._config.scale * 100))
        self.separate_widgets_checkbox.setChecked(self._config.separate_widgets)
        self.always_on_top_checkbox.setChecked(self._config.always_on_top)
        self.lock_checkbox.setChecked(self._config.locked)
        self.click_through_checkbox.setChecked(self._config.click_through)
        self._update_click_through_availability()
        self.startup_checkbox.setChecked(self._config.start_with_windows)
        rate_index = self.rate_unit_combo.findData(self._config.rate_unit)
        self.rate_unit_combo.setCurrentIndex(max(0, rate_index))
        self._populate_network_interfaces(self._config.network_interface)

    def show_with_config(self, config: AppConfig) -> None:
        self.set_config(config)
        self.tabs.setCurrentIndex(0)
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _preset_changed(self, name: str) -> None:
        if self._selection_sync or name == "Custom":
            return
        metrics = PRESETS.get(name)
        if metrics is not None:
            self._set_selected_metrics(metrics)

    def _metric_selection_changed(self, _checked: bool) -> None:
        if self._selection_sync:
            return
        self._update_selection_summary()
        self._select_matching_preset()

    def _select_matching_preset(self) -> None:
        name = matching_preset(self._selected_metric_ids())
        self.preset_combo.blockSignals(True)
        try:
            self.preset_combo.setCurrentText(name)
        finally:
            self.preset_combo.blockSignals(False)

    def _update_selection_summary(self) -> None:
        count = len(self._selected_metric_ids())
        suffix = "metric" if count == 1 else "metrics"
        self.selection_summary.setText(f"{count} {suffix} selected")

    def _reset_defaults(self) -> None:
        defaults = AppConfig(geometry=list(self._config.geometry)).normalized()
        self.set_config(defaults)

    def _build_config(self) -> AppConfig | None:
        selected_metrics = self._selected_metric_ids()
        if not selected_metrics:
            QMessageBox.warning(
                self,
                "Select a metric",
                "Choose at least one metric row. Selected rows show [x] and a blue background.",
            )
            return None
        refresh_data = self.refresh_combo.currentData()
        refresh_ms = int(refresh_data) if refresh_data is not None else self._config.refresh_ms
        return replace(
            self._config,
            selected_metrics=selected_metrics,
            refresh_ms=refresh_ms,
            opacity=self.opacity_slider.value() / 100.0,
            scale=self.scale_slider.value() / 100.0,
            separate_widgets=self.separate_widgets_checkbox.isChecked(),
            locked=self.lock_checkbox.isChecked(),
            always_on_top=self.always_on_top_checkbox.isChecked(),
            click_through=self.click_through_checkbox.isChecked(),
            start_with_windows=self.startup_checkbox.isChecked(),
            rate_unit=str(self.rate_unit_combo.currentData() or "bits"),
            network_interface=str(self.network_interface_combo.currentData() or "auto"),
        ).normalized()

    def _apply(self, *, close_after: bool) -> None:
        config = self._build_config()
        if config is None:
            return
        self._config = config
        self.config_applied.emit(config)
        if close_after:
            self.accept()
