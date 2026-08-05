import re

from .. import bibliography
from ..logging_setup import get_logger

log = get_logger("docx")

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_TBLPR_ORDER = [
    "tblStyle", "tblpPr", "tblOverlap", "bidiVisual",
    "tblStyleRowBandSize", "tblStyleColBandSize",
    "tblW", "jc", "tblCellSpacing", "tblInd",
    "tblBorders", "shd", "tblLayout", "tblCellMar",
    "tblLook", "tblCaption", "tblDescription", "tblPrChange",
]

_SECTPR_ORDER = [
    "headerReference", "footerReference",
    "footnotePr", "endnotePr",
    "type",
    "pgSz", "pgMar", "paperSrc",
    "pgBorders",
    "lnNumType",
    "pgNumType",
    "cols",
    "formProt",
    "vAlign",
    "noEndnote",
    "titlePg",
    "textDirection",
    "bidi",
    "rtlGutter",
    "docGrid",
    "printerSettings",
    "footnoteColumns", "endnoteColumns",
    "sectPrChange",
]

_ESC_OPEN_BRACKET = "\uE000"
_ESC_CLOSE_BRACKET = "\uE001"
_ESC_OPEN_BRACE = "\uE002"
_ESC_CLOSE_BRACE = "\uE003"

INLINE_RE = re.compile(
    r"(\*\*[^*]+\*\*"
    r"|\*[^*]+\*"
    r"|`[^`]+`)"
)

_CHAPTER_H1_RE = re.compile(
    r"^(?:Глава\s+)?(\d+)\s*[.:]?\s*(.+)$",
    re.IGNORECASE,
)

_APPENDIX_TOC_H1_RE = re.compile(
    r"^ПРИЛОЖЕНИЕ\s+[А-ЯЁA-Z]\s*$", re.IGNORECASE
)

_CYR_APPENDIX_LETTERS = (
    "АБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
)

APP_REF_RE = re.compile(
    r"(?:ПРИЛОЖЕНИЕ|[Пп]риложени\w+)\s+"
    r"([А-ЯЁA-Za-z])"
    r"(\.\d+|\.(?=\s|$))?",
)
_BOLD_WRAP_AROUND_APP_RE = re.compile(
    r"\*\*((?:[^*]|\*(?!\*))*?)"
    r"((?:ПРИЛОЖЕНИЕ|[Пп]риложени\w+)\s+[А-ЯЁA-Za-z](?:\.\d+|\.(?=\s|$))?)"
    r"\*\*",
    re.IGNORECASE,
)

CITE_RE = bibliography.NUMERIC_CITE_RE

FORMULA_TEXT_RE = re.compile(
    r"(?:Формула|формула|Formula|formula|Eq\.?|eq\.?)\s*\(\s*([\w\d.]+)\s*\)"
)

_XREF: dict[str, dict[str, str]] = {}
_DOC_METADATA: dict | None = None
_CITE_KEY_NUM: dict[str, int] = {}
_KNOWN_SOURCE_NUMS: set[int] = set()
_FORMULA_NUM_TO_BOOKMARK: dict[str, str] = {}
_REFERENCED_SOURCES = set()
_REFERENCED_APP_KEYS = set()
_BOOKMARK_ID = [100]
_BOOKMARKS = {}
_XREF_BOOKMARKS = {}
