from docx.oxml import OxmlElement
from docx.oxml.ns import qn

from .. import docx_style
from ..docx_style import font_half_points, list_numbering_indents_dxa
from .bookmarks import _add_runs_with_links, _unwrap_bold_around_appendix_phrases
from .runs import _force_paragraph_runs_bold, _normalize_text, set_run_font

class NumberingManager:
    def __init__(self, doc):
        self.doc = doc
        self.numbering_part = doc.part.numbering_part
        self.numbering_root = self.numbering_part.element

        existing_abs = [
            int(e.get(qn("w:abstractNumId")))
            for e in self.numbering_root.findall(qn("w:abstractNum"))
        ]
        existing_num = [
            int(e.get(qn("w:numId")))
            for e in self.numbering_root.findall(qn("w:num"))
        ]
        self._next_abs_id = (max(existing_abs) + 1) if existing_abs else 0
        self._next_num_id = (max(existing_num) + 1) if existing_num else 1
        self._abstract_cache: dict[tuple, int] = {}

    @staticmethod
    def _lvl_num_fmt(kind):
        return {
            "decimal-paren": "decimal",
            "russian-paren": "russianLower",
            "bullet-dash": "bullet",
        }[kind]

    @staticmethod
    def _lvl_text(kind, ilvl):
        if kind == "bullet-dash":
            return "\u2013"
        return f"%{ilvl + 1})"

    def _make_level(self, ilvl, kind):
        lvl = OxmlElement("w:lvl")
        lvl.set(qn("w:ilvl"), str(ilvl))

        start = OxmlElement("w:start")
        start.set(qn("w:val"), "1")
        lvl.append(start)

        nf = OxmlElement("w:numFmt")
        nf.set(qn("w:val"), self._lvl_num_fmt(kind))
        lvl.append(nf)

        lt = OxmlElement("w:lvlText")
        lt.set(qn("w:val"), self._lvl_text(kind, ilvl))
        lvl.append(lt)

        jc = OxmlElement("w:lvlJc")
        jc.set(qn("w:val"), "left")
        lvl.append(jc)

        pPr = OxmlElement("w:pPr")
        ind = OxmlElement("w:ind")
        left_dxa, hanging_dxa = list_numbering_indents_dxa()
        ind.set(qn("w:left"), str(left_dxa + ilvl * (left_dxa - hanging_dxa)))
        ind.set(qn("w:hanging"), str(hanging_dxa))
        pPr.append(ind)
        lvl.append(pPr)

        hp = font_half_points(docx_style.BODY_FONT_PT)
        rPr = OxmlElement("w:rPr")
        rFonts = OxmlElement("w:rFonts")
        rFonts.set(qn("w:ascii"), docx_style.FONT_FAMILY)
        rFonts.set(qn("w:hAnsi"), docx_style.FONT_FAMILY)
        rFonts.set(qn("w:cs"), docx_style.FONT_FAMILY)
        rFonts.set(qn("w:eastAsia"), docx_style.FONT_FAMILY)
        rFonts.set(qn("w:hint"), "default")
        rPr.append(rFonts)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), hp)
        rPr.append(sz)
        szCs = OxmlElement("w:szCs")
        szCs.set(qn("w:val"), hp)
        rPr.append(szCs)
        lvl.append(rPr)
        return lvl

    def _get_abstract(self, level_kinds):
        if level_kinds in self._abstract_cache:
            return self._abstract_cache[level_kinds]

        abs_id = self._next_abs_id
        self._next_abs_id += 1

        abstract = OxmlElement("w:abstractNum")
        abstract.set(qn("w:abstractNumId"), str(abs_id))

        mlt = OxmlElement("w:multiLevelType")
        mlt.set(qn("w:val"),
                "multiLevel" if len(level_kinds) > 1 else "singleLevel")
        abstract.append(mlt)

        for ilvl, kind in enumerate(level_kinds):
            abstract.append(self._make_level(ilvl, kind))

        last_abstract = None
        for ch in self.numbering_root:
            if ch.tag == qn("w:abstractNum"):
                last_abstract = ch
        if last_abstract is not None:
            last_abstract.addnext(abstract)
        else:
            self.numbering_root.insert(0, abstract)

        self._abstract_cache[level_kinds] = abs_id
        return abs_id

    def add_list(self, level_kinds):
        level_kinds = tuple(level_kinds)
        abs_id = self._get_abstract(level_kinds)
        num_id = self._next_num_id
        self._next_num_id += 1

        num = OxmlElement("w:num")
        num.set(qn("w:numId"), str(num_id))

        abs_ref = OxmlElement("w:abstractNumId")
        abs_ref.set(qn("w:val"), str(abs_id))
        num.append(abs_ref)

        for ilvl in range(len(level_kinds)):
            lvl_override = OxmlElement("w:lvlOverride")
            lvl_override.set(qn("w:ilvl"), str(ilvl))
            start_override = OxmlElement("w:startOverride")
            start_override.set(qn("w:val"), "1")
            lvl_override.append(start_override)
            num.append(lvl_override)

        self.numbering_root.append(num)
        return num_id

    def allocate_num(self, kind):
        return self.add_list((kind,))

def _marker_kind(marker_type, marker):
    if marker_type == "number":
        return "decimal-paren"
    if marker_type == "letter":
        return "russian-paren"
    return "bullet-dash"

def add_list_item(doc, marker_type, marker, text, num_id, level=0):
    p = doc.add_paragraph(style=docx_style.STYLE_BODY)
    pPr = p._element.get_or_add_pPr()

    ind = pPr.find(qn("w:ind"))
    if ind is not None:
        pPr.remove(ind)

    numPr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl")
    ilvl.set(qn("w:val"), str(level))
    numPr.append(ilvl)
    numId_el = OxmlElement("w:numId")
    numId_el.set(qn("w:val"), str(num_id))
    numPr.append(numId_el)

    pStyle = pPr.find(qn("w:pStyle"))
    if pStyle is not None:
        pStyle.addnext(numPr)
    else:
        pPr.insert(0, numPr)

    text = _normalize_text(text)
    text = _unwrap_bold_around_appendix_phrases(text)
    _add_runs_with_links(p, text)

    for r in p.runs:
        set_run_font(r, font_name=docx_style.FONT_FAMILY, size_pt=docx_style.BODY_FONT_PT,
                     bold=False, italic=False,
                     color_rgb=docx_style.COLOR_RGB_TUPLE_BLACK)
    _force_paragraph_runs_bold(p, False)
    return p
