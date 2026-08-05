import re

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .. import crossref, docx_style
from ..md import append_display_math
from . import state
from .bookmarks import (
    _next_bookmark_id,
    _wrap_with_bookmark,
)
from .ooxml import _insert_tblpr_child_in_order
from .runs import (
    _force_paragraph_runs_bold,
    _force_paragraph_runs_italic,
    add_error_run,
    add_runs,
    set_run_font,
)
from .state import log

def _table_col_widths_dxa(header, rows, n_cols):
    PAGE_WIDTH_DXA = docx_style.CONTENT_TEXT_WIDTH_DXA
    CHAR_DXA = 160

    def longest_word(s):
        return max((len(w) for w in s.split()), default=1)

    min_widths = []
    for j in range(n_cols):
        col_texts = [header[j]] + [r[j] for r in rows]
        max_word = max(longest_word(t) for t in col_texts)
        min_widths.append((max_word + 2) * CHAR_DXA)

    total = sum(min_widths)
    if total <= PAGE_WIDTH_DXA:
        slack = PAGE_WIDTH_DXA - total
        phrase_weights = []
        for j in range(n_cols):
            col_texts = [header[j]] + [r[j] for r in rows]
            phrase_weights.append(max(len(t) for t in col_texts))
        pwt_total = sum(phrase_weights) or 1
        col_widths_dxa = [
            min_widths[j] + int(slack * phrase_weights[j] / pwt_total)
            for j in range(n_cols)
        ]
    else:
        col_widths_dxa = [
            int(PAGE_WIDTH_DXA * min_widths[j] / total)
            for j in range(n_cols)
        ]
    col_widths_dxa[-1] += PAGE_WIDTH_DXA - sum(col_widths_dxa)
    return col_widths_dxa


def _render_table_fragment(doc, header, aligns, data_rows, col_widths_dxa, n_cols):
    PAGE_WIDTH_DXA = docx_style.CONTENT_TEXT_WIDTH_DXA
    table = doc.add_table(rows=len(data_rows) + 1, cols=n_cols)
    table.style = "Table Grid"
    table.autofit = False

    tblPr = table._tbl.find(qn("w:tblPr"))
    if tblPr is not None:
        for old in list(tblPr.findall(qn("w:tblLayout"))):
            tblPr.remove(old)
        tbl_layout = OxmlElement("w:tblLayout")
        tbl_layout.set(qn("w:type"), "autofit")
        tblPr.append(tbl_layout)
        for old in list(tblPr.findall(qn("w:tblW"))):
            tblPr.remove(old)
        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:type"), "dxa")
        tblW.set(qn("w:w"), str(PAGE_WIDTH_DXA))
        tblPr.append(tblW)

    grid = table._tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for gc in list(grid.findall(qn("w:gridCol"))):
            grid.remove(gc)
        for w in col_widths_dxa:
            gc = OxmlElement("w:gridCol")
            gc.set(qn("w:w"), str(w))
            grid.append(gc)

    if tblPr is not None:
        for old in list(tblPr.findall(qn("w:tblCellMar"))):
            tblPr.remove(old)
        cell_mar = OxmlElement("w:tblCellMar")
        for side, val in [("top", "0"), ("left", "60"),
                          ("bottom", "0"), ("right", "60")]:
            el = OxmlElement(f"w:{side}")
            el.set(qn("w:w"), val)
            el.set(qn("w:type"), "dxa")
            cell_mar.append(el)
        tblPr.append(cell_mar)
    for row in table._tbl.findall(qn("w:tr")):
        for j, tc in enumerate(row.findall(qn("w:tc"))):
            tcPr = tc.find(qn("w:tcPr"))
            if tcPr is None:
                tcPr = OxmlElement("w:tcPr")
                tc.insert(0, tcPr)
            for old in list(tcPr.findall(qn("w:tcW"))):
                tcPr.remove(old)
            tcW = OxmlElement("w:tcW")
            tcW.set(qn("w:type"), "dxa")
            tcW.set(qn("w:w"), str(col_widths_dxa[j] if j < len(col_widths_dxa) else 0))
            tcPr.append(tcW)

    def _set_cell(cell, txt, align, bold=False):
        cell.text = ""
        para = cell.paragraphs[0]
        if align == "center":
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif align == "right":
            para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        else:
            para.alignment = WD_ALIGN_PARAGRAPH.LEFT
        para.paragraph_format.first_line_indent = Cm(0)
        para.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        para.paragraph_format.space_after = Pt(0)
        pPr = para._element.get_or_add_pPr()
        if pPr.find(qn("w:suppressAutoHyphens")) is None:
            pPr.append(OxmlElement("w:suppressAutoHyphens"))
        add_runs(para, txt.strip(), base_size_pt=docx_style.TABLE_CELL_FONT_PT)
        for r in para.runs:
            set_run_font(r, font_name=docx_style.FONT_FAMILY, size_pt=docx_style.TABLE_CELL_FONT_PT,
                         bold=bold, italic=False,
                         color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK)
        _force_paragraph_runs_bold(para, bold)

    for j, txt in enumerate(header):
        align = aligns[j] if j < len(aligns) else "left"
        _set_cell(table.cell(0, j), txt, align, bold=False)

    for i, row in enumerate(data_rows):
        for j, txt in enumerate(row):
            align = aligns[j] if j < len(aligns) else "left"
            _set_cell(table.cell(i + 1, j), txt, align, bold=False)

    for idx, tr in enumerate(table._tbl.findall(qn("w:tr"))):
        trPr = tr.find(qn("w:trPr"))
        if trPr is None:
            trPr = OxmlElement("w:trPr")
            tr.insert(0, trPr)
        if trPr.find(qn("w:cantSplit")) is None:
            trPr.append(OxmlElement("w:cantSplit"))
        if idx == 0 and trPr.find(qn("w:tblHeader")) is None:
            th = OxmlElement("w:tblHeader")
            th.set(qn("w:val"), "true")
            trPr.append(th)

    return table


