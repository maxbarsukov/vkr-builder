from __future__ import annotations

from dataclasses import replace
import re
from typing import Any, Mapping

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .config import default_page_number_from
from .typography import TypographySettings


_DEFAULT_STYLE_NAMES: dict[str, str] = {
    "body": "ДИПЛОМ - Обычный текст",
    "toc_heading": "ДИПЛОМ - Заголовок",
    "figure": "ДИПЛОМ - Рисунки",
    "table_caption": "ДИПЛОМ - Таблицы",
    "code": "ДИПЛОМ - Код",
    "list_paragraph": "List Paragraph",
    "heading_1": "Heading 1",
    "heading_2": "Heading 2",
    "heading_3": "Heading 3",
    "toc_1": "toc 1",
    "toc_2": "toc 2",
    "toc_3": "toc 3",
    "footer": "Footer",
}

_KNOWN_STYLE_KEYS = frozenset(_DEFAULT_STYLE_NAMES.keys())

STYLE_NORMAL = "Normal"
STYLE_BODY = _DEFAULT_STYLE_NAMES["body"]
STYLE_TOC_HEADING = _DEFAULT_STYLE_NAMES["toc_heading"]
STYLE_DIPLOM_HEAD2 = "ДИПЛОМ - Заголовок 2"
STYLE_FIGURE = _DEFAULT_STYLE_NAMES["figure"]
STYLE_TABLE_CAPTION = _DEFAULT_STYLE_NAMES["table_caption"]
STYLE_CODE = _DEFAULT_STYLE_NAMES["code"]
STYLE_LIST_PARA = _DEFAULT_STYLE_NAMES["list_paragraph"]
STYLE_HEADING_1 = _DEFAULT_STYLE_NAMES["heading_1"]
STYLE_HEADING_2 = _DEFAULT_STYLE_NAMES["heading_2"]
STYLE_HEADING_3 = _DEFAULT_STYLE_NAMES["heading_3"]
STYLE_TOC_1 = _DEFAULT_STYLE_NAMES["toc_1"]
STYLE_TOC_2 = _DEFAULT_STYLE_NAMES["toc_2"]
STYLE_TOC_3 = _DEFAULT_STYLE_NAMES["toc_3"]
STYLE_FOOTER = _DEFAULT_STYLE_NAMES["footer"]


def _sync_module_aliases(flat: dict[str, str]) -> None:
    global STYLE_BODY, STYLE_TOC_HEADING, STYLE_FIGURE, STYLE_TABLE_CAPTION
    global STYLE_CODE, STYLE_LIST_PARA
    global STYLE_HEADING_1, STYLE_HEADING_2, STYLE_HEADING_3
    global STYLE_TOC_1, STYLE_TOC_2, STYLE_TOC_3, STYLE_FOOTER

    STYLE_BODY = flat["body"]
    STYLE_TOC_HEADING = flat["toc_heading"]
    STYLE_FIGURE = flat["figure"]
    STYLE_TABLE_CAPTION = flat["table_caption"]
    STYLE_CODE = flat["code"]
    STYLE_LIST_PARA = flat["list_paragraph"]
    STYLE_HEADING_1 = flat["heading_1"]
    STYLE_HEADING_2 = flat["heading_2"]
    STYLE_HEADING_3 = flat["heading_3"]
    STYLE_TOC_1 = flat["toc_1"]
    STYLE_TOC_2 = flat["toc_2"]
    STYLE_TOC_3 = flat["toc_3"]
    STYLE_FOOTER = flat["footer"]


def configure_style_names(user: Mapping[str, Any] | None) -> None:
    flat = dict(_DEFAULT_STYLE_NAMES)
    if user:
        for key, val in user.items():
            if key not in _KNOWN_STYLE_KEYS:
                raise ValueError(
                    f"Неизвестный ключ word_styles: {key!r}. "
                    f"Допустимы: {', '.join(sorted(_KNOWN_STYLE_KEYS))}"
                )
            if not isinstance(val, str) or not val.strip():
                raise ValueError(f"style.word_styles.{key} должен быть непустой строкой")
            flat[key] = val.strip()
    _sync_module_aliases(flat)


