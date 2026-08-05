import re

from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .. import bibliography, crossref, docx_style
from ..docx_style import font_half_points
from ..md import append_inline_math, split_text_and_math
from . import state
from .runs import (
    _add_markup_runs,
    _apply_bracket_escapes,
    _normalize_text,
    _restore_bracket_escapes,
    set_run_font,
)
from .state import (
    APP_REF_RE,
    CITE_RE,
    FORMULA_TEXT_RE,
    _BOLD_WRAP_AROUND_APP_RE,
    _CYR_APPENDIX_LETTERS,
)

def _hyperlink_run_properties(font_pt: float) -> OxmlElement:
    rPr = OxmlElement("w:rPr")
    rFonts = OxmlElement("w:rFonts")
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rFonts.set(qn(attr), docx_style.FONT_FAMILY)
    rPr.append(rFonts)
    hp = font_half_points(font_pt)
    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), hp)
    rPr.append(sz)
    sz_cs = OxmlElement("w:szCs")
    sz_cs.set(qn("w:val"), hp)
    rPr.append(sz_cs)
    for tag in ("w:b", "w:bCs", "w:i", "w:iCs"):
        off = OxmlElement(tag)
        off.set(qn("w:val"), "0")
        rPr.append(off)
    u_none = OxmlElement("w:u")
    u_none.set(qn("w:val"), "none")
    rPr.append(u_none)
    return rPr

def _append_internal_hyperlink(
    paragraph, anchor, parts: tuple[str, ...], *, font_size_pt: float | None = None
):
    fs = font_size_pt if font_size_pt is not None else docx_style.BODY_FONT_PT
    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("w:anchor"), anchor)
    hyperlink.set(qn("w:history"), "1")

    for part in parts:
        if part == "":
            continue
        run = OxmlElement("w:r")
        run.append(_hyperlink_run_properties(fs))
        t = OxmlElement("w:t")
        t.text = part
        if part != part.strip() or "\t" in part or part.startswith(" ") or part.endswith(" "):
            t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        run.append(t)
        hyperlink.append(run)
    paragraph._element.append(hyperlink)

def _add_internal_hyperlink_run(
    paragraph, anchor, display_text, *, font_size_pt: float | None = None
):
    if not display_text:
        return
    _append_internal_hyperlink(
        paragraph, anchor, (display_text,), font_size_pt=font_size_pt
    )

def _appendix_letter_to_cyrillic(ch: str) -> str:
    if not ch:
        return ch
    u = ch.strip().upper()
    if not u:
        return ch
    if (
        len(u) == 1
        and ("А" <= u <= "Я" or u == "Ё")
    ):
        return u
    if len(u) == 1 and "A" <= u <= "Z":
        i = ord(u) - ord("A")
        if i < len(_CYR_APPENDIX_LETTERS):
            return _CYR_APPENDIX_LETTERS[i]
    return u

def _appendix_subsec_from_ref_suffix(suffix: str | None) -> str | None:
    if not suffix:
        return None
    if len(suffix) > 1 and suffix.startswith(".") and suffix[1:].isdigit():
        return suffix
    return None

def _unwrap_bold_around_appendix_phrases(text: str) -> str:
    prev = None
    out = text
    while prev != out:
        prev = out
        out = _BOLD_WRAP_AROUND_APP_RE.sub(lambda m: m.group(1) + m.group(2), out)
    return out

def _cite_numbers(inner):
    return bibliography.cite_numbers(inner)

def _prescan_references(elements):
    state._REFERENCED_SOURCES.clear()
    state._REFERENCED_APP_KEYS.clear()
    for e in elements:
        if e["type"] not in ("para", "list_item"):
            continue
        text = _normalize_text(e.get("text", ""))
        for m in CITE_RE.finditer(text):
            for num in _cite_numbers(m.group(0)[1:-1]):
                state._REFERENCED_SOURCES.add(str(num))
        for m in APP_REF_RE.finditer(text):
            letter = _appendix_letter_to_cyrillic(m.group(1))
            subsec = _appendix_subsec_from_ref_suffix(m.group(2))
            state._REFERENCED_APP_KEYS.add((letter, subsec))

