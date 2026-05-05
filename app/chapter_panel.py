from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTreeWidget,
    QTreeWidgetItem, QPushButton, QLineEdit,
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QIcon, QFont


class ChapterPanel(QWidget):
    chapter_clicked = pyqtSignal(str)  # heading text
    chapter_add_requested = pyqtSignal(int)  # heading level

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
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(12, 10, 8, 10)

        title = QLabel("Kapitel")
        title.setObjectName("panel-title")
        header_layout.addWidget(title)
        header_layout.addStretch()

        layout.addWidget(header)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setObjectName("chapter-tree")
        self.tree.setIndentation(16)
        self.tree.setAnimated(True)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

        # Add chapter buttons
        btn_bar = QWidget()
        btn_bar.setObjectName("panel-footer")
        btn_layout = QHBoxLayout(btn_bar)
        btn_layout.setContentsMargins(8, 6, 8, 6)
        btn_layout.setSpacing(4)

        for level, label in [(1, "H1"), (2, "H2"), (3, "H3")]:
            btn = QPushButton(label)
            btn.setObjectName("chapter-add-btn")
            btn.setFixedHeight(24)
            btn.clicked.connect(lambda checked, lvl=level: self.chapter_add_requested.emit(lvl))
            btn_layout.addWidget(btn)

        btn_layout.addStretch()
        layout.addWidget(btn_bar)

    def update_headings(self, headings: list):
        """Update the chapter tree from a list of {level, text} dicts."""
        self.tree.clear()
        stack: list[tuple[int, QTreeWidgetItem]] = []

        for h in headings:
            level = h.get("level", 1)
            text = h.get("text", "").strip() or "(ohne Titel)"
            item = QTreeWidgetItem([text])
            item.setData(0, Qt.ItemDataRole.UserRole, text)

            font = item.font(0)
            if level == 1:
                font.setBold(True)
                font.setPointSize(11)
            elif level == 2:
                font.setPointSize(10)
            else:
                font.setPointSize(9)
            item.setFont(0, font)

            # Find correct parent
            while stack and stack[-1][0] >= level:
                stack.pop()

            if stack:
                stack[-1][1].addChild(item)
            else:
                self.tree.addTopLevelItem(item)

            stack.append((level, item))

        self.tree.expandAll()

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        text = item.data(0, Qt.ItemDataRole.UserRole)
        if text:
            self.chapter_clicked.emit(text)