def reset_style_names_to_defaults() -> None:
    _sync_module_aliases(dict(_DEFAULT_STYLE_NAMES))


def toc_style_for_level(level: int) -> str:
    return {1: STYLE_TOC_1, 2: STYLE_TOC_2, 3: STYLE_TOC_3}.get(level, STYLE_TOC_1)


_TABLE_CONTINUATION_DEFAULTS: dict[str, Any] = {
    "enabled": True,
    "label": "Продолжение таблицы {n}",
    "align": "right",
}
_CONTINUATION_ALIGN_VALUES = frozenset({"left", "right", "center"})

TABLE_CONTINUATION_ENABLED: bool = bool(_TABLE_CONTINUATION_DEFAULTS["enabled"])
TABLE_CONTINUATION_LABEL: str = str(_TABLE_CONTINUATION_DEFAULTS["label"])
TABLE_CONTINUATION_ALIGN: str = str(_TABLE_CONTINUATION_DEFAULTS["align"])


DASH_CHARS = {
    "en-dash": "\u2013", "em-dash": "\u2014",
    "en": "\u2013", "em": "\u2014",
}
DASH_NAMES = ("en-dash", "em-dash")
_DASH_DEFAULTS = {"normalize": True, "captions": "en-dash", "body": "en-dash"}

_WORD_INNER_RE = re.compile(r"(?<=[^\W\d_])[\u2013\u2014](?=[^\W\d_])")
_RANGE_RE = re.compile(r"(?<=\d)[-\u2013\u2014](?=\d)")
_SENTENCE_RE = re.compile(r"(?<=\s)[-\u2013\u2014](?=\s)")

DASH_NORMALIZE = bool(_DASH_DEFAULTS["normalize"])
DASH_CAPTION = DASH_CHARS[_DASH_DEFAULTS["captions"]]
DASH_BODY = DASH_CHARS[_DASH_DEFAULTS["body"]]


def _dash_char(value: Any, where: str) -> str:
    name = str(value).strip().lower()
    if name in DASH_CHARS:
        return DASH_CHARS[name]
    if name in DASH_CHARS.values():
        return name
    raise ValueError(
        f"{where}: ожидается 'en-dash' или 'em-dash' (получено {value!r})"
    )


def configure_dashes(user: Mapping[str, Any] | None) -> None:
    global DASH_NORMALIZE, DASH_CAPTION, DASH_BODY
    DASH_NORMALIZE = bool(_DASH_DEFAULTS["normalize"])
    DASH_CAPTION = DASH_CHARS[_DASH_DEFAULTS["captions"]]
    DASH_BODY = DASH_CHARS[_DASH_DEFAULTS["body"]]
    if not user:
        return
    if "normalize" in user and user["normalize"] is not None:
        DASH_NORMALIZE = bool(user["normalize"])
    if user.get("captions"):
        DASH_CAPTION = _dash_char(user["captions"], "style.dashes.captions")
    if user.get("body"):
        DASH_BODY = _dash_char(user["body"], "style.dashes.body")


def normalise_body_dashes(text: str) -> str:
    if not DASH_NORMALIZE or not text:
        return text
    text = _WORD_INNER_RE.sub("-", text)
    text = _RANGE_RE.sub("\u2013", text)
    return _SENTENCE_RE.sub(DASH_BODY, text)


def configure_table_continuation(user: Mapping[str, Any] | None) -> None:
    global TABLE_CONTINUATION_ENABLED, TABLE_CONTINUATION_LABEL, TABLE_CONTINUATION_ALIGN
    enabled = bool(_TABLE_CONTINUATION_DEFAULTS["enabled"])
    label = str(_TABLE_CONTINUATION_DEFAULTS["label"])
    align = str(_TABLE_CONTINUATION_DEFAULTS["align"])
    if user:
        if "enabled" in user and user["enabled"] is not None:
            enabled = bool(user["enabled"])
        if user.get("label"):
            label = str(user["label"])
        if user.get("align"):
            a = str(user["align"]).strip().lower()
            if a not in _CONTINUATION_ALIGN_VALUES:
                raise ValueError(
                    "table continuation align: ожидается 'left', 'right' или "
                    f"'center' (получено {user['align']!r})"
                )
            align = a
    TABLE_CONTINUATION_ENABLED = enabled
    TABLE_CONTINUATION_LABEL = label
    TABLE_CONTINUATION_ALIGN = align


