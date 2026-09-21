from __future__ import annotations

import ctypes
import datetime as dt
import os
from typing import Any

from PySide6.QtCore import QPoint, QRect, Qt, QTimer, Signal
from PySide6.QtGui import (
    QCloseEvent,
    QContextMenuEvent,
    QHideEvent,
    QMouseEvent,
    QMoveEvent,
    QResizeEvent,
    QShowEvent,
)
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QScrollArea,
    QSizeGrip,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig
from .constants import APP_VERSION
from .widgets import MetricGrid


class DragHeader(QFrame):
    settings_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("dragHeader")
        self._locked = False
        self._drag_global: QPoint | None = None
        self._window_position: QPoint | None = None
        self.setCursor(Qt.CursorShape.OpenHandCursor)

    def set_locked(self, locked: bool) -> None:
        self._locked = bool(locked)
        self.setCursor(Qt.CursorShape.ArrowCursor if self._locked else Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton and not self._locked:
            self._drag_global = event.globalPosition().toPoint()
            window = self.window()
            self._window_position = window.screen_position() if hasattr(window, "screen_position") else window.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            not self._locked
            and self._drag_global is not None
            and self._window_position is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            delta = event.globalPosition().toPoint() - self._drag_global
            target = self._window_position + delta
            window = self.window()
            if hasattr(window, "move_to_screen"):
                window.move_to_screen(target.x(), target.y())
            else:
                window.move(target)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_global = None
            self._window_position = None
            self.setCursor(Qt.CursorShape.ArrowCursor if self._locked else Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.settings_requested.emit()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class DesktopWidget(QWidget):
    settings_requested = Signal()
    quit_requested = Signal()
    reset_position_requested = Signal()
    lock_toggled = Signal(bool)
    geometry_changed = Signal(list)
    visibility_changed = Signal(bool)
    metric_activated = Signal(str)
    always_on_top_toggled = Signal(bool)
    click_through_toggled = Signal(bool)

    def __init__(
        self,
        config: AppConfig,
        metric_ids: list[str] | None = None,
        parent: QWidget | None = None,
        *,
        widget_key: str = "combined",
        header_title: str | None = None,
        initial_geometry: list[int] | tuple[int, int, int, int] | None = None,
    ) -> None:
        super().__init__(parent)
        self._config = config.normalized()
        self.widget_key = str(widget_key or "combined")
        self._metric_ids = list(metric_ids or self._config.selected_metrics)
        self._header_title = str(header_title or "Desktop Metrics")
        self._locked = self._config.locked

        # A frameless tool window stays out of the taskbar. Topmost and
        # click-through flags are optional and can be changed at runtime.
        self.setWindowFlags(self._desired_window_flags())
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowTitle(f"{self._header_title} - Desktop Metrics v{APP_VERSION}")
        if self.widget_key == "combined":
            self.setMinimumSize(360, 220)
        else:
            self.setMinimumSize(300, 190)

        self._geometry_save_timer = QTimer(self)
        self._geometry_save_timer.setSingleShot(True)
        self._geometry_save_timer.setInterval(350)
        self._geometry_save_timer.timeout.connect(self._emit_geometry)

        self._build_ui()
        self._apply_stylesheet()
        geometry = list(initial_geometry) if initial_geometry is not None else list(self._config.geometry)
        self.apply_config(
            self._config,
            metric_ids=self._metric_ids,
            header_title=self._header_title,
            restore_geometry=True,
            initial_geometry=geometry,
        )

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self.panel = QFrame()
        self.panel.setObjectName("desktopPanel")
        outer.addWidget(self.panel)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(12, 10, 12, 9)
        panel_layout.setSpacing(8)

        self.header = DragHeader()
        self.header.settings_requested.connect(self.settings_requested.emit)
        header_layout = QHBoxLayout(self.header)
        header_layout.setContentsMargins(5, 1, 3, 2)
        header_layout.setSpacing(8)
        self.title_label = QLabel()
        self.title_label.setObjectName("widgetTitle")
        self.title_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.live_label = QLabel("LIVE")
        self.live_label.setObjectName("liveBadge")
        self.live_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.hide_button = QToolButton()
        self.hide_button.setObjectName("hideButton")
        self.hide_button.setText("X")
        self.hide_button.setToolTip("Hide this widget. Use the tray icon to show it again.")
        self.hide_button.setAccessibleName("Hide widget")
        self.hide_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hide_button.clicked.connect(self.hide_widget)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch(1)
        header_layout.addWidget(self.live_label)
        header_layout.addWidget(self.hide_button)
        panel_layout.addWidget(self.header)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("metricScroll")
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        # Always reserve the scrollbar gutter. If it appeared/disappeared as
        # cards changed their content, the viewport width changed by a few
        # pixels and the centered/equal-width grid visibly shifted sideways.
        self.metric_grid = MetricGrid(self._metric_ids, self._config.scale)
        self.metric_grid.metric_activated.connect(self.metric_activated.emit)
        self.scroll.setWidget(self.metric_grid)
        panel_layout.addWidget(self.scroll, 1)

        footer = QFrame()
        footer.setObjectName("widgetFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(5, 0, 0, 0)
        footer_layout.setSpacing(8)
        self.status_label = QLabel("Starting monitor...")
        self.status_label.setObjectName("statusLabel")
        self.size_grip = QSizeGrip(self)
        self.size_grip.setObjectName("sizeGrip")
        self.size_grip.setToolTip("Drag to resize")
        footer_layout.addWidget(self.status_label)
        footer_layout.addStretch(1)
        footer_layout.addWidget(
            self.size_grip,
            0,
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignBottom,
        )
        panel_layout.addWidget(footer)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QWidget { color: #E5E7EB; font-family: "Segoe UI"; }
            QFrame#desktopPanel {
                background-color: rgba(15, 23, 42, 232);
                border: 1px solid rgba(148, 163, 184, 48);
                border-radius: 15px;
            }
            QFrame#dragHeader { background: transparent; border: none; }
            QLabel#widgetTitle {
                color: #CBD5E1; font-size: 10px; font-weight: 700; letter-spacing: 1px;
            }
            QLabel#liveBadge {
                color: #86EFAC; background-color: rgba(34, 197, 94, 30);
                border: 1px solid rgba(34, 197, 94, 62); border-radius: 8px;
                padding: 2px 7px; font-size: 8px; font-weight: 700;
            }
            QToolButton#hideButton {
                color: #CBD5E1; background: transparent; border: none; border-radius: 8px;
                min-width: 24px; min-height: 22px; padding: 0px; font-size: 13px; font-weight: 700;
            }
            QToolButton#hideButton:hover { color: #FFFFFF; background-color: rgba(239, 68, 68, 95); }
            QToolButton#hideButton:pressed { background-color: rgba(220, 38, 38, 135); }
            QScrollArea#metricScroll, QScrollArea#metricScroll > QWidget > QWidget {
                background: transparent; border: none;
            }
            QFrame#metricCard {
                background-color: rgba(30, 41, 59, 205);
                border: 1px solid rgba(148, 163, 184, 32); border-radius: 11px;
            }
            QFrame#metricCard[unavailable="true"] {
                background-color: rgba(30, 41, 59, 145);
                border-color: rgba(148, 163, 184, 22);
            }
            QLabel#metricLabel { color: #94A3B8; letter-spacing: 0.7px; }
            QLabel#metricValue { color: #F8FAFC; }
            QFrame#metricCard[unavailable="true"] QLabel#metricValue { color: #94A3B8; }
            QLabel#metricDetail { color: #94A3B8; }
            QProgressBar#metricProgress {
                background-color: rgba(148, 163, 184, 25); border: none; border-radius: 2px;
            }
            QProgressBar#metricProgress::chunk { background-color: #60A5FA; border-radius: 2px; }
            QLabel#statusLabel { color: #64748B; font-size: 9px; }
            QScrollBar:vertical { width: 7px; background: transparent; margin: 2px 0; }
            QScrollBar::handle:vertical {
                background: rgba(148, 163, 184, 65); border-radius: 3px; min-height: 24px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
            QMenu {
                background-color: #111827; color: #E5E7EB;
                border: 1px solid #334155; padding: 5px;
            }
            QMenu::item { padding: 6px 24px 6px 10px; border-radius: 4px; }
            QMenu::item:selected { background-color: #1E3A5F; }
            """
        )

    def _click_through_effective(self) -> bool:
        return bool(self._config.always_on_top and self._locked and self._config.click_through)

    def _desired_window_flags(self) -> Qt.WindowType:
        flags = (
            Qt.WindowType.Tool
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.NoDropShadowWindowHint
        )
        if self._config.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self._click_through_effective():
            flags |= Qt.WindowType.WindowTransparentForInput
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        return flags

    def _apply_native_click_through(self, enabled: bool) -> None:
        """Apply a Windows extended-style fallback for transparent input."""
        if os.name != "nt":
            return
        try:
            hwnd = int(self.winId())
            user32 = ctypes.windll.user32
            get_style = user32.GetWindowLongPtrW if hasattr(user32, "GetWindowLongPtrW") else user32.GetWindowLongW
            set_style = user32.SetWindowLongPtrW if hasattr(user32, "SetWindowLongPtrW") else user32.SetWindowLongW
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t
            ex_style = int(get_style(hwnd, -20))
            ws_ex_transparent = 0x00000020
            updated = ex_style | ws_ex_transparent if enabled else ex_style & ~ws_ex_transparent
            if updated != ex_style:
                set_style(hwnd, -20, updated)
        except Exception:
            # Qt's WindowTransparentForInput remains the primary mechanism.
            pass

    def _apply_window_behavior_flags(self) -> None:
        desired = self._desired_window_flags()
        effective_click_through = self._click_through_effective()
        was_visible = self.isVisible()
        geometry = self.geometry()
        if self.windowFlags() != desired:
            self.setWindowFlags(desired)
            self.setGeometry(geometry)
            if was_visible:
                self.showNormal()
        self._apply_native_click_through(effective_click_through)
        self.hide_button.setEnabled(not effective_click_through)
        if effective_click_through:
            self.hide_button.setToolTip("Click-through is active. Use the tray icon to hide or unlock the widget.")
        else:
            self.hide_button.setToolTip("Hide this widget. Use the tray icon to show it again.")

    def _window_mode_text(self) -> str:
        if self._click_through_effective():
            return "topmost + click-through"
        if self._config.always_on_top:
            return "topmost"
        return "normal"

    def _refresh_header(self) -> None:
        if self.widget_key == "combined":
            text = f"DESKTOP METRICS  v{APP_VERSION}"
        else:
            text = f"{self._header_title.upper()}  -  v{APP_VERSION}"
        self.title_label.setText(text)
        self.setWindowTitle(f"{self._header_title} - Desktop Metrics v{APP_VERSION}")

    def apply_config(
        self,
        config: AppConfig,
        *,
        metric_ids: list[str] | None = None,
        header_title: str | None = None,
        metadata: dict[str, dict[str, Any]] | None = None,
        restore_geometry: bool = False,
        initial_geometry: list[int] | tuple[int, int, int, int] | None = None,
    ) -> None:
        self._config = config.normalized()
        if metric_ids is not None:
            self._metric_ids = list(metric_ids)
        if header_title:
            self._header_title = str(header_title)
        self.setWindowOpacity(self._config.opacity)
        self.metric_grid.set_metrics(self._metric_ids, metadata)
        self.metric_grid.set_scale(self._config.scale)
        self._locked = self._config.locked
        self.header.set_locked(self._locked)
        self.size_grip.setVisible(not self._locked)
        self._apply_window_behavior_flags()
        title_size = max(8, int(10 * self._config.scale))
        self.title_label.setStyleSheet(f"font-size: {title_size}px;")
        self._refresh_header()
        if restore_geometry:
            geometry = initial_geometry if initial_geometry is not None else self._config.geometry
            self.set_screen_geometry(geometry)
            QTimer.singleShot(0, self.ensure_visible)

    def set_metrics(
        self,
        metric_ids: list[str],
        metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._metric_ids = list(metric_ids)
        self.metric_grid.set_metrics(self._metric_ids, metadata)

    def set_header_title(self, header_title: str) -> None:
        normalized = str(header_title or "Desktop Metrics")
        if normalized != self._header_title:
            self._header_title = normalized
            self._refresh_header()

    def update_snapshot(self, snapshot: dict[str, dict[str, Any]]) -> None:
        self.metric_grid.update_snapshot(snapshot)
        if self.widget_key != "combined" and len(self._metric_ids) == 1:
            reading = snapshot.get(self._metric_ids[0], {})
            label = str(reading.get("label") or self.metric_grid.card_label(self._metric_ids[0]) or self._header_title)
            if label != self._header_title:
                self._header_title = label
                self._refresh_header()
        sampled_at = dt.datetime.now().astimezone().strftime("%H:%M:%S")
        mode = self._window_mode_text()
        self.status_label.setText(f"Updated {sampled_at} | {mode} | tray menu always available")
        if self._click_through_effective():
            tooltip = "Mouse input passes through this locked topmost widget. Use the tray menu to disable click-through."
        elif self._config.always_on_top:
            tooltip = "This widget stays above normal windows. Enable lock and click-through to use controls beneath it."
        else:
            tooltip = "Normal windows can cover this widget. Always-on-top is available in Settings or the tray menu."
        self.status_label.setToolTip(tooltip)

    def set_collection_error(self, message: str) -> None:
        self.status_label.setText(f"Monitor error: {message}")
        self.status_label.setToolTip(message)

    def screen_position(self) -> QPoint:
        geometry = self.geometry()
        return QPoint(geometry.x(), geometry.y())

    def move_to_screen(self, x: int, y: int) -> None:
        self.move(int(x), int(y))

    def set_screen_geometry(self, geometry: list[int] | tuple[int, int, int, int]) -> None:
        if len(geometry) != 4:
            return
        x, y, width, height = (int(value) for value in geometry)
        self.setGeometry(x, y, max(self.minimumWidth(), width), max(self.minimumHeight(), height))

    @staticmethod
    def _intersection_area(first: QRect, second: QRect) -> int:
        intersection = first.intersected(second)
        return max(0, intersection.width()) * max(0, intersection.height())

    @staticmethod
    def _distance_to_rect(point: QPoint, rect: QRect) -> int:
        if point.x() < rect.left():
            dx = rect.left() - point.x()
        elif point.x() > rect.right():
            dx = point.x() - rect.right()
        else:
            dx = 0
        if point.y() < rect.top():
            dy = rect.top() - point.y()
        elif point.y() > rect.bottom():
            dy = point.y() - rect.bottom()
        else:
            dy = 0
        return dx * dx + dy * dy

    def ensure_visible(self) -> None:
        screens = QApplication.screens()
        if not screens:
            return

        geometry = self.geometry()
        areas = [screen.availableGeometry() for screen in screens]
        intersections = [self._intersection_area(geometry, area) for area in areas]
        minimum_visible_area = min(geometry.width(), 100) * min(geometry.height(), 80)
        if max(intersections, default=0) >= minimum_visible_area:
            return

        center = geometry.center()
        target = min(areas, key=lambda area: self._distance_to_rect(center, area))
        width = min(geometry.width(), target.width())
        height = min(geometry.height(), target.height())
        max_x = target.right() - width + 1
        max_y = target.bottom() - height + 1
        x = min(max(geometry.x(), target.left()), max_x)
        y = min(max(geometry.y(), target.top()), max_y)
        self.setGeometry(x, y, width, height)

    def show_widget(self, *, activate: bool = True) -> None:
        self.showNormal()
        QTimer.singleShot(0, self.ensure_visible)
        if activate:
            QTimer.singleShot(0, self._activate_for_user)

    def _activate_for_user(self) -> None:
        if not self.isVisible():
            return
        self.raise_()
        if not self._click_through_effective():
            self.activateWindow()

    def hide_widget(self) -> None:
        self.hide()

    def _schedule_geometry_save(self) -> None:
        if self.isVisible():
            self._geometry_save_timer.start()

    def _emit_geometry(self) -> None:
        geometry = self.geometry()
        self.geometry_changed.emit([geometry.x(), geometry.y(), geometry.width(), geometry.height()])

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.visibility_changed.emit(True)
        QTimer.singleShot(0, self.ensure_visible)

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.visibility_changed.emit(False)

    def moveEvent(self, event: QMoveEvent) -> None:
        super().moveEvent(event)
        self._schedule_geometry_save()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._schedule_geometry_save()

    def closeEvent(self, event: QCloseEvent) -> None:
        self.hide_widget()
        event.ignore()

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = QMenu(self)
        settings_action = menu.addAction("Settings...")
        lock_action = menu.addAction("Lock position and size")
        lock_action.setCheckable(True)
        lock_action.setChecked(self._locked)
        topmost_action = menu.addAction("Always on top")
        topmost_action.setCheckable(True)
        topmost_action.setChecked(self._config.always_on_top)
        click_action = menu.addAction("Click through")
        click_action.setCheckable(True)
        click_action.setChecked(self._config.click_through)
        click_action.setEnabled(self._locked and self._config.always_on_top)
        menu.addSeparator()
        reset_action = menu.addAction("Reset position")
        hide_action = menu.addAction("Hide this widget")
        menu.addSeparator()
        quit_action = menu.addAction("Quit Desktop Metrics")
        selected = menu.exec(event.globalPos())
        if selected is settings_action:
            self.settings_requested.emit()
        elif selected is lock_action:
            self.lock_toggled.emit(lock_action.isChecked())
        elif selected is topmost_action:
            self.always_on_top_toggled.emit(topmost_action.isChecked())
        elif selected is click_action:
            self.click_through_toggled.emit(click_action.isChecked())
        elif selected is reset_action:
            self.reset_position_requested.emit()
        elif selected is hide_action:
            self.hide_widget()
        elif selected is quit_action:
            self.quit_requested.emit()