def add_table_continuation_caption(doc, table_number):
    n = "" if table_number is None else str(table_number)
    try:
        label = docx_style.TABLE_CONTINUATION_LABEL.format(n=n)
    except (KeyError, IndexError, ValueError):
        label = f"{docx_style.TABLE_CONTINUATION_LABEL} {n}".strip()

    p = doc.add_paragraph(style=docx_style.STYLE_TABLE_CAPTION)
    pf = p.paragraph_format
    pf.page_break_before = True
    pf.keep_with_next = True
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_before = Pt(0)
    pf.space_after = Pt(6)
    pf.first_line_indent = Cm(0)
    p.alignment = docx_style.table_continuation_alignment()
    add_runs(p, label)
    _force_paragraph_runs_bold(p, False)
    return p


def add_table(doc, header, aligns, rows, *, split_after=(), table_number=None):
    n_cols = max(len(header), max((len(r) for r in rows), default=0))

    def pad(row):
        return list(row) + [""] * (n_cols - len(row))
    header = pad(header)
    rows = [pad(r) for r in rows]

    col_widths_dxa = _table_col_widths_dxa(header, rows, n_cols)

    cuts = sorted({int(b) for b in split_after if 0 < int(b) < len(rows)})
    bounds = [0] + cuts + [len(rows)]

    table = None
    for f in range(len(bounds) - 1):
        a, b = bounds[f], bounds[f + 1]
        if f > 0:
            add_table_continuation_caption(doc, table_number)
        table = _render_table_fragment(
            doc, header, aligns, rows[a:b], col_widths_dxa, n_cols
        )

    _add_block_spacer(doc)
    return table

def _add_block_spacer(doc, height_pt=None):
    if height_pt is None:
        height_pt = docx_style.BODY_FONT_PT
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.first_line_indent = Cm(0)
    pf.left_indent = Cm(0)
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    pf.line_spacing = Pt(height_pt)
    return p

def add_image(doc, path, max_width_cm=14):
    _add_block_spacer(doc)

    p = doc.add_paragraph(style=docx_style.STYLE_FIGURE)
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    run = p.add_run()
    try:
        run.add_picture(path, width=Cm(max_width_cm))
    except Exception as e:
        add_error_run(p, f"Не удалось найти файл: {path}")
        log.warning("could not insert image %s: %s", path, e, extra={"rule": "image"})

