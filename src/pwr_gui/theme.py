"""A focused dark theme for inspecting and cleaning PDF documents."""

INK = "#091018"
SURFACE = "#111a24"
SURFACE_RAISED = "#182433"
CANVAS = "#070b10"
BORDER = "#263648"
BORDER_SOFT = "#1b2836"
TEXT = "#edf4fb"
TEXT_DIM = "#8fa2b7"
ACCENT = "#f5a800"
ACCENT_HOVER = "#ffba24"
ACCENT_DIM = "#795a0c"
DANGER = "#ef6a61"
OK = "#4ac27c"

PANEL_CONTENT_MARGINS = (14, 12, 14, 12)
PANEL_SPACING = 10
WORKSPACE_GUTTER = 16

STYLESHEET = f"""
QWidget {{
    color: {TEXT};
    font-family: 'Segoe UI Variable', 'Segoe UI', sans-serif;
    font-size: 13px;
}}
QWidget#MainWindow {{ background: {INK}; }}
QFrame#Card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#WorkspacePanel {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QFrame#HeaderDivider, QFrame#PanelRule {{ background: {BORDER_SOFT}; border: none; }}
QLabel#PanelTitle {{
    background: transparent;
    border: none;
    color: #b8c7d6;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 1.5px;
}}
QLabel#Hint, QLabel#PanelSummary {{ color: {TEXT_DIM}; }}
QLabel#PanelSummary {{ font-size: 12px; }}
QLabel#DocTitle {{ font-size: 17px; font-weight: 700; }}
QLabel#AppLogo {{ background: transparent; border: none; }}
QLabel#FormLabel {{
    color: {TEXT_DIM};
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel#PageCounter {{ color: #b8c7d6; font-size: 12px; padding: 0 6px; }}
QLabel#PreviewEmpty {{
    background: {CANVAS};
    border: 1px solid {BORDER};
    border-radius: 12px;
    color: {TEXT_DIM};
}}
QPushButton {{
    background: {SURFACE_RAISED};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 14px;
    color: {TEXT};
}}
QPushButton:hover {{ border-color: #3b526b; background: #1d2b3c; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:focus {{ border-color: {ACCENT}; }}
QPushButton:disabled {{ color: #526170; border-color: {BORDER_SOFT}; background: #111923; }}
QPushButton#Primary {{
    background: {ACCENT};
    color: #1d1600;
    border: none;
    font-weight: 800;
    padding: 12px 24px;
    font-size: 13px;
}}
QPushButton#Primary:hover {{ background: {ACCENT_HOVER}; color: #1d1600; }}
QPushButton#Primary:disabled {{ background: #3d3522; color: #817862; }}
QPushButton#AccentOutline {{
    background: transparent;
    border-color: {ACCENT_DIM};
    color: #ffd66f;
    font-weight: 600;
}}
QPushButton#AccentOutline:hover {{ border-color: {ACCENT}; color: {ACCENT_HOVER}; }}
QPushButton#Ghost {{ background: transparent; border-color: transparent; color: {TEXT_DIM}; }}
QPushButton#Ghost:hover {{ background: #121c27; color: {TEXT}; border-color: transparent; }}
QPushButton#NavButton {{ min-width: 18px; padding: 7px 10px; }}
QListWidget, QScrollArea {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 12px;
    outline: none;
}}
QScrollArea#CandidateScroll QWidget#CandidateTrack {{ background: {SURFACE}; }}
QGraphicsView {{
    background: {CANVAS};
    border: 1px solid {BORDER};
    border-radius: 12px;
}}
QListWidget::item {{
    padding: 0;
    border-bottom: 1px solid {BORDER_SOFT};
    color: {TEXT};
}}
QListWidget::item:hover {{ background: #15202c; }}
QListWidget::item:selected {{
    background: {SURFACE_RAISED};
    border-left: 3px solid {ACCENT};
    color: {TEXT};
}}
QFrame#QueueRow {{ background: transparent; border: none; }}
QLabel#QueueMark, QLabel#QueueName, QLabel#QueueDetail {{ background: transparent; }}
QLabel#QueueName {{ color: {TEXT}; font-size: 12px; font-weight: 600; }}
QLabel#QueueDetail {{ color: {TEXT_DIM}; font-size: 11px; }}
QToolButton#DeleteIcon {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
    color: #708297;
    font-size: 19px;
    font-weight: 500;
}}
QToolButton#DeleteIcon:hover {{
    background: #2a1c22;
    border-color: #61313a;
    color: {DANGER};
}}
QToolButton#DeleteIcon:pressed {{ background: #3a2028; }}
QCheckBox {{ spacing: 9px; color: #c9d5e1; }}
QCheckBox::indicator {{
    width: 17px; height: 17px;
    border: 1.5px solid {BORDER};
    border-radius: 5px;
    background: {INK};
}}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QCheckBox::indicator:hover {{ border-color: {ACCENT}; }}
QProgressBar {{
    background: {SURFACE_RAISED};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QLineEdit {{
    background: {INK};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 8px 11px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:hover {{ border-color: #3b526b; }}
QLineEdit:focus {{ border-color: {ACCENT}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: #34475b; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: #496079; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QSplitter#WorkspaceSplitter::handle {{ background: {INK}; }}
QSplitter#WorkspaceSplitter::handle:hover {{ background: #111b26; }}
QToolTip {{
    background: {SURFACE_RAISED};
    color: {TEXT};
    border: 1px solid {BORDER};
    padding: 7px;
}}
"""
