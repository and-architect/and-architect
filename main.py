#!/usr/bin/env python3
"""
Dissertation Writer – OmmWriter-style academic writing app
with Zotero integration, formula rendering, and multi-format export.

Requirements:
    pip install PyQt6 PyQt6-WebEngine requests python-docx odfpy weasyprint Pillow

Usage:
    python main.py
    python main.py path/to/document.diss
"""

import sys
import os
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt, QCoreApplication
from PyQt6.QtGui import QIcon

from app.main_window import MainWindow


def main():
    # Needed for QWebEngineView on some systems
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")

    QCoreApplication.setApplicationName("Dissertation Writer")
    QCoreApplication.setOrganizationName("AndArchitect")
    QCoreApplication.setApplicationVersion("1.0")

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    # Open file from command line
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if Path(path).exists():
            from app.document_model import Document
            try:
                window.document = Document.load(path)
            except Exception as e:
                print(f"Could not load {path}: {e}")

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