def reset_table_continuation_to_defaults() -> None:
    configure_table_continuation(None)


def table_continuation_alignment() -> WD_ALIGN_PARAGRAPH:
    return {
        "left": WD_ALIGN_PARAGRAPH.LEFT,
        "right": WD_ALIGN_PARAGRAPH.RIGHT,
        "center": WD_ALIGN_PARAGRAPH.CENTER,
    }[TABLE_CONTINUATION_ALIGN]


def lo_pagination_skip_paragraph_styles() -> frozenset[str]:
    return frozenset(
        {
            STYLE_BODY,
            STYLE_TOC_HEADING,
            STYLE_FIGURE,
            STYLE_TABLE_CAPTION,
            STYLE_CODE,
            STYLE_LIST_PARA,
            STYLE_TOC_1,
            STYLE_TOC_2,
            STYLE_TOC_3,
            STYLE_FOOTER,
            "Normal",
        }
    )


def _style_exists(doc: Document, name: str) -> bool:
    try:
        doc.styles[name]
        return True
    except KeyError:
        return False


def _ensure_paragraph_style(doc: Document, name: str, *, base: str = "Normal") -> None:
    if _style_exists(doc, name):
        return
    style = doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    try:
        style.base_style = doc.styles[base]
    except KeyError:
        pass


def _ensure_character_style(doc: Document, name: str) -> None:
    if _style_exists(doc, name):
        return
    doc.styles.add_style(name, WD_STYLE_TYPE.CHARACTER)


def ensure_document_styles(doc: Document) -> None:
    _ensure_paragraph_style(doc, STYLE_BODY)
    _ensure_paragraph_style(doc, STYLE_TOC_HEADING, base=STYLE_HEADING_1)
    _ensure_paragraph_style(doc, STYLE_FIGURE)
    _ensure_paragraph_style(doc, STYLE_TABLE_CAPTION)
    _ensure_paragraph_style(doc, STYLE_CODE)
    for toc_name in (STYLE_TOC_1, STYLE_TOC_2, STYLE_TOC_3):
        _ensure_paragraph_style(doc, toc_name)
    for link_name in ("Hyperlink", "FollowedHyperlink"):
        _ensure_character_style(doc, link_name)


def style_id(doc: Document, style_name: str) -> str:
    return doc.styles[style_name].style_id


RGB_BLACK = RGBColor(0x00, 0x00, 0x00)
COLOR_RGB_TUPLE_BLACK = (0, 0, 0)
COLOR_RGB_TUPLE_ERROR = (192, 0, 0)

BODY_BOLD_DEFAULT = False
HEADING_BOLD_DEFAULT = True

_BASE_FLAT: dict[str, Any] = replace(
    TypographySettings(),
    page_number_from=default_page_number_from(),
).to_flat()

_KNOWN_TOP_LEVEL = frozenset(_BASE_FLAT.keys()) | frozenset({"margins_cm"})

_TOC_HEADING_SPACE_AFTER_PT = 8.0
_TOC_ENTRY_SPACE_AFTER_PT = 5.0
_TOC_HEADING_CHAR_SPACING = -10
_TOC_HEADING_KERN = 28
_TOC_LEFT_INDENT_CM = {2: 0.3881, 3: 0.7761}

_W14_NS = "http://schemas.microsoft.com/office/word/2010/wordml"
_DXA_PER_CM = 567


def _spacing_rule_from_name(name: str) -> WD_LINE_SPACING:
    n = (name or "multiple").strip().lower()
    if n == "multiple":
        return WD_LINE_SPACING.MULTIPLE
    if n == "single":
        return WD_LINE_SPACING.SINGLE
    raise ValueError(
        "body_line_spacing_rule: ожидается 'multiple' или 'single' "
        f"(получено {name!r})"
    )


