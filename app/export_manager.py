"""Multi-format export: PDF, DOCX, ODS, Markdown."""

import json
import re
import tempfile
import os
from pathlib import Path
from typing import List, Optional


# ── TipTap JSON → plain structures ──────────────────────────────────────────

def _node_text(node: dict) -> str:
    if node.get("type") == "text":
        return node.get("text", "")
    parts = [_node_text(c) for c in node.get("content", [])]
    return "".join(parts)


def _has_mark(node: dict, mark: str) -> bool:
    return any(m.get("type") == mark for m in node.get("marks", []))


def _inline_md(node: dict) -> str:
    if node.get("type") != "text":
        if node.get("type") == "hardBreak":
            return "  \n"
        return "".join(_inline_md(c) for c in node.get("content", []))
    text = node.get("text", "")
    marks = {m.get("type") for m in node.get("marks", [])}
    if "bold" in marks and "italic" in marks:
        text = f"***{text}***"
    elif "bold" in marks:
        text = f"**{text}**"
    elif "italic" in marks:
        text = f"*{text}*"
    if "underline" in marks:
        text = f"<u>{text}</u>"
    if "code" in marks:
        text = f"`{text}`"
    if "superscript" in marks:
        text = f"<sup>{text}</sup>"
    if "subscript" in marks:
        text = f"<sub>{text}</sub>"
    return text


def _row_md(row: dict) -> str:
    cells = row.get("content", [])
    parts = [_node_text(c) for c in cells]
    return "| " + " | ".join(parts) + " |"


def tiptap_to_markdown(doc: dict, metadata: dict = None) -> str:
    lines: List[str] = []

    if metadata:
        lines += [
            f"# {metadata.get('title', '')}",
            f"**Autor:** {metadata.get('author', '')}",
            f"**Institution:** {metadata.get('institution', '')}",
            "",
        ]

    def process(node: dict):
        t = node.get("type")
        content = node.get("content", [])

        if t == "doc":
            for c in content:
                process(c)

        elif t == "heading":
            level = node.get("attrs", {}).get("level", 1)
            text = "".join(_inline_md(c) for c in content)
            lines.append(f"{'#' * level} {text}")
            lines.append("")

        elif t == "paragraph":
            text = "".join(_inline_md(c) for c in content)
            if text.strip():
                lines.append(text)
                lines.append("")

        elif t == "blockquote":
            for c in content:
                inner = "".join(_inline_md(x) for x in c.get("content", []))
                lines.append(f"> {inner}")
            lines.append("")

        elif t == "bulletList":
            for item in content:
                for para in item.get("content", []):
                    text = "".join(_inline_md(c) for c in para.get("content", []))
                    lines.append(f"- {text}")
            lines.append("")

        elif t == "orderedList":
            for i, item in enumerate(content, 1):
                for para in item.get("content", []):
                    text = "".join(_inline_md(c) for c in para.get("content", []))
                    lines.append(f"{i}. {text}")
            lines.append("")

        elif t == "codeBlock":
            lang = node.get("attrs", {}).get("language", "")
            text = _node_text(node)
            lines.append(f"```{lang}")
            lines.append(text)
            lines.append("```")
            lines.append("")

        elif t == "horizontalRule":
            lines.append("---")
            lines.append("")

        elif t == "table":
            rows = content
            if not rows:
                return
            header = rows[0]
            lines.append(_row_md(header))
            cols = len(header.get("content", []))
            lines.append("| " + " | ".join(["---"] * cols) + " |")
            for row in rows[1:]:
                lines.append(_row_md(row))
            lines.append("")

        elif t == "image":
            attrs = node.get("attrs", {})
            src = attrs.get("src", "")
            alt = attrs.get("alt", "")
            title = attrs.get("title", "")
            if src.startswith("data:"):
                src = "<embedded-image>"
            lines.append(f"![{alt}]({src} \"{title}\")")
            lines.append("")

    process(doc)
    return "\n".join(lines)


# ── HTML generation for PDF export ──────────────────────────────────────────

