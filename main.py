"""Entry point for the Project Context Dumper desktop application.

Run with:  python main.py
"""
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from app.gui import MainWindow


def load_app_icon() -> QIcon:
    """Load the custom application icon from the project root.
    Falls back to an empty QIcon if the file is missing."""
    icon_candidates = [
        Path(__file__).parent / "app_icon.png",
        Path(__file__).parent / "app_icon.ico",
        Path(__file__).parent / "icon.png",
        Path(__file__).parent / "icon.ico",
    ]
    for path in icon_candidates:
        if path.exists():
            return QIcon(str(path))
    # If no icon file found, return an empty icon (the window will use the default)
    return QIcon()


def main() -> int:
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # renders the custom stylesheet consistently across platforms
    from app import theme
    app.setPalette(theme.build_palette())
    app.setApplicationName("Project Context Dumper")
    app.setOrganizationName("ProjectContextDumper")

    # Set the application icon (loads from main.py's folder)
    app.setWindowIcon(load_app_icon())

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())