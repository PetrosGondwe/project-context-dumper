"""PySide6 desktop UI for Project Context Dumper.

Visual design lives in theme.py — see that module's docstring for the
rationale. This module focuses on structure and behavior.
"""
from __future__ import annotations

import html as html_lib
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import __version__, theme
from .config import Config, default_config_path
from .dumper import Mode, default_output_path
from .worker import DumpWorker

APP_TITLE = "Project Context Dumper"
TAGLINE = "Turn project directories and PDF collections into LLM-ready context."
DEVELOPER_NAME = "Chipu_Data_Labs"
CONTACT_EMAIL = "2012peter.c@gmail.com"
CONTACT_PHONE = "+265881050865"
CONTACT_YEAR = "2026"


def _open_containing_folder(path: Path) -> None:
    folder = path.parent
    try:
        if sys.platform.startswith("win"):
            subprocess.run(["explorer", f"/select,{path}"])
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(path)])
        else:
            subprocess.run(["xdg-open", str(folder)])
    except Exception:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))


def _render_summary_html(pairs: Sequence[Tuple[str, str]], sections: Sequence[Tuple[str, List[str]]] = ()) -> str:
    """A small, aligned label/value readout plus optional bulleted sections
    (skipped files, multi-part output paths) — all dynamic content is
    HTML-escaped since real filenames can legally contain '<', '&', etc."""
    rows = "".join(
        f'<tr><td style="color:{theme.TEXT_MUTED}; padding-right:18px; white-space:nowrap;">'
        f'{html_lib.escape(str(label))}</td>'
        f'<td style="color:{theme.TEXT_PRIMARY};">{html_lib.escape(str(value))}</td></tr>'
        for label, value in pairs
    )
    html = f'<div style="font-family:{theme.FONT_MONO}; font-size:12px;">' \
           f'<table cellspacing="0" cellpadding="2">{rows}</table>'
    for heading, items in sections:
        html += (
            f'<p style="color:{theme.TEXT_PRIMARY}; margin-top:14px; margin-bottom:4px; font-weight:bold;">'
            f'{html_lib.escape(heading)}</p>'
        )
        html += '<ul style="margin:0; padding-left:18px;">'
        for item in items:
            html += f'<li style="color:{theme.TEXT_MUTED};">{html_lib.escape(str(item))}</li>'
        html += "</ul>"
    html += "</div>"
    return html


class CheckListWidget(QWidget):
    """A reusable checkable list with Add and Remove buttons."""

    def __init__(self, items: set, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.ExtendedSelection)
        self.list.setObjectName("checkListWidget")
        self._populate(items)
        layout.addWidget(self.list)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("Add")
        self.add_btn.clicked.connect(self._add_item)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.clicked.connect(self._remove_selected)
        btn_row.addWidget(self.add_btn)
        btn_row.addWidget(self.remove_btn)
        btn_row.addStretch(1)
        layout.addLayout(btn_row)

        self.add_line = QLineEdit()
        self.add_line.setObjectName("addItemLineEdit")
        self.add_line.setPlaceholderText("Type new item and press Add…")
        layout.addWidget(self.add_line)

    def _populate(self, items: set) -> None:
        self.list.clear()
        for item in sorted(items):
            list_item = QListWidgetItem(item)
            list_item.setFlags(list_item.flags() | Qt.ItemIsUserCheckable)
            list_item.setCheckState(Qt.Checked)
            self.list.addItem(list_item)

    def _add_item(self) -> None:
        text = self.add_line.text().strip()
        if not text:
            return
        existing = {self.list.item(i).text() for i in range(self.list.count())}
        if text in existing:
            QMessageBox.information(self, "Already exists", f"'{text}' is already in the list.")
            return
        list_item = QListWidgetItem(text)
        list_item.setFlags(list_item.flags() | Qt.ItemIsUserCheckable)
        list_item.setCheckState(Qt.Checked)
        self.list.addItem(list_item)
        self.add_line.clear()

    def _remove_selected(self) -> None:
        for item in self.list.selectedItems():
            self.list.takeItem(self.list.row(item))

    def set_items(self, items: set) -> None:
        self._populate(items)

    def get_checked(self) -> set:
        return {
            self.list.item(i).text()
            for i in range(self.list.count())
            if self.list.item(i).checkState() == Qt.Checked
        }

    def get_all_items(self) -> set:
        return {self.list.item(i).text() for i in range(self.list.count())}