def tiptap_to_html(doc: dict, metadata: dict = None, page_number: bool = True) -> str:
    body_parts: List[str] = []

    def marks_wrap(text: str, marks: list) -> str:
        mark_types = {m.get("type") for m in marks}
        if "bold" in mark_types:
            text = f"<strong>{text}</strong>"
        if "italic" in mark_types:
            text = f"<em>{text}</em>"
        if "underline" in mark_types:
            text = f"<u>{text}</u>"
        if "code" in mark_types:
            text = f"<code>{text}</code>"
        if "superscript" in mark_types:
            text = f"<sup>{text}</sup>"
        if "subscript" in mark_types:
            text = f"<sub>{text}</sub>"
        return text

    def inline_html(node: dict) -> str:
        if node.get("type") == "text":
            text = node.get("text", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            return marks_wrap(text, node.get("marks", []))
        if node.get("type") == "hardBreak":
            return "<br>"
        return "".join(inline_html(c) for c in node.get("content", []))

    def process_node(node: dict):
        t = node.get("type")
        content = node.get("content", [])
        attrs = node.get("attrs", {})

        if t == "doc":
            for c in content:
                process_node(c)
        elif t == "heading":
            lvl = attrs.get("level", 1)
            text = "".join(inline_html(c) for c in content)
            body_parts.append(f"<h{lvl}>{text}</h{lvl}>")
        elif t == "paragraph":
            align = attrs.get("textAlign", "left")
            text = "".join(inline_html(c) for c in content)
            body_parts.append(f'<p style="text-align:{align}">{text}</p>')
        elif t == "blockquote":
            inner = "".join(
                f'<p>{"".join(inline_html(c) for c in para.get("content", []))}</p>'
                for para in content
            )
            body_parts.append(f"<blockquote>{inner}</blockquote>")
        elif t == "bulletList":
            items = "".join(
                f'<li>{"".join(inline_html(c) for c in (item.get("content", [{}])[0]).get("content", []))}</li>'
                for item in content
            )
            body_parts.append(f"<ul>{items}</ul>")
        elif t == "orderedList":
            items = "".join(
                f'<li>{"".join(inline_html(c) for c in (item.get("content", [{}])[0]).get("content", []))}</li>'
                for item in content
            )
            body_parts.append(f"<ol>{items}</ol>")
        elif t == "codeBlock":
            text = _node_text(node)
            body_parts.append(f"<pre><code>{text}</code></pre>")
        elif t == "horizontalRule":
            body_parts.append("<hr>")
        elif t == "table":
            rows_html = []
            for i, row in enumerate(content):
                cells_html = []
                for cell in row.get("content", []):
                    cell_text = "".join(inline_html(c) for c in cell.get("content", [{}])[0].get("content", []))
                    tag = "th" if i == 0 else "td"
                    cells_html.append(f"<{tag}>{cell_text}</{tag}>")
                rows_html.append(f"<tr>{''.join(cells_html)}</tr>")
            body_parts.append(f"<table>{''.join(rows_html)}</table>")
        elif t == "image":
            src = attrs.get("src", "")
            alt = attrs.get("alt", "Abbildung")
            body_parts.append(f'<figure><img src="{src}" alt="{alt}"><figcaption>{alt}</figcaption></figure>')

    process_node(doc)

    meta_html = ""
    if metadata:
        meta_html = f"""
        <div class="title-page">
          <h1 class="doc-title">{metadata.get('title','')}</h1>
          <p class="doc-author">{metadata.get('author','')}</p>
          <p class="doc-institution">{metadata.get('institution','')}</p>
          <p class="doc-date">{metadata.get('date','')}</p>
        </div>
        """

    return f"""<!DOCTYPE html>
<html lang="{metadata.get('language','de') if metadata else 'de'}">
<head>
<meta charset="UTF-8">
<style>
  @page {{
    size: A4;
    margin: 25mm 25mm 30mm 30mm;
    @bottom-center {{ content: counter(page); font-size: 10pt; color: #666; }}
  }}
  body {{ font-family: 'Georgia', serif; font-size: 12pt; line-height: 1.5; color: #111; }}
  h1 {{ font-size: 24pt; margin: 24pt 0 12pt; page-break-after: avoid; }}
  h2 {{ font-size: 18pt; margin: 18pt 0 9pt; page-break-after: avoid; }}
  h3 {{ font-size: 14pt; margin: 14pt 0 7pt; page-break-after: avoid; }}
  p {{ margin: 0 0 12pt; text-align: justify; }}
  blockquote {{ margin: 12pt 0 12pt 24pt; padding-left: 12pt; border-left: 3px solid #7c6f9f; font-style: italic; color: #444; }}
  table {{ border-collapse: collapse; width: 100%; margin: 12pt 0; }}
  th {{ background: #f0f0f0; font-weight: bold; }}
  td, th {{ border: 1px solid #ccc; padding: 6pt 10pt; }}
  pre {{ background: #f8f8f8; padding: 12pt; border-radius: 4px; font-size: 10pt; overflow: auto; }}
  code {{ font-family: monospace; font-size: 10pt; }}
  img {{ max-width: 100%; display: block; margin: 12pt auto; }}
  figure {{ margin: 12pt 0; text-align: center; }}
  figcaption {{ font-size: 10pt; color: #666; font-style: italic; margin-top: 4pt; }}
  hr {{ border: none; border-top: 1px solid #ccc; margin: 24pt 0; }}
  .title-page {{ text-align: center; margin-bottom: 48pt; padding-top: 96pt; page-break-after: always; }}
  .doc-title {{ font-size: 28pt; font-weight: bold; margin-bottom: 24pt; }}
  .doc-author {{ font-size: 16pt; margin-bottom: 8pt; }}
  .doc-institution {{ font-size: 12pt; color: #555; }}
  .doc-date {{ font-size: 12pt; color: #555; margin-top: 8pt; }}
</style>
</head>
<body>
{meta_html}
{''.join(body_parts)}
</body>
</html>"""


# ── Markdown export ──────────────────────────────────────────────────────────

def export_markdown(doc_content: dict, metadata: dict, path: str):
    md = tiptap_to_markdown(doc_content, metadata)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md)


