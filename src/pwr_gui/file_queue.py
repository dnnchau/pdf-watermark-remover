"""Left-hand queue of PDFs waiting to be cleaned."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStyle,
    QToolButton,
    QVBoxLayout,
)

from pwr import AnalyzeReport

from . import theme
from .panel_header import PanelHeader


class Status(str, Enum):
    PENDING = "Chờ phân tích"
    ANALYZING = "Đang phân tích…"
    READY = "Sẵn sàng"
    WORKING = "Đang xóa…"
    DONE = "Đã xong"
    ERROR = "Lỗi"


STATUS_MARK = {
    Status.PENDING: "•",
    Status.ANALYZING: "◐",
    Status.READY: "✓",
    Status.WORKING: "◑",
    Status.DONE: "✔",
    Status.ERROR: "⚠",
}

STATUS_COLOR = {
    Status.PENDING: theme.TEXT_DIM,
    Status.ANALYZING: theme.ACCENT,
    Status.READY: theme.TEXT,
    Status.WORKING: theme.ACCENT,
    Status.DONE: theme.OK,
    Status.ERROR: theme.DANGER,
}


@dataclass
class FileEntry:
    path: str
    status: Status = Status.PENDING
    report: AnalyzeReport | None = None
    selected: set[str] = field(default_factory=set)
    message: str = ""
    output: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


class QueueRow(QFrame):
    """One queue row with a dedicated remove action."""

    selected = Signal(str)
    remove_requested = Signal(str)

    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path
        self.setObjectName("QueueRow")
        self.setCursor(Qt.PointingHandCursor)

        self.mark = QLabel()
        self.mark.setObjectName("QueueMark")
        self.mark.setFixedWidth(18)
        self.mark.setAlignment(Qt.AlignTop | Qt.AlignHCenter)

        self.name = QLabel()
        self.name.setObjectName("QueueName")
        self.name.setWordWrap(True)
        self.detail = QLabel()
        self.detail.setObjectName("QueueDetail")

        copy = QVBoxLayout()
        copy.setContentsMargins(0, 0, 0, 0)
        copy.setSpacing(3)
        copy.addWidget(self.name)
        copy.addWidget(self.detail)

        self.remove_btn = QToolButton()
        self.remove_btn.setObjectName("DeleteIcon")
        self.remove_btn.setIcon(self.style().standardIcon(QStyle.SP_TrashIcon))
        self.remove_btn.setIconSize(QSize(15, 15))
        self.remove_btn.setToolTip("Bỏ file này khỏi hàng đợi")
        self.remove_btn.setAccessibleName("Bỏ khỏi hàng đợi")
        self.remove_btn.setFixedSize(28, 28)
        self.remove_btn.clicked.connect(lambda: self.remove_requested.emit(self.path))

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 9, 8, 9)
        layout.setSpacing(7)
        layout.addWidget(self.mark)
        layout.addLayout(copy, 1)
        layout.addWidget(self.remove_btn, 0, Qt.AlignVCenter)

    def update_entry(self, entry: FileEntry) -> None:
        detail = entry.message or entry.status.value
        if entry.status is Status.READY and entry.report is not None:
            detail = f"{entry.report.doc.page_count} trang · chọn {len(entry.selected)} mục"
        self.mark.setText(STATUS_MARK[entry.status])
        self.mark.setStyleSheet(
            f"color: {STATUS_COLOR[entry.status]}; font-size: 14px; font-weight: 700;"
        )
        self.name.setText(entry.name)
        self.detail.setText(detail)
        self.setToolTip(f"{entry.path}\n{detail}")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.selected.emit(self.path)
        super().mousePressEvent(event)


class FileQueue(QFrame):
    current_changed = Signal(str)
    remove_requested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("WorkspacePanel")
        self.setMinimumWidth(220)
        self.entries: dict[str, FileEntry] = {}

        title = PanelHeader("HÀNG ĐỢI FILE")

        self.list = QListWidget()
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list.setWordWrap(True)
        self.list.currentItemChanged.connect(self._on_current_changed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(*theme.PANEL_CONTENT_MARGINS)
        layout.setSpacing(theme.PANEL_SPACING)
        layout.addWidget(title)
        layout.addWidget(self.list, 1)

    def add_paths(self, paths: list[str]) -> list[str]:
        added = []
        for path in paths:
            path = os.path.abspath(path)
            if not path.lower().endswith(".pdf") or path in self.entries:
                continue
            entry = FileEntry(path=path)
            self.entries[path] = entry
            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 70))
            item.setData(Qt.UserRole, path)
            self.list.addItem(item)
            self._paint(item, entry)
            added.append(path)
        if added and self.list.currentRow() < 0:
            self.list.setCurrentRow(0)
        return added

    def remove_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        self.remove_path(item.data(Qt.UserRole))

    def remove_path(self, path: str) -> None:
        self.entries.pop(path, None)
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.UserRole) == path:
                was_current = item is self.list.currentItem()
                self.list.takeItem(index)
                if was_current and self.list.count() and self.list.currentItem() is None:
                    self.list.setCurrentRow(min(index, self.list.count() - 1))
                return

    def entry(self, path: str) -> FileEntry | None:
        return self.entries.get(path)

    def current_entry(self) -> FileEntry | None:
        item = self.list.currentItem()
        return self.entries.get(item.data(Qt.UserRole)) if item else None

    def update_entry(self, path: str) -> None:
        entry = self.entries.get(path)
        if entry is None:
            return
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.UserRole) == path:
                self._paint(item, entry)
                return

    def pending_for_run(self) -> list[FileEntry]:
        return [
            self.entries[self.list.item(i).data(Qt.UserRole)]
            for i in range(self.list.count())
            if self.entries[self.list.item(i).data(Qt.UserRole)].status
            not in (Status.DONE, Status.WORKING, Status.ERROR)
        ]

    def _paint(self, item: QListWidgetItem, entry: FileEntry) -> None:
        row = self.list.itemWidget(item)
        if row is None:
            row = QueueRow(entry.path)
            row.selected.connect(self._select_path)
            row.remove_requested.connect(self.remove_requested.emit)
            self.list.setItemWidget(item, row)
        row.update_entry(entry)

    def _select_path(self, path: str) -> None:
        for index in range(self.list.count()):
            item = self.list.item(index)
            if item.data(Qt.UserRole) == path:
                self.list.setCurrentItem(item)
                return

    def _on_current_changed(self, item: QListWidgetItem | None, _previous) -> None:
        if item is not None:
            self.current_changed.emit(item.data(Qt.UserRole))
