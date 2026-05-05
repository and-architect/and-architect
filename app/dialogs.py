"""All dialog boxes for the dissertation writer."""

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QTextEdit, QPushButton, QComboBox,
    QSpinBox, QCheckBox, QDialogButtonBox, QWidget,
    QSizePolicy, QGroupBox, QListWidget, QListWidgetItem,
    QSplitter,
)
from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtGui import QFont


# ── Formula Dialog ────────────────────────────────────────────────────────

KATEX_PREVIEW_HTML = """<!DOCTYPE html>
<html><head>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
<script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
<style>
  body {{ background:#fff; display:flex; align-items:center; justify-content:center;
          height:100vh; margin:0; font-family:serif; }}
  #preview {{ font-size:18px; padding:20px; text-align:center; color:#222; }}
  #error {{ color:#c00; font-size:13px; font-family:monospace; }}
</style>
</head><body>
<div>
  <div id="preview"></div>
  <div id="error"></div>
</div>
<script>
function renderLatex(latex, display) {{
  const el = document.getElementById('preview')
  const err = document.getElementById('error')
  try {{
    katex.render(latex || '\\\\text{{Vorschau}}', el, {{
      displayMode: display, throwOnError: true
    }})
    err.textContent = ''
  }} catch(e) {{
    el.innerHTML = ''
    err.textContent = e.message
  }}
}}
renderLatex('E = mc^2', true)
</script>
</body></html>"""


class FormulaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Formel einfügen")
        self.setMinimumSize(580, 400)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # LaTeX input
        lbl = QLabel("LaTeX-Formel:")
        lbl.setFont(QFont("Georgia", 11))
        layout.addWidget(lbl)

        self.input = QLineEdit()
        self.input.setFont(QFont("Courier New", 12))
        self.input.setPlaceholderText(r"z.B.  \frac{d}{dx}\left(x^2\right) = 2x")
        self.input.textChanged.connect(self._update_preview)
        layout.addWidget(self.input)

        # Display mode toggle
        self.display_check = QCheckBox("Abgesetzt (display mode)")
        self.display_check.setChecked(True)
        self.display_check.toggled.connect(self._update_preview)
        layout.addWidget(self.display_check)

        # Preview
        preview_lbl = QLabel("Vorschau:")
        layout.addWidget(preview_lbl)

        self.preview = QWebEngineView()
        self.preview.setFixedHeight(180)
        self.preview.setHtml(KATEX_PREVIEW_HTML)
        layout.addWidget(self.preview)

        # Common formulas
        group = QGroupBox("Häufige Formeln")
        glayout = QHBoxLayout(group)
        examples = [
            ("Bruch", r"\frac{a}{b}"),
            ("Integral", r"\int_0^\infty f(x)\,dx"),
            ("Summe", r"\sum_{i=1}^{n} x_i"),
            ("Griechisch", r"\alpha, \beta, \gamma, \Delta"),
            ("Matrix", r"\begin{pmatrix} a & b \\ c & d \end{pmatrix}"),
            ("E=mc²", r"E = mc^2"),
        ]
        for name, latex in examples:
            btn = QPushButton(name)
            btn.setFixedHeight(26)
            btn.clicked.connect(lambda _, l=latex: self._set_example(l))
            glayout.addWidget(btn)
        layout.addWidget(group)

        # Buttons
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_example(self, latex: str):
        self.input.setText(latex)

    def _update_preview(self):
        latex = self.input.text()
        display = "true" if self.display_check.isChecked() else "false"
        escaped = latex.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")
        self.preview.page().runJavaScript(f"renderLatex('{escaped}', {display})")

    def get_formula(self) -> tuple[str, bool]:
        return self.input.text(), self.display_check.isChecked()


# ── Table Dialog ─────────────────────────────────────────────────────────

class TableDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Tabelle einfügen")
        self.setFixedSize(280, 160)
        self._setup_ui()

    def _setup_ui(self):
        layout = QFormLayout(self)
        layout.setSpacing(10)

        self.rows = QSpinBox()
        self.rows.setRange(1, 50)
        self.rows.setValue(3)
        layout.addRow("Zeilen:", self.rows)

        self.cols = QSpinBox()
        self.cols.setRange(1, 20)
        self.cols.setValue(3)
        layout.addRow("Spalten:", self.cols)

        self.header = QCheckBox("Mit Kopfzeile")
        self.header.setChecked(True)
        layout.addRow("", self.header)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def get_params(self) -> tuple[int, int, bool]:
        return self.rows.value(), self.cols.value(), self.header.isChecked()


# ── Metadata Dialog ───────────────────────────────────────────────────────

