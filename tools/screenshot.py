"""Render the window to a PNG for visual review (offscreen, no display needed)."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from PySide6.QtCore import QElapsedTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from pwr_gui import theme  # noqa: E402
from pwr_gui.main_window import MainWindow  # noqa: E402


def main() -> int:
    pdf = sys.argv[1]
    out = sys.argv[2] if len(sys.argv) > 2 else "window.png"

    app = QApplication([])
    app.setStyleSheet(theme.STYLESHEET)
    window = MainWindow()
    window.resize(1400, 900)
    window.show()
    window._add([pdf])

    entry = window.queue.entry(os.path.abspath(pdf))
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < 180_000:
        app.processEvents()
        window.pool.waitForDone(50)
        window.render_pool.waitForDone(50)
        app.processEvents()
        if entry.report is not None and not window.preview.pixmap_item.pixmap().isNull():
            break

    if "--after" in sys.argv:
        window.preview.toggle_btn.setChecked(True)
        timer.restart()
        while timer.elapsed() < 120_000:
            app.processEvents()
            window.render_pool.waitForDone(50)
            app.processEvents()
            if not window.render_pool.activeThreadCount():
                break

    for _ in range(40):
        app.processEvents()
    window.grab().save(out, "PNG")
    print(f"saved {out} | status={entry.status.value} | selected={len(entry.selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
