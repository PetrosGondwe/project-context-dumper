"""Visual design tokens for Project Context Dumper.

Design direction: Rufus-style Light Theme.
Highly utilitarian, focused on maximum contrast and readability.
Light gray backgrounds, black text, standard Windows-style controls,
and clear bold section headers with horizontal separators.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

# -- Palette -----------------------------------------------------------------
BG_BASE = "#F5F5F5"        # main window light gray
BG_PANEL = "#FFFFFF"       # grouped-section / card surface (white)
BG_INSET = "#FFFFFF"       # input fields and results (white)
BG_SIDEBAR = "#FFFFFF"     # pure white sidebar
BORDER = "#000000"         # structural hairlines (black)
BORDER_HOVER = "#333333"
SIDEBAR_BORDER = "#000000" # the sidebar's right border (black)
TEXT_PRIMARY = "#000000"   # pure black text
TEXT_MUTED = "#555555"     # dark gray for secondary text
ACCENT = "#000000"         # black for active states
ACCENT_HOVER = "#333333"
ACCENT_INK = "#FFFFFF"     # text color sitting on top of the accent fill
PRIMARY_BTN_BG = "#E6E6E6" # Primary button background (Rufus gray)
PRIMARY_BTN_BORDER = "#C0C0C0"
DANGER = "#D14343"         # failures only, never decorative

FONT_SANS = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
FONT_MONO = '"Consolas", "Menlo", "DejaVu Sans Mono", monospace'


def build_palette() -> QPalette:
    """A light QPalette to back the QSS below."""
    pal = QPalette()
    pal.setColor(QPalette.ColorRole.Window, QColor(BG_BASE))
    pal.setColor(QPalette.ColorRole.WindowText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Base, QColor(BG_INSET))
    pal.setColor(QPalette.ColorRole.AlternateBase, QColor(BG_PANEL))
    pal.setColor(QPalette.ColorRole.Text, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.Button, QColor(BG_PANEL))
    pal.setColor(QPalette.ColorRole.ButtonText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.BrightText, QColor(DANGER))
    pal.setColor(QPalette.ColorRole.Highlight, QColor("#E6E6E6"))
    pal.setColor(QPalette.ColorRole.HighlightedText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.ToolTipBase, QColor(BG_PANEL))
    pal.setColor(QPalette.ColorRole.ToolTipText, QColor(TEXT_PRIMARY))
    pal.setColor(QPalette.ColorRole.PlaceholderText, QColor(TEXT_MUTED))
    pal.setColor(QPalette.ColorRole.Link, QColor("#005A9E"))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(TEXT_MUTED))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(TEXT_MUTED))
    pal.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(TEXT_MUTED))
    return pal


def build_stylesheet() -> str:
    """Return the global Qt stylesheet as an f-string."""
    return f"""
    QMainWindow, QWidget {{
        background-color: {BG_BASE};
        color: {TEXT_PRIMARY};
        font-family: {FONT_SANS};
        font-size: 13px;
    }}

    /* ---- Sidebar ---- */
    QFrame#sidebar {{
        background-color: {BG_SIDEBAR};
        border-right: 1px solid {SIDEBAR_BORDER};
    }}
    QWidget#sidebarTitleContainer {{
        background-color: {BG_SIDEBAR};
        border-bottom: 2px solid {BORDER};
        padding: 16px 14px;
    }}
    QLabel#sidebarTitle {{
        font-family: {FONT_SANS};
        font-size: 28px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
        background: transparent;
    }}
    QLabel#sidebarTitleSub {{
        font-family: {FONT_SANS};
        font-size: 28px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
        background: transparent;
        padding-left: 1.2em;   /* aligns under the 'j' of Project */
    }}
    QPushButton#sidebarButton {{
        background-color: {BG_SIDEBAR};
        color: {TEXT_PRIMARY};
        border: none;
        border-left: 4px solid transparent;
        padding: 12px 14px;
        text-align: left;
        font-weight: 500;
        border-radius: 0;
        font-family: {FONT_SANS};
        font-size: 14px;
    }}
    QPushButton#sidebarButton:hover {{
        background-color: #E6E6E6;
        color: {TEXT_PRIMARY};
    }}
    QPushButton#sidebarButton:checked {{
        color: {TEXT_PRIMARY};
        border-left-color: {BORDER};
        background-color: #E6E6E6;
        font-weight: 700;
    }}
    QLabel#versionLabel {{
        color: {TEXT_MUTED};
        font-size: 11px;
        padding: 8px 0;
    }}

    /* ---- General widgets ---- */
    QWidget#settingsScrollContent, QScrollArea {{
        background-color: {BG_BASE};
        border: none;
    }}

    QLabel {{
        background: transparent;
        color: {TEXT_PRIMARY};
    }}
    QCheckBox {{
        background: transparent;
        spacing: 8px;
        padding: 3px 0;
    }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1px solid {BORDER};
        border-radius: 2px;
        background-color: {BG_INSET};
    }}
    QCheckBox::indicator:hover {{
        border-color: {BORDER_HOVER};
    }}
    QCheckBox::indicator:checked {{
        background-color: {BG_PANEL};
        border-color: {BORDER};
    }}
    QCheckBox::indicator:disabled {{
        border-color: {TEXT_MUTED};
        background-color: {BG_BASE};
    }}
    QLabel#appTitleLabel {{
        font-size: 20px;
        font-weight: 700;
        color: {TEXT_PRIMARY};
    }}
    QLabel#appTaglineLabel {{
        color: {TEXT_MUTED};
        font-size: 12px;
    }}
    QLabel#mutedLabel, QLabel#sectionNoteLabel {{
        color: {TEXT_MUTED};
        font-size: 12px;
    }}
    QLabel#statusLine {{
        color: {TEXT_PRIMARY};
        font-size: 12px;
        font-family: {FONT_SANS};
    }}
    QFrame#titleBlock {{
        border-bottom: 2px solid {BORDER};
    }}

    QLabel#folderPathLabel, QLineEdit#outputPathEdit,
    QPlainTextEdit#excludedDirsEdit, QPlainTextEdit#includeExtEdit,
    QTextEdit#resultsBox {{
        font-family: {FONT_MONO};
    }}

    QFrame#dropArea {{
        border: 1px dashed {BORDER};
        border-radius: 0;
        background-color: {BG_PANEL};
    }}
    QFrame#dropArea[dragging="true"] {{
        background-color: #E6E6E6;
    }}

    /* Group Boxes: Rufus Style - Bold Title with Horizontal Line */
    QGroupBox {{
        background-color: transparent;
        border: none;
        border-bottom: 2px solid {BORDER};
        margin-top: 14px;
        padding: 10px 0 14px 0;
        font-weight: 700;
        font-family: {FONT_SANS};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 0px;
        padding: 0 4px;
        color: {TEXT_PRIMARY};
        background-color: transparent;
    }}

    /* Buttons: Rufus Standard */
    QPushButton {{
        background-color: #F0F0F0;
        color: {TEXT_PRIMARY};
        border: 1px solid {PRIMARY_BTN_BORDER};
        border-radius: 2px;
        padding: 6px 16px;
        font-family: {FONT_SANS};
        font-size: 13px;
    }}
    QPushButton:hover:!disabled {{
        background-color: #E6E6E6;
        border-color: {BORDER};
    }}
    QPushButton:pressed:!disabled {{
        background-color: #CCCCCC;
    }}
    QPushButton:disabled {{
        color: {TEXT_MUTED};
        border-color: {BORDER_HOVER};
        background-color: #F5F5F5;
    }}
    QPushButton#primaryButton {{
        background-color: {PRIMARY_BTN_BG};
        color: {TEXT_PRIMARY};
        border: 1px solid {PRIMARY_BTN_BORDER};
        font-weight: 700;
    }}
    QPushButton#primaryButton:hover:!disabled {{
        background-color: #D9D9D9;
        border-color: {BORDER};
    }}
    QPushButton#primaryButton:disabled {{
        background-color: #F5F5F5;
        border-color: {BORDER_HOVER};
        color: {TEXT_MUTED};
    }}

    QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background-color: {BG_INSET};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 2px;
        padding: 4px 6px;
        selection-background-color: #CCCCCC;
        selection-color: {TEXT_PRIMARY};
    }}
    QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {BORDER_HOVER};
        background-color: #FCFCFC;
    }}
    QLineEdit:disabled, QPlainTextEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {TEXT_MUTED};
        border-color: {BORDER_HOVER};
        background-color: #F5F5F5;
    }}
    QComboBox QAbstractItemView {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        selection-background-color: #E6E6E6;
        selection-color: {TEXT_PRIMARY};
        outline: none;
    }}

    /* ---- QListWidget (for Settings checklists) ---- */
    QListWidget {{
        background-color: {BG_INSET};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 2px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 4px 6px;
        border-bottom: 1px solid #E0E0E0;
    }}
    QListWidget::item:selected {{
        background-color: #E6E6E6;
        color: {TEXT_PRIMARY};
    }}
    QListWidget::item:hover {{
        background-color: #F0F0F0;
    }}
    QListWidget::item:checked {{
        color: {TEXT_PRIMARY};
    }}
    QLineEdit#addItemLineEdit {{
        background-color: {BG_INSET};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        border-radius: 2px;
        padding: 4px 6px;
    }}

    /* Progress Bar: Rufus Status Style */
    QProgressBar {{
        border: 1px solid {BORDER};
        border-radius: 0;
        background-color: {BG_PANEL};
        text-align: center;
        color: {TEXT_PRIMARY};
        font-weight: 700;
        min-height: 20px;
    }}
    QProgressBar::chunk {{
        background-color: #A0A0A0;
    }}

    QMenuBar {{
        background-color: {BG_BASE};
        color: {TEXT_PRIMARY};
        border-bottom: 1px solid {BORDER};
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 4px 10px;
    }}
    QMenuBar::item:selected {{
        background-color: #E6E6E6;
    }}
    QMenu {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
    }}
    QMenu::item:selected {{
        background-color: #E6E6E6;
        color: {TEXT_PRIMARY};
    }}

    QStatusBar {{
        background-color: {BG_BASE};
        color: {TEXT_MUTED};
        border-top: 1px solid {BORDER};
    }}

    QScrollBar:vertical {{
        background: {BG_BASE};
        width: 11px;
        margin: 0;
    }}
    QScrollBar::handle:vertical {{
        background: #C0C0C0;
        border-radius: 2px;
        min-height: 24px;
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: none;
    }}

    QToolTip {{
        background-color: {BG_PANEL};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER};
        padding: 4px 6px;
    }}
    """


STYLESHEET = build_stylesheet()