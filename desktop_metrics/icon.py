from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def bundled_resource(relative_path: str) -> Path:
    """Resolve a source asset or an asset bundled by PyInstaller."""
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        return Path(bundle_root) / relative_path
    return Path(__file__).resolve().parents[1] / relative_path


def _draw_fallback_icon(size: int) -> QIcon:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    outer = QRectF(2, 2, size - 4, size - 4)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor("#111827"))
    painter.drawRoundedRect(outer, size * 0.20, size * 0.20)

    inset = size * 0.20
    path = QPainterPath(QPointF(inset, size * 0.65))
    path.lineTo(QPointF(size * 0.34, size * 0.46))
    path.lineTo(QPointF(size * 0.49, size * 0.57))
    path.lineTo(QPointF(size * 0.66, size * 0.30))
    path.lineTo(QPointF(size - inset, size * 0.41))
    pen = QPen(
        QColor("#60A5FA"),
        max(2.0, size * 0.075),
        Qt.PenStyle.SolidLine,
        Qt.PenCapStyle.RoundCap,
        Qt.PenJoinStyle.RoundJoin,
    )
    painter.setPen(pen)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def create_app_icon(size: int = 64) -> QIcon:
    """Return the exact multi-resolution icon used by tray, EXEs, and installer."""
    icon_path = bundled_resource("assets/desktop_metrics.ico")
    if icon_path.is_file():
        icon = QIcon(str(icon_path))
        if not icon.isNull():
            return icon
    return _draw_fallback_icon(size)
