from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Any

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)


@dataclass(slots=True)
class ClipboardEntry:
    text: str
    captured_at: dt.datetime


class ClipboardHistoryTracker(QObject):
    """Private, in-memory text history for the current app session only."""

    history_changed = Signal()

    def __init__(self, parent: QObject | None = None, *, max_items: int = 20) -> None:
        super().__init__(parent)
        self._max_items = max(1, min(100, int(max_items)))
        self._items: list[ClipboardEntry] = []
        self._enabled = False
        self._clipboard = QGuiApplication.clipboard()
        self._clipboard.dataChanged.connect(self._clipboard_changed)

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def items(self) -> list[ClipboardEntry]:
        return list(self._items)

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if not enabled:
            self.clear()
        else:
            # Do not silently import clipboard content that existed before the
            # user enabled the metric. Capture starts with the next change.
            self.history_changed.emit()

    @staticmethod
    def _clean_text(text: str) -> str:
        normalized = str(text).replace("\r\n", "\n").replace("\r", "\n")
        # Keep the viewer responsive if an application copies a very large
        # document. The truncation is explicit in the stored text.
        limit = 32_000
        if len(normalized) > limit:
            normalized = normalized[:limit] + "\n\n[Truncated by Desktop Metrics]"
        return normalized

    def _clipboard_changed(self) -> None:
        if not self._enabled:
            return
        mime = self._clipboard.mimeData()
        if mime is None or not mime.hasText():
            return
        text = self._clean_text(mime.text())
        if not text:
            return
        self._items = [entry for entry in self._items if entry.text != text]
        self._items.insert(0, ClipboardEntry(text=text, captured_at=dt.datetime.now().astimezone()))
        del self._items[self._max_items :]
        self.history_changed.emit()

    def clear(self) -> None:
        if not self._items:
            self.history_changed.emit()
            return
        self._items.clear()
        self.history_changed.emit()

    def reading(self) -> dict[str, Any]:
        if not self._enabled:
            return {
                "value": "Disabled",
                "detail": "Enable Clipboard history (session) in Settings",
                "progress": None,
                "history": None,
                "available": False,
            }
        if not self._items:
            return {
                "value": "Empty",
                "detail": "Copy text to record it for this session | double-click to open",
                "progress": 0.0,
                "history": 0.0,
                "available": True,
            }
        latest = self._items[0].text.replace("\n", " ").replace("\t", " ")
        latest = " ".join(latest.split())
        preview = latest if len(latest) <= 34 else latest[:31] + "..."
        count = len(self._items)
        noun = "item" if count == 1 else "items"
        return {
            "value": preview or "Text item",
            "detail": f"{count} {noun} kept in memory | double-click to open",
            "progress": min(100.0, count / self._max_items * 100.0),
            "history": float(count),
            "available": True,
        }


class ClipboardHistoryDialog(QDialog):
    clear_requested = Signal()

    def __init__(self, tracker: ClipboardHistoryTracker, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tracker = tracker
        self.setWindowTitle("Desktop Metrics - Clipboard history (session)")
        self.setMinimumSize(680, 460)
        self.resize(780, 540)
        self.setModal(False)
        self._build_ui()
        self._apply_stylesheet()
        self._tracker.history_changed.connect(self.refresh)
        self.refresh()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 14)
        root.setSpacing(10)

        title = QLabel("Clipboard history (this Desktop Metrics session)")
        title.setObjectName("clipboardTitle")
        note = QLabel(
            "Only text copied after this metric was enabled is kept. Entries stay in memory, "
            "are never written to disk, and are cleared when Desktop Metrics exits or the metric is disabled."
        )
        note.setObjectName("clipboardNote")
        note.setWordWrap(True)
        root.addWidget(title)
        root.addWidget(note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._selection_changed)
        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("Select an entry to view its full text.")
        splitter.addWidget(self.list_widget)
        splitter.addWidget(self.preview)
        splitter.setSizes([280, 470])
        root.addWidget(splitter, 1)

        actions = QHBoxLayout()
        self.copy_button = QPushButton("Copy selected")
        self.copy_button.clicked.connect(self._copy_selected)
        self.clear_button = QPushButton("Clear history")
        self.clear_button.clicked.connect(self._clear_history)
        actions.addWidget(self.copy_button)
        actions.addWidget(self.clear_button)
        actions.addStretch(1)
        root.addLayout(actions)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.hide)
        root.addWidget(buttons)

    def _apply_stylesheet(self) -> None:
        self.setStyleSheet(
            """
            QDialog { background-color: #F8FAFC; color: #0F172A; font-family: "Segoe UI"; }
            QLabel#clipboardTitle { font-size: 20px; font-weight: 700; }
            QLabel#clipboardNote { color: #475569; }
            QListWidget, QPlainTextEdit {
                background: #FFFFFF; color: #0F172A; border: 1px solid #CBD5E1;
                border-radius: 7px; padding: 5px;
            }
            QListWidget::item { padding: 7px; border-radius: 4px; }
            QListWidget::item:selected { background: #DBEAFE; color: #1E3A8A; }
            QPushButton {
                min-height: 28px; border: 1px solid #CBD5E1; border-radius: 5px;
                background: #FFFFFF; color: #0F172A; padding: 3px 10px;
            }
            QPushButton:hover { background: #F1F5F9; }
            """
        )

    @staticmethod
    def _entry_label(entry: ClipboardEntry) -> str:
        preview = " ".join(entry.text.replace("\n", " ").replace("\t", " ").split())
        if len(preview) > 42:
            preview = preview[:39] + "..."
        return f"{entry.captured_at.strftime('%H:%M:%S')}  {preview or '[blank text]'}"

    def refresh(self) -> None:
        previous = self.list_widget.currentRow()
        self.list_widget.clear()
        for entry in self._tracker.items:
            item = QListWidgetItem(self._entry_label(entry))
            item.setToolTip(entry.text[:1000])
            self.list_widget.addItem(item)
        if self.list_widget.count():
            self.list_widget.setCurrentRow(min(max(0, previous), self.list_widget.count() - 1))
        else:
            self.preview.clear()
        self.copy_button.setEnabled(self.list_widget.count() > 0)
        self.clear_button.setEnabled(self.list_widget.count() > 0)

    def _selection_changed(self, row: int) -> None:
        items = self._tracker.items
        self.preview.setPlainText(items[row].text if 0 <= row < len(items) else "")

    def _copy_selected(self) -> None:
        row = self.list_widget.currentRow()
        items = self._tracker.items
        if 0 <= row < len(items):
            QGuiApplication.clipboard().setText(items[row].text)

    def _clear_history(self) -> None:
        if not self._tracker.items:
            return
        result = QMessageBox.question(
            self,
            "Clear clipboard history",
            "Clear every clipboard entry held by Desktop Metrics for this session?",
        )
        if result == QMessageBox.StandardButton.Yes:
            self._tracker.clear()
            self.clear_requested.emit()

    def show_history(self) -> None:
        self.refresh()
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.hide()
        event.ignore()