def _heading_is_referenced(text):
    t = text.strip()
    for letter, subsec in state._REFERENCED_APP_KEYS:
        if subsec:
            if t.startswith(f"{letter}{subsec} ") or t == f"{letter}{subsec}":
                return True
        else:
            if t.startswith(f"ПРИЛОЖЕНИЕ {letter}"):
                return True
    return False

def _add_plain_text_run(paragraph, text, bold=False, italic=False):
    if not text:
        return
    run = paragraph.add_run(text)
    set_run_font(run, font_name=docx_style.FONT_FAMILY, size_pt=docx_style.BODY_FONT_PT,
                 bold=bold, italic=italic, color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK)
    t = run._element.find(qn("w:t"))
    if t is not None and (text != text.strip() or " " in text):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")

def _emit_keyed_citation_links(paragraph, full_match):
    keys = bibliography.citation_keys(full_match)
    nums = []
    for key in keys:
        num = state._CITE_KEY_NUM.get(key)
        if num is None:
            _add_plain_text_run(paragraph, full_match)
            return
        nums.append(num)
    nums = sorted(set(nums))
    _add_plain_text_run(paragraph, "[")
    for idx, num in enumerate(nums):
        if idx:
            _add_plain_text_run(paragraph, "; ")
        _add_internal_hyperlink_run(paragraph, f"src_{num}", str(num))
    _add_plain_text_run(paragraph, "]")

def _emit_citation_links(paragraph, full_match):
    nums = bibliography.numbers_in_citation_token(full_match)
    if not nums or not all(n in state._KNOWN_SOURCE_NUMS for n in nums):
        _add_plain_text_run(paragraph, _restore_bracket_escapes(full_match))
        return
    inner = full_match[1:-1]
    parts = re.split(r"(\d+)", inner)
    if not any(p.isdigit() for p in parts):
        _add_plain_text_run(paragraph, _restore_bracket_escapes(full_match))
        return
    _add_plain_text_run(paragraph, "[")
    for part in parts:
        if part.isdigit():
            _add_internal_hyperlink_run(paragraph, f"src_{part}", part)
        elif part:
            _add_plain_text_run(paragraph, part)
    _add_plain_text_run(paragraph, "]")

def _emit_formula_text_link(paragraph, full_match, num_label: str):
    bm = state._FORMULA_NUM_TO_BOOKMARK.get(num_label)
    if bm:
        _add_internal_hyperlink_run(paragraph, bm, full_match)
    else:
        _add_plain_text_run(paragraph, full_match)

def _resolve_appendix_anchor(target_letter, target_subsec):
    if target_subsec:
        for key, bm in state._BOOKMARKS.items():
            if key.startswith(f"{target_letter}{target_subsec} "):
                return bm
    for key, bm in state._BOOKMARKS.items():
        if key.startswith(f"ПРИЛОЖЕНИЕ {target_letter}"):
            return bm
    return None

def _add_runs_no_strip(paragraph, text):
    for kind, chunk in split_text_and_math(text):
        if kind == "math":
            append_inline_math(paragraph, chunk)
        elif chunk:
            _add_markup_runs(paragraph, chunk)

def _wrap_with_bookmark(paragraph, bookmark_name, bookmark_id):
    p_elem = paragraph._element
    runs = p_elem.findall(qn("w:r"))
    if not runs:
        return
    bs = OxmlElement("w:bookmarkStart")
    bs.set(qn("w:id"), str(bookmark_id))
    bs.set(qn("w:name"), bookmark_name)
    be = OxmlElement("w:bookmarkEnd")
    be.set(qn("w:id"), str(bookmark_id))
    runs[0].addprevious(bs)
    runs[-1].addnext(be)

