from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterator

from vkr import bibliography, md_lint
from vkr.docx.headings import heading_kind

_APPENDIX_RE = re.compile(r"^\s*ПРИЛОЖЕНИЕ\b", re.IGNORECASE)

_WORDS_PER_PAGE = 250
_TABLE_ROWS_PER_PAGE = 28
_CODE_LINES_PER_PAGE = 40
_TOC_ROWS_PER_PAGE = 30
_PAGES_PER_FIGURE = 0.35
_PAGE_LOST_TO_A_BREAK = 0.4


@dataclass(frozen=True)
class DocumentStats:
    sections: int
    chapters: int
    appendices: int
    headings: int
    paragraphs: int
    list_items: int
    figures: int
    tables: int
    listings: int
    formulas: int
    sources: int
    words: int
    characters: int
    estimated_pages: int


def _texts(element: dict) -> Iterator[str]:
    kind = element["type"]
    if kind in ("para", "list_item", "heading") or kind.endswith("_caption"):
        yield element.get("text", "") or ""
    elif kind == "table":
        yield from element.get("header") or ()
        for row in element.get("rows") or ():
            yield from row
    elif kind == "code":
        yield from element.get("lines") or ()


def _is_appendix(element: dict) -> bool:
    return bool(_APPENDIX_RE.match(element.get("text", "") or ""))


def estimate_pages(elements: list[dict], words: int) -> int:
    figures = sum(1 for e in elements if e["type"] == "image")
    table_rows = sum(len(e.get("rows") or ()) for e in elements if e["type"] == "table")
    code_lines = sum(len(e.get("lines") or ()) for e in elements if e["type"] == "code")
    breaks = sum(
        1 for e in elements if e["type"] == "heading" and e.get("level") == 1
    )
    toc_rows = sum(
        1
        for e in elements
        if e["type"] == "heading" and (e.get("level") or 1) <= 3
    )

    pages = (
        words / _WORDS_PER_PAGE
        + figures * _PAGES_PER_FIGURE
        + table_rows / _TABLE_ROWS_PER_PAGE
        + code_lines / _CODE_LINES_PER_PAGE
        + breaks * _PAGE_LOST_TO_A_BREAK
        + max(1, math.ceil(toc_rows / _TOC_ROWS_PER_PAGE))
    )
    return max(1, math.ceil(pages))


def _count_sources(elements: list[dict]) -> int:
    numbered = md_lint._defined_sources(elements)
    if numbered:
        return len(numbered)
    _keynum, keyed = bibliography.scan(elements)
    return len(keyed)


def collect_stats(elements: list[dict]) -> DocumentStats:
    counts = Counter(e["type"] for e in elements)
    strings = [s for e in elements for s in _texts(e)]
    words = sum(len(s.split()) for s in strings)
    characters = sum(len(s) for s in strings)

    tops = [
        e for e in elements if e["type"] == "heading" and e.get("level") == 1
    ]
    appendices = sum(1 for e in tops if _is_appendix(e))
    chapters = sum(1 for e in tops if heading_kind(e.get("text", "")) == "chapter")

    return DocumentStats(
        sections=len(tops) - appendices - chapters,
        chapters=chapters,
        appendices=appendices,
        headings=counts.get("heading", 0),
        paragraphs=counts.get("para", 0),
        list_items=counts.get("list_item", 0),
        figures=counts.get("figure_caption", 0),
        tables=counts.get("table", 0),
        listings=counts.get("code", 0),
        formulas=counts.get("math_block", 0),
        sources=_count_sources(elements),
        words=words,
        characters=characters,
        estimated_pages=estimate_pages(elements, words),
    )
