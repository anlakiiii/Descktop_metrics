from __future__ import annotations

from collections import deque
from typing import Any

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QResizeEvent,
)
from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QProgressBar, QSizePolicy, QVBoxLayout, QWidget

from .constants import METRIC_SPEC_BY_ID


def _fallback_metadata(metric_id: str) -> tuple[str, str]:
    spec = METRIC_SPEC_BY_ID.get(metric_id)
    if spec is not None:
        return spec.label, spec.description
    if "|" in metric_id:
        _prefix, suffix = metric_id.split("|", 1)
        readable = suffix or "Metric"
    else:
        readable = metric_id.replace("_", " ").strip() or "Metric"
    return readable, "Live system metric."


def metric_card_height(scale: float) -> int:
    """Return one deterministic height for every card at a given UI scale."""
    normalized = max(0.75, min(1.5, float(scale)))
    return max(120, int(round(148 * normalized)))


class ElidedLabel(QLabel):
    """Single-line label that never makes a metric card wider.

    QLabel's normal size hint is based on the full string. A long hardware
    diagnostic can therefore force an entire grid column (and sometimes the
    containing window) to become wider. This label keeps the full text for its
    tooltip, but reports a compact horizontal size hint and draws an ellipsis
    when the available width is smaller than the string.
    """

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        *,
        elide_mode: Qt.TextElideMode = Qt.TextElideMode.ElideRight,
    ) -> None:
        super().__init__(parent)
        self._full_text = ""
        self._elide_mode = elide_mode
        self.setMinimumWidth(0)
        self.setWordWrap(False)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setText(text)

    @property
    def full_text(self) -> str:
        return self._full_text

    def setText(self, text: str) -> None:  # noqa: N802 - Qt API name
        self._full_text = str(text)
        self.setToolTip(self._full_text)
        self._refresh_elision()

    def _refresh_elision(self) -> None:
        width = max(0, self.contentsRect().width())
        if width <= 0:
            displayed = self._full_text
        else:
            displayed = QFontMetrics(self.font()).elidedText(
                self._full_text,
                self._elide_mode,
                width,
            )
        super().setText(displayed)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        metrics = QFontMetrics(self.font())
        return QSize(max(80, metrics.horizontalAdvance("MMMMMMMMMM")), metrics.height() + 2)

    def minimumSizeHint(self) -> QSize:  # noqa: N802 - Qt API name
        return QSize(0, QFontMetrics(self.font()).height() + 2)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._refresh_elision()

    def changeEvent(self, event: QEvent) -> None:
        super().changeEvent(event)
        if event.type() in {
            QEvent.Type.FontChange,
            QEvent.Type.StyleChange,
            QEvent.Type.ApplicationFontChange,
        }:
            self._refresh_elision()


class SparklineWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._history: deque[float] = deque(maxlen=48)
        self._available = True
        self.setMinimumHeight(28)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def sizeHint(self) -> QSize:
        return QSize(180, 34)

    def set_available(self, available: bool) -> None:
        self._available = available
        self.update()

    def add_value(self, value: float | int | None) -> None:
        if value is None:
            return
        try:
            self._history.append(float(value))
        except (TypeError, ValueError):
            return
        self.update()

    def paintEvent(self, _event: Any) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bounds = QRectF(self.rect()).adjusted(1.0, 2.0, -1.0, -2.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 255, 255, 10))
        painter.drawRoundedRect(bounds, 6.0, 6.0)

        if not self._available or len(self._history) < 2:
            painter.end()
            return

        values = list(self._history)
        low = min(values)
        high = max(values)
        if high - low < 0.0001:
            low -= 1.0
            high += 1.0

        usable = bounds.adjusted(4.0, 4.0, -4.0, -4.0)
        step = usable.width() / max(1, len(values) - 1)
        path = QPainterPath()
        points: list[QPointF] = []
        for index, value in enumerate(values):
            normalized = (value - low) / (high - low)
            point = QPointF(usable.left() + index * step, usable.bottom() - normalized * usable.height())
            points.append(point)
            if index == 0:
                path.moveTo(point)
            else:
                path.lineTo(point)

        fill_path = QPainterPath(path)
        fill_path.lineTo(points[-1].x(), usable.bottom())
        fill_path.lineTo(points[0].x(), usable.bottom())
        fill_path.closeSubpath()
        gradient = QLinearGradient(0.0, usable.top(), 0.0, usable.bottom())
        gradient.setColorAt(0.0, QColor(96, 165, 250, 82))
        gradient.setColorAt(1.0, QColor(96, 165, 250, 3))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(fill_path)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(
            QPen(
                QColor("#60A5FA"),
                2.0,
                Qt.PenStyle.SolidLine,
                Qt.PenCapStyle.RoundCap,
                Qt.PenJoinStyle.RoundJoin,
            )
        )
        painter.drawPath(path)
        painter.end()


