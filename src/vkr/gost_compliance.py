from __future__ import annotations

import re

from . import crossref
from . import gost_sections

_CAPTION_PREFIX_RE = re.compile(
    r"^(?:Рисунок|Таблица|Листинг)\s+",
    re.IGNORECASE,
)
_GOOD_CAPTION_SEP_RE = re.compile(
    r"^(?:Рисунок|Таблица|Листинг)\s+[\w\d.{}]+(?:\s+[–-]\s+)",
    re.IGNORECASE,
)
_EXPLICIT_NUM_RE = re.compile(
    r"^(?:Рисунок|Таблица|Листинг)\s+(\d+(?:\.\d+)?)\s",
    re.IGNORECASE,
)

STRUCTURAL_H1_NAMES = gost_sections.STRUCTURAL_HEADINGS


def caption_separator_issue(text: str) -> str | None:
    line = (text or "").strip()
    if not _CAPTION_PREFIX_RE.match(line):
        return None
    if crossref.extract_key(line):
        if _GOOD_CAPTION_SEP_RE.match(line):
            return None
        return "caption must use spaced ' - ' or en-dash after the key or number"
    if _GOOD_CAPTION_SEP_RE.match(line):
        return None
    if re.search(r"[\w\d.]+[—\-]\S", line):
        return "caption separator must be spaced, not a tight dash"
    return "caption must use spaced ' - ' or en-dash after the number"


def structural_heading_issues(elements: list[dict]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    for e in elements:
        if e.get("type") != "heading" or e.get("level") != 1:
            continue
        raw = (e.get("text") or "").strip()
        upper = raw.upper()
        if upper.startswith("ПРИЛОЖЕНИЕ"):
            continue
        if re.match(r"^\d+\s+\S", raw):
            continue
        if upper not in STRUCTURAL_H1_NAMES and not gost_sections.is_dictionary_heading(
            upper
        ):
            issues.append(
                (
                    raw,
                    "level-1 heading is not a recognized structural section name",
                )
            )
    return issues


def numbering_gap_issues(elements: list[dict]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    per_kind: dict[str, list[float]] = {
        crossref.FIGURE: [],
        crossref.TABLE: [],
        crossref.LISTING: [],
    }
    kind_by_type = {
        "figure_caption": crossref.FIGURE,
        "table_caption": crossref.TABLE,
        "listing_caption": crossref.LISTING,
    }
    for e in elements:
        et = e.get("type")
        kind = kind_by_type.get(et)
        if not kind:
            continue
        text = e.get("text", "")
        if crossref.extract_key(text):
            continue
        m = _EXPLICIT_NUM_RE.match(text.strip())
        if not m:
            continue
        label = m.group(1)
        try:
            per_kind[kind].append(float(label))
        except ValueError:
            continue
    for kind, nums in per_kind.items():
        if len(nums) < 2:
            continue
        ints = sorted(set(int(n) for n in nums if n == int(n)))
        if not ints:
            continue
        expected = list(range(1, ints[-1] + 1))
        if ints != expected:
            issues.append(
                (
                    kind,
                    f"explicit {kind} numbers have gaps: found {ints}, "
                    f"expected 1..{ints[-1]}",
                )
            )
    return issues
