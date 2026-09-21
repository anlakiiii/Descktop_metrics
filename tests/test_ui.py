import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PySide6")
from PySide6.QtWidgets import QApplication, QSizePolicy

from desktop_metrics.config import AppConfig
from desktop_metrics.desktop_widget import DesktopWidget
from desktop_metrics.settings_window import SettingsWindow
from desktop_metrics.widgets import MetricCard, metric_card_height


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_widget_has_hide_button_and_supports_separate_metric() -> None:
    _app()
    config = AppConfig(selected_metrics=["cpu_usage"], separate_widgets=True).normalized()
    widget = DesktopWidget(
        config,
        metric_ids=["cpu_usage"],
        widget_key="cpu_usage",
        header_title="CPU usage",
        initial_geometry=[20, 30, 340, 220],
    )
    try:
        assert widget.hide_button.text() == "X"
        assert widget.metric_grid.metric_ids == ["cpu_usage"]
        assert widget.geometry().width() >= 300
        widget.hide_button.click()
        assert widget.isVisible() is False
    finally:
        widget.deleteLater()


def test_settings_exposes_layout_network_and_click_through_options() -> None:
    _app()
    dialog = SettingsWindow(AppConfig())
    try:
        assert dialog.separate_widgets_checkbox.text()
        assert dialog.always_on_top_checkbox.text()
        assert dialog.lock_checkbox.text()
        assert dialog.click_through_checkbox.text()
        assert dialog.click_through_checkbox.isEnabled() is False
        dialog.always_on_top_checkbox.setChecked(True)
        dialog.lock_checkbox.setChecked(True)
        assert dialog.click_through_checkbox.isEnabled() is True
        assert dialog.rate_unit_combo.findData("bits") >= 0
        assert dialog.rate_unit_combo.findData("bytes") >= 0
        assert dialog.network_interface_combo.findData("all") >= 0
    finally:
        dialog.deleteLater()


def test_application_icon_uses_bundled_multiresolution_asset() -> None:
    _app()
    from desktop_metrics.icon import create_app_icon

    icon = create_app_icon()
    assert icon.isNull() is False
    assert icon.availableSizes()


def test_widget_click_through_requires_topmost_and_lock() -> None:
    _app()
    config = AppConfig(
        selected_metrics=["cpu_usage"],
        always_on_top=True,
        locked=True,
        click_through=True,
    ).normalized()
    widget = DesktopWidget(config, metric_ids=["cpu_usage"])
    try:
        assert widget._click_through_effective() is True
        assert widget.hide_button.isEnabled() is False
    finally:
        widget.deleteLater()


def test_metric_cards_have_equal_fixed_height_and_compact_long_details() -> None:
    _app()
    compact = MetricCard("cpu_usage", 1.0)
    verbose = MetricCard("cpu_fan", 1.0)
    try:
        long_reason = (
            "No CPU fan RPM was exposed. On Windows, run LibreHardwareMonitor "
            "or OpenHardwareMonitor with its WMI sensors enabled."
        )
        compact.update_reading({"value": "24%", "detail": "Normal", "available": True})
        verbose.update_reading(
            {
                "value": "Unavailable",
                "detail": "Fan sensor not detected",
                "tooltip": long_reason,
                "available": False,
            }
        )

        expected_height = metric_card_height(1.0)
        assert compact.minimumHeight() == compact.maximumHeight() == expected_height
        assert verbose.minimumHeight() == verbose.maximumHeight() == expected_height
        assert verbose.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Ignored
        assert verbose.detail.full_text == "Fan sensor not detected"
        assert verbose.detail.toolTip() == long_reason
    finally:
        compact.deleteLater()
        verbose.deleteLater()
