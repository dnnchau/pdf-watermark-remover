"""Headless smoke test: the window really analyses, lists and toggles marks."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSplitter  # noqa: E402

from pwr_gui.main_window import MainWindow  # noqa: E402
from pwr_gui.panel_header import PanelHeader  # noqa: E402
from pwr_gui.file_queue import QueueRow  # noqa: E402
from pwr_gui import theme  # noqa: E402


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


def _pump(app, window, predicate, timeout_ms: int = 60_000) -> bool:
    """Spin the event loop until predicate() or timeout."""
    from PySide6.QtCore import QDeadlineTimer, QElapsedTimer

    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < timeout_ms:
        app.processEvents()
        window.pool.waitForDone(50)
        window.render_pool.waitForDone(50)
        app.processEvents()
        if predicate():
            return True
        QDeadlineTimer(10)
    return predicate()


def test_workspace_panels_share_the_same_top_edge_and_insets(app):
    window = MainWindow()
    window.resize(1360, 880)
    window.show()
    app.processEvents()

    splitter = window.findChild(QSplitter)
    panels = [splitter.widget(index) for index in range(splitter.count())]

    assert [panel.y() for panel in panels] == [0, 0, 0]
    assert [panel.layout().contentsMargins().top() for panel in panels] == [12, 12, 12]
    assert [panel.layout().contentsMargins().left() for panel in panels] == [14, 14, 14]
    assert [panel.objectName() for panel in panels] == ["WorkspacePanel"] * 3
    assert splitter.handleWidth() == theme.WORKSPACE_GUTTER
    assert len(window.findChildren(PanelHeader)) == 3
    assert not window.windowIcon().isNull()

    window.close()


def test_queue_row_can_remove_its_own_file(app, tmp_path):
    window = MainWindow()
    first = str(tmp_path / "first.pdf")
    second = str(tmp_path / "second.pdf")
    window.queue.add_paths([first, second])

    first_item = window.queue.list.item(0)
    first_row = window.queue.list.itemWidget(first_item)
    assert isinstance(first_row, QueueRow)

    first_row.remove_requested.emit(first)

    assert window.queue.entry(first) is None
    assert window.queue.entry(second) is not None
    assert window.queue.list.count() == 1

    window.close()


def test_window_analyses_and_lists_candidates(app, marked_pdf, tmp_path):
    window = MainWindow()
    window.out_dir.setText(str(tmp_path))
    window._add([marked_pdf])

    entry = window.queue.entry(os.path.abspath(marked_pdf))
    assert _pump(app, window, lambda: entry.report is not None), "analysis never finished"

    assert entry.selected, "high-confidence marks should be pre-ticked"
    assert window.picker._cards, "candidate cards should be rendered"
    assert window.run_btn.isEnabled()

    key = next(iter(entry.selected))
    window._toggle_key(key)
    assert key not in entry.selected
    window._toggle_key(key)
    assert key in entry.selected

    assert _pump(app, window, lambda: not window.preview.pixmap_item.pixmap().isNull())
    assert window.preview._boxes, "clickable mark boxes should be drawn on the page"

    window.close()


def test_batch_run_cleans_every_queued_file(app, tmp_path):
    from conftest import build_pdf

    from pwr_gui.file_queue import Status

    first = build_pdf(str(tmp_path / "a.pdf"), pages=4)
    second = build_pdf(str(tmp_path / "b.pdf"), pages=4)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    window = MainWindow()
    window.out_dir.setText(str(out_dir))
    window._add([first, second])

    entries = [window.queue.entry(os.path.abspath(p)) for p in (first, second)]
    assert _pump(app, window, lambda: all(e.report is not None for e in entries))

    window._start_run()
    assert _pump(
        app, window, lambda: all(e.status is Status.DONE for e in entries), 120_000
    ), [e.status for e in entries]

    outputs = sorted(os.listdir(out_dir))
    assert outputs == ["a_clean.pdf", "b_clean.pdf"]
    window.close()


def test_nothing_is_removed_without_a_selection(app, clean_pdf):
    window = MainWindow()
    window._add([clean_pdf])

    entry = window.queue.entry(os.path.abspath(clean_pdf))
    assert _pump(app, window, lambda: entry.report is not None)

    assert entry.selected == set()
    assert not window.run_btn.isEnabled()
    window.close()
