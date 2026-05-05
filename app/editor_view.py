"""QWebEngineView wrapper that hosts the TipTap WYSIWYG editor."""

import json
import base64
from pathlib import Path

from PyQt6.QtCore import QObject, QUrl, pyqtSignal, pyqtSlot, QTimer
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEnginePage
from PyQt6.QtWebChannel import QWebChannel

EDITOR_HTML = Path(__file__).parent.parent / "resources" / "editor.html"


class Bridge(QObject):
    """Exposed to JavaScript via QWebChannel."""

    content_changed = pyqtSignal(str, int)    # json, word_count
    selection_changed = pyqtSignal(str)        # json of active marks

    @pyqtSlot(str, int)
    def onContentChanged(self, json_str: str, word_count: int):
        self.content_changed.emit(json_str, word_count)

    @pyqtSlot(str)
    def onSelectionChanged(self, state_json: str):
        self.selection_changed.emit(state_json)


class EditorView(QWebEngineView):
    content_changed = pyqtSignal(str, int)
    selection_changed = pyqtSignal(dict)
    ready = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._bridge = Bridge()
        self._channel = QWebChannel(self.page())
        self._channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(self._channel)

        self._bridge.content_changed.connect(self._on_content_changed)
        self._bridge.selection_changed.connect(self._on_selection_changed)

        self._current_content: dict = {}
        self._ready = False

        self.loadFinished.connect(self._on_load_finished)
        self.load(QUrl.fromLocalFile(str(EDITOR_HTML.resolve())))

    def _on_load_finished(self, ok: bool):
        if ok:
            self._ready = True
            self.ready.emit()

    def _on_content_changed(self, json_str: str, word_count: int):
        try:
            self._current_content = json.loads(json_str)
        except Exception:
            pass
        self.content_changed.emit(json_str, word_count)

    def _on_selection_changed(self, state_json: str):
        try:
            state = json.loads(state_json)
            self.selection_changed.emit(state)
        except Exception:
            pass

    # ── Low-level JS execution ───────────────────────────────────────────

    def run_js(self, script: str, callback=None):
        if callback:
            self.page().runJavaScript(script, callback)
        else:
            self.page().runJavaScript(script)

    # ── Content API ──────────────────────────────────────────────────────

    def get_content(self, callback):
        self.run_js("window.getContent()", callback)

    def set_content(self, content: dict):
        json_str = json.dumps(content, ensure_ascii=False)
        escaped = json_str.replace("\\", "\\\\").replace("`", "\\`")
        self.run_js(f"window.setContent(`{escaped}`)")

    def get_html(self, callback):
        self.run_js("window.getHTML()", callback)

    def get_headings(self, callback):
        self.run_js("window.getHeadings()", lambda raw: callback(json.loads(raw or "[]")))

    def scroll_to_heading(self, text: str):
        escaped = text.replace("'", "\\'")
        self.run_js(f"window.scrollToHeading('{escaped}')")

    # ── Formatting commands ──────────────────────────────────────────────

    def toggle_bold(self): self.run_js("window.toggleBold()")
    def toggle_italic(self): self.run_js("window.toggleItalic()")
    def toggle_underline(self): self.run_js("window.toggleUnderline()")
    def toggle_strike(self): self.run_js("window.toggleStrike()")
    def toggle_blockquote(self): self.run_js("window.toggleBlockquote()")
    def toggle_bullet_list(self): self.run_js("window.toggleBulletList()")
    def toggle_ordered_list(self): self.run_js("window.toggleOrderedList()")
    def toggle_code(self): self.run_js("window.toggleCode()")
    def toggle_code_block(self): self.run_js("window.toggleCodeBlock()")
    def undo(self): self.run_js("window.undo()")
    def redo(self): self.run_js("window.redo()")

    def set_heading(self, level: int):
        self.run_js(f"window.setHeading({level})")

    def set_text_align(self, align: str):
        self.run_js(f"window.setTextAlign('{align}')")

    # ── Insert operations ────────────────────────────────────────────────

    def insert_citation(self, key: str, label: str):
        k = key.replace("'", "\\'")
        l = label.replace("'", "\\'")
        self.run_js(f"window.insertCitation('{k}', '{l}')")

    def insert_formula(self, latex: str, display: bool = False):
        escaped = latex.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")
        disp = "true" if display else "false"
        self.run_js(f"window.insertFormula('{escaped}', {disp})")

    def insert_table(self, rows: int = 3, cols: int = 3):
        self.run_js(f"window.insertTable({rows}, {cols})")

    def insert_image(self, file_path: str):
        """Read image file and insert as base64 data URL."""
        path = Path(file_path)
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif",
                    ".svg": "image/svg+xml", ".webp": "image/webp"}
        mime = mime_map.get(suffix, "image/png")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        src = f"data:{mime};base64,{b64}"
        escaped = src.replace("`", "\\`")
        self.run_js(f"window.insertImage(`{escaped}`)")

    def add_text_frame(self, x: int = 100, y: int = 100,
                       w: int = 200, h: int = 120):
        self.run_js(f"window.addTextFrame({x}, {y}, {w}, {h})")

    def add_image_frame(self, file_path: str,
                        x: int = 100, y: int = 100,
                        w: int = 300, h: int = 200):
        path = Path(file_path)
        suffix = path.suffix.lower()
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                    ".png": "image/png", ".gif": "image/gif"}
        mime = mime_map.get(suffix, "image/png")
        with open(path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        src = f"data:{mime};base64,{b64}"
        escaped = src.replace("`", "\\`")
        self.run_js(f"window.addImageFrame(`{escaped}`, {x}, {y}, {w}, {h})")

    # ── Table commands ───────────────────────────────────────────────────
    def add_table_row(self): self.run_js("window.addTableRow()")
    def add_table_col(self): self.run_js("window.addTableCol()")
    def delete_table(self): self.run_js("window.deleteTable()")
