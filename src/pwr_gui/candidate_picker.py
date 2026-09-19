"""Watermark picker: fixed-size cards in a column, so nothing can clip or overflow."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from pwr import Candidate
from pwr.pipeline import describe

from . import theme
from .panel_header import PanelHeader

CARD_W = 286
CARD_H = 112
THUMB_W = 96
THUMB_H = 68


class CandidateCard(QFrame):
    toggled = Signal(str, bool)
    focused = Signal(str)

    def __init__(self, candidate: Candidate, checked: bool, page_w: float, page_h: float) -> None:
        super().__init__()
        self.key = candidate.key
        self.checked = checked
        self.setFixedSize(QSize(CARD_W, CARD_H))
        self.setCursor(Qt.PointingHandCursor)

        self.thumb = QLabel()
        self.thumb.setFixedSize(THUMB_W, THUMB_H)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet(
            f"background: #ffffff; border: 1px solid {theme.BORDER}; border-radius: 6px;"
        )
        if candidate.thumbnail_png:
            pixmap = QPixmap()
            pixmap.loadFromData(candidate.thumbnail_png, "PNG")
            if not pixmap.isNull():
                self.thumb.setPixmap(
                    pixmap.scaled(
                        THUMB_W - 6, THUMB_H - 6, Qt.KeepAspectRatio, Qt.SmoothTransformation
                    )
                )
        else:
            self.thumb.setText("—")

        text = describe(candidate, page_w, page_h)
        self.title = QLabel()
        self.title.setFixedHeight(34)
        self.title.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.title.setStyleSheet("font-weight: 650; font-size: 12px;")
        self._title_text = text

        self.meta = QLabel(
            f"{candidate.estimated_pages}/{candidate.page_count} trang · tin cậy {candidate.score:.0%}"
        )
        self.meta.setStyleSheet(f"color: {theme.TEXT_DIM}; font-size: 11px;")

        self.meter = QFrame()
        self.meter.setFixedHeight(4)
        ratio = max(0.04, candidate.score)
        bar = theme.ACCENT if candidate.auto_check else theme.TEXT_DIM
        self.meter.setStyleSheet(
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0,"
            f" stop:0 {bar}, stop:{ratio:.2f} {bar},"
            f" stop:{min(1.0, ratio + 0.001):.3f} {theme.INK}, stop:1 {theme.INK});"
            f" border-radius: 2px;"
        )

        self.state = QLabel()
        self.state.setFixedHeight(18)

        info = QVBoxLayout()
        info.setContentsMargins(0, 0, 0, 0)
        info.setSpacing(2)
        info.addWidget(self.title)
        info.addWidget(self.meta)
        info.addWidget(self.state)

        content = QHBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(10)
        content.addWidget(self.thumb)
        content.addLayout(info, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 9)
        layout.setSpacing(7)
        layout.addLayout(content)
        layout.addWidget(self.meter)

        tooltip = [text, f"Xuất hiện trên khoảng {candidate.estimated_pages} trang."]
        tooltip += [f"· {reason}" for reason in candidate.reasons]
        tooltip.append("Bấm để chọn hoặc bỏ chọn.")
        self.setToolTip("\n".join(tooltip))

        self.set_checked(checked)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._elide_title()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._elide_title()

    def _elide_title(self) -> None:
        metrics = self.title.fontMetrics()
        width = self.title.width() or (CARD_W - THUMB_W - 34)
        words = self._title_text.split(" ")
        lines: list[str] = []
        current = ""
        for word in words:
            probe = f"{current} {word}".strip()
            if metrics.horizontalAdvance(probe) <= width or not current:
                current = probe
            else:
                lines.append(current)
                current = word
            if len(lines) == 2:
                break
        if current and len(lines) < 2:
            lines.append(current)
        if len(lines) == 2:
            lines[1] = metrics.elidedText(lines[1], Qt.ElideRight, width)
        self.title.setText("\n".join(lines))

    def set_checked(self, checked: bool) -> None:
        self.checked = checked
        border = theme.ACCENT if checked else theme.BORDER
        background = theme.SURFACE_RAISED if checked else "#0e1720"
        self.setStyleSheet(
            f"CandidateCard {{ background: {background}; border: 1.6px solid {border};"
            f" border-radius: 12px; }}"
        )
        self.state.setText("✓  SẼ XÓA" if checked else "○  Giữ lại")
        self.state.setStyleSheet(
            f"font-size: 10px; font-weight: 800; letter-spacing: 0.5px;"
            f" color: {theme.ACCENT if checked else theme.TEXT_DIM};"
        )

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.toggled.emit(self.key, not self.checked)
        super().mousePressEvent(event)

    def enterEvent(self, event) -> None:
        self.focused.emit(self.key)
        super().enterEvent(event)


class CandidatePicker(QWidget):
    selection_changed = Signal(set)
    card_focused = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._cards: dict[str, CandidateCard] = {}
        self._selected: set[str] = set()

        title = PanelHeader("WATERMARK PHÁT HIỆN")
        self.summary = QLabel("Chưa có file nào được phân tích.")
        self.summary.setObjectName("PanelSummary")

        self.select_all = QPushButton("Chọn tất cả")
        self.select_none = QPushButton("Bỏ chọn tất cả")
        for button in (self.select_all, self.select_none):
            button.setObjectName("Ghost")
        self.select_all.clicked.connect(lambda: self._set_all(True))
        self.select_none.clicked.connect(lambda: self._set_all(False))

        self.summary.setWordWrap(True)
        self.setFixedWidth(CARD_W + 20)

        buttons = QHBoxLayout()
        buttons.setSpacing(4)
        buttons.addWidget(self.select_all)
        buttons.addWidget(self.select_none)
        buttons.addStretch(1)

        self.track = QWidget()
        self.track.setObjectName("CandidateTrack")
        self.track_layout = QVBoxLayout(self.track)
        self.track_layout.setContentsMargins(2, 2, 2, 2)
        self.track_layout.setSpacing(12)
        self.track_layout.addStretch(1)

        self.scroll = QScrollArea()
        self.scroll.setObjectName("CandidateScroll")
        self.scroll.setWidget(self.track)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.empty = QLabel("Thêm file PDF để xem các phần tử lặp lại giữa các trang.")
        self.empty.setObjectName("Hint")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setWordWrap(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(title)
        layout.addWidget(self.summary)
        layout.addLayout(buttons)
        layout.addWidget(self.empty, 1)
        layout.addWidget(self.scroll, 1)
        self.scroll.hide()

    def clear(self) -> None:
        for card in self._cards.values():
            self.track_layout.removeWidget(card)
            card.setParent(None)
        self._cards = {}
        self._selected = set()
        self.scroll.hide()
        self.empty.show()
        self.summary.setText("Chưa có file nào được phân tích.")

    def set_candidates(
        self, candidates: list[Candidate], selected: set[str], page_w: float, page_h: float
    ) -> None:
        self.clear()
        self._selected = set(selected)
        for candidate in candidates:
            card = CandidateCard(candidate, candidate.key in self._selected, page_w, page_h)
            card.toggled.connect(self._on_card_toggled)
            card.focused.connect(self.card_focused.emit)
            self.track_layout.insertWidget(self.track_layout.count() - 1, card)
            self._cards[candidate.key] = card

        if candidates:
            self.empty.hide()
            self.scroll.show()
            auto = sum(1 for c in candidates if c.auto_check)
            self.summary.setText(
                f"{len(candidates)} phần tử lặp lại · {auto} mục được tick sẵn · "
                "bấm thẻ hoặc khung trên trang để đổi"
            )
        else:
            self.empty.setText("File này không có phần tử nào lặp lại giữa các trang.")
            self.summary.setText("Không tìm thấy watermark.")

    def set_selection(self, selected: set[str]) -> None:
        self._selected = set(selected)
        for key, card in self._cards.items():
            card.set_checked(key in self._selected)

    def _on_card_toggled(self, key: str, checked: bool) -> None:
        if checked:
            self._selected.add(key)
        else:
            self._selected.discard(key)
        self.set_selection(self._selected)
        self.selection_changed.emit(set(self._selected))

    def _set_all(self, checked: bool) -> None:
        self._selected = set(self._cards) if checked else set()
        self.set_selection(self._selected)
        self.selection_changed.emit(set(self._selected))