def add_caption(doc, text, kind):
    xref_key = crossref.extract_key(text)
    text = crossref.render_caption_label(text, state._XREF, kind)
    text = crossref.resolve_references(text, state._XREF)
    text = text.strip()
    if docx_style.DASH_NORMALIZE:
        text = re.sub(
            r"^(Рисунок|Таблица|Листинг)\s+([\w\d.А-Яа-я]+)\s*[—–-]\s+",
            lambda m: f"{m.group(1)} {m.group(2)} {docx_style.DASH_CAPTION} ",
            text,
        )

    if kind == "figure":
        p = doc.add_paragraph(style=docx_style.STYLE_FIGURE)
    elif kind in ("table", "listing"):
        _add_block_spacer(doc)
        p = doc.add_paragraph(style=docx_style.STYLE_TABLE_CAPTION)
        p.paragraph_format.keep_with_next = True
    else:
        p = doc.add_paragraph(style=docx_style.STYLE_BODY)

    pf = p.paragraph_format
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.space_after = Pt(6)
    if kind == "figure":
        pf.keep_with_next = False
        pf.keep_together = True
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)

    add_runs(p, text, normalise_dashes=False)
    _force_paragraph_runs_bold(p, False)

    if xref_key:
        bm = state._XREF_BOOKMARKS.get((kind, xref_key))
        if bm:
            _wrap_with_bookmark(p, bm, _next_bookmark_id())

    if kind == "figure":
        _add_block_spacer(doc)

def _tbl_set_no_borders_and_cell_mar(table):
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    for old in list(tblPr.findall(qn("w:tblBorders"))):
        tblPr.remove(old)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{side}")
        b.set(qn("w:val"), "nil")
        b.set(qn("w:sz"), "0")
        b.set(qn("w:space"), "0")
        b.set(qn("w:color"), "auto")
        borders.append(b)
    _insert_tblpr_child_in_order(tblPr, borders)
    for old in list(tblPr.findall(qn("w:tblCellMar"))):
        tblPr.remove(old)
    cell_mar = OxmlElement("w:tblCellMar")
    for side in ("top", "left", "bottom", "right"):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), "0")
        el.set(qn("w:type"), "dxa")
        cell_mar.append(el)
    _insert_tblpr_child_in_order(tblPr, cell_mar)

def _set_cell_width_and_valign_center(cell, width_dxa: int):
    tc = cell._tc
    tcPr = tc.find(qn("w:tcPr"))
    if tcPr is None:
        tcPr = OxmlElement("w:tcPr")
        tc.insert(0, tcPr)
    for old in list(tcPr.findall(qn("w:tcW"))):
        tcPr.remove(old)
    tcW = OxmlElement("w:tcW")
    tcW.set(qn("w:type"), "dxa")
    tcW.set(qn("w:w"), str(width_dxa))
    tcPr.append(tcW)
    for old in list(tcPr.findall(qn("w:vAlign"))):
        tcPr.remove(old)
    va = OxmlElement("w:vAlign")
    va.set(qn("w:val"), "center")
    tcPr.append(va)