# ── PDF export ───────────────────────────────────────────────────────────────

def export_pdf(doc_content: dict, metadata: dict, path: str):
    try:
        from weasyprint import HTML as WP_HTML
        html = tiptap_to_html(doc_content, metadata)
        WP_HTML(string=html).write_pdf(path)
        return True
    except ImportError:
        # Fallback: save HTML and note that weasyprint is needed
        html_path = path.replace(".pdf", "_preview.html")
        html = tiptap_to_html(doc_content, metadata)
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html)
        return False


# ── DOCX export ──────────────────────────────────────────────────────────────

def export_docx(doc_content: dict, metadata: dict, path: str):
    from docx import Document as DocxDocument
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = DocxDocument()

    # Page margins
    for section in doc.sections:
        section.top_margin = Cm(2.5)
        section.bottom_margin = Cm(3.0)
        section.left_margin = Cm(3.0)
        section.right_margin = Cm(2.5)

    # Title page
    if metadata:
        title_para = doc.add_paragraph()
        title_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = title_para.add_run(metadata.get("title", ""))
        run.bold = True
        run.font.size = Pt(24)

        if metadata.get("author"):
            p = doc.add_paragraph(metadata["author"])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.runs[0].font.size = Pt(14)
        if metadata.get("institution"):
            p = doc.add_paragraph(metadata["institution"])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        if metadata.get("date"):
            p = doc.add_paragraph(metadata["date"])
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_page_break()

    ALIGN_MAP = {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }

    def apply_marks(run, marks: list):
        for m in marks:
            mt = m.get("type")
            if mt == "bold":
                run.bold = True
            elif mt == "italic":
                run.italic = True
            elif mt == "underline":
                run.underline = True
            elif mt == "superscript":
                run.font.superscript = True
            elif mt == "subscript":
                run.font.subscript = True

    def add_paragraph_content(para, content: list):
        for node in content:
            if node.get("type") == "text":
                run = para.add_run(node.get("text", ""))
                apply_marks(run, node.get("marks", []))
            elif node.get("type") == "hardBreak":
                para.add_run("\n")

    def process(node: dict):
        t = node.get("type")
        content = node.get("content", [])
        attrs = node.get("attrs", {})

        if t == "doc":
            for c in content:
                process(c)

        elif t == "heading":
            lvl = attrs.get("level", 1)
            style = f"Heading {lvl}"
            try:
                para = doc.add_paragraph(style=style)
            except Exception:
                para = doc.add_paragraph()
                para.runs[0].bold = True if lvl <= 2 else False
            add_paragraph_content(para, content)

        elif t == "paragraph":
            para = doc.add_paragraph()
            align_key = attrs.get("textAlign", "justify")
            para.alignment = ALIGN_MAP.get(align_key, WD_ALIGN_PARAGRAPH.JUSTIFY)
            add_paragraph_content(para, content)

        elif t == "blockquote":
            for child in content:
                try:
                    para = doc.add_paragraph(style="Quote")
                except Exception:
                    para = doc.add_paragraph()
                add_paragraph_content(para, child.get("content", []))

        elif t == "bulletList":
            for item in content:
                for para_node in item.get("content", []):
                    try:
                        para = doc.add_paragraph(style="List Bullet")
                    except Exception:
                        para = doc.add_paragraph()
                        para.style.paragraph_format.left_indent = Cm(1)
                    add_paragraph_content(para, para_node.get("content", []))

        elif t == "orderedList":
            for item in content:
                for para_node in item.get("content", []):
                    try:
                        para = doc.add_paragraph(style="List Number")
                    except Exception:
                        para = doc.add_paragraph()
                    add_paragraph_content(para, para_node.get("content", []))

        elif t == "table":
            rows = content
            if not rows:
                return
            num_cols = len(rows[0].get("content", []))
            table = doc.add_table(rows=len(rows), cols=num_cols)
            table.style = "Table Grid"
            for r_idx, row in enumerate(rows):
                for c_idx, cell in enumerate(row.get("content", [])):
                    cell_text = _node_text(cell)
                    table.cell(r_idx, c_idx).text = cell_text
                    if r_idx == 0:
                        for run in table.cell(r_idx, c_idx).paragraphs[0].runs:
                            run.bold = True
            doc.add_paragraph()

        elif t == "codeBlock":
            try:
                para = doc.add_paragraph(style="No Spacing")
            except Exception:
                para = doc.add_paragraph()
            run = para.add_run(_node_text(node))
            run.font.name = "Courier New"
            run.font.size = Pt(10)

        elif t == "horizontalRule":
            doc.add_paragraph("─" * 50)

        elif t == "image":
            # Skip base64 images in DOCX for now - too complex without file path
            para = doc.add_paragraph("[Abbildung]")
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER

    process(doc_content)

    # Add page numbers in footer
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    for section in doc.sections:
        footer = section.footer
        footer_para = footer.paragraphs[0] if footer.paragraphs else footer.add_paragraph()
        footer_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = footer_para.add_run()
        fldChar = OxmlElement("w:fldChar")
        fldChar.set(qn("w:fldCharType"), "begin")
        run._r.append(fldChar)
        instrText = OxmlElement("w:instrText")
        instrText.text = "PAGE"
        run._r.append(instrText)
        fldChar2 = OxmlElement("w:fldChar")
        fldChar2.set(qn("w:fldCharType"), "end")
        run._r.append(fldChar2)

    doc.save(path)


