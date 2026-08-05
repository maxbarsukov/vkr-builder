from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT, WD_TAB_LEADER
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm

from .. import docx_style
from ..docx_style import toc_style_for_level
from .bookmarks import _append_internal_hyperlink
from . import state
from .runs import set_run_font
from .state import _APPENDIX_TOC_H1_RE

def add_toc_heading(doc):
    p = doc.add_paragraph(style=docx_style.STYLE_TOC_HEADING)
    pPr = p._element.get_or_add_pPr()
    outlineLvl = OxmlElement("w:outlineLvl")
    outlineLvl.set(qn("w:val"), "9")
    pPr.append(outlineLvl)
    p.add_run("СОДЕРЖАНИЕ")

def add_toc_entries(doc, entries):
    from docx.enum.text import WD_TAB_ALIGNMENT, WD_TAB_LEADER

    for entry in entries:
        if len(entry) == 4:
            level, text, page, bookmark_key = entry
        else:
            level, text, page = entry
            bookmark_key = text
        style_name = toc_style_for_level(level)
        try:
            p = doc.add_paragraph(style=style_name)
        except KeyError:
            p = doc.add_paragraph(style=docx_style.STYLE_BODY)

        pf = p.paragraph_format
        pf.tab_stops.add_tab_stop(Cm(docx_style.CONTENT_TEXT_WIDTH_CM),
                                  alignment=WD_TAB_ALIGNMENT.RIGHT,
                                  leader=WD_TAB_LEADER.DOTS)
        pf.first_line_indent = Cm(0)
        if level == 2:
            pf.left_indent = Cm(0.5)
        elif level == 3:
            pf.left_indent = Cm(1.0)
        else:
            pf.left_indent = Cm(0)

        bm = state._BOOKMARKS.get((bookmark_key or text).strip())
        if bm:
            _append_internal_hyperlink(
                p, bm, (text, "\t", str(page)), font_size_pt=docx_style.TOC_ENTRY_FONT_PT
            )
        else:
            r0 = p.add_run(text)
            set_run_font(
                r0,
                font_name=docx_style.FONT_FAMILY,
                size_pt=docx_style.TOC_ENTRY_FONT_PT,
                bold=False,
                italic=False,
                color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
            )
            r1 = p.add_run("\t")
            set_run_font(
                r1,
                font_name=docx_style.FONT_FAMILY,
                size_pt=docx_style.TOC_ENTRY_FONT_PT,
                bold=False,
                italic=False,
                color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
            )
            r2 = p.add_run(str(page))
            set_run_font(
                r2,
                font_name=docx_style.FONT_FAMILY,
                size_pt=docx_style.TOC_ENTRY_FONT_PT,
                bold=False,
                italic=False,
                color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
            )

def collapse_appendix_toc_rows(headings, pages):
    if len(headings) != len(pages):
        raise ValueError("collapse_appendix_toc_rows: headings and pages differ in length")
    out = []
    n = len(headings)
    i = 0
    in_appendix = False

    def _is_appendix_h1(level: int, text: str) -> bool:
        if level != 1:
            return False
        u = text.strip().upper()
        return bool(_APPENDIX_TOC_H1_RE.match(u))

    while i < n:
        lv, tx, bm_key = headings[i]
        pg = pages[i]
        tx_st = tx.strip()
        bm_st = (bm_key or tx).strip()

        if in_appendix and lv in (2, 3):
            i += 1
            continue

        if _is_appendix_h1(lv, tx):
            merged = False
            if i + 1 < n and headings[i + 1][0] == 2:
                sub = headings[i + 1][1].strip()
                if not sub.upper().startswith("ПРИЛОЖЕНИЕ"):
                    disp = f"{tx_st.upper()} {sub}"
                    out.append((1, disp, pg, bm_st))
                    i += 2
                    in_appendix = True
                    merged = True
            if not merged:
                out.append((1, tx_st.upper(), pg, bm_st))
                i += 1
                in_appendix = True
            continue

        if in_appendix and lv == 1 and not _is_appendix_h1(lv, tx):
            in_appendix = False

        out.append((lv, tx_st, pg, bm_st))
        i += 1

    return out