class MetadataDialog(QDialog):
    def __init__(self, metadata, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dokument-Metadaten")
        self.setMinimumSize(480, 400)
        self._fields = {}
        self._setup_ui(metadata)

    def _setup_ui(self, meta):
        layout = QVBoxLayout(self)
        form = QFormLayout()
        form.setSpacing(10)

        fields = [
            ("title", "Titel:"),
            ("author", "Autor/in:"),
            ("institution", "Institution:"),
            ("supervisor", "Betreuer/in:"),
            ("date", "Datum:"),
            ("subject", "Fachbereich:"),
            ("language", "Sprache (de/en):"),
            ("bibliography_style", "Zitierstil (apa/chicago/...):"),
        ]

        for key, label in fields:
            edit = QLineEdit()
            edit.setText(getattr(meta, key, "") or "")
            form.addRow(label, edit)
            self._fields[key] = edit

        layout.addLayout(form)

        abstract_lbl = QLabel("Abstract:")
        layout.addWidget(abstract_lbl)
        self.abstract = QTextEdit()
        self.abstract.setPlainText(meta.abstract or "")
        self.abstract.setFixedHeight(80)
        layout.addWidget(self.abstract)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_metadata(self) -> dict:
        result = {k: w.text().strip() for k, w in self._fields.items()}
        result["abstract"] = self.abstract.toPlainText().strip()
        return result


# ── Zotero Panel Dialog ────────────────────────────────────────────────────

class ZoteroDialog(QDialog):
    citation_selected = pyqtSignal(str, str)   # key, display_label

    def __init__(self, zotero_client, parent=None):
        super().__init__(parent)
        self.zotero = zotero_client
        self.setWindowTitle("Zotero – Literatur einfügen")
        self.setMinimumSize(640, 480)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # CAYW button (simplest path)
        cayw_btn = QPushButton("Zotero-Dialog öffnen (Cite As You Write)")
        cayw_btn.setFixedHeight(36)
        cayw_btn.setStyleSheet("font-size:13px;font-weight:bold;")
        cayw_btn.clicked.connect(self._cayw)
        layout.addWidget(cayw_btn)

        sep = QLabel("— oder manuell suchen —")
        sep.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sep)

        # Search
        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Autor, Titel, Jahr suchen…")
        self.search_input.returnPressed.connect(self._search)
        search_btn = QPushButton("Suchen")
        search_btn.clicked.connect(self._search)
        search_row.addWidget(self.search_input)
        search_row.addWidget(search_btn)
        layout.addLayout(search_row)

        # Results list
        self.results = QListWidget()
        self.results.itemDoubleClicked.connect(self._insert_selected)
        layout.addWidget(self.results)

        # Status
        self.status = QLabel("")
        self.status.setStyleSheet("color:#888;font-size:11px;")
        layout.addWidget(self.status)

        # Buttons
        row = QHBoxLayout()
        insert_btn = QPushButton("Zitat einfügen")
        insert_btn.clicked.connect(self._insert_selected)
        cancel_btn = QPushButton("Abbrechen")
        cancel_btn.clicked.connect(self.reject)
        row.addWidget(insert_btn)
        row.addWidget(cancel_btn)
        layout.addLayout(row)

        if not self.zotero.check_connection():
            self.status.setText(
                "Zotero nicht gefunden. Bitte Zotero starten und Better BibTeX installieren."
            )
            self.status.setStyleSheet("color:#c44;font-size:11px;")

    def _cayw(self):
        self.status.setText("Warte auf Zotero-Dialog…")
        citation = self.zotero.cite_as_you_write()
        if citation:
            self.citation_selected.emit(citation, citation)
            self.accept()
        else:
            self.status.setText("Kein Zitat ausgewählt oder Zotero nicht erreichbar.")

    def _search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        self.status.setText("Suche…")
        items = self.zotero.search_items(query)
        self.results.clear()
        for item in items[:50]:
            data = item.get("data", item)
            title = data.get("title", "")
            creators = data.get("creators", [])
            author = creators[0].get("lastName", "") if creators else ""
            year = data.get("date", "")[:4] if data.get("date") else ""
            key = data.get("citekey") or item.get("key", "")
            label = f"{author} ({year})" if author else title[:60]
            list_item = QListWidgetItem(f"{label} – {title[:80]}")
            list_item.setData(Qt.ItemDataRole.UserRole, (key, label))
            self.results.addItem(list_item)
        self.status.setText(f"{len(items)} Treffer" if items else "Keine Treffer")

    def _insert_selected(self):
        item = self.results.currentItem()
        if not item:
            return
        key, label = item.data(Qt.ItemDataRole.UserRole)
        self.citation_selected.emit(key, f"({label})")
        self.accept()


# ── Export Dialog ─────────────────────────────────────────────────────────

class ExportDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Exportieren")
        self.setFixedSize(340, 200)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.format_combo = QComboBox()
        self.format_combo.addItems(["PDF (.pdf)", "Word (.docx)", "Tabelle (.ods)", "Markdown (.md)"])
        form.addRow("Format:", self.format_combo)

        self.include_meta = QCheckBox("Titelseite mit Metadaten")
        self.include_meta.setChecked(True)
        form.addRow("", self.include_meta)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok |
                                   QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Exportieren")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_params(self) -> tuple[str, bool]:
        fmt_map = {0: "pdf", 1: "docx", 2: "ods", 3: "md"}
        fmt = fmt_map[self.format_combo.currentIndex()]
        return fmt, self.include_meta.isChecked()