def _validate_flat(f: dict[str, Any]) -> None:
    if f["body_font_pt"] < 12:
        raise ValueError("body_font_pt: по п. 4.2 не менее 12 пт")
    if f["line_spacing_multiple"] <= 0:
        raise ValueError("line_spacing_multiple: должно быть > 0")
    if f["paragraph_indent_cm"] <= 0:
        raise ValueError("paragraph_indent_cm: положительное число (см)")
    if f["table_cell_font_pt"] < 12:
        raise ValueError("table_cell_font_pt: по п. 4.2 не менее 12 пт")
    for fk in (
        "heading_font_pt",
        "toc_entry_font_pt",
        "caption_font_pt",
        "footer_page_font_pt",
    ):
        if f[fk] < 12:
            raise ValueError(f"{fk}: по п. 4.2 не менее 12 пт")
    for k in (
        "margin_left_cm",
        "margin_right_cm",
        "margin_top_cm",
        "margin_bottom_cm",
    ):
        if f[k] <= 0:
            raise ValueError(f"{k}: положительное число (см)")
    if f["page_width_cm"] <= f["margin_left_cm"] + f["margin_right_cm"]:
        raise ValueError("Сумма левого и правого полей не должна превышать ширину страницы")
    if f["page_height_cm"] <= f["margin_top_cm"] + f["margin_bottom_cm"]:
        raise ValueError("Сумма верхнего и нижнего полей не должна превышать высоту страницы")
    if int(f["page_number_from"]) < 1:
        raise ValueError("page_number_from: ожидается целое число >= 1")
    _spacing_rule_from_name(f["body_line_spacing_rule"])