class MetricCard(QFrame):
    activated = Signal(str)

    def __init__(
        self,
        metric_id: str,
        scale: float = 1.0,
        parent: QWidget | None = None,
        *,
        label: str | None = None,
        description: str | None = None,
    ) -> None:
        super().__init__(parent)
        self.metric_id = metric_id
        self._scale = scale
        self.setObjectName("metricCard")
        # Ignoring the horizontal size hint makes every grid column share the
        # available width equally, even when one metric contains a long value.
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setMinimumWidth(0)
        self.setToolTip("Double-click for metric actions when available")

        default_label, default_description = _fallback_metadata(metric_id)
        self._display_label = label or default_label
        self._description = description or default_description

        self.label = ElidedLabel(self._display_label.upper())
        self.label.setObjectName("metricLabel")
        self.value = ElidedLabel("Waiting...")
        self.value.setObjectName("metricValue")
        self.detail = ElidedLabel(self._description)
        self.detail.setObjectName("metricDetail")
        self.detail.setToolTip(self._description)
        self.progress = QProgressBar()
        self.progress.setObjectName("metricProgress")
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.hide()
        # Keep a fixed slot for the progress bar even when a metric has no
        # percentage. Otherwise cards with and without a bar get different
        # size hints and appear to have different heights.
        self.progress_slot = QWidget()
        self.progress_slot.setObjectName("metricProgressSlot")
        progress_layout = QVBoxLayout(self.progress_slot)
        progress_layout.setContentsMargins(0, 0, 0, 0)
        progress_layout.setSpacing(0)
        progress_layout.addWidget(self.progress)
        self.sparkline = SparklineWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 10)
        layout.setSpacing(5)
        layout.addWidget(self.label)
        layout.addWidget(self.value)
        layout.addWidget(self.detail)
        layout.addWidget(self.progress_slot)
        layout.addWidget(self.sparkline)
        self.set_scale(scale)

    @property
    def display_label(self) -> str:
        return self._display_label

    def set_metadata(self, label: str | None = None, description: str | None = None) -> None:
        if label:
            self._display_label = str(label)
            self.label.setText(self._display_label.upper())
        if description:
            self._description = str(description)
            if self.value.full_text in {"Waiting...", "Unavailable"}:
                self.detail.setText(self._description)
            self.detail.setToolTip(self._description)

    def set_scale(self, scale: float) -> None:
        self._scale = max(0.75, min(1.5, float(scale)))
        label_font = QFont(self.font())
        label_font.setPointSizeF(7.8 * self._scale)
        label_font.setWeight(QFont.Weight.DemiBold)
        self.label.setFont(label_font)

        value_font = QFont(self.font())
        value_font.setPointSizeF(16.5 * self._scale)
        value_font.setWeight(QFont.Weight.DemiBold)
        self.value.setFont(value_font)

        detail_font = QFont(self.font())
        detail_font.setPointSizeF(8.5 * self._scale)
        self.detail.setFont(detail_font)

        self.label.setFixedHeight(max(13, QFontMetrics(label_font).height() + 1))
        self.value.setFixedHeight(max(23, QFontMetrics(value_font).height() + 2))
        self.detail.setFixedHeight(max(15, QFontMetrics(detail_font).height() + 2))

        margins = int(14 * self._scale)
        self.layout().setContentsMargins(margins, int(11 * self._scale), margins, int(9 * self._scale))
        self.layout().setSpacing(max(3, int(5 * self._scale)))
        self.sparkline.setFixedHeight(max(22, int(30 * self._scale)))
        progress_height = max(3, int(4 * self._scale))
        self.progress.setFixedHeight(progress_height)
        self.progress_slot.setFixedHeight(progress_height)
        self.setFixedHeight(metric_card_height(self._scale))
        self.updateGeometry()

    def update_reading(self, reading: dict[str, Any]) -> None:
        self.set_metadata(reading.get("label"), reading.get("description"))
        available = bool(reading.get("available", True))
        value = str(reading.get("value", "Unavailable"))
        detail = str(reading.get("detail", ""))
        self.value.setText(value)
        self.detail.setText(detail)
        tooltip = str(reading.get("tooltip") or detail or self._description)
        self.detail.setToolTip(tooltip)
        self.setProperty("unavailable", not available)
        self.style().unpolish(self)
        self.style().polish(self)

        progress = reading.get("progress")
        if available and progress is not None:
            try:
                progress_value = max(0.0, min(100.0, float(progress)))
                self.progress.setValue(round(progress_value * 10.0))
                self.progress.show()
            except (TypeError, ValueError):
                self.progress.hide()
        else:
            self.progress.hide()

        self.sparkline.set_available(available)
        if available:
            self.sparkline.add_value(reading.get("history"))

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.activated.emit(self.metric_id)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)