def _next_bookmark_id():
    state._BOOKMARK_ID[0] += 1
    return state._BOOKMARK_ID[0]

def _xref_bookmark_name(kind, key):
    return _slugify_bookmark(f"xr_{kind}_{key}")

def _build_xref_bookmarks():
    state._XREF_BOOKMARKS.clear()
    state._FORMULA_NUM_TO_BOOKMARK.clear()
    for kind, key_map in state._XREF.items():
        for key in key_map:
            state._XREF_BOOKMARKS[(kind, key)] = _xref_bookmark_name(kind, key)
    for key, num in state._XREF.get(crossref.FORMULA, {}).items():
        bm = state._XREF_BOOKMARKS.get((crossref.FORMULA, key))
        if bm:
            state._FORMULA_NUM_TO_BOOKMARK[num] = bm
            state._FORMULA_NUM_TO_BOOKMARK[f"({num})"] = bm

def _emit_xref_link(paragraph, match):
    target = crossref.reference_target(match, state._XREF)
    if target is None:
        _add_plain_text_run(paragraph, match.group(0))
        return
    kind, key, display = target
    bm = state._XREF_BOOKMARKS.get((kind, key))
    if bm:
        _add_internal_hyperlink_run(paragraph, bm, display)
    else:
        _add_plain_text_run(paragraph, display)

def _add_runs_with_links(paragraph, text):
    text = _apply_bracket_escapes(text)
    text = docx_style.normalise_body_dashes(text)
    matches = []
    for m in APP_REF_RE.finditer(text):
        matches.append((m.start(), m.end(), "app", m))
    for m in CITE_RE.finditer(text):
        matches.append((m.start(), m.end(), "cite", m))
    for m in bibliography.KEYED_CITE_RE.finditer(text):
        matches.append((m.start(), m.end(), "kcite", m))
    for m in crossref.REFERENCE_RE.finditer(text):
        matches.append((m.start(), m.end(), "xref", m))
    for m in FORMULA_TEXT_RE.finditer(text):
        matches.append((m.start(), m.end(), "formtext", m))
    matches.sort(key=lambda t: t[0])

    if not matches:
        _add_runs_no_strip(paragraph, _restore_bracket_escapes(text))
        return

    cursor = 0
    for start, end, kind, m in matches:
        if start < cursor:
            continue
        if start > cursor:
            _add_runs_no_strip(paragraph, _restore_bracket_escapes(text[cursor:start]))
        if kind == "app":
            full_match = m.group(0)
            letter = _appendix_letter_to_cyrillic(m.group(1))
            subsec = _appendix_subsec_from_ref_suffix(m.group(2))
            anchor = _resolve_appendix_anchor(letter, subsec)
            if anchor:
                _add_internal_hyperlink_run(paragraph, anchor, full_match)
            else:
                _add_plain_text_run(paragraph, full_match)
        elif kind == "cite":
            _emit_citation_links(paragraph, m.group(0))
        elif kind == "kcite":
            _emit_keyed_citation_links(paragraph, m.group(0))
        elif kind == "formtext":
            _emit_formula_text_link(paragraph, m.group(0), m.group(1))
        else:
            _emit_xref_link(paragraph, m)
        cursor = end

    if cursor < len(text):
        _add_runs_no_strip(paragraph, _restore_bracket_escapes(text[cursor:]))

def heading_bookmark_name(heading_text: str) -> str:
    return _slugify_bookmark(heading_text)


def _slugify_bookmark(s):
    s = re.sub(r"\s+", "_", s.strip())
    s = re.sub(r"[^\w_А-Яа-яЁё.-]", "", s)
    if not s:
        s = "x"
    s = "_" + s
    return s[:40]

def _prescan_bookmarks(elements):
    state._BOOKMARKS.clear()
    for e in elements:
        if e["type"] == "heading":
            key = e["text"].strip()
            state._BOOKMARKS[key] = _slugify_bookmark(key)