def add_math_block(doc, latex: str, number: str | None = None, bookmark: str | None = None):
    _add_block_spacer(doc)
    if not number:
        p = doc.add_paragraph(style=docx_style.STYLE_BODY)
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf = p.paragraph_format
        pf.first_line_indent = Cm(0)
        pf.left_indent = Cm(0)
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)
        append_display_math(p, latex)
        _add_block_spacer(doc)
        return

    total = docx_style.CONTENT_TEXT_WIDTH_DXA
    num_w = min(1000, max(540, total // 7))
    form_w = total - num_w

    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    tbl = table._tbl
    tblPr = tbl.tblPr
    if tblPr is None:
        tblPr = OxmlElement("w:tblPr")
        tbl.insert(0, tblPr)
    for old in list(tblPr.findall(qn("w:tblW"))):
        tblPr.remove(old)
    tblW = OxmlElement("w:tblW")
    tblW.set(qn("w:type"), "dxa")
    tblW.set(qn("w:w"), str(total))
    _insert_tblpr_child_in_order(tblPr, tblW)
    for old in list(tblPr.findall(qn("w:tblLayout"))):
        tblPr.remove(old)
    tbl_layout = OxmlElement("w:tblLayout")
    tbl_layout.set(qn("w:type"), "fixed")
    _insert_tblpr_child_in_order(tblPr, tbl_layout)
    _tbl_set_no_borders_and_cell_mar(table)

    grid = tbl.find(qn("w:tblGrid"))
    if grid is not None:
        for gc in list(grid.findall(qn("w:gridCol"))):
            grid.remove(gc)
        for w in (form_w, num_w):
            gc = OxmlElement("w:gridCol")
            gc.set(qn("w:w"), str(w))
            grid.append(gc)

    row = table.rows[0]
    cells = row.cells
    _set_cell_width_and_valign_center(cells[0], form_w)
    _set_cell_width_and_valign_center(cells[1], num_w)

    cells[0].text = ""
    p_f = cells[0].paragraphs[0]
    p_f.style = docx_style.STYLE_BODY
    p_f.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_ff = p_f.paragraph_format
    p_ff.first_line_indent = Cm(0)
    p_ff.left_indent = Cm(0)
    p_ff.space_before = Pt(0)
    p_ff.space_after = Pt(0)
    append_display_math(p_f, latex)
    _force_paragraph_runs_bold(p_f, False)

    cells[1].text = ""
    p_n = cells[1].paragraphs[0]
    p_n.style = docx_style.STYLE_BODY
    p_n.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_nf = p_n.paragraph_format
    p_nf.first_line_indent = Cm(0)
    p_nf.left_indent = Cm(0)
    p_nf.space_before = Pt(0)
    p_nf.space_after = Pt(0)
    add_runs(p_n, number)
    _force_paragraph_runs_bold(p_n, False)
    if bookmark:
        _wrap_with_bookmark(p_n, bookmark, _next_bookmark_id())

    _add_block_spacer(doc)

def add_code_block(doc, lines, lang=""):
    while lines and lines[0].strip() == "":
        lines = lines[1:]
    while lines and lines[-1].strip() == "":
        lines = lines[:-1]
    if not lines:
        return

    table = doc.add_table(rows=1, cols=1)
    table.style = "Table Grid"
    table.autofit = False

    content_width_dxa = docx_style.CONTENT_TEXT_WIDTH_DXA
    tbl_pr = table._element.find(qn("w:tblPr"))
    if tbl_pr is not None:
        for old in list(tbl_pr.findall(qn("w:tblW"))):
            tbl_pr.remove(old)
        for old in list(tbl_pr.findall(qn("w:tblLayout"))):
            tbl_pr.remove(old)

        tblW = OxmlElement("w:tblW")
        tblW.set(qn("w:w"), str(content_width_dxa))
        tblW.set(qn("w:type"), "dxa")
        _insert_tblpr_child_in_order(tbl_pr, tblW)

        tblLayout = OxmlElement("w:tblLayout")
        tblLayout.set(qn("w:type"), "fixed")
        _insert_tblpr_child_in_order(tbl_pr, tblLayout)

    cell = table.cell(0, 0)
    tcW = cell._tc.find(qn("w:tcPr"))
    if tcW is None:
        tcW = OxmlElement("w:tcPr")
        cell._tc.insert(0, tcW)
    for old in list(tcW.findall(qn("w:tcW"))):
        tcW.remove(old)
    w = OxmlElement("w:tcW")
    w.set(qn("w:w"), str(content_width_dxa))
    w.set(qn("w:type"), "dxa")
    tcW.append(w)

    margins = OxmlElement("w:tcMar")
    for side, val in [("top", "80"), ("start", "120"),
                      ("bottom", "80"), ("end", "120")]:
        m = OxmlElement(f"w:{side}")
        m.set(qn("w:w"), val)
        m.set(qn("w:type"), "dxa")
        margins.append(m)
    for old in list(tcW.findall(qn("w:tcMar"))):
        tcW.remove(old)
    tcW.append(margins)

    default_p = cell.paragraphs[0]

    for i, line in enumerate(lines):
        if i == 0:
            p = default_p
            for r in list(p.runs):
                r._element.getparent().remove(r._element)
            p.text = ""
        else:
            p = cell.add_paragraph()

        pf = p.paragraph_format
        pf.first_line_indent = Cm(0)
        pf.left_indent = Cm(0)
        pf.line_spacing = 1.0
        pf.space_after = Pt(0)
        pf.space_before = Pt(0)
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT

        if line == "":
            run = p.add_run(" ")
        else:
            run = p.add_run(line)
            t = run._element.find(qn("w:t"))
            if t is not None:
                t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        set_run_font(
            run,
            font_name=docx_style.LISTING_FONT_FAMILY,
            size_pt=docx_style.CODE_LINE_FONT_PT,
            bold=False,
            italic=False,
            color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
        )

    for para in cell.paragraphs:
        _force_paragraph_runs_bold(para, False)
        _force_paragraph_runs_italic(para, False)

    _add_block_spacer(doc)
