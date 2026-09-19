"""Shared heading for the three stages of the PDF-cleaning workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget


class PanelHeader(QWidget):
    """A fixed-height workflow label that keeps every panel on one grid."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setFixedHeight(30)

        title_label = QLabel(title)
        title_label.setObjectName("PanelTitle")

        rule = QFrame()
        rule.setObjectName("PanelRule")
        rule.setFixedHeight(1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(title_label)
        layout.addWidget(rule, 1, Qt.AlignVCenter)
