"""Page preview with clickable watermark boxes and a before/after toggle."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pwr import Candidate
from pwr.pipeline import THUMB_DPI  # noqa: F401  (kept for dpi parity reference)

from . import theme

PREVIEW_DPI = 100
SCALE = PREVIEW_DPI / 72.0


class MarkBox(QGraphicsRectItem):
    """One watermark occurrence drawn over the page; click toggles selection."""

    def __init__(self, rect: QRectF, key: str, selected: bool, owner: "PreviewPane") -> None:
        super().__init__(rect)
        self.key = key
        self.owner = owner
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlag(QGraphicsItem.ItemIsFocusable, False)
        self.apply_state(selected, hovered=False)

    def apply_state(self, selected: bool, hovered: bool) -> None:
        color = QColor(theme.ACCENT) if selected else QColor(theme.TEXT_DIM)
        width = 3 if hovered else 2
        self.setPen(QPen(color, width, Qt.SolidLine))
        fill = QColor(color)
        fill.setAlpha(60 if selected else (30 if hovered else 0))
        self.setBrush(QBrush(fill))
        self.setToolTip(
            "Đang chọn xóa - bấm để bỏ chọn" if selected else "Bấm để chọn xóa vùng này"
        )

    def hoverEnterEvent(self, event) -> None:
        self.apply_state(self.owner.is_selected(self.key), hovered=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:
        self.apply_state(self.owner.is_selected(self.key), hovered=False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self.owner.toggled.emit(self.key)
        super().mousePressEvent(event)


class PreviewPane(QWidget):
    toggled = Signal(str)
    page_changed = Signal(int)
    mode_changed = Signal(bool)  # True = show "after"

    def __init__(self) -> None:
        super().__init__()
        self._candidates: list[Candidate] = []
        self._selected: set[str] = set()
        self._page_no = 0
        self._page_count = 0
        self._show_after = False
        self._boxes: list[MarkBox] = []

        self.scene = QGraphicsScene(self)
        self.view = QGraphicsView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setAlignment(Qt.AlignCenter)
        self.pixmap_item = QGraphicsPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.placeholder = QLabel("Thêm file PDF để bắt đầu")
        self.placeholder.setObjectName("PreviewEmpty")
        self.placeholder.setAlignment(Qt.AlignCenter)

        self.prev_btn = QPushButton("‹")
        self.next_btn = QPushButton("›")
        self.prev_btn.setObjectName("NavButton")
        self.next_btn.setObjectName("NavButton")
        self.page_label = QLabel("—")
        self.page_label.setObjectName("PageCounter")
        self.toggle_btn = QPushButton("Xem kết quả sau khi xóa")
        self.toggle_btn.setObjectName("AccentOutline")
        self.toggle_btn.setCheckable(True)

        self.prev_btn.clicked.connect(lambda: self.go_to(self._page_no - 1))
        self.next_btn.clicked.connect(lambda: self.go_to(self._page_no + 1))
        self.toggle_btn.toggled.connect(self._on_toggle_mode)

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.prev_btn)
        bar.addWidget(self.page_label)
        bar.addWidget(self.next_btn)
        bar.addStretch(1)
        bar.addWidget(self.toggle_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addWidget(self.placeholder, 1)
        layout.addWidget(self.view, 1)
        layout.addLayout(bar)
        self.view.hide()
        self._update_controls()

    # -- state -------------------------------------------------------------

    def is_selected(self, key: str) -> bool:
        return key in self._selected

    def set_document(self, page_count: int, candidates: list[Candidate], selected: set[str]) -> None:
        self._page_count = page_count
        self._candidates = candidates
        self._selected = selected
        self._page_no = min(self._page_no, max(0, page_count - 1))
        self._update_controls()

    def set_selection(self, selected: set[str]) -> None:
        self._selected = selected
        for box in self._boxes:
            box.apply_state(box.key in selected, hovered=False)

    def clear(self) -> None:
        self._candidates = []
        self._selected = set()
        self._page_count = 0
        self.pixmap_item.setPixmap(QPixmap())
        self._clear_boxes()
        self.view.hide()
        self.placeholder.show()
        self._update_controls()

    @property
    def page_no(self) -> int:
        return self._page_no

    @property
    def show_after(self) -> bool:
        return self._show_after

    def first_page_with_marks(self) -> int:
        for candidate in self._candidates:
            if candidate.auto_check and candidate.hits:
                return candidate.hits[len(candidate.hits) // 2].page_no
        if self._candidates and self._candidates[0].hits:
            return self._candidates[0].hits[0].page_no
        return 0

    def go_to(self, page_no: int) -> None:
        if not self._page_count:
            return
        page_no = max(0, min(self._page_count - 1, page_no))
        if page_no != self._page_no:
            self._page_no = page_no
            self._update_controls()
            self.page_changed.emit(page_no)

    def _on_toggle_mode(self, checked: bool) -> None:
        self._show_after = checked
        self.toggle_btn.setText(
            "Xem bản gốc" if checked else "Xem kết quả sau khi xóa"
        )
        self.mode_changed.emit(checked)

    # -- rendering ---------------------------------------------------------

    def show_page(self, page_no: int, png: bytes) -> None:
        pixmap = QPixmap()
        pixmap.loadFromData(png, "PNG")
        self.pixmap_item.setPixmap(pixmap)
        self.scene.setSceneRect(QRectF(pixmap.rect()))
        self.placeholder.hide()
        self.view.show()
        self._page_no = page_no
        self._draw_boxes(page_no)
        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        self._update_controls()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self.pixmap_item.pixmap().isNull():
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def _clear_boxes(self) -> None:
        for box in self._boxes:
            self.scene.removeItem(box)
        self._boxes = []

    def _draw_boxes(self, page_no: int) -> None:
        self._clear_boxes()
        if self._show_after:
            return
        for candidate in self._candidates:
            for hit in candidate.hits:
                if hit.page_no != page_no:
                    continue
                rect = QRectF(
                    hit.rect.x0 * SCALE,
                    hit.rect.y0 * SCALE,
                    hit.rect.width * SCALE,
                    hit.rect.height * SCALE,
                )
                box = MarkBox(rect, candidate.key, candidate.key in self._selected, self)
                self.scene.addItem(box)
                self._boxes.append(box)

    def _update_controls(self) -> None:
        has_doc = self._page_count > 0
        self.prev_btn.setEnabled(has_doc and self._page_no > 0)
        self.next_btn.setEnabled(has_doc and self._page_no < self._page_count - 1)
        self.toggle_btn.setEnabled(has_doc)
        self.page_label.setText(
            f"Trang {self._page_no + 1} / {self._page_count}" if has_doc else "—"
        )