class MetricGrid(QWidget):
    metric_activated = Signal(str)

    def __init__(self, metric_ids: list[str], scale: float = 1.0, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._metric_ids: list[str] = []
        self._cards: dict[str, MetricCard] = {}
        self._scale = scale
        self._columns = 1
        self._layout = QGridLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setHorizontalSpacing(10)
        self._layout.setVerticalSpacing(10)
        self._layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.set_metrics(metric_ids)

    @property
    def metric_ids(self) -> list[str]:
        return list(self._metric_ids)

    def card_label(self, metric_id: str) -> str | None:
        card = self._cards.get(metric_id)
        return card.display_label if card is not None else None

    def set_metrics(
        self,
        metric_ids: list[str],
        metadata: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        cleaned: list[str] = []
        seen: set[str] = set()
        for raw_metric_id in metric_ids:
            metric_id = str(raw_metric_id)
            if metric_id and metric_id not in seen:
                cleaned.append(metric_id)
                seen.add(metric_id)

        for metric_id in list(self._cards):
            if metric_id not in cleaned:
                card = self._cards.pop(metric_id)
                self._layout.removeWidget(card)
                card.deleteLater()
        for metric_id in cleaned:
            reading = (metadata or {}).get(metric_id, {})
            if metric_id not in self._cards:
                self._cards[metric_id] = MetricCard(
                    metric_id,
                    self._scale,
                    self,
                    label=reading.get("label"),
                    description=reading.get("description"),
                )
                self._cards[metric_id].activated.connect(self.metric_activated.emit)
            else:
                self._cards[metric_id].set_metadata(reading.get("label"), reading.get("description"))

        changed = cleaned != self._metric_ids
        self._metric_ids = cleaned
        if changed:
            self._relayout(force=True)

    def set_scale(self, scale: float) -> None:
        self._scale = max(0.75, min(1.5, float(scale)))
        for card in self._cards.values():
            card.set_scale(self._scale)
        spacing = max(7, int(10 * self._scale))
        self._layout.setHorizontalSpacing(spacing)
        self._layout.setVerticalSpacing(spacing)
        self._relayout(force=True)

    def update_snapshot(self, snapshot: dict[str, dict[str, Any]]) -> None:
        for metric_id, reading in snapshot.items():
            card = self._cards.get(metric_id)
            if card is not None:
                card.update_reading(reading)

    def _desired_columns(self) -> int:
        width = max(1, self.contentsRect().width())
        card_width = max(195, int(235 * self._scale))
        spacing = self._layout.horizontalSpacing()
        return max(1, min(4, (width + spacing) // (card_width + spacing)))

    def _relayout(self, force: bool = False) -> None:
        columns = self._desired_columns()
        if not force and columns == self._columns:
            return
        self._columns = columns
        while self._layout.count():
            self._layout.takeAt(0)
        for column in range(4):
            self._layout.setColumnStretch(column, 0)
        for index, metric_id in enumerate(self._metric_ids):
            row, column = divmod(index, columns)
            self._layout.addWidget(self._cards[metric_id], row, column)
        for column in range(columns):
            self._layout.setColumnStretch(column, 1)

        rows = (len(self._metric_ids) + columns - 1) // columns
        card_height = metric_card_height(self._scale)
        total_height = rows * card_height + max(0, rows - 1) * self._layout.verticalSpacing()
        self.setMinimumHeight(max(0, total_height))
        self.updateGeometry()

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        QTimer.singleShot(0, self._relayout)
