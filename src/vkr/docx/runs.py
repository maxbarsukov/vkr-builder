import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor

from .. import docx_style
from ..md import append_inline_math, split_text_and_math
from .ooxml import el
from .state import (
    INLINE_RE,
    _ESC_CLOSE_BRACE,
    _ESC_CLOSE_BRACKET,
    _ESC_OPEN_BRACE,
    _ESC_OPEN_BRACKET,
)

def set_run_font(run, font_name=None, size_pt=None, bold=None, color_rgb=None,
                 italic=None):
    if font_name is None:
        font_name = docx_style.FONT_FAMILY
    if font_name is not None:
        run.font.name = font_name
        rPr = run._element.get_or_add_rPr()
        rFonts = rPr.find(qn("w:rFonts"))
        if rFonts is None:
            rFonts = OxmlElement("w:rFonts")
            rPr.insert(0, rFonts)
        for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
            rFonts.set(qn(attr), font_name)
    if size_pt is not None:
        run.font.size = Pt(size_pt)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color_rgb is not None:
        run.font.color.rgb = RGBColor(*color_rgb)

def add_error_run(paragraph, text):
    run = paragraph.add_run()
    run.add_text(text)
    set_run_font(
        run,
        font_name=docx_style.FONT_FAMILY,
        size_pt=docx_style.BODY_FONT_PT,
        bold=False,
        italic=False,
        color_rgb=docx_style.COLOR_RGB_TUPLE_ERROR,
    )
    return run

def _force_paragraph_runs_bold(paragraph, want_bold: bool) -> None:
    _force_paragraph_runs_flag(paragraph, "w:b", "w:bCs", want_bold)

def _force_paragraph_runs_italic(paragraph, want_italic: bool) -> None:
    _force_paragraph_runs_flag(paragraph, "w:i", "w:iCs", want_italic)

def _force_paragraph_runs_flag(
    paragraph, tag_on: str, tag_cs: str, want_on: bool
) -> None:
    for r_elem in paragraph._element.iter():
        if r_elem.tag != qn("w:r"):
            continue
        rPr = r_elem.find(qn("w:rPr"))
        if rPr is None:
            rPr = OxmlElement("w:rPr")
            r_elem.insert(0, rPr)
        for tag in (qn(tag_on), qn(tag_cs)):
            for old in list(rPr.findall(tag)):
                rPr.remove(old)
        if want_on:
            on = OxmlElement(tag_on)
            on.set(qn("w:val"), "1")
            rPr.append(on)
            cs = OxmlElement(tag_cs)
            cs.set(qn("w:val"), "1")
            rPr.append(cs)
        else:
            for tnm in (tag_on, tag_cs):
                el = OxmlElement(tnm)
                el.set(qn("w:val"), "0")
                rPr.append(el)

def _normalize_text(s):
    return re.sub(r"\s+", " ", s).strip()

def _apply_bracket_escapes(text: str) -> str:
    if not text:
        return text
    out = []
    i = 0
    n = len(text)
    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] in "[{}]":
            ch = text[i + 1]
            out.append(
                {
                    "[": _ESC_OPEN_BRACKET,
                    "]": _ESC_CLOSE_BRACKET,
                    "{": _ESC_OPEN_BRACE,
                    "}": _ESC_CLOSE_BRACE,
                }[ch]
            )
            i += 2
            continue
        out.append(text[i])
        i += 1
    return "".join(out)

def _restore_bracket_escapes(text: str) -> str:
    return (
        text.replace(_ESC_OPEN_BRACKET, "[")
        .replace(_ESC_CLOSE_BRACKET, "]")
        .replace(_ESC_OPEN_BRACE, "{")
        .replace(_ESC_CLOSE_BRACE, "}")
    )

def _add_markup_runs(paragraph, text, base_size_pt=None, base_font=None):
    if base_size_pt is None:
        base_size_pt = docx_style.BODY_FONT_PT
    if base_font is None:
        base_font = docx_style.FONT_FAMILY
    chunks = INLINE_RE.split(text)
    for chunk in chunks:
        if not chunk:
            continue
        if chunk.startswith("**") and chunk.endswith("**"):
            r = paragraph.add_run(chunk[2:-2])
            set_run_font(
                r,
                font_name=base_font,
                size_pt=base_size_pt,
                bold=False,
                italic=False,
                color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
            )
        elif chunk.startswith("*") and chunk.endswith("*") and len(chunk) > 2:
            r = paragraph.add_run(chunk[1:-1])
            set_run_font(r, font_name=base_font, size_pt=base_size_pt, italic=True,
                         bold=False, color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK)
        elif chunk.startswith("`") and chunk.endswith("`"):
            r = paragraph.add_run(chunk[1:-1])
            set_run_font(r, font_name=base_font, size_pt=base_size_pt, italic=True,
                         bold=False, color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK)
        else:
            r = paragraph.add_run(chunk)
            set_run_font(
                r,
                font_name=base_font,
                size_pt=base_size_pt,
                bold=False,
                italic=False,
                color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK,
            )

def add_runs(paragraph, text, base_size_pt=None, base_font=None, normalise_dashes=True):
    if base_size_pt is None:
        base_size_pt = docx_style.BODY_FONT_PT
    if base_font is None:
        base_font = docx_style.FONT_FAMILY
    text = _normalize_text(text)
    if normalise_dashes:
        text = docx_style.normalise_body_dashes(text)
    for kind, chunk in split_text_and_math(text):
        if kind == "math":
            append_inline_math(paragraph, chunk)
        elif chunk:
            _add_markup_runs(paragraph, chunk, base_size_pt=base_size_pt, base_font=base_font)
