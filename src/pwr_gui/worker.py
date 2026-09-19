"""Background workers - every PDF operation stays off the UI thread."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from pwr import AnalyzeReport, Candidate, ManualRegion, RemovalExecutor, RunReport, analyze
from pwr.models import Progress
from pwr.pipeline import render_page_after, render_page_png
from pwr.remove import Cancelled


class _Signals(QObject):
    progress = Signal(object)
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    """Base runnable that outlives the pool, so queued signals still arrive."""

    def __init__(self) -> None:
        super().__init__()
        # Qt deletes an auto-delete runnable the moment run() returns, which
        # drops the queued done/failed signal before the UI thread sees it.
        self.setAutoDelete(False)
        self.signals = _Signals()

    def emit_done(self, payload) -> None:
        self._emit(self.signals.done, payload)

    def emit_failed(self, message: str) -> None:
        self._emit(self.signals.failed, message)

    @staticmethod
    def _emit(signal, payload) -> None:
        try:
            signal.emit(payload)
        except RuntimeError:
            pass  # the window closed while this task was still running


class AnalyzeTask(_Task):
    def __init__(self, path: str) -> None:
        super().__init__()
        self.path = path

    @Slot()
    def run(self) -> None:
        try:
            report = analyze(self.path, on_progress=self.signals.progress.emit)
            self.emit_done((self.path, report))
        except Exception as error:  # surfaced in the file list, never silently dropped
            self.emit_failed(f"{self.path}\n{error}")


class RemoveTask(_Task):
    def __init__(
        self,
        path: str,
        dst: str,
        candidates: list[Candidate],
        manual_regions: list[ManualRegion],
        report: AnalyzeReport,
        aggressive: bool = False,
    ) -> None:
        super().__init__()
        self.path = path
        self.dst = dst
        self.candidates = candidates
        self.manual_regions = manual_regions
        self.report = report
        self.aggressive = aggressive
        self.cancel = threading.Event()

    @Slot()
    def run(self) -> None:
        try:
            run: RunReport = RemovalExecutor(self.aggressive).run(
                self.path,
                self.dst,
                self.candidates,
                manual_regions=self.manual_regions,
                on_progress=self.signals.progress.emit,
                cancel=self.cancel,
                expected_size=self.report.doc.size_bytes,
                expected_mtime=self.report.doc.mtime,
            )
            self.emit_done((self.path, run))
        except Cancelled:
            self.emit_failed(f"{self.path}\nĐã hủy theo yêu cầu.")
        except Exception as error:
            self.emit_failed(f"{self.path}\n{error}")


class VerifyTask(_Task):
    """Pixel-diff proof that only the selected marks changed."""

    def __init__(self, src: str, dst: str, pages: list[int], rects: list) -> None:
        super().__init__()
        self.src = src
        self.dst = dst
        self.pages = pages
        self.rects = rects

    @Slot()
    def run(self) -> None:
        try:
            from pwr import compare_pages, summarize

            self.emit_done(summarize(compare_pages(self.src, self.dst, self.pages, self.rects)))
        except Exception as error:
            self.emit_failed(str(error))


class RenderTask(_Task):
    """Renders one page, optionally as it will look after removal."""

    def __init__(
        self,
        path: str,
        page_no: int,
        candidates: list[Candidate],
        manual_regions: list[ManualRegion],
        token: int,
    ) -> None:
        super().__init__()
        self.path = path
        self.page_no = page_no
        self.candidates = candidates
        self.manual_regions = manual_regions
        self.token = token

    @Slot()
    def run(self) -> None:
        try:
            import pymupdf

            doc = pymupdf.open(self.path)
            try:
                before = render_page_png(doc, self.page_no)
            finally:
                doc.close()
            after = None
            if self.candidates or any(
                region.applies_to(self.page_no) for region in self.manual_regions
            ):
                after = render_page_after(
                    self.path, self.page_no, self.candidates, self.manual_regions
                )
            self.emit_done((self.token, self.page_no, before, after))
        except Exception as error:
            self.emit_failed(str(error))


__all__ = ["AnalyzeTask", "RemoveTask", "RenderTask", "Progress"]
