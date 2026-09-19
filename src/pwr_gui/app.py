"""Application entry point."""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import theme
from .main_window import MainWindow
from .resources import app_icon_path


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(argv)
    app.setApplicationName("PDF Watermark Remover")
    app.setWindowIcon(QIcon(str(app_icon_path())))
    app.setStyleSheet(theme.STYLESHEET)

    window = MainWindow()
    window.show()

    files = [a for a in argv[1:] if a.lower().endswith(".pdf")]
    if files:
        window._add(files)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
