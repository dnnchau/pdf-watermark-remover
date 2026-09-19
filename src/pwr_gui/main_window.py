"""Main window: queue on the left, page preview centre, candidates on the right."""

from __future__ import annotations

import os
from dataclasses import replace

from PySide6.QtCore import Qt, QThreadPool
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QInputDialog,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from pwr import (
    AnalyzeReport,
    Candidate,
    ManualRegion,
    Rect,
    RunReport,
    assess_manual_region,
    parse_page_scope,
)
from pwr.remove import DEFAULT_SUFFIX, default_output_path, unique_output_path

from . import theme
from .candidate_picker import CandidatePicker
from .file_queue import FileEntry, FileQueue, Status
from .panel_header import PanelHeader
from .preview_pane import PreviewPane
from .presets import PresetStore
from .resources import app_icon_path
from .worker import AnalyzeTask, RemoveTask, RenderTask, VerifyTask

VERIFY_SAMPLE = 3


class MainWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("MainWindow")
        self.setWindowTitle("PDF Watermark Remover")
        self.setWindowIcon(QIcon(str(app_icon_path())))
        self.resize(1360, 880)
        self.setAcceptDrops(True)

        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.render_pool = QThreadPool()
        self.render_pool.setMaxThreadCount(1)

        self.render_token = 0
        self._tasks: set = set()
        self.run_queue: list[FileEntry] = []
        self.active_remove: RemoveTask | None = None
        self.template_selection: list[Candidate] = []
        self.template_manual: list[dict] = []
        self.template_was_auto = True
        self.run_active = False
        self.waiting_for: str | None = None

        self.queue = FileQueue()
        self.preview = PreviewPane()
        self.picker = CandidatePicker()
        self.preset_store = PresetStore()

        self._build_layout()
        self._wire()
        self.picker.set_presets(self.preset_store.names())

    # -- layout ------------------------------------------------------------

    def _build_layout(self) -> None:
        add_file = QPushButton("Thêm PDF")
        add_file.setObjectName("AccentOutline")
        add_folder = QPushButton("Thêm thư mục")
        remove_btn = QPushButton("Bỏ khỏi hàng đợi")
        remove_btn.setObjectName("Ghost")
        add_file.clicked.connect(self._pick_files)
        add_folder.clicked.connect(self._pick_folder)
        remove_btn.clicked.connect(self._remove_current)

        heading = QLabel("PDF Watermark Remover")
        heading.setObjectName("DocTitle")
        subtitle = QLabel("Tự tìm phần tử lặp lại giữa các trang — bạn quyết định xóa cái nào")
        subtitle.setObjectName("Hint")

        logo = QLabel()
        logo.setObjectName("AppLogo")
        logo.setFixedSize(40, 40)
        logo.setPixmap(
            QPixmap(str(app_icon_path())).scaled(
                40, 40, Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title_box.addWidget(heading)
        title_box.addWidget(subtitle)

        top = QHBoxLayout()
        top.setSpacing(10)
        top.addWidget(logo)
        top.addSpacing(2)
        top.addLayout(title_box)
        top.addStretch(1)
        top.addWidget(add_file)
        top.addWidget(add_folder)
        top.addWidget(remove_btn)

        preview_card = QFrame()
        preview_card.setObjectName("WorkspacePanel")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(*theme.PANEL_CONTENT_MARGINS)
        preview_layout.setSpacing(theme.PANEL_SPACING)
        preview_title = PanelHeader("XEM TRƯỚC")
        preview_layout.addWidget(preview_title)
        preview_layout.addWidget(self.preview, 1)

        picker_card = QFrame()
        picker_card.setObjectName("WorkspacePanel")
        picker_layout = QVBoxLayout(picker_card)
        picker_layout.setContentsMargins(*theme.PANEL_CONTENT_MARGINS)
        picker_layout.setSpacing(theme.PANEL_SPACING)
        picker_layout.addWidget(self.picker)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setObjectName("WorkspaceSplitter")
        splitter.setHandleWidth(theme.WORKSPACE_GUTTER)
        splitter.addWidget(self.queue)
        splitter.addWidget(preview_card)
        splitter.addWidget(picker_card)
        splitter.setSizes([260, 745, 330])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        for index in range(splitter.count()):
            splitter.setCollapsible(index, False)

        self.out_dir = QLineEdit()
        self.out_dir.setPlaceholderText("Cùng thư mục với file gốc")
        self.suffix = QLineEdit(DEFAULT_SUFFIX)
        self.suffix.setMaximumWidth(120)
        browse = QPushButton("Duyệt…")
        browse.clicked.connect(self._pick_out_dir)

        self.apply_all = QCheckBox("Áp dụng cùng lựa chọn cho mọi file trong hàng đợi")
        self.apply_all.setChecked(True)

        self.aggressive = QCheckBox("Xóa triệt để")
        self.aggressive.setToolTip(
            "Mặc định (tắt): phần watermark nằm đè lên chữ của trang sẽ được giữ lại, "
            "vì xóa nó sẽ xóa luôn dòng chữ bên dưới.\n"
            "Bật: xóa sạch watermark, chấp nhận rủi ro mất chữ nằm dưới nó."
        )

        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        output_label = QLabel("THƯ MỤC XUẤT")
        output_label.setObjectName("FormLabel")
        suffix_label = QLabel("HẬU TỐ")
        suffix_label.setObjectName("FormLabel")
        out_row.addWidget(output_label)
        out_row.addWidget(self.out_dir, 1)
        out_row.addWidget(browse)
        out_row.addSpacing(8)
        out_row.addWidget(suffix_label)
        out_row.addWidget(self.suffix)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.hide()
        self.status = QLabel("Kéo thả file PDF vào cửa sổ để bắt đầu.")
        self.status.setObjectName("Hint")
        self.status.setWordWrap(True)

        self.cancel_btn = QPushButton("Hủy")
        self.cancel_btn.clicked.connect(self._cancel)
        self.cancel_btn.hide()
        self.run_btn = QPushButton("XÓA WATERMARK")
        self.run_btn.setObjectName("Primary")
        self.run_btn.setMinimumWidth(170)
        self.run_btn.clicked.connect(self._start_run)
        self.run_btn.setEnabled(False)

        action_row = QHBoxLayout()
        action_row.setSpacing(14)
        action_row.addWidget(self.status, 1)
        action_row.addWidget(self.apply_all)
        action_row.addWidget(self.aggressive)
        action_row.addWidget(self.cancel_btn)
        action_row.addWidget(self.run_btn)

        bottom = QFrame()
        bottom.setObjectName("Card")
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.setSpacing(9)
        bottom_layout.addLayout(out_row)
        bottom_layout.addWidget(self.progress)
        bottom_layout.addLayout(action_row)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(14)
        layout.addLayout(top)

        divider = QFrame()
        divider.setObjectName("HeaderDivider")
        divider.setFixedHeight(1)
        layout.addWidget(divider)
        layout.addWidget(splitter, 1)
        layout.addWidget(bottom)

    def _keep(self, task) -> None:
        """Hold a reference until the task reports back; Qt no longer owns it."""
        self._tasks.add(task)
        task.signals.done.connect(lambda *_: self._tasks.discard(task))
        task.signals.failed.connect(lambda *_: self._tasks.discard(task))

    def _wire(self) -> None:
        self.queue.current_changed.connect(self._show_file)
        self.queue.remove_requested.connect(self._remove_path)
        self.picker.selection_changed.connect(self._on_selection_changed)
        self.picker.card_focused.connect(self._focus_candidate)
        self.preview.toggled.connect(self._toggle_key)
        self.preview.page_changed.connect(lambda _: self._render_current())
        self.preview.manual_region_added.connect(self._add_manual_region)
        self.preview.undo_manual_requested.connect(self._undo_manual_region)
        self.picker.save_preset_requested.connect(self._save_preset)
        self.picker.apply_preset_requested.connect(self._apply_preset)

    # -- input -------------------------------------------------------------

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths: list[str] = []
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if os.path.isdir(local):
                paths.extend(self._pdfs_in(local))
            else:
                paths.append(local)
        self._add(paths)

    @staticmethod
    def _pdfs_in(folder: str) -> list[str]:
        found = []
        for root, _dirs, files in os.walk(folder):
            found.extend(
                os.path.join(root, name)
                for name in sorted(files)
                if name.lower().endswith(".pdf")
            )
        return found

    def _pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Chọn file PDF", "", "PDF (*.pdf)")
        self._add(paths)

    def _pick_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa PDF")
        if folder:
            self._add(self._pdfs_in(folder))

    def _pick_out_dir(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục xuất")
        if folder:
            self.out_dir.setText(folder)

    def _add(self, paths: list[str]) -> None:
        added = self.queue.add_paths(paths)
        for path in added:
            self._analyze(path)
        if added:
            self.status.setText(f"Đã thêm {len(added)} file. Đang phân tích…")

    def _remove_current(self) -> None:
        entry = self.queue.current_entry()
        if entry is not None:
            self._remove_path(entry.path)

    def _remove_path(self, path: str) -> None:
        entry = self.queue.entry(path)
        if entry is None:
            return
        if entry is not None and entry.status is Status.WORKING:
            self.status.setText(
                f"{entry.name} đang được xử lý. Bấm Hủy trước khi bỏ khỏi hàng đợi."
            )
            return
        self.queue.remove_path(path)
        if not self.queue.entries:
            self.preview.clear()
            self.picker.clear()
            self.run_btn.setEnabled(False)

    # -- analysis ----------------------------------------------------------

    def _analyze(self, path: str, then_remove: bool = False) -> None:
        entry = self.queue.entry(path)
        if entry is None:
            return
        entry.status = Status.ANALYZING
        entry.message = ""
        self.queue.update_entry(path)

        task = AnalyzeTask(path)
        task.signals.progress.connect(self._on_progress)
        task.signals.done.connect(
            lambda payload: self._on_analyzed(payload, then_remove)
        )
        task.signals.failed.connect(self._on_failed)
        self._keep(task)
        self.pool.start(task)

    def _on_analyzed(self, payload: tuple[str, AnalyzeReport], then_remove: bool) -> None:
        path, report = payload
        entry = self.queue.entry(path)
        if entry is None:
            return
        entry.report = report
        entry.status = Status.READY
        entry.selected = set(report.auto_selected_keys())
        if then_remove and (self.template_selection or self.template_manual):
            entry.selected = self._match_template(report)
            entry.manual_regions = self._manual_from_template(report)
        self.queue.update_entry(path)

        current = self.queue.current_entry()
        if current is not None and current.path == path:
            self._show_file(path)
        self._refresh_run_button()
        self.progress.hide()
        if not then_remove:
            self.status.setText(
                f"{entry.name}: đã tick sẵn {len(entry.selected)} mục. "
                "Bấm khung trên trang hoặc thẻ bên phải để đổi, rồi bấm XÓA WATERMARK."
                if entry.selected
                else f"{entry.name}: không tìm thấy watermark rõ ràng. "
                "Bạn có thể tự chọn thẻ muốn xóa ở cột bên phải."
            )

        if then_remove or self.waiting_for == path:
            self.waiting_for = None
            if self.run_active:
                if not entry.selected and self.template_selection:
                    entry.selected = self._match_template(report)
                if not entry.manual_regions and self.template_manual:
                    entry.manual_regions = self._manual_from_template(report)
            self._remove_entry(entry)

    def _match_template(self, report: AnalyzeReport) -> set[str]:
        """Carry the user's choice to another file by matching mark fingerprints."""
        wanted_keys = {c.key for c in self.template_selection}
        wanted_text = {c.text.strip().lower() for c in self.template_selection if c.text}
        matched = set()
        for candidate in report.candidates:
            if candidate.key in wanted_keys:
                matched.add(candidate.key)
            elif candidate.text and candidate.text.strip().lower() in wanted_text:
                matched.add(candidate.key)
        # Only fall back to this file's own suggestions when the template was itself
        # the untouched suggestion - never re-tick something the user unticked.
        if not matched and self.template_was_auto:
            matched = set(report.auto_selected_keys())
        return matched

    @staticmethod
    def _manual_template(entry: FileEntry) -> list[dict]:
        if entry.report is None:
            return []
        width = entry.report.doc.page_width or 1
        height = entry.report.doc.page_height or 1
        return [
            {
                "rect": [
                    region.rect.x0 / width,
                    region.rect.y0 / height,
                    region.rect.x1 / width,
                    region.rect.y1 / height,
                ],
                "scope": region.scope,
            }
            for region in entry.manual_regions
        ]

    def _manual_from_template(
        self, report: AnalyzeReport, templates: list[dict] | None = None
    ) -> list[ManualRegion]:
        regions: list[ManualRegion] = []
        for item in templates if templates is not None else self.template_manual:
            values = item.get("rect", [])
            if len(values) != 4:
                continue
            rect = Rect(
                float(values[0]) * report.doc.page_width,
                float(values[1]) * report.doc.page_height,
                float(values[2]) * report.doc.page_width,
                float(values[3]) * report.doc.page_height,
            )
            scope = str(item.get("scope") or "tất cả")
            try:
                pages = parse_page_scope(scope, report.doc.page_count, 0)
            except (ValueError, TypeError):
                continue
            region = ManualRegion(rect, pages, scope)
            risk = assess_manual_region(report.doc.path, region)
            regions.append(replace(region, risk_count=risk.total))
        return regions

    # -- display -----------------------------------------------------------

    def _show_file(self, path: str) -> None:
        entry = self.queue.entry(path)
        if entry is None or entry.report is None:
            self.preview.clear()
            self.picker.clear()
            return
        report = entry.report
        self.picker.set_candidates(
            list(report.candidates), entry.selected, report.doc.page_width, report.doc.page_height
        )
        self.preview.set_document(
            report.doc.page_count, list(report.candidates), entry.selected
        )
        self.preview.set_manual_regions(entry.manual_regions)
        self._refresh_safety(entry)
        self.preview.go_to(self.preview.first_page_with_marks())
        self._render_current()
        self._refresh_run_button()

    def _render_current(self) -> None:
        entry = self.queue.current_entry()
        if entry is None or entry.report is None:
            return
        if self.run_active:
            return
        self.render_token += 1
        token = self.render_token
        selected = [c for c in entry.report.candidates if c.key in entry.selected]
        task = RenderTask(
            entry.path,
            self.preview.page_no,
            selected,
            list(entry.manual_regions),
            token,
        )
        task.signals.done.connect(self._on_rendered)
        task.signals.failed.connect(lambda msg: self.status.setText(f"Lỗi hiển thị: {msg}"))
        self._keep(task)
        self.render_pool.start(task)

    def _on_rendered(self, payload: tuple[int, int, bytes, bytes | None]) -> None:
        token, page_no, before, after = payload
        if token == self.render_token:
            self.preview.show_page(page_no, before, after)

    def _focus_candidate(self, key: str) -> None:
        entry = self.queue.current_entry()
        if entry is None or entry.report is None:
            return
        candidate = next((c for c in entry.report.candidates if c.key == key), None)
        if candidate is None or not candidate.hits:
            return
        if not any(hit.page_no == self.preview.page_no for hit in candidate.hits):
            self.preview.go_to(candidate.hits[len(candidate.hits) // 2].page_no)

    # -- selection ---------------------------------------------------------

    def _on_selection_changed(self, selected: set) -> None:
        entry = self.queue.current_entry()
        if entry is None:
            return
        entry.selected = set(selected)
        self.preview.set_selection(entry.selected)
        self.queue.update_entry(entry.path)
        self._refresh_run_button()
        self._render_current()

    def _toggle_key(self, key: str) -> None:
        entry = self.queue.current_entry()
        if entry is None:
            return
        if key in entry.selected:
            entry.selected.discard(key)
        else:
            entry.selected.add(key)
        self.picker.set_selection(entry.selected)
        self.preview.set_selection(entry.selected)
        self.queue.update_entry(entry.path)
        self._refresh_run_button()
        self._render_current()

    def _add_manual_region(self, page_no: int, rect: Rect, scope: str) -> None:
        entry = self.queue.current_entry()
        if entry is None or entry.report is None:
            return
        scope_label = scope.strip() or str(page_no + 1)
        try:
            pages = parse_page_scope(scope_label, entry.report.doc.page_count, page_no)
        except (ValueError, TypeError) as error:
            self.status.setText(str(error))
            QMessageBox.warning(self, "Phạm vi trang không hợp lệ", str(error))
            return
        region = ManualRegion(rect, pages, scope_label)
        risk = assess_manual_region(entry.path, region)
        region = replace(region, risk_count=risk.total)
        entry.manual_regions.append(region)
        self.preview.set_manual_regions(entry.manual_regions)
        self.preview.set_safety(risk.message(), bool(risk.total))
        self.queue.update_entry(entry.path)
        self.status.setText(risk.message())
        self._refresh_run_button()
        self._render_current()

    def _undo_manual_region(self) -> None:
        entry = self.queue.current_entry()
        if entry is None or not entry.manual_regions:
            return
        entry.manual_regions.pop()
        self.preview.set_manual_regions(entry.manual_regions)
        self._refresh_safety(entry)
        self.queue.update_entry(entry.path)
        self._refresh_run_button()
        self._render_current()

    def _refresh_safety(self, entry: FileEntry) -> None:
        risky = sum(region.risk_count for region in entry.manual_regions)
        if risky:
            self.preview.set_safety(
                f"Cảnh báo: {risky} nội dung nằm trong vùng thủ công", True
            )
        elif entry.manual_regions:
            self.preview.set_safety(
                f"{len(entry.manual_regions)} vùng thủ công · chưa thấy xung đột", False
            )
        else:
            self.preview.set_safety("Bảo vệ chữ tự động đang bật", False)

    def _preset_payload(self, entry: FileEntry) -> dict:
        if entry.report is None:
            return {}
        width = entry.report.doc.page_width or 1
        height = entry.report.doc.page_height or 1
        selected = [c for c in entry.report.candidates if c.key in entry.selected]
        return {
            "version": 1,
            "candidates": [
                {
                    "key": candidate.key,
                    "text": candidate.text.strip().lower(),
                    "kind": candidate.kind.value,
                    "center": [
                        (candidate.rect.x0 + candidate.rect.x1) / 2 / width,
                        (candidate.rect.y0 + candidate.rect.y1) / 2 / height,
                    ],
                }
                for candidate in selected
            ],
            "manual": self._manual_template(entry),
        }

    def _save_preset(self) -> None:
        entry = self.queue.current_entry()
        if entry is None or entry.report is None or not (entry.selected or entry.manual_regions):
            self.status.setText("Hãy chọn watermark hoặc vẽ vùng trước khi lưu preset.")
            return
        name, accepted = QInputDialog.getText(self, "Lưu preset", "Tên preset:")
        if not accepted or not name.strip():
            return
        self.preset_store.save(name, self._preset_payload(entry))
        self.picker.set_presets(self.preset_store.names())
        self.picker.preset_combo.setCurrentText(" ".join(name.split()))
        self.status.setText(f"Đã lưu preset “{' '.join(name.split())}”.")

    def _apply_preset(self, name: str) -> None:
        entry = self.queue.current_entry()
        if entry is None or entry.report is None or not name:
            return
        payload = self.preset_store.load(name)
        if payload is None:
            self.status.setText("Không tìm thấy preset đã chọn.")
            return
        wanted = payload.get("candidates", [])
        matched: set[str] = set()
        for candidate in entry.report.candidates:
            cx = (candidate.rect.x0 + candidate.rect.x1) / 2 / (entry.report.doc.page_width or 1)
            cy = (candidate.rect.y0 + candidate.rect.y1) / 2 / (entry.report.doc.page_height or 1)
            for selector in wanted:
                center = selector.get("center", [99, 99])
                same_position = (
                    len(center) == 2
                    and abs(cx - float(center[0])) < 0.08
                    and abs(cy - float(center[1])) < 0.08
                )
                if (
                    candidate.key == selector.get("key")
                    or (
                        candidate.text
                        and candidate.text.strip().lower() == selector.get("text")
                    )
                    or (candidate.kind.value == selector.get("kind") and same_position)
                ):
                    matched.add(candidate.key)
                    break
        entry.selected = matched
        entry.manual_regions = self._manual_from_template(
            entry.report, list(payload.get("manual", []))
        )
        self.picker.set_selection(entry.selected)
        self.preview.set_selection(entry.selected)
        self.preview.set_manual_regions(entry.manual_regions)
        self._refresh_safety(entry)
        self.queue.update_entry(entry.path)
        self._refresh_run_button()
        self._render_current()
        self.status.setText(
            f"Đã áp dụng preset “{name}”: {len(matched)} watermark, "
            f"{len(entry.manual_regions)} vùng thủ công."
        )

    def _refresh_run_button(self) -> None:
        ready = [
            e
            for e in self.queue.entries.values()
            if e.status in (Status.READY, Status.PENDING)
            and (e.selected or e.manual_regions or e.report is None)
        ]
        self.run_btn.setEnabled(bool(ready))

    # -- run ---------------------------------------------------------------

    def _start_run(self) -> None:
        current = self.queue.current_entry()
        if self.apply_all.isChecked() and current is not None and current.report:
            self.template_selection = [
                c for c in current.report.candidates if c.key in current.selected
            ]
            self.template_was_auto = current.selected == set(
                current.report.auto_selected_keys()
            )
            self.template_manual = self._manual_template(current)
        else:
            self.template_selection = []
            self.template_manual = []
            self.template_was_auto = False

        pending = self.queue.pending_for_run()
        use_template = bool(self.template_selection or self.template_manual)
        entries = [
            entry
            for entry in pending
            if use_template or entry.selected or entry.manual_regions or entry.report is None
        ]
        if not entries:
            return

        # Materialize the template for already analyzed files before the safety
        # confirmation so its warning count covers the whole batch.
        if use_template:
            for entry in entries:
                if entry.report is None:
                    continue
                if self.template_selection and not entry.selected:
                    entry.selected = self._match_template(entry.report)
                if self.template_manual and not entry.manual_regions:
                    entry.manual_regions = self._manual_from_template(entry.report)
                self.queue.update_entry(entry.path)

        risky = sum(
            region.risk_count for entry in entries for region in entry.manual_regions
        )
        if risky:
            answer = QMessageBox.question(
                self,
                "Vùng thủ công có thể xóa nội dung",
                f"Các vùng thủ công đang chạm khoảng {risky} nội dung nền trên các trang "
                "đã kiểm tra. Bạn vẫn muốn tiếp tục?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if answer != QMessageBox.Yes:
                return

        self.run_queue = entries
        self.run_active = True
        self.run_btn.setEnabled(False)
        self.cancel_btn.show()
        self.progress.show()
        self._run_next()

    def _run_next(self) -> None:
        if not self.run_queue:
            self.run_active = False
            self.waiting_for = None
            self.cancel_btn.hide()
            self.progress.hide()
            self._refresh_run_button()
            self.status.setText("Hoàn tất hàng đợi.")
            return
        entry = self.run_queue.pop(0)
        if entry.status is Status.ANALYZING:
            # Already being scanned - pick it up again when that finishes.
            self.waiting_for = entry.path
        elif entry.report is None:
            self._analyze(entry.path, then_remove=True)
        else:
            if self.template_selection and not entry.selected:
                entry.selected = self._match_template(entry.report)
            if self.template_manual and not entry.manual_regions:
                entry.manual_regions = self._manual_from_template(entry.report)
            self._remove_entry(entry)

    def _remove_entry(self, entry: FileEntry) -> None:
        if entry.report is None or not (entry.selected or entry.manual_regions):
            entry.status = Status.ERROR
            entry.message = "Không có mục nào được chọn."
            self.queue.update_entry(entry.path)
            self._run_next()
            return

        candidates = [c for c in entry.report.candidates if c.key in entry.selected]
        wanted = default_output_path(
            entry.path, self.out_dir.text().strip() or None, self.suffix.text().strip() or "_clean"
        )
        dst = unique_output_path(wanted)
        if dst != wanted:
            self.status.setText(
                f"Đã có {os.path.basename(wanted)} nên lưu thành {os.path.basename(dst)}."
            )
        entry.output = dst
        entry.status = Status.WORKING
        self.queue.update_entry(entry.path)
        self.status.setText(f"Đang xử lý {entry.name} → {os.path.basename(dst)}")

        task = RemoveTask(
            entry.path,
            dst,
            candidates,
            list(entry.manual_regions),
            entry.report,
            self.aggressive.isChecked(),
        )
        task.signals.progress.connect(self._on_progress)
        task.signals.done.connect(self._on_removed)
        task.signals.failed.connect(self._on_failed)
        self.active_remove = task
        self._keep(task)
        self.pool.start(task)

    def _on_removed(self, payload: tuple[str, RunReport]) -> None:
        path, run = payload
        entry = self.queue.entry(path)
        self.active_remove = None
        if entry is None:
            return
        entry.status = Status.DONE
        entry.message = f"{run.images_removed} ảnh · {run.areas_redacted} vùng chữ/vector"
        if run.warnings:
            entry.message += f" · {len(run.warnings)} cảnh báo"
        self.queue.update_entry(path)
        self.status.setText(f"Đã lưu {os.path.basename(run.dst)}. Đang đối chiếu…")

        if entry.report is not None:
            candidates = [c for c in entry.report.candidates if c.key in entry.selected]
            pages = list(
                dict.fromkeys(
                    [h.page_no for c in candidates for h in c.hits]
                    + [page for region in entry.manual_regions for page in region.pages]
                )
            )[:VERIFY_SAMPLE]
            if pages:
                name = os.path.basename(run.dst)
                rects = [c.rect for c in candidates] + [r.rect for r in entry.manual_regions]
                task = VerifyTask(path, run.dst, pages, rects)
                task.signals.done.connect(
                    lambda verdict: self.status.setText(f"Đã lưu {name}. {verdict}")
                )
                task.signals.failed.connect(
                    lambda _msg: self.status.setText(f"Đã lưu {name}.")
                )
                self._keep(task)
                self.render_pool.start(task)
        self._run_next()

    def _on_progress(self, progress) -> None:
        if progress.total:
            self.progress.setRange(0, progress.total)
            self.progress.setValue(progress.current)
        else:
            self.progress.setRange(0, 0)
        self.progress.show()
        if progress.detail:
            self.status.setText(progress.detail)

    def _on_failed(self, message: str) -> None:
        path, _, detail = message.partition("\n")
        entry = self.queue.entry(path)
        if entry is not None:
            entry.status = Status.ERROR
            entry.message = detail
            self.queue.update_entry(path)
        self.active_remove = None
        self.progress.hide()
        self.status.setText(detail or message)
        if "mật khẩu" in detail or "thay đổi" in detail:
            QMessageBox.warning(self, "Không xử lý được file", f"{path}\n\n{detail}")
        self._run_next()

    def _cancel(self) -> None:
        self.run_queue = []
        if self.active_remove is not None:
            self.active_remove.cancel.set()
            self.status.setText("Đang hủy…")
        self.cancel_btn.hide()
        self._refresh_run_button()