class DropArea(QFrame):
    """A dashed-border zone that accepts exactly one dropped folder."""

    def __init__(self, on_folder_chosen, parent=None):
        super().__init__(parent)
        self._on_folder_chosen = on_folder_chosen
        self.setAcceptDrops(True)
        self.setObjectName("dropArea")
        self.setProperty("dragging", False)
        self.setMinimumHeight(120)
        self.setFrameShape(QFrame.NoFrame)
        layout = QVBoxLayout(self)
        self.label = QLabel("Drag & drop a project folder here\nor use \u201cChoose Folder\u201d below")
        self.label.setObjectName("mutedLabel")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label)

    def _set_dragging(self, dragging: bool) -> None:
        self.setProperty("dragging", dragging)
        self.style().unpolish(self)
        self.style().polish(self)

    @staticmethod
    def _extract_single_dir(mime) -> Optional[str]:
        if not mime.hasUrls():
            return None
        dirs, files = [], []
        for url in mime.urls():
            if not url.isLocalFile():
                continue
            p = url.toLocalFile()
            (dirs if os.path.isdir(p) else files).append(p)
        if len(dirs) == 1 and not files:
            return dirs[0]
        return None

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._extract_single_dir(event.mimeData()):
            event.acceptProposedAction()
            self._set_dragging(True)
        else:
            event.ignore()

    def dragLeaveEvent(self, event) -> None:
        self._set_dragging(False)

    def dropEvent(self, event: QDropEvent) -> None:
        self._set_dragging(False)
        path = self._extract_single_dir(event.mimeData())
        if path:
            self._on_folder_chosen(path)
            event.acceptProposedAction()
        else:
            QMessageBox.warning(
                self, "Unsupported drop",
                "Please drop exactly one folder.\n\n"
                "Individual files, or multiple items at once, aren't supported — "
                "use “Choose Folder” instead if you need to pick something specific.",
            )
            event.ignore()


