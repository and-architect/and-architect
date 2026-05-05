"""Main application window – OmmWriter-style dissertation editor."""

import json
import os
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QStatusBar, QLabel, QFileDialog,
    QMessageBox, QToolBar, QComboBox, QPushButton,
    QSizePolicy, QProgressBar,
)
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QAction, QKeySequence, QFont, QIcon

from .editor_view import EditorView
from .chapter_panel import ChapterPanel
from .notes_panel import NotesPanel
from .document_model import Document, DocumentMetadata
from .zotero_client import ZoteroClient
from .export_manager import export_pdf, export_docx, export_ods, export_markdown
from .dialogs import (
    FormulaDialog, TableDialog, MetadataDialog,
    ZoteroDialog, ExportDialog,
)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.document = Document()
        self.zotero = ZoteroClient()
        self._word_count = 0
        self._headings_timer = QTimer(self)
        self._headings_timer.setSingleShot(True)
        self._headings_timer.timeout.connect(self._refresh_headings)

        self.setWindowTitle("Dissertation Writer")
        self.setMinimumSize(1100, 720)
        self._apply_stylesheet()
        self._build_ui()
        self._build_menus()
        self._build_toolbar()
        self._connect_signals()

    # ── UI construction ──────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Main splitter
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(True)
        self.splitter.setHandleWidth(1)
        root.addWidget(self.splitter)

        # Left: Chapter panel
        self.chapter_panel = ChapterPanel()
        self.splitter.addWidget(self.chapter_panel)

        # Center: Editor
        self.editor = EditorView()
        self.splitter.addWidget(self.editor)

        # Right: Notes
        self.notes_panel = NotesPanel()
        self.splitter.addWidget(self.notes_panel)

        # Proportions: 18 / 64 / 18
        self.splitter.setSizes([210, 680, 210])
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setStretchFactor(2, 0)

        # Status bar
        sb = self.statusBar()
        sb.setObjectName("main-status")

        self._status_words = QLabel("0 Wörter")
        self._status_words.setObjectName("status-label")
        sb.addPermanentWidget(self._status_words)

        self._status_file = QLabel("Ungespeichert")
        self._status_file.setObjectName("status-label")
        sb.addWidget(self._status_file)

        self._status_zotero = QLabel()
        self._status_zotero.setObjectName("status-label")
        sb.addPermanentWidget(self._status_zotero)
        self._update_zotero_status()

    def _build_menus(self):
        mb = self.menuBar()

        # ── Datei ────────────────────────────────────────────────────────
        file_menu = mb.addMenu("Datei")

        act_new = QAction("Neu", self, shortcut=QKeySequence.StandardKey.New)
        act_new.triggered.connect(self._new_document)
        file_menu.addAction(act_new)

        act_open = QAction("Öffnen…", self, shortcut=QKeySequence.StandardKey.Open)
        act_open.triggered.connect(self._open_document)
        file_menu.addAction(act_open)

        file_menu.addSeparator()

        act_save = QAction("Speichern", self, shortcut=QKeySequence.StandardKey.Save)
        act_save.triggered.connect(self._save_document)
        file_menu.addAction(act_save)

        act_save_as = QAction("Speichern unter…", self,
                              shortcut=QKeySequence.StandardKey.SaveAs)
        act_save_as.triggered.connect(self._save_document_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_meta = QAction("Dokument-Info…", self)
        act_meta.triggered.connect(self._edit_metadata)
        file_menu.addAction(act_meta)

        file_menu.addSeparator()

        act_export = QAction("Exportieren…", self, shortcut="Ctrl+E")
        act_export.triggered.connect(self._export)
        file_menu.addAction(act_export)

        file_menu.addSeparator()

        act_quit = QAction("Beenden", self, shortcut=QKeySequence.StandardKey.Quit)
        act_quit.triggered.connect(self.close)
        file_menu.addAction(act_quit)

        # ── Bearbeiten ───────────────────────────────────────────────────
        edit_menu = mb.addMenu("Bearbeiten")

        act_undo = QAction("Rückgängig", self, shortcut=QKeySequence.StandardKey.Undo)
        act_undo.triggered.connect(self.editor.undo)
        edit_menu.addAction(act_undo)

        act_redo = QAction("Wiederherstellen", self, shortcut=QKeySequence.StandardKey.Redo)
        act_redo.triggered.connect(self.editor.redo)
        edit_menu.addAction(act_redo)

        edit_menu.addSeparator()

        act_find = QAction("Suchen…", self, shortcut=QKeySequence.StandardKey.Find)
        act_find.triggered.connect(lambda: self.editor.page().triggerAction(
            self.editor.page().WebAction.Find))
        edit_menu.addAction(act_find)

        # ── Format ───────────────────────────────────────────────────────
        fmt_menu = mb.addMenu("Format")

        for level, name in [(1, "Überschrift 1"), (2, "Überschrift 2"),
                            (3, "Überschrift 3"), (0, "Fließtext")]:
            shortcut = f"Ctrl+Alt+{level}" if level else "Ctrl+Alt+0"
            act = QAction(name, self, shortcut=shortcut)
            act.triggered.connect(lambda _, l=level: self.editor.set_heading(l))
            fmt_menu.addAction(act)

        fmt_menu.addSeparator()

        act_bold = QAction("Fett", self, shortcut="Ctrl+B")
        act_bold.triggered.connect(self.editor.toggle_bold)
        fmt_menu.addAction(act_bold)

        act_italic = QAction("Kursiv", self, shortcut="Ctrl+I")
        act_italic.triggered.connect(self.editor.toggle_italic)
        fmt_menu.addAction(act_italic)

        act_underline = QAction("Unterstrichen", self, shortcut="Ctrl+U")
        act_underline.triggered.connect(self.editor.toggle_underline)
        fmt_menu.addAction(act_underline)

        fmt_menu.addSeparator()

        act_quote = QAction("Blockzitat", self, shortcut="Ctrl+Shift+B")
        act_quote.triggered.connect(self.editor.toggle_blockquote)
        fmt_menu.addAction(act_quote)

        # ── Einfügen ─────────────────────────────────────────────────────
        ins_menu = mb.addMenu("Einfügen")

        act_image = QAction("Bild…", self, shortcut="Ctrl+Shift+I")
        act_image.triggered.connect(self._insert_image)
        ins_menu.addAction(act_image)

        act_image_frame = QAction("Bild-Rahmen…", self)
        act_image_frame.triggered.connect(self._insert_image_frame)
        ins_menu.addAction(act_image_frame)

        act_text_frame = QAction("Text-Rahmen", self)
        act_text_frame.triggered.connect(lambda: self.editor.add_text_frame())
        ins_menu.addAction(act_text_frame)

        ins_menu.addSeparator()

        act_table = QAction("Tabelle…", self, shortcut="Ctrl+Shift+T")
        act_table.triggered.connect(self._insert_table)
        ins_menu.addAction(act_table)

        act_formula = QAction("Formel (LaTeX)…", self, shortcut="Ctrl+Shift+F")
        act_formula.triggered.connect(self._insert_formula)
        ins_menu.addAction(act_formula)

        ins_menu.addSeparator()

        act_hr = QAction("Horizontale Linie", self)
        act_hr.triggered.connect(lambda: self.editor.run_js(
            "window.editor.chain().focus().setHorizontalRule().run()"))
        ins_menu.addAction(act_hr)

        # ── Ansicht ──────────────────────────────────────────────────────
        view_menu = mb.addMenu("Ansicht")

        act_chapters = QAction("Kapitelübersicht", self, shortcut="Ctrl+1",
                               checkable=True, checked=True)
        act_chapters.toggled.connect(lambda v: self.chapter_panel.setVisible(v))
        view_menu.addAction(act_chapters)

        act_notes = QAction("Notizen", self, shortcut="Ctrl+2",
                            checkable=True, checked=True)
        act_notes.toggled.connect(lambda v: self.notes_panel.setVisible(v))
        view_menu.addAction(act_notes)

        view_menu.addSeparator()

        act_fullscreen = QAction("Vollbild", self,
                                 shortcut=QKeySequence.StandardKey.FullScreen)
        act_fullscreen.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(act_fullscreen)

        act_focus = QAction("Fokus-Modus (Spalten ausblenden)", self, shortcut="Ctrl+F10")
        act_focus.triggered.connect(self._toggle_focus_mode)
        view_menu.addAction(act_focus)

        # ── Zotero ───────────────────────────────────────────────────────
        zotero_menu = mb.addMenu("Zotero")

        act_cite = QAction("Zitat einfügen…", self, shortcut="Ctrl+Z")
        act_cite.triggered.connect(self._insert_citation)
        zotero_menu.addAction(act_cite)

        act_cayw = QAction("Schnell-Zitat (CAYW)…", self, shortcut="Ctrl+Shift+Z")
        act_cayw.triggered.connect(self._cayw_citation)
        zotero_menu.addAction(act_cayw)

        zotero_menu.addSeparator()

        act_refresh_z = QAction("Zotero-Verbindung prüfen", self)
        act_refresh_z.triggered.connect(self._update_zotero_status)
        zotero_menu.addAction(act_refresh_z)

        # ── Tabelle ──────────────────────────────────────────────────────
        table_menu = mb.addMenu("Tabelle")

        for label, fn in [
            ("Zeile hinzufügen", self.editor.add_table_row),
            ("Spalte hinzufügen", self.editor.add_table_col),
            ("Tabelle löschen", self.editor.delete_table),
        ]:
            act = QAction(label, self)
            act.triggered.connect(fn)
            table_menu.addAction(act)

    def _build_toolbar(self):
        tb = QToolBar("Formatierung")
        tb.setObjectName("main-toolbar")
        tb.setMovable(False)
        tb.setIconSize(QSize(16, 16))
        tb.setFloatable(False)
        self.addToolBar(tb)

        # Style selector
        self.style_combo = QComboBox()
        self.style_combo.setObjectName("style-combo")
        self.style_combo.setFixedWidth(160)
        self.style_combo.addItems([
            "Fließtext",
            "Überschrift 1",
            "Überschrift 2",
            "Überschrift 3",
            "Überschrift 4",
        ])
        self.style_combo.currentIndexChanged.connect(self._style_combo_changed)
        tb.addWidget(self.style_combo)

        tb.addSeparator()

        # Format buttons
        def add_btn(label: str, shortcut: str, slot, checkable=False):
            btn = QPushButton(label)
            btn.setObjectName("toolbar-btn")
            btn.setFixedSize(32, 28)
            btn.setCheckable(checkable)
            btn.setShortcut(shortcut)
            btn.clicked.connect(slot)
            tb.addWidget(btn)
            return btn

        self.btn_bold = add_btn("B", "Ctrl+B", self.editor.toggle_bold, True)
        self.btn_bold.setFont(QFont("Georgia", 11, QFont.Weight.Bold))
        self.btn_italic = add_btn("I", "Ctrl+I", self.editor.toggle_italic, True)
        self.btn_italic.setFont(QFont("Georgia", 11, italic=True))
        self.btn_underline = add_btn("U", "Ctrl+U", self.editor.toggle_underline, True)

        tb.addSeparator()

        add_btn("≡L", "", lambda: self.editor.set_text_align("left"))
        add_btn("≡C", "", lambda: self.editor.set_text_align("center"))
        add_btn("≡R", "", lambda: self.editor.set_text_align("right"))
        add_btn("≡J", "", lambda: self.editor.set_text_align("justify"))

        tb.addSeparator()

        add_btn("•", "", self.editor.toggle_bullet_list)
        add_btn("1.", "", self.editor.toggle_ordered_list)
        add_btn("❝", "Ctrl+Shift+B", self.editor.toggle_blockquote)

        tb.addSeparator()

        add_btn("∑", "Ctrl+Shift+F", self._insert_formula)
        add_btn("⊞", "Ctrl+Shift+T", self._insert_table)
        add_btn("🖼", "Ctrl+Shift+I", self._insert_image)

        tb.addSeparator()

        act_zotero_btn = QPushButton("Zotero")
        act_zotero_btn.setObjectName("zotero-btn")
        act_zotero_btn.setFixedHeight(28)
        act_zotero_btn.clicked.connect(self._insert_citation)
        tb.addWidget(act_zotero_btn)

        tb.addSeparator()

        exp_btn = QPushButton("Export")
        exp_btn.setObjectName("toolbar-btn")
        exp_btn.setFixedHeight(28)
        exp_btn.clicked.connect(self._export)
        tb.addWidget(exp_btn)

    def _connect_signals(self):
        self.editor.ready.connect(self._on_editor_ready)
        self.editor.content_changed.connect(self._on_content_changed)
        self.editor.selection_changed.connect(self._on_selection_changed)
        self.chapter_panel.chapter_clicked.connect(self._on_chapter_clicked)
        self.chapter_panel.chapter_add_requested.connect(
            lambda lvl: self.editor.set_heading(lvl))
        self.notes_panel.notes_changed.connect(self._on_notes_changed)

    # ── Event handlers ────────────────────────────────────────────────────

    def _on_editor_ready(self):
        if self.document.content:
            self.editor.set_content(self.document.content)
        if self.document.notes:
            self.notes_panel.set_notes(self.document.notes)

    def _on_content_changed(self, json_str: str, word_count: int):
        self._word_count = word_count
        self._status_words.setText(f"{word_count:,} Wörter")
        self.document.modified = True
        try:
            self.document.content = json.loads(json_str)
        except Exception:
            pass
        # Debounce heading refresh
        self._headings_timer.start(600)
        self._update_title()

    def _on_selection_changed(self, state: dict):
        self.btn_bold.setChecked(state.get("bold", False))
        self.btn_italic.setChecked(state.get("italic", False))
        self.btn_underline.setChecked(state.get("underline", False))

        if state.get("h1"):
            self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(1)
            self.style_combo.blockSignals(False)
        elif state.get("h2"):
            self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(2)
            self.style_combo.blockSignals(False)
        elif state.get("h3"):
            self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(3)
            self.style_combo.blockSignals(False)
        else:
            self.style_combo.blockSignals(True)
            self.style_combo.setCurrentIndex(0)
            self.style_combo.blockSignals(False)

    def _on_chapter_clicked(self, heading_text: str):
        self.editor.scroll_to_heading(heading_text)

    def _on_notes_changed(self, text: str):
        self.document.notes = text
        self.document.modified = True

    def _refresh_headings(self):
        self.editor.get_headings(self.chapter_panel.update_headings)

    def _style_combo_changed(self, index: int):
        self.editor.set_heading(index)

    # ── Document operations ───────────────────────────────────────────────

    def _new_document(self):
        if self.document.modified:
            if not self._confirm_discard():
                return
        self.document = Document()
        self.editor.set_content({})
        self.notes_panel.set_notes("")
        self.chapter_panel.update_headings([])
        self._update_title()

    def _open_document(self):
        if self.document.modified:
            if not self._confirm_discard():
                return
        path, _ = QFileDialog.getOpenFileName(
            self, "Öffnen", "",
            "Dissertation (*.diss *.json);;Alle Dateien (*)"
        )
        if path:
            try:
                self.document = Document.load(path)
                self.editor.set_content(self.document.content)
                self.notes_panel.set_notes(self.document.notes)
                self._update_title()
                self._refresh_headings()
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Datei konnte nicht geöffnet werden:\n{e}")

    def _save_document(self):
        if self.document.file_path:
            self._do_save(self.document.file_path)
        else:
            self._save_document_as()

    def _save_document_as(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Speichern unter", "",
            "Dissertation (*.diss);;JSON (*.json);;Alle Dateien (*)"
        )
        if path:
            if not path.endswith((".diss", ".json")):
                path += ".diss"
            self._do_save(path)

    def _do_save(self, path: str):
        def on_content(json_str):
            try:
                if json_str:
                    self.document.content = json.loads(json_str)
                self.document.notes = self.notes_panel.get_notes()
                self.document.save(path)
                self._status_file.setText(f"Gespeichert: {Path(path).name}")
                self._update_title()
            except Exception as e:
                QMessageBox.critical(self, "Fehler", f"Speichern fehlgeschlagen:\n{e}")

        self.editor.get_content(on_content)

    def _edit_metadata(self):
        dlg = MetadataDialog(self.document.metadata, self)
        if dlg.exec():
            data = dlg.get_metadata()
            for k, v in data.items():
                if hasattr(self.document.metadata, k):
                    setattr(self.document.metadata, k, v)
            self.document.modified = True
            self._update_title()

    def _update_title(self):
        title = self.document.metadata.title or "Unbenannte Dissertation"
        modified = " *" if self.document.modified else ""
        fname = f" – {Path(self.document.file_path).name}" if self.document.file_path else ""
        self.setWindowTitle(f"{title}{fname}{modified} – Dissertation Writer")

    def _confirm_discard(self) -> bool:
        reply = QMessageBox.question(
            self, "Ungespeicherte Änderungen",
            "Es gibt ungespeicherte Änderungen. Trotzdem fortfahren?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        return reply == QMessageBox.StandardButton.Yes

    # ── Insert operations ─────────────────────────────────────────────────

    def _insert_image(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Bild einfügen", "",
            "Bilder (*.png *.jpg *.jpeg *.gif *.svg *.webp);;Alle Dateien (*)"
        )
        if path:
            try:
                self.editor.insert_image(path)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", f"Bild konnte nicht eingefügt werden:\n{e}")

    def _insert_image_frame(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Bild-Rahmen", "",
            "Bilder (*.png *.jpg *.jpeg *.gif);;Alle Dateien (*)"
        )
        if path:
            try:
                self.editor.add_image_frame(path)
            except Exception as e:
                QMessageBox.warning(self, "Fehler", str(e))

    def _insert_formula(self):
        dlg = FormulaDialog(self)
        if dlg.exec():
            latex, display = dlg.get_formula()
            if latex.strip():
                self.editor.insert_formula(latex, display)

    def _insert_table(self):
        dlg = TableDialog(self)
        if dlg.exec():
            rows, cols, _ = dlg.get_params()
            self.editor.insert_table(rows, cols)

    def _insert_citation(self):
        dlg = ZoteroDialog(self.zotero, self)
        dlg.citation_selected.connect(
            lambda key, label: self.editor.insert_citation(key, label))
        dlg.exec()

    def _cayw_citation(self):
        citation = self.zotero.cite_as_you_write()
        if citation:
            self.editor.insert_citation(citation, citation)
        else:
            QMessageBox.information(
                self, "Zotero",
                "Kein Zitat ausgewählt oder Zotero nicht erreichbar.\n"
                "Bitte Zotero mit Better BibTeX starten."
            )

    # ── Export ────────────────────────────────────────────────────────────

    def _export(self):
        dlg = ExportDialog(self)
        if not dlg.exec():
            return
        fmt, include_meta = dlg.get_params()

        ext_map = {"pdf": "pdf", "docx": "docx", "ods": "ods", "md": "md"}
        filter_map = {
            "pdf": "PDF (*.pdf)",
            "docx": "Word-Dokument (*.docx)",
            "ods": "Tabellendokument (*.ods)",
            "md": "Markdown (*.md)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, "Exportieren", self.document.metadata.title or "dissertation",
            filter_map[fmt]
        )
        if not path:
            return
        if not path.endswith(f".{fmt}"):
            path += f".{fmt}"

        meta_dict = {
            "title": self.document.metadata.title,
            "author": self.document.metadata.author,
            "institution": self.document.metadata.institution,
            "date": self.document.metadata.date,
            "language": self.document.metadata.language,
        } if include_meta else None

        def do_export(json_str):
            try:
                content = json.loads(json_str) if json_str else self.document.content
                if fmt == "pdf":
                    ok = export_pdf(content, meta_dict, path)
                    if not ok:
                        html_path = path.replace(".pdf", "_preview.html")
                        QMessageBox.information(
                            self, "Export",
                            f"weasyprint nicht gefunden. HTML-Vorschau gespeichert:\n{html_path}\n\n"
                            "Installiere weasyprint für PDF-Export:\n  pip install weasyprint"
                        )
                        return
                elif fmt == "docx":
                    export_docx(content, meta_dict, path)
                elif fmt == "ods":
                    export_ods(content, meta_dict, path)
                elif fmt == "md":
                    export_markdown(content, meta_dict, path)
                QMessageBox.information(
                    self, "Export erfolgreich",
                    f"Dokument exportiert:\n{path}"
                )
            except Exception as e:
                QMessageBox.critical(self, "Export-Fehler", str(e))

        self.editor.get_content(do_export)

    # ── View helpers ──────────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _toggle_focus_mode(self):
        panels_visible = self.chapter_panel.isVisible()
        self.chapter_panel.setVisible(not panels_visible)
        self.notes_panel.setVisible(not panels_visible)

    def _update_zotero_status(self):
        if self.zotero.check_connection():
            self._status_zotero.setText("● Zotero")
            self._status_zotero.setStyleSheet("color:#5a9;font-size:11px;")
        else:
            self._status_zotero.setText("○ Zotero")
            self._status_zotero.setStyleSheet("color:#888;font-size:11px;")

    def closeEvent(self, event):
        if self.document.modified:
            reply = QMessageBox.question(
                self, "Beenden",
                "Es gibt ungespeicherte Änderungen.\nTrotzdem beenden?",
                QMessageBox.StandardButton.Save |
                QMessageBox.StandardButton.Discard |
                QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                self._save_document()
        event.accept()

    # ── Stylesheet ────────────────────────────────────────────────────────

    def _apply_stylesheet(self):
        self.setStyleSheet("""
/* ── Application window ────────────────────────── */
QMainWindow {
    background: #1c1c2e;
}
QMainWindow::separator {
    background: #2e2e4e;
    width: 1px;
    height: 1px;
}

/* ── Menu bar ──────────────────────────────────── */
QMenuBar {
    background: #12122a;
    color: #c0b8e8;
    padding: 2px 0;
    font-size: 13px;
    border-bottom: 1px solid #2a2a4a;
}
QMenuBar::item {
    padding: 4px 12px;
    border-radius: 4px;
    background: transparent;
}
QMenuBar::item:selected {
    background: #2a2a4a;
    color: #e0d8ff;
}
QMenu {
    background: #1e1e38;
    color: #c8c0e8;
    border: 1px solid #3a3a5a;
    border-radius: 6px;
    padding: 4px 0;
    font-size: 13px;
}
QMenu::item {
    padding: 5px 24px 5px 16px;
}
QMenu::item:selected {
    background: #3a3468;
    color: #fff;
    border-radius: 3px;
}
QMenu::separator {
    height: 1px;
    background: #3a3a5a;
    margin: 4px 8px;
}

/* ── Toolbar ────────────────────────────────────── */
QToolBar#main-toolbar {
    background: #14142a;
    border-bottom: 1px solid #2a2a4a;
    padding: 3px 6px;
    spacing: 2px;
}
QToolBar::separator {
    background: #3a3a5a;
    width: 1px;
    margin: 4px 4px;
}
QPushButton#toolbar-btn {
    background: transparent;
    color: #b8b0d8;
    border: 1px solid transparent;
    border-radius: 4px;
    font-size: 13px;
    padding: 2px 4px;
}
QPushButton#toolbar-btn:hover {
    background: #2a2a4a;
    border-color: #4a4a6a;
    color: #e0d8ff;
}
QPushButton#toolbar-btn:checked {
    background: #3a3468;
    border-color: #6a5fa0;
    color: #fff;
}
QPushButton#zotero-btn {
    background: #3a3468;
    color: #c8b8ff;
    border: 1px solid #6a5fa0;
    border-radius: 4px;
    font-size: 12px;
    font-weight: bold;
    padding: 2px 10px;
}
QPushButton#zotero-btn:hover {
    background: #4a4478;
    color: #fff;
}
QComboBox#style-combo {
    background: #1e1e38;
    color: #c0b8e8;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    padding: 2px 8px;
    font-size: 12px;
    min-height: 24px;
}
QComboBox#style-combo::drop-down {
    border: none;
    width: 20px;
}
QComboBox#style-combo QAbstractItemView {
    background: #1e1e38;
    color: #c0b8e8;
    border: 1px solid #3a3a5a;
    selection-background-color: #3a3468;
}

/* ── Splitter ────────────────────────────────────── */
QSplitter::handle {
    background: #2a2a4a;
    width: 1px;
}

/* ── Side panels ─────────────────────────────────── */
QWidget#panel-header {
    background: #12122a;
    border-bottom: 1px solid #2a2a4a;
}
QLabel#panel-title {
    color: #9890c0;
    font-size: 11px;
    font-weight: bold;
    text-transform: uppercase;
    letter-spacing: 1px;
    font-family: Georgia, serif;
}
QWidget#panel-footer {
    background: #12122a;
    border-top: 1px solid #2a2a4a;
}

/* ── Chapter tree ────────────────────────────────── */
QTreeWidget#chapter-tree {
    background: #16162e;
    color: #b0a8d0;
    border: none;
    font-family: Georgia, serif;
    font-size: 12px;
    outline: none;
    padding: 4px 0;
}
QTreeWidget#chapter-tree::item {
    padding: 4px 8px;
    border-radius: 3px;
}
QTreeWidget#chapter-tree::item:hover {
    background: #2a2a4a;
    color: #e0d8ff;
}
QTreeWidget#chapter-tree::item:selected {
    background: #3a3468;
    color: #fff;
}
QPushButton#chapter-add-btn {
    background: transparent;
    color: #7870a8;
    border: 1px solid #3a3a5a;
    border-radius: 3px;
    font-size: 11px;
    padding: 1px 6px;
}
QPushButton#chapter-add-btn:hover {
    background: #2a2a4a;
    color: #c0b8e8;
}

/* ── Notes editor ────────────────────────────────── */
QTextEdit#notes-editor {
    background: #16162e;
    color: #b0a8d0;
    border: none;
    font-family: Georgia, serif;
    font-size: 12px;
    padding: 12px;
    line-height: 1.5;
}

/* ── Status bar ──────────────────────────────────── */
QStatusBar#main-status {
    background: #0e0e22;
    color: #7870a8;
    border-top: 1px solid #2a2a4a;
    font-size: 11px;
}
QLabel#status-label {
    color: #7870a8;
    font-size: 11px;
    padding: 0 8px;
}

/* ── Dialogs ─────────────────────────────────────── */
QDialog {
    background: #1c1c2e;
    color: #c0b8e8;
    font-family: Georgia, serif;
}
QDialog QLabel {
    color: #c0b8e8;
}
QDialog QLineEdit, QDialog QTextEdit, QDialog QSpinBox, QDialog QComboBox {
    background: #12122a;
    color: #e0d8ff;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    padding: 4px 8px;
    font-size: 13px;
    font-family: Georgia, serif;
}
QDialog QLineEdit:focus, QDialog QTextEdit:focus {
    border-color: #6a5fa0;
}
QDialog QPushButton {
    background: #2a2a4a;
    color: #c0b8e8;
    border: 1px solid #4a4a6a;
    border-radius: 5px;
    padding: 5px 16px;
    font-size: 12px;
}
QDialog QPushButton:hover {
    background: #3a3468;
    color: #fff;
}
QDialog QPushButton:default {
    background: #4a3a88;
    border-color: #7c6f9f;
    color: #fff;
}
QGroupBox {
    color: #9890c0;
    border: 1px solid #3a3a5a;
    border-radius: 6px;
    margin-top: 8px;
    padding-top: 8px;
    font-size: 11px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QListWidget {
    background: #12122a;
    color: #c0b8e8;
    border: 1px solid #3a3a5a;
    border-radius: 4px;
    font-size: 12px;
}
QListWidget::item { padding: 4px 8px; }
QListWidget::item:selected { background: #3a3468; color: #fff; }
QListWidget::item:hover { background: #2a2a4a; }
QScrollBar:vertical {
    background: #16162e;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #3a3a5a;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #5a5a7a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QCheckBox { color: #c0b8e8; }
QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #5a5a7a;
    border-radius: 3px;
    background: #12122a;
}
QCheckBox::indicator:checked {
    background: #4a3a88;
    border-color: #7c6f9f;
}
        """)
