from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton,
)
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QFont


class NotesPanel(QWidget):
    notes_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self):
        self.setMinimumWidth(200)
        self.setMaximumWidth(320)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Header
        header = QWidget()
        header.setObjectName("panel-header")
        hl = QHBoxLayout(header)
        hl.setContentsMargins(12, 10, 8, 10)

        title = QLabel("Notizen")
        title.setObjectName("panel-title")
        hl.addWidget(title)
        hl.addStretch()

        layout.addWidget(header)

        # Notes editor
        self.editor = QTextEdit()
        self.editor.setObjectName("notes-editor")
        self.editor.setPlaceholderText(
            "Persönliche Notizen, Ideen, Quellen-Gedanken…\n\n"
            "Diese Notizen werden mit dem Dokument gespeichert."
        )
        font = QFont("Georgia", 11)
        self.editor.setFont(font)
        self.editor.textChanged.connect(self._on_change)
        layout.addWidget(self.editor)

        # Footer with word count
        footer = QWidget()
        footer.setObjectName("panel-footer")
        fl = QHBoxLayout(footer)
        fl.setContentsMargins(12, 4, 12, 6)

        self.word_count_label = QLabel("0 Wörter")
        self.word_count_label.setObjectName("status-label")
        fl.addWidget(self.word_count_label)
        fl.addStretch()

        layout.addWidget(footer)

    def _on_change(self):
        text = self.editor.toPlainText()
        words = len([w for w in text.split() if w])
        self.word_count_label.setText(f"{words} Wörter")
        self.notes_changed.emit(text)

    def set_notes(self, text: str):
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)

    def get_notes(self) -> str:
        return self.editor.toPlainText()