def _merge_typography_user(base: dict[str, Any], user: Mapping[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in user.items():
        if key not in _KNOWN_TOP_LEVEL:
            raise ValueError(
                f"Неизвестный ключ typography: {key!r}. "
                f"Допустимы: {', '.join(sorted(_KNOWN_TOP_LEVEL))}"
            )
        if key == "page_number_from":
            out[key] = int(val)
            continue
        if key == "margins_cm":
            if val is None:
                continue
            if not isinstance(val, dict):
                raise ValueError("margins_cm должен быть объектом с ключами left, right, top, bottom")
            submap = {
                "left": "margin_left_cm",
                "right": "margin_right_cm",
                "top": "margin_top_cm",
                "bottom": "margin_bottom_cm",
            }
            for sk, tk in submap.items():
                if sk in val:
                    out[tk] = float(val[sk])
            continue
        if isinstance(val, bool) or val is not None:
            if key in ("body_justify",):
                out[key] = bool(val)
            elif key in ("font_family", "listing_font_family"):
                out[key] = str(val).strip()
            elif key == "body_line_spacing_rule":
                out[key] = str(val).strip().lower()
            else:
                out[key] = float(val)
    return out


def _sync_module_from_flat(f: dict[str, Any]) -> None:
    global FONT_FAMILY, BODY_FONT_PT, HEADING_FONT_PT, TOC_ENTRY_FONT_PT
    global CAPTION_FONT_PT, LISTING_FONT_FAMILY, CODE_LINE_FONT_PT
    global FOOTER_PAGE_FONT_PT, TABLE_CELL_FONT_PT
    global BODY_LINE_SPACING_RULE, BODY_LINE_SPACING, BODY_FIRST_LINE_INDENT
    global BODY_JUSTIFY, PARAGRAPH_INDENT_CM
    global PAGE_WIDTH_CM, PAGE_HEIGHT_CM
    global MARGIN_LEFT_CM, MARGIN_RIGHT_CM, MARGIN_TOP_CM, MARGIN_BOTTOM_CM
    global HEADER_DISTANCE_CM, FOOTER_DISTANCE_CM
    global CONTENT_TEXT_WIDTH_CM, CONTENT_TEXT_WIDTH_DXA
    global PAGE_NUMBERING_DISPLAY_START

    FONT_FAMILY = f["font_family"]
    BODY_FONT_PT = f["body_font_pt"]
    HEADING_FONT_PT = f["heading_font_pt"]
    TOC_ENTRY_FONT_PT = f["toc_entry_font_pt"]
    CAPTION_FONT_PT = f["caption_font_pt"]
    LISTING_FONT_FAMILY = f["listing_font_family"]
    CODE_LINE_FONT_PT = f["code_line_font_pt"]
    FOOTER_PAGE_FONT_PT = f["footer_page_font_pt"]
    TABLE_CELL_FONT_PT = f["table_cell_font_pt"]

    BODY_LINE_SPACING_RULE = _spacing_rule_from_name(f["body_line_spacing_rule"])
    BODY_LINE_SPACING = float(f["line_spacing_multiple"])
    if BODY_LINE_SPACING_RULE == WD_LINE_SPACING.SINGLE:
        BODY_LINE_SPACING = 1.0

    PARAGRAPH_INDENT_CM = float(f["paragraph_indent_cm"])
    BODY_FIRST_LINE_INDENT = Cm(PARAGRAPH_INDENT_CM)
    BODY_JUSTIFY = bool(f["body_justify"])

    PAGE_WIDTH_CM = float(f["page_width_cm"])
    PAGE_HEIGHT_CM = float(f["page_height_cm"])
    MARGIN_LEFT_CM = float(f["margin_left_cm"])
    MARGIN_RIGHT_CM = float(f["margin_right_cm"])
    MARGIN_TOP_CM = float(f["margin_top_cm"])
    MARGIN_BOTTOM_CM = float(f["margin_bottom_cm"])
    HEADER_DISTANCE_CM = float(f["header_distance_cm"])
    FOOTER_DISTANCE_CM = float(f["footer_distance_cm"])

    CONTENT_TEXT_WIDTH_CM = PAGE_WIDTH_CM - MARGIN_LEFT_CM - MARGIN_RIGHT_CM
    CONTENT_TEXT_WIDTH_DXA = int(round(CONTENT_TEXT_WIDTH_CM * _DXA_PER_CM))

    PAGE_NUMBERING_DISPLAY_START = int(f["page_number_from"])


def apply_typography_from_mapping(user: Mapping[str, Any] | None) -> None:
    merged = _merge_typography_user(_BASE_FLAT, user or {})
    _validate_flat(merged)
    _sync_module_from_flat(merged)


def reset_typography_to_defaults() -> None:
    _sync_module_from_flat(dict(_BASE_FLAT))


def list_numbering_indents_dxa() -> tuple[int, int]:
    first_dxa = int(round(PARAGRAPH_INDENT_CM * _DXA_PER_CM))
    cont_dxa = int(round((PARAGRAPH_INDENT_CM + 0.5) * _DXA_PER_CM))
    hanging = cont_dxa - first_dxa
    return cont_dxa, hanging


_sync_module_from_flat(dict(_BASE_FLAT))


def font_half_points(pt: float) -> str:
    return str(int(round(pt * 2)))


def _paragraph_style(doc, name: str):
    try:
        return doc.styles[name]
    except KeyError:
        return None


_STYLES_ALLOWED_BOLD: frozenset[str] = frozenset(
    {
        STYLE_HEADING_1,
        STYLE_HEADING_2,
        STYLE_HEADING_3,
        STYLE_TOC_HEADING,
        STYLE_DIPLOM_HEAD2,
    }
)


def _ensure_rfonts_all_scripts(rFonts, font_name: str) -> None:
    for attr in ("ascii", "hAnsi", "cs", "eastAsia"):
        rFonts.set(qn(f"w:{attr}"), font_name)


def _patch_style_rfonts_from_element(style_el, font_name: str) -> None:
    rPr = style_el.find(qn("w:rPr"))
    if rPr is None:
        return
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        return
    _ensure_rfonts_all_scripts(rFonts, font_name)


def _ensure_style_xml_flag(style_el, flag: str) -> None:
    tag = qn(f"w:{flag}")
    if style_el.find(tag) is None:
        style_el.append(OxmlElement(f"w:{flag}"))


def _patch_styles_gallery_visibility(doc: Document) -> None:
    gallery_styles = (
        STYLE_BODY,
        STYLE_TOC_HEADING,
        STYLE_FIGURE,
        STYLE_TABLE_CAPTION,
        STYLE_CODE,
        STYLE_DIPLOM_HEAD2,
    )
    auto_redefine = {STYLE_TOC_HEADING}
    for name in gallery_styles:
        try:
            style_el = doc.styles[name].element
        except KeyError:
            continue
        _ensure_style_xml_flag(style_el, "qFormat")
        if name in auto_redefine:
            _ensure_style_xml_flag(style_el, "autoRedefine")


def _style_rpr(style_el):
    rPr = style_el.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        style_el.append(rPr)
    return rPr


def _patch_style_run_spacing_kern(
    style_el,
    *,
    char_spacing: int | None = None,
    kern: int | None = None,
) -> None:
    rPr = _style_rpr(style_el)
    if char_spacing is not None:
        sp = rPr.find(qn("w:spacing"))
        if sp is None:
            sp = OxmlElement("w:spacing")
            rPr.append(sp)
        sp.set(qn("w:val"), str(char_spacing))
    if kern is not None:
        k = rPr.find(qn("w:kern"))
        if k is None:
            k = OxmlElement("w:kern")
            rPr.append(k)
        k.set(qn("w:val"), str(kern))


def _patch_doc_defaults(styles_el, font_name: str) -> None:
    dd = styles_el.find(qn("w:docDefaults"))
    if dd is None:
        dd = OxmlElement("w:docDefaults")
        styles_el.insert(0, dd)

    rpd = dd.find(qn("w:rPrDefault"))
    if rpd is None:
        rpd = OxmlElement("w:rPrDefault")
        dd.append(rpd)
    rPr = rpd.find(qn("w:rPr"))
    if rPr is None:
        rPr = OxmlElement("w:rPr")
        rpd.append(rPr)

    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.insert(0, rFonts)
    _ensure_rfonts_all_scripts(rFonts, font_name)
    for theme_attr, theme_val in (
        ("asciiTheme", "minorHAnsi"),
        ("hAnsiTheme", "minorHAnsi"),
        ("eastAsiaTheme", "minorHAnsi"),
        ("cstheme", "minorBidi"),
    ):
        rFonts.set(qn(f"w:{theme_attr}"), theme_val)

    kern_el = rPr.find(qn("w:kern"))
    if kern_el is None:
        kern_el = OxmlElement("w:kern")
        rPr.append(kern_el)
    kern_el.set(qn("w:val"), "2")

    lang = rPr.find(qn("w:lang"))
    if lang is None:
        lang = OxmlElement("w:lang")
        rPr.append(lang)
    lang.set(qn("w:val"), "ru-RU")
    lang.set(qn("w:eastAsia"), "en-US")
    lang.set(qn("w:bidi"), "ar-SA")

    w14_lig = f"{{{_W14_NS}}}ligatures"
    if rPr.find(w14_lig) is None:
        rPr.append(
            parse_xml(
                f'<w14:ligatures xmlns:w14="{_W14_NS}" w14:val="standardContextual"/>'
            )
        )

    ppd = dd.find(qn("w:pPrDefault"))
    if ppd is None:
        ppd = OxmlElement("w:pPrDefault")
        dd.append(ppd)
    pPr = ppd.find(qn("w:pPr"))
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        ppd.append(pPr)
    spacing = pPr.find(qn("w:spacing"))
    if spacing is None:
        spacing = OxmlElement("w:spacing")
        pPr.append(spacing)
    spacing.set(qn("w:after"), "160")
    spacing.set(qn("w:line"), "259")
    spacing.set(qn("w:lineRule"), "auto")


def _set_compat_mode(settings_el, mode: int) -> None:
    compat = settings_el.find(qn("w:compat"))
    if compat is None:
        compat = OxmlElement("w:compat")
        settings_el.append(compat)
    uri = "http://schemas.microsoft.com/office/word"
    for cs in compat.findall(qn("w:compatSetting")):
        if cs.get(qn("w:name")) == "compatibilityMode" and cs.get(qn("w:uri")) == uri:
            cs.set(qn("w:val"), str(mode))
            return
    cs = OxmlElement("w:compatSetting")
    cs.set(qn("w:name"), "compatibilityMode")
    cs.set(qn("w:uri"), uri)
    cs.set(qn("w:val"), str(mode))
    compat.append(cs)


def _patch_document_settings(doc: Document) -> None:
    el = doc.settings.element

    dts = el.find(qn("w:defaultTabStop"))
    if dts is None:
        dts = OxmlElement("w:defaultTabStop")
        el.insert(0, dts)
    dts.set(qn("w:val"), "708")

    tfl = el.find(qn("w:themeFontLang"))
    if tfl is None:
        tfl = OxmlElement("w:themeFontLang")
        el.append(tfl)
    tfl.set(qn("w:val"), "ru-RU")
    east_asia = qn("w:eastAsia")
    if east_asia in tfl.attrib:
        del tfl.attrib[east_asia]

    _set_compat_mode(el, 15)


def _patch_doc_defaults_rfonts(styles_el, font_name: str) -> None:
    _patch_doc_defaults(styles_el, font_name)


def _apply_font_family_and_bold_to_all_styles(doc) -> None:
    ff = FONT_FAMILY
    for style in doc.styles:
        try:
            stype = style.type
            name = style.name
        except (AttributeError, ValueError):
            continue
        if stype == WD_STYLE_TYPE.TABLE:
            continue
        _linked = getattr(WD_STYLE_TYPE, "LINKED", None)
        allowed = (WD_STYLE_TYPE.PARAGRAPH, WD_STYLE_TYPE.CHARACTER)
        if _linked is not None:
            allowed = allowed + (_linked,)
        if stype not in allowed:
            continue
        try:
            font = style.font
        except AttributeError:
            continue
        try:
            font.name = ff
            font.bold = name in _STYLES_ALLOWED_BOLD
        except (AttributeError, ValueError, NotImplementedError):
            pass
        try:
            _patch_style_rfonts_from_element(style.element, ff)
        except (AttributeError, ValueError):
            pass


def apply_itmo_document_styles(doc) -> None:
    def _body_paragraph_style(name: str) -> None:
        st = _paragraph_style(doc, name)
        if st is None:
            return
        f = st.font
        f.name = FONT_FAMILY
        f.size = Pt(BODY_FONT_PT)
        f.bold = BODY_BOLD_DEFAULT
        f.italic = False
        if hasattr(f, "all_caps"):
            try:
                f.all_caps = False
            except (AttributeError, NotImplementedError):
                pass
        f.color.rgb = RGB_BLACK
        pf = st.paragraph_format
        pf.line_spacing_rule = BODY_LINE_SPACING_RULE
        pf.line_spacing = BODY_LINE_SPACING
        pf.alignment = (
            WD_ALIGN_PARAGRAPH.JUSTIFY if BODY_JUSTIFY else WD_ALIGN_PARAGRAPH.LEFT
        )
        pf.first_line_indent = BODY_FIRST_LINE_INDENT

    _body_paragraph_style(STYLE_BODY)
    _body_paragraph_style(STYLE_LIST_PARA)

    for toc_level, toc_name in enumerate((STYLE_TOC_1, STYLE_TOC_2, STYLE_TOC_3), start=1):
        st = _paragraph_style(doc, toc_name)
        if st is None:
            continue
        f = st.font
        f.name = FONT_FAMILY
        f.size = Pt(TOC_ENTRY_FONT_PT)
        f.bold = BODY_BOLD_DEFAULT
        f.italic = False
        if hasattr(f, "all_caps"):
            try:
                f.all_caps = False
            except (AttributeError, NotImplementedError):
                pass
        f.color.rgb = RGB_BLACK
        pf = st.paragraph_format
        pf.line_spacing_rule = BODY_LINE_SPACING_RULE
        pf.line_spacing = BODY_LINE_SPACING
        pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pf.first_line_indent = Cm(0)
        pf.space_after = Pt(_TOC_ENTRY_SPACE_AFTER_PT)
        if toc_level in _TOC_LEFT_INDENT_CM:
            pf.left_indent = Cm(_TOC_LEFT_INDENT_CM[toc_level])

    st = _paragraph_style(doc, STYLE_TOC_HEADING)
    if st is not None:
        f = st.font
        f.name = FONT_FAMILY
        f.size = Pt(HEADING_FONT_PT)
        f.bold = HEADING_BOLD_DEFAULT
        f.italic = False
        if hasattr(f, "all_caps"):
            try:
                f.all_caps = False
            except (AttributeError, NotImplementedError):
                pass
        f.color.rgb = RGB_BLACK
        pf = st.paragraph_format
        pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
        pf.first_line_indent = Cm(0)
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = 1.0
        pf.space_after = Pt(_TOC_HEADING_SPACE_AFTER_PT)
        _patch_style_run_spacing_kern(
            st.element,
            char_spacing=_TOC_HEADING_CHAR_SPACING,
            kern=_TOC_HEADING_KERN,
        )

    for name in (STYLE_FIGURE, STYLE_TABLE_CAPTION):
        st = _paragraph_style(doc, name)
        if st is None:
            continue
        f = st.font
        f.name = FONT_FAMILY
        f.size = Pt(CAPTION_FONT_PT)
        f.bold = BODY_BOLD_DEFAULT
        f.italic = False
        if hasattr(f, "all_caps"):
            try:
                f.all_caps = False
            except (AttributeError, NotImplementedError):
                pass
        f.color.rgb = RGB_BLACK

    st = _paragraph_style(doc, STYLE_CODE)
    if st is not None:
        f = st.font
        f.name = LISTING_FONT_FAMILY
        f.size = Pt(CODE_LINE_FONT_PT)
        f.bold = BODY_BOLD_DEFAULT
        f.italic = False
        if hasattr(f, "all_caps"):
            try:
                f.all_caps = False
            except (AttributeError, NotImplementedError):
                pass
        f.color.rgb = RGB_BLACK
        try:
            _patch_style_rfonts_from_element(st.element, LISTING_FONT_FAMILY)
        except (AttributeError, ValueError):
            pass

    for outline_idx, name in enumerate((STYLE_HEADING_1, STYLE_HEADING_2, STYLE_HEADING_3)):
        st = _paragraph_style(doc, name)
        if st is None:
            continue
        f = st.font
        f.name = FONT_FAMILY
        f.size = Pt(HEADING_FONT_PT)
        f.bold = HEADING_BOLD_DEFAULT
        f.italic = False
        if hasattr(f, "all_caps"):
            try:
                f.all_caps = False
            except (AttributeError, NotImplementedError):
                pass
        f.color.rgb = RGB_BLACK
        pf = st.paragraph_format
        pf.line_spacing_rule = WD_LINE_SPACING.MULTIPLE
        pf.line_spacing = 1.0
        pf.first_line_indent = BODY_FIRST_LINE_INDENT
        try:
            pf.outline_level = outline_idx
        except (AttributeError, ValueError):
            pass

    st = _paragraph_style(doc, "Normal")
    if st is not None:
        f = st.font
        f.name = FONT_FAMILY
        f.size = Pt(BODY_FONT_PT)
        f.bold = BODY_BOLD_DEFAULT
        f.color.rgb = RGB_BLACK

    for name in ("Hyperlink", "FollowedHyperlink"):
        try:
            cst = doc.styles[name]
        except KeyError:
            continue
        if getattr(cst, "type", None) != WD_STYLE_TYPE.CHARACTER:
            continue
        cf = cst.font
        cf.name = FONT_FAMILY
        cf.size = Pt(BODY_FONT_PT)
        cf.bold = BODY_BOLD_DEFAULT
        cf.italic = False
        cf.color.rgb = RGB_BLACK
        try:
            _patch_style_rfonts_from_element(cst.element, FONT_FAMILY)
        except (AttributeError, ValueError):
            pass

    _patch_doc_defaults(doc.styles.element, FONT_FAMILY)
    _apply_font_family_and_bold_to_all_styles(doc)
    _patch_styles_gallery_visibility(doc)


def create_vkr_document() -> Document:
    doc = Document()
    ensure_document_styles(doc)
    apply_itmo_document_styles(doc)
    _patch_document_settings(doc)
    return doc