# ── ODS export ───────────────────────────────────────────────────────────────

def export_ods(doc_content: dict, metadata: dict, path: str):
    """Export all tables from the document to an ODS spreadsheet."""
    try:
        from odf.opendocument import OpenDocumentSpreadsheet
        from odf.table import Table, TableRow, TableCell
        from odf.text import P

        ods = OpenDocumentSpreadsheet()
        sheet_index = 1

        meta_sheet = Table(name="Dokument")
        ods.spreadsheet.addElement(meta_sheet)
        for key, val in (metadata or {}).items():
            if val:
                row = TableRow()
                meta_sheet.addElement(row)
                c1 = TableCell()
                c1.addElement(P(text=str(key)))
                row.addElement(c1)
                c2 = TableCell()
                c2.addElement(P(text=str(val)))
                row.addElement(c2)

        def extract_tables(node: dict):
            if node.get("type") == "table":
                sheet = Table(name=f"Tabelle_{sheet_index}")
                ods.spreadsheet.addElement(sheet)
                for row_node in node.get("content", []):
                    tr = TableRow()
                    sheet.addElement(tr)
                    for cell_node in row_node.get("content", []):
                        tc = TableCell()
                        tc.addElement(P(text=_node_text(cell_node)))
                        tr.addElement(tc)
                return 1
            count = 0
            for c in node.get("content", []):
                count += extract_tables(c)
            return count

        extract_tables(doc_content)
        ods.save(path)

    except ImportError:
        # Fallback: CSV-like format
        with open(path.replace(".ods", "_tables.txt"), "w", encoding="utf-8") as f:
            f.write(tiptap_to_markdown(doc_content, metadata))