class SettingsPage(QWidget):
    """An embedded page (not a popup window) showing all Settings fields."""

    saved = Signal(object)   # emits the new Config
    cancelled = Signal()

    def __init__(self, config: Config, parent=None):
        super().__init__(parent)
        self._config = config

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 18, 24, 18)
        outer.setSpacing(14)

        header_row = QHBoxLayout()
        back_btn = QPushButton("\u2190 Back")
        back_btn.clicked.connect(self.cancelled.emit)
        header_row.addWidget(back_btn)
        title = QLabel("Settings")
        title.setObjectName("appTitleLabel")
        header_row.addWidget(title)
        header_row.addStretch(1)
        outer.addLayout(header_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_widget = QWidget()
        form_widget.setObjectName("settingsScrollContent")
        form = QVBoxLayout(form_widget)
        form.setSpacing(14)
        scroll.setWidget(form_widget)
        outer.addWidget(scroll, 1)

        exclusions_group = QGroupBox("Exclusions and File Types")
        exclusions_layout = QVBoxLayout(exclusions_group)

        exclusions_layout.addWidget(QLabel("Excluded directory names (check to exclude):"))
        self.excluded_dirs_list = CheckListWidget(config.excluded_dirs)
        self.excluded_dirs_list.setMinimumHeight(150)
        exclusions_layout.addWidget(self.excluded_dirs_list)

        exclusions_layout.addWidget(QLabel("Included source file extensions (check to include):"))
        self.include_ext_list = CheckListWidget(config.include_ext)
        self.include_ext_list.setMinimumHeight(150)
        exclusions_layout.addWidget(self.include_ext_list)

        form.addWidget(exclusions_group)

        size_group = QGroupBox("Size Limits")
        size_layout = QHBoxLayout(size_group)
        size_layout.addWidget(QLabel("Max source file:"))
        self.max_file_size = QDoubleSpinBox()
        self.max_file_size.setRange(0.01, 1024)
        self.max_file_size.setSuffix(" MB")
        size_layout.addWidget(self.max_file_size)
        size_layout.addSpacing(24)
        size_layout.addWidget(QLabel("Max PDF:"))
        self.max_pdf_size = QDoubleSpinBox()
        self.max_pdf_size.setRange(0.1, 4096)
        self.max_pdf_size.setSuffix(" MB")
        size_layout.addWidget(self.max_pdf_size)
        size_layout.addStretch(1)
        form.addWidget(size_group)

        traversal_group = QGroupBox("Traversal")
        traversal_layout = QVBoxLayout(traversal_group)
        self.include_hidden_cb = QCheckBox("Include hidden files/folders (dotfiles)")
        traversal_layout.addWidget(self.include_hidden_cb)
        self.follow_symlinks_cb = QCheckBox("Follow symlinked directories (cycle-safe)")
        traversal_layout.addWidget(self.follow_symlinks_cb)
        form.addWidget(traversal_group)

        chunk_group = QGroupBox("Output Splitting")
        chunk_layout = QVBoxLayout(chunk_group)
        chunk_row = QHBoxLayout()
        self.chunk_cb = QCheckBox("Split output if larger than:")
        chunk_row.addWidget(self.chunk_cb)
        self.chunk_spin = QSpinBox()
        self.chunk_spin.setRange(1_000, 10_000_000)
        self.chunk_spin.setSingleStep(10_000)
        self.chunk_spin.setSuffix(" characters")
        self.chunk_cb.toggled.connect(self.chunk_spin.setEnabled)
        chunk_row.addWidget(self.chunk_spin)
        chunk_row.addStretch(1)
        chunk_layout.addLayout(chunk_row)

        preset_row = QHBoxLayout()
        preset_row.addWidget(QLabel("Quick presets:"))
        self.chunk_preset_combo = QComboBox()
        self.chunk_preset_combo.addItems([
            "\u2014",
            "ChatGPT web paste (~100,000 chars)",
            "Claude web paste (~350,000 chars)",
        ])
        self.chunk_preset_combo.currentIndexChanged.connect(self._apply_chunk_preset)
        preset_row.addWidget(self.chunk_preset_combo)
        preset_row.addStretch(1)
        chunk_layout.addLayout(preset_row)

        note = QLabel(
            "Splitting only happens between whole files, never in the middle of one — "
            "a part may run a bit over this size. Presets are rough starting points, "
            "not guaranteed platform limits."
        )
        note.setObjectName("sectionNoteLabel")
        note.setWordWrap(True)
        chunk_layout.addWidget(note)
        form.addWidget(chunk_group)

        form.addStretch(1)

        button_row = QHBoxLayout()
        restore_btn = QPushButton("Restore Defaults")
        restore_btn.clicked.connect(self._restore_defaults)
        button_row.addWidget(restore_btn)
        button_row.addStretch(1)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.cancelled.emit)
        button_row.addWidget(cancel_btn)
        save_btn = QPushButton("Save")
        save_btn.setObjectName("primaryButton")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        button_row.addWidget(save_btn)
        outer.addLayout(button_row)

        self.load_config(config)

    def load_config(self, config: Config) -> None:
        """(Re)populate every field from `config`. Called each time this
        page is shown, so it always reflects the currently active settings
        rather than whatever was left over from a previous visit."""
        self._config = config
        self.excluded_dirs_list.set_items(config.excluded_dirs)
        self.include_ext_list.set_items(config.include_ext)
        self.max_file_size.setValue(config.max_file_size_bytes / (1024 * 1024))
        self.max_pdf_size.setValue(config.max_pdf_size_bytes / (1024 * 1024))
        self.include_hidden_cb.setChecked(config.include_hidden)
        self.follow_symlinks_cb.setChecked(config.follow_symlinks)
        self.chunk_cb.setChecked(config.max_chunk_chars is not None)
        self.chunk_spin.setValue(config.max_chunk_chars or 100_000)
        self.chunk_spin.setEnabled(self.chunk_cb.isChecked())
        self.chunk_preset_combo.setCurrentIndex(0)

    def _apply_chunk_preset(self, index: int) -> None:
        presets = {1: 100_000, 2: 350_000}
        if index in presets:
            self.chunk_cb.setChecked(True)
            self.chunk_spin.setValue(presets[index])

    def _restore_defaults(self) -> None:
        """Reset the lists to the built‑in defaults."""
        default_cfg = Config()
        self.excluded_dirs_list.set_items(default_cfg.excluded_dirs)
        self.include_ext_list.set_items(default_cfg.include_ext)
        self.load_config(Config())

    def _on_save(self) -> None:
        self.saved.emit(self._build_config())

    def _build_config(self) -> Config:
        c = self._config
        c.excluded_dirs = self.excluded_dirs_list.get_checked()
        c.include_ext = self.include_ext_list.get_checked()
        c.max_file_size_bytes = int(self.max_file_size.value() * 1024 * 1024)
        c.max_pdf_size_bytes = int(self.max_pdf_size.value() * 1024 * 1024)
        c.include_hidden = self.include_hidden_cb.isChecked()
        c.follow_symlinks = self.follow_symlinks_cb.isChecked()
        c.max_chunk_chars = self.chunk_spin.value() if self.chunk_cb.isChecked() else None
        return c


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(900, 680)
        self.setMinimumSize(700, 520)

        self.config = Config.load(default_config_path())
        self.selected_folder: Optional[Path] = None
        self._thread: Optional[QThread] = None
        self._worker: Optional[DumpWorker] = None
        self._running = False
        self._last_output_paths: List[Path] = []

        app = QApplication.instance()
        if app is not None:
            app.setPalette(theme.build_palette())
            app.setStyleSheet(theme.STYLESHEET)

        self.setMenuBar(None)
        self._build_status_bar()

        central_widget = QWidget()
        central_layout = QHBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)

        # Sidebar (no title/icon, just a clean navigation rail)
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(220)
        sidebar_layout = QVBoxLayout(self.sidebar)
        sidebar_layout.setContentsMargins(0, 0, 0, 0)
        sidebar_layout.setSpacing(0)
        sidebar_layout.addSpacing(8)

        # Dash Board button
        self.btn_dash = QPushButton("  Dash Board")
        self.btn_dash.setObjectName("sidebarButton")
        self.btn_dash.setCheckable(True)
        self.btn_dash.setChecked(True)
        self.btn_dash.clicked.connect(lambda: self._switch_page(0))
        self.btn_dash.setMinimumWidth(0)
        sidebar_layout.addWidget(self.btn_dash)

        self.btn_settings = QPushButton("  Settings")
        self.btn_settings.setObjectName("sidebarButton")
        self.btn_settings.setCheckable(True)
        self.btn_settings.clicked.connect(lambda: self._switch_page(1))
        self.btn_settings.setMinimumWidth(0)
        sidebar_layout.addWidget(self.btn_settings)

        sidebar_layout.addStretch(1)

        self.about_btn = QPushButton("  About")
        self.about_btn.setObjectName("sidebarButton")
        self.about_btn.clicked.connect(self._show_about)
        self.about_btn.setMinimumWidth(0)
        sidebar_layout.addWidget(self.about_btn)

        # Content stack
        self.stack = QStackedWidget()
        main_page = self._build_main_page()
        self.settings_page = SettingsPage(self.config)
        self.settings_page.saved.connect(self._on_settings_saved)
        self.settings_page.cancelled.connect(self._on_settings_cancelled)
        self.stack.addWidget(main_page)
        self.stack.addWidget(self.settings_page)
        self.stack.setCurrentWidget(main_page)

        central_layout.addWidget(self.sidebar)
        central_layout.addWidget(self.stack, 1)
        self.setCentralWidget(central_widget)

    # -- construction ---------------------------------------------------------
    def _build_title_block(self) -> QWidget:
        block = QFrame()
        block.setObjectName("titleBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)
        tagline = QLabel(TAGLINE)
        tagline.setObjectName("appTaglineLabel")
        layout.addWidget(tagline)
        return block

    def _build_main_page(self) -> QWidget:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 0, 16, 18)
        root.setSpacing(12)

        root.addWidget(self._build_title_block())

        self.drop_area = DropArea(self._set_folder)
        root.addWidget(self.drop_area)

        choose_row = QHBoxLayout()
        self.choose_btn = QPushButton("Choose Folder\u2026")
        self.choose_btn.clicked.connect(self._choose_folder)
        choose_row.addWidget(self.choose_btn)
        self.folder_label = QLabel("No folder selected")
        self.folder_label.setObjectName("folderPathLabel")
        self.folder_label.setStyleSheet(f"color: {theme.TEXT_MUTED};")
        choose_row.addWidget(self.folder_label, 1)
        root.addLayout(choose_row)

        # Group Mode & Output together
        options_group = QGroupBox("Processing Options")
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(8)

        mode_row = QHBoxLayout()
        mode_label = QLabel("Mode:")
        mode_label.setStyleSheet("font-weight: bold;")
        mode_row.addWidget(mode_label)
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Auto Detect", "CodeBase Mode", "Research Mode"])
        mode_row.addWidget(self.mode_combo)
        mode_row.addStretch(1)
        options_layout.addLayout(mode_row)

        out_row = QHBoxLayout()
        out_label = QLabel("Output file:")
        out_label.setStyleSheet("font-weight: bold;")
        out_row.addWidget(out_label)
        self.output_edit = QLineEdit()
        self.output_edit.setObjectName("outputPathEdit")
        self.output_edit.setPlaceholderText("default: <folder>_context_utf8.txt")
        out_row.addWidget(self.output_edit, 1)
        self.browse_output_btn = QPushButton("Browse\u2026")
        self.browse_output_btn.clicked.connect(self._browse_output)
        out_row.addWidget(self.browse_output_btn)
        options_layout.addLayout(out_row)

        root.addWidget(options_group)

        action_row = QHBoxLayout()
        self.start_btn = QPushButton("Start Processing")
        self.start_btn.setObjectName("primaryButton")
        self.start_btn.setEnabled(False)
        self.start_btn.clicked.connect(self._start_processing)
        action_row.addWidget(self.start_btn)
        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.clicked.connect(self._cancel_processing)
        action_row.addWidget(self.cancel_btn)
        root.addLayout(action_row)

        # Status + progress aligned
        status_row = QHBoxLayout()
        status_row.setSpacing(6)
        self.status_label = QLabel("Ready.")
        self.status_label.setObjectName("statusLine")
        status_row.addWidget(self.status_label)

        # Progress bar: show percentage text
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("%p%")  # shows percentage
        self.progress_bar.setMaximumWidth(200)
        status_row.addWidget(self.progress_bar, 1)
        status_row.addStretch(1)
        root.addLayout(status_row)

        self.summary_box = QTextEdit()
        self.summary_box.setObjectName("resultsBox")
        self.summary_box.setReadOnly(True)
        self.summary_box.setPlaceholderText("Results will appear here after processing.")
        root.addWidget(self.summary_box, 1)

        result_row = QHBoxLayout()
        self.open_folder_btn = QPushButton("Open Containing Folder")
        self.open_folder_btn.clicked.connect(self._open_output_folder)
        result_row.addWidget(self.open_folder_btn)
        self.copy_clipboard_btn = QPushButton("Copy to Clipboard")
        self.copy_clipboard_btn.clicked.connect(self._copy_output_to_clipboard)
        result_row.addWidget(self.copy_clipboard_btn)
        self.open_folder_btn.setVisible(False)
        self.copy_clipboard_btn.setVisible(False)
        root.addLayout(result_row)

        return central

    def _build_status_bar(self) -> None:
        bar = self.statusBar()
        credit = QLabel(DEVELOPER_NAME)
        credit.setObjectName("mutedLabel")
        bar.addPermanentWidget(credit)

    # -- sidebar navigation --------------------------------------------------
    def _switch_page(self, index: int) -> None:
        self.stack.setCurrentIndex(index)
        self.btn_dash.setChecked(index == 0)
        self.btn_settings.setChecked(index == 1)

    # -- about ---------------------------------------------------------------
    def _show_about(self) -> None:
        about_text = (
            f"<h3>{APP_TITLE}</h3>"
            f"<p>Version {__version__}</p>"
            f"<p>Developed by <b>{DEVELOPER_NAME}</b></p>"
            f"<p>Email: {CONTACT_EMAIL}</p>"
            f"<p>Phone: {CONTACT_PHONE}</p>"
            f"<p>&copy; {CONTACT_YEAR} {DEVELOPER_NAME}. All rights reserved.</p>"
        )
        QMessageBox.about(self, f"About {APP_TITLE}", about_text)

    # -- folder selection ---------------------------------------------------
    def _set_folder(self, path_str: str) -> None:
        path = Path(path_str)
        if not path.is_dir():
            QMessageBox.warning(self, "Invalid folder", f"{path} is not a directory.")
            return
        if not os.access(path, os.R_OK):
            QMessageBox.warning(self, "Permission denied", f"Cannot read {path}.")
            return
        self.selected_folder = path
        self.folder_label.setText(str(path))
        self.folder_label.setStyleSheet(f"color: {theme.TEXT_PRIMARY};")
        self.start_btn.setEnabled(True)

    def _choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a project folder")
        if path:
            self._set_folder(path)

    def _browse_output(self) -> None:
        start_dir = str(self.selected_folder) if self.selected_folder else str(Path.home())
        path, _ = QFileDialog.getSaveFileName(self, "Choose output file", start_dir, "Text files (*.txt)")
        if path:
            self.output_edit.setText(path)

    # -- settings navigation -------------------------------------------------
    def _open_settings(self) -> None:
        self.settings_page.load_config(self.config)
        self._switch_page(1)

    def _on_settings_saved(self, config: Config) -> None:
        self.config = config
        try:
            self.config.save(default_config_path())
        except OSError as e:
            QMessageBox.warning(self, "Couldn't save settings", str(e))
        self._switch_page(0)

    def _on_settings_cancelled(self) -> None:
        self._switch_page(0)

    # -- processing lifecycle ------------------------------------------------
    def _selected_mode(self) -> Mode:
        return {
            0: Mode.AUTO,
            1: Mode.SOURCE,
            2: Mode.PDF,
        }[self.mode_combo.currentIndex()]

    def _start_processing(self) -> None:
        if not self.selected_folder:
            return

        output_text = self.output_edit.text().strip()
        output_path = Path(output_text) if output_text else None
        effective_output = output_path or default_output_path(self.selected_folder)

        overwrite = False
        if effective_output.exists():
            resp = QMessageBox.question(
                self, "Overwrite file?",
                f"{effective_output} already exists. Overwrite it?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                return
            overwrite = True

        self._set_running(True)
        self.summary_box.clear()
        self.progress_bar.setRange(0, 0)  # indeterminate mode
        self.status_label.setText("Scanning folder…")
        self.open_folder_btn.setVisible(False)
        self.copy_clipboard_btn.setVisible(False)

        self._thread = QThread(self)
        self._worker = DumpWorker(
            self.selected_folder, self.config, output_path, self._selected_mode(), overwrite=overwrite,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cancel_processing(self) -> None:
        if self._worker:
            self._worker.request_cancel()
            self.status_label.setText("Cancelling…")
            self.cancel_btn.setEnabled(False)

    def _set_running(self, running: bool) -> None:
        self._running = running
        self.start_btn.setEnabled(not running and self.selected_folder is not None)
        self.cancel_btn.setEnabled(running)
        self.choose_btn.setEnabled(not running)
        self.mode_combo.setEnabled(not running)
        self.output_edit.setEnabled(not running)
        self.browse_output_btn.setEnabled(not running)
        self.drop_area.setEnabled(not running)
        self.btn_dash.setEnabled(not running)
        self.btn_settings.setEnabled(not running)
        self.about_btn.setEnabled(not running)

    def _on_progress(self, done: int, total: int, rel_path: str, phase: str) -> None:
        if total > 0:
            self.progress_bar.setRange(0, total)
            self.progress_bar.setValue(done)
            pct = int((done / total) * 100)
            self.status_label.setText(f"[{phase}] {done}/{total} ({pct}%) {rel_path}")
        else:
            self.status_label.setText(f"[{phase}] {rel_path}")

    def _on_finished(self, summary) -> None:
        self._set_running(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        if summary.cancelled:
            self.status_label.setText("Cancelled.")
            self.summary_box.setHtml(
                f'<div style="font-family:{theme.FONT_MONO}; color:{theme.TEXT_MUTED};">'
                "Processing was cancelled. No output file was written.</div>"
            )
            self.open_folder_btn.setVisible(False)
            self.copy_clipboard_btn.setVisible(False)
            self._last_output_paths = []
            return

        self.status_label.setText("Done.")
        self._last_output_paths = list(summary.output_paths)

        pairs: List[Tuple[str, str]] = [
            ("Mode used", summary.mode_used),
            ("Source files", summary.source_file_count),
            ("PDF files", summary.pdf_file_count),
            ("Skipped/warned", len(summary.skipped)),
            ("Elapsed", f"{summary.elapsed_seconds:.2f}s"),
            ("Characters", f"{summary.char_count:,}"),
            ("Est. tokens", f"~{summary.estimated_tokens:,} (rough, ~4 chars/token)"),
        ]
        if len(summary.output_paths) > 1:
            pairs.append(("Output", f"{len(summary.output_paths)} parts, {summary.output_size_bytes:,} bytes total"))
        else:
            pairs.append(("Output file", str(summary.output_path)))
            pairs.append(("Output size", f"{summary.output_size_bytes:,} bytes"))

        sections: List[Tuple[str, List[str]]] = []
        if len(summary.output_paths) > 1:
            sections.append(("Parts", [str(p) for p in summary.output_paths]))
        if summary.skipped:
            skip_lines = [f"{rec.path}: {rec.reason}" for rec in summary.skipped[:200]]
            if len(summary.skipped) > 200:
                skip_lines.append(f"... and {len(summary.skipped) - 200} more (see the output file)")
            sections.append(("Skipped / warnings", skip_lines))

        self.summary_box.setHtml(_render_summary_html(pairs, sections))
        self.open_folder_btn.setVisible(True)
        self.copy_clipboard_btn.setVisible(len(self._last_output_paths) == 1)
        self.copy_clipboard_btn.setToolTip(
            "" if len(self._last_output_paths) == 1
            else "Output was split into multiple parts — open the folder, "
                 "or increase the chunk size in Settings, to copy as one piece."
        )

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.status_label.setText("Failed.")
        escaped = html_lib.escape(message).replace("\n", "<br>")
        self.summary_box.setHtml(
            f'<div style="font-family:{theme.FONT_MONO}; color:{theme.DANGER};">'
            f"<b>Processing failed:</b><br><br>{escaped}</div>"
        )
        self.copy_clipboard_btn.setVisible(False)
        QMessageBox.critical(self, "Processing failed", message.splitlines()[0] if message else "Unknown error")

    def _cleanup_thread(self) -> None:
        if self._thread:
            self._thread.wait()
            self._thread.deleteLater()
        if self._worker:
            self._worker.deleteLater()
        self._thread = None
        self._worker = None

    def _open_output_folder(self) -> None:
        if self._last_output_paths:
            _open_containing_folder(self._last_output_paths[0])

    def _copy_output_to_clipboard(self) -> None:
        if len(self._last_output_paths) != 1:
            return
        path = self._last_output_paths[0]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as e:
            QMessageBox.warning(self, "Couldn't read output", str(e))
            return
        QApplication.clipboard().setText(text)
        self.statusBar().showMessage(f"Copied {len(text):,} characters to clipboard.", 4000)

    # -- window lifecycle -----------------------------------------------------
    def closeEvent(self, event) -> None:
        if self._running:
            resp = QMessageBox.question(
                self, "Processing in progress",
                "Processing is still running. Cancel it and quit?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if resp != QMessageBox.Yes:
                event.ignore()
                return
            if self._worker:
                self._worker.request_cancel()
            if self._thread:
                self._thread.quit()
                self._thread.wait(5000)
        event.accept()