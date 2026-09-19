"""Interactive page preview, manual regions, and before/after comparison slider."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from pwr import Candidate, ManualRegion, Rect

from . import theme

PREVIEW_DPI = 100
SCALE = PREVIEW_DPI / 72.0


class ComparisonPixmapItem(QGraphicsItem):
    """Paint original and cleaned pixmaps with a movable vertical reveal."""

    def __init__(self) -> None:
        super().__init__()
        self.before = QPixmap()
        self.after = QPixmap()
        self.ratio = 0.0

    def boundingRect(self) -> QRectF:
        return QRectF(self.before.rect())

    def set_pixmaps(self, before: QPixmap, after: QPixmap | None) -> None:
        self.prepareGeometryChange()
        self.before = before
        self.after = after or QPixmap()
        self.update()

    def set_ratio(self, ratio: float) -> None:
        self.ratio = max(0.0, min(1.0, ratio))
        self.update()

    def pixmap(self) -> QPixmap:
        """Keep the small QGraphicsPixmapItem API used by GUI smoke tests."""
        return self.before

    def paint(self, painter: QPainter, _option, _widget=None) -> None:
        if self.before.isNull():
            return
        painter.drawPixmap(0, 0, self.before)
        if self.after.isNull() or self.ratio <= 0:
            return
        reveal = self.before.width() * self.ratio
        painter.save()
        painter.setClipRect(QRectF(0, 0, reveal, self.before.height()))
        painter.drawPixmap(0, 0, self.after)
        painter.restore()
        if self.ratio < 1:
            painter.setPen(QPen(QColor(theme.ACCENT), 2))
            painter.drawLine(int(reveal), 0, int(reveal), self.before.height())


class DrawingView(QGraphicsView):
    region_drawn = Signal(object)

    def __init__(self, scene: QGraphicsScene) -> None:
        super().__init__(scene)
        self.draw_mode = False
        self._origin = None
        self._rubber: QGraphicsRectItem | None = None

    def set_draw_mode(self, enabled: bool) -> None:
        self.draw_mode = enabled
        self.setCursor(Qt.CrossCursor if enabled else Qt.ArrowCursor)

    def mousePressEvent(self, event) -> None:
        if self.draw_mode and event.button() == Qt.LeftButton and not self.sceneRect().isEmpty():
            self._origin = self.mapToScene(event.position().toPoint())
            self._rubber = QGraphicsRectItem()
            pen = QPen(QColor(theme.ACCENT), 2, Qt.DashLine)
            fill = QColor(theme.ACCENT)
            fill.setAlpha(45)
            self._rubber.setPen(pen)
            self._rubber.setBrush(QBrush(fill))
            self._rubber.setZValue(50)
            self.scene().addItem(self._rubber)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._origin is not None and self._rubber is not None:
            current = self.mapToScene(event.position().toPoint())
            self._rubber.setRect(QRectF(self._origin, current).normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if self._origin is not None and self._rubber is not None:
            rect = self._rubber.rect().intersected(self.sceneRect())
            self.scene().removeItem(self._rubber)
            self._rubber = None
            self._origin = None
            if rect.width() >= 5 and rect.height() >= 5:
                self.region_drawn.emit(rect)
            event.accept()
            return
        super().mouseReleaseEvent(event)


class MarkBox(QGraphicsRectItem):
    def __init__(self, rect: QRectF, key: str, selected: bool, owner: "PreviewPane") -> None:
        super().__init__(rect)
        self.key = key
        self.owner = owner
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlag(QGraphicsItem.ItemIsFocusable, False)
        self.setZValue(10)
        self.apply_state(selected, hovered=False)

    def apply_state(self, selected: bool, hovered: bool) -> None:
        color = QColor(theme.ACCENT) if selected else QColor(theme.TEXT_DIM)
        self.setPen(QPen(color, 3 if hovered else 2, Qt.SolidLine))
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


class ManualBox(QGraphicsRectItem):
    def __init__(self, rect: QRectF, scope: str) -> None:
        super().__init__(rect)
        color = QColor("#55c7ff")
        fill = QColor(color)
        fill.setAlpha(35)
        self.setPen(QPen(color, 2, Qt.DashLine))
        self.setBrush(QBrush(fill))
        self.setToolTip(f"Vùng thủ công · {scope or 'trang hiện tại'}")
        self.setZValue(9)


class PreviewPane(QWidget):
    toggled = Signal(str)
    page_changed = Signal(int)
    mode_changed = Signal(bool)
    manual_region_added = Signal(int, object, str)
    undo_manual_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self._candidates: list[Candidate] = []
        self._selected: set[str] = set()
        self._manual_regions: list[ManualRegion] = []
        self._page_no = 0
        self._page_count = 0
        self._boxes: list[QGraphicsRectItem] = []

        self.scene = QGraphicsScene(self)
        self.view = DrawingView(self.scene)
        self.view.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.view.setAlignment(Qt.AlignCenter)
        self.view.region_drawn.connect(self._on_region_drawn)
        self.pixmap_item = ComparisonPixmapItem()
        self.scene.addItem(self.pixmap_item)

        self.placeholder = QLabel("Thêm file PDF để bắt đầu")
        self.placeholder.setObjectName("PreviewEmpty")
        self.placeholder.setAlignment(Qt.AlignCenter)

        self.draw_btn = QPushButton("Vẽ vùng xóa")
        self.draw_btn.setObjectName("AccentOutline")
        self.draw_btn.setCheckable(True)
        self.draw_btn.toggled.connect(self.view.set_draw_mode)
        self.scope_edit = QLineEdit()
        self.scope_edit.setPlaceholderText("trang hiện tại")
        self.scope_edit.setToolTip("Nhập: 1-5,8 · tất cả · lẻ · chẵn")
        self.scope_edit.setMaximumWidth(150)
        self.undo_btn = QPushButton("Hoàn tác vùng")
        self.undo_btn.setObjectName("Ghost")
        self.undo_btn.clicked.connect(self.undo_manual_requested.emit)
        self.safety = QLabel("Bảo vệ chữ tự động đang bật")
        self.safety.setObjectName("SafetyStatus")

        manual_bar = QHBoxLayout()
        manual_bar.setContentsMargins(0, 0, 0, 0)
        manual_bar.setSpacing(8)
        manual_bar.addWidget(self.draw_btn)
        manual_bar.addWidget(QLabel("Áp dụng:"))
        manual_bar.addWidget(self.scope_edit)
        manual_bar.addWidget(self.undo_btn)
        manual_bar.addStretch(1)
        manual_bar.addWidget(self.safety)

        self.prev_btn = QPushButton("‹")
        self.next_btn = QPushButton("›")
        self.prev_btn.setObjectName("NavButton")
        self.next_btn.setObjectName("NavButton")
        self.page_label = QLabel("—")
        self.page_label.setObjectName("PageCounter")

        self.compare_slider = QSlider(Qt.Horizontal)
        self.compare_slider.setRange(0, 100)
        self.compare_slider.setValue(0)
        self.compare_slider.setFixedWidth(170)
        self.compare_slider.valueChanged.connect(self._on_compare_changed)
        self.before_label = QLabel("GỐC")
        self.before_label.setObjectName("CompareLabel")
        self.after_label = QLabel("SAU XÓA")
        self.after_label.setObjectName("CompareLabel")
        self.toggle_btn = QPushButton("Chỉ xem sau")
        self.toggle_btn.setObjectName("Ghost")
        self.toggle_btn.setCheckable(True)
        self.toggle_btn.toggled.connect(self._on_toggle_mode)

        self.prev_btn.clicked.connect(lambda: self.go_to(self._page_no - 1))
        self.next_btn.clicked.connect(lambda: self.go_to(self._page_no + 1))

        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(8)
        nav.addWidget(self.prev_btn)
        nav.addWidget(self.page_label)
        nav.addWidget(self.next_btn)
        nav.addStretch(1)
        nav.addWidget(self.before_label)
        nav.addWidget(self.compare_slider)
        nav.addWidget(self.after_label)
        nav.addWidget(self.toggle_btn)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(9)
        layout.addWidget(self.placeholder, 1)
        layout.addWidget(self.view, 1)
        layout.addLayout(manual_bar)
        layout.addLayout(nav)
        self.view.hide()
        self._update_controls()

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
            if isinstance(box, MarkBox):
                box.apply_state(box.key in selected, hovered=False)

    def set_manual_regions(self, regions: list[ManualRegion]) -> None:
        self._manual_regions = list(regions)
        self._draw_boxes(self._page_no)
        self._update_controls()

    def set_safety(self, text: str, warning: bool = False) -> None:
        self.safety.setText(text)
        self.safety.setProperty("warning", warning)
        self.safety.style().unpolish(self.safety)
        self.safety.style().polish(self.safety)

    def clear(self) -> None:
        self._candidates = []
        self._selected = set()
        self._manual_regions = []
        self._page_count = 0
        self.pixmap_item.set_pixmaps(QPixmap(), None)
        self._clear_boxes()
        self.view.hide()
        self.placeholder.show()
        self.compare_slider.setValue(0)
        self.set_safety("Bảo vệ chữ tự động đang bật")
        self._update_controls()

    @property
    def page_no(self) -> int:
        return self._page_no

    @property
    def show_after(self) -> bool:
        return self.compare_slider.value() == 100

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
        self.compare_slider.setValue(100 if checked else 0)
        self.toggle_btn.setText("Xem bản gốc" if checked else "Chỉ xem sau")
        self.mode_changed.emit(checked)

    def _on_compare_changed(self, value: int) -> None:
        self.pixmap_item.set_ratio(value / 100.0)
        checked = value == 100
        self.toggle_btn.blockSignals(True)
        self.toggle_btn.setChecked(checked)
        self.toggle_btn.setText("Xem bản gốc" if checked else "Chỉ xem sau")
        self.toggle_btn.blockSignals(False)
        visible = value == 0
        for box in self._boxes:
            box.setVisible(visible)

    def _on_region_drawn(self, rect: QRectF) -> None:
        pdf_rect = Rect(
            rect.left() / SCALE,
            rect.top() / SCALE,
            rect.right() / SCALE,
            rect.bottom() / SCALE,
        )
        self.draw_btn.setChecked(False)
        self.manual_region_added.emit(self._page_no, pdf_rect, self.scope_edit.text())

    def show_page(
        self, page_no: int, before_png: bytes, after_png: bytes | None = None
    ) -> None:
        before = QPixmap()
        before.loadFromData(before_png, "PNG")
        after = QPixmap()
        if after_png:
            after.loadFromData(after_png, "PNG")
        if after.isNull() and self.compare_slider.value():
            self.compare_slider.setValue(0)
        self.pixmap_item.set_pixmaps(before, after if not after.isNull() else None)
        self.scene.setSceneRect(self.pixmap_item.boundingRect())
        self.placeholder.hide()
        self.view.show()
        self._page_no = page_no
        self._draw_boxes(page_no)
        self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)
        self._update_controls()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self.pixmap_item.before.isNull():
            self.view.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def _clear_boxes(self) -> None:
        for box in self._boxes:
            self.scene.removeItem(box)
        self._boxes = []

    def _draw_boxes(self, page_no: int) -> None:
        self._clear_boxes()
        for candidate in self._candidates:
            for hit in candidate.hits:
                if hit.page_no != page_no:
                    continue
                box = MarkBox(
                    QRectF(
                        hit.rect.x0 * SCALE,
                        hit.rect.y0 * SCALE,
                        hit.rect.width * SCALE,
                        hit.rect.height * SCALE,
                    ),
                    candidate.key,
                    candidate.key in self._selected,
                    self,
                )
                self.scene.addItem(box)
                self._boxes.append(box)
        for region in self._manual_regions:
            if not region.applies_to(page_no):
                continue
            rect = region.rect
            box = ManualBox(
                QRectF(rect.x0 * SCALE, rect.y0 * SCALE, rect.width * SCALE, rect.height * SCALE),
                region.scope,
            )
            self.scene.addItem(box)
            self._boxes.append(box)
        self._on_compare_changed(self.compare_slider.value())

    def _update_controls(self) -> None:
        has_doc = self._page_count > 0
        has_after = has_doc and (
            bool(self._selected) or any(r.applies_to(self._page_no) for r in self._manual_regions)
        )
        self.prev_btn.setEnabled(has_doc and self._page_no > 0)
        self.next_btn.setEnabled(has_doc and self._page_no < self._page_count - 1)
        self.draw_btn.setEnabled(has_doc)
        self.undo_btn.setEnabled(bool(self._manual_regions))
        self.scope_edit.setEnabled(has_doc)
        self.compare_slider.setEnabled(has_after)
        self.toggle_btn.setEnabled(has_after)
        self.page_label.setText(
            f"Trang {self._page_no + 1} / {self._page_count}" if has_doc else "—"
        )
