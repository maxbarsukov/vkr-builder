import re

from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .. import docx_style, gost_sections
from . import state
from .bookmarks import (
    _add_runs_with_links,
    _next_bookmark_id,
    _unwrap_bold_around_appendix_phrases,
    _wrap_with_bookmark,
)
from .ooxml import page_break_before
from .runs import _force_paragraph_runs_bold, _normalize_text, add_runs, set_run_font
from .state import _CHAPTER_H1_RE

STRUCTURAL_HEADINGS = gost_sections.STRUCTURAL_HEADINGS

def _section_key(text):
    return (text or "").strip().upper()

def heading_kind(text):
    t = text.strip()
    u = t.upper()
    if u in STRUCTURAL_HEADINGS:
        return "structural"
    if u.startswith("ПРИЛОЖЕНИЕ"):
        return "structural"
    if re.match(r"^\d+\s+\S", t):
        return "chapter"
    if re.match(r"^Глава\s+\d+", u):
        return "chapter"
    return "structural"

def _title_case_ru(title: str) -> str:
    t = (title or "").strip()
    if not t:
        return t
    low = t.lower()
    return low[0].upper() + low[1:]

def format_chapter_heading(text: str) -> str:
    t = text.strip()
    m = _CHAPTER_H1_RE.match(t)
    if not m:
        return t
    num, title = m.group(1), m.group(2).strip()
    return f"{num} {_title_case_ru(title)}"

def _is_introduction_subsection(current_top: str | None, level: int) -> bool:
    return _section_key(current_top) == "ВВЕДЕНИЕ" and level >= 2

def heading_display_text(level: int, raw: str) -> str:
    text = (raw or "").strip()
    if level == 1:
        kind = heading_kind(text)
        if kind == "chapter":
            return format_chapter_heading(text)
        return text.upper()
    return text

def add_body_paragraph(doc, text):
    text = _normalize_text(text)
    text = _unwrap_bold_around_appendix_phrases(text)
    p = doc.add_paragraph(style=docx_style.STYLE_BODY)
    _add_runs_with_links(p, text)
    _force_paragraph_runs_bold(p, False)
    return p

def _apply_body_text_paragraph_format(paragraph, *, first_line_indent=None):
    if first_line_indent is None:
        first_line_indent = docx_style.BODY_FIRST_LINE_INDENT
    pf = paragraph.paragraph_format
    pf.first_line_indent = first_line_indent
    pf.line_spacing_rule = docx_style.BODY_LINE_SPACING_RULE
    pf.line_spacing = docx_style.BODY_LINE_SPACING
    paragraph.alignment = (
        WD_ALIGN_PARAGRAPH.JUSTIFY if docx_style.BODY_JUSTIFY else WD_ALIGN_PARAGRAPH.LEFT
    )

def add_dictionary_paragraph(doc, text):
    text = text.strip()

    p = doc.add_paragraph(style=docx_style.STYLE_BODY)
    pf = p.paragraph_format
    pf.space_after = Pt(6)
    _apply_body_text_paragraph_format(p, first_line_indent=Cm(0))
    add_runs(p, text)
    _force_paragraph_runs_bold(p, False)
    return p

def add_introduction_block_title(doc, text):
    p = doc.add_paragraph(style=docx_style.STYLE_BODY)
    pf = p.paragraph_format
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    _apply_body_text_paragraph_format(p)
    run = p.add_run(text.strip())
    set_run_font(
        run,
        font_name=docx_style.FONT_FAMILY,
        size_pt=docx_style.BODY_FONT_PT,
        bold=True,
        italic=False,
        color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
    )
    _force_paragraph_runs_bold(p, True)
    return p

def add_source_entry(doc, text):
    p = doc.add_paragraph(style=docx_style.STYLE_BODY)
    pf = p.paragraph_format
    pf.first_line_indent = docx_style.BODY_FIRST_LINE_INDENT
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT
    add_runs(p, text)
    m = re.match(r"^\s*(\d+)\.", text)
    if m:
        _wrap_with_bookmark(p, f"src_{m.group(1)}", _next_bookmark_id())
    _force_paragraph_runs_bold(p, False)
    return p

def _set_outline_level(paragraph, level_0_based):
    pPr = paragraph._element.get_or_add_pPr()
    for old in list(pPr.findall(qn("w:outlineLvl"))):
        pPr.remove(old)
    ol = OxmlElement("w:outlineLvl")
    ol.set(qn("w:val"), str(level_0_based))
    pPr.append(ol)

def add_heading_1(doc, text):
    kind = heading_kind(text)
    display = heading_display_text(1, text)
    p = doc.add_paragraph(style=docx_style.STYLE_HEADING_1)
    page_break_before(p)
    _set_outline_level(p, 0)

    pf = p.paragraph_format
    pf.space_before = Pt(0)
    pf.space_after = Pt(12)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.keep_with_next = True

    if kind == "structural":
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf.first_line_indent = docx_style.BODY_FIRST_LINE_INDENT

    key = text.strip()
    add_runs(p, display)
    bm_name = state._BOOKMARKS.get(key)
    if bm_name:
        _wrap_with_bookmark(p, bm_name, _next_bookmark_id())
    _force_paragraph_runs_bold(p, True)

def add_heading_2(doc, text, centered=False):
    p = doc.add_paragraph(style=docx_style.STYLE_HEADING_2)
    _set_outline_level(p, 1)

    pf = p.paragraph_format
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.keep_with_next = True

    if centered:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)
    else:
        p.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf.first_line_indent = docx_style.BODY_FIRST_LINE_INDENT

    key = text.strip()
    add_runs(p, text)
    bm_name = state._BOOKMARKS.get(key)
    if bm_name:
        _wrap_with_bookmark(p, bm_name, _next_bookmark_id())
    _force_paragraph_runs_bold(p, True)

def add_heading_3(doc, text):
    p = doc.add_paragraph(style=docx_style.STYLE_HEADING_3)
    _set_outline_level(p, 2)

    pf = p.paragraph_format
    pf.space_before = Pt(12)
    pf.space_after = Pt(6)
    pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
    pf.first_line_indent = docx_style.BODY_FIRST_LINE_INDENT
    pf.keep_with_next = True
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT

    key = text.strip()
    add_runs(p, text)
    bm_name = state._BOOKMARKS.get(key)
    if bm_name:
        _wrap_with_bookmark(p, bm_name, _next_bookmark_id())
    _force_paragraph_runs_bold(p, True)

def collect_toc_headings(elements):
    out = []
    current_top = None
    for e in elements:
        if e["type"] != "heading":
            continue
        level = e["level"]
        if level == 1:
            current_top = e["text"].strip()
        if level not in (1, 2, 3):
            continue
        if _is_introduction_subsection(current_top, level):
            continue
        raw = e["text"].strip()
        out.append((level, heading_display_text(level, raw), raw))
    return out
