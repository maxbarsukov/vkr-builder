from __future__ import annotations

import re
from dataclasses import dataclass

from . import bibliography
from . import crossref
from . import gost_compliance
from . import gost_sections

_CAPTION_KIND = {
    "figure_caption": crossref.FIGURE,
    "table_caption": crossref.TABLE,
    "listing_caption": crossref.LISTING,
}

_SOURCES_HEADING = "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"
_COMMA_CITE_RE = re.compile(r"\[\s*\d+\s*,\s*\d+")
_SPACED_RANGE_RE = re.compile(r"(?<!\d)\d+\s+[-–—]\s+\d+(?!\d)")
_GLUED_CAPTION_RE = re.compile(
    r"^!\[[^\]]*\]\([^)]+\)\s+(?:Рисунок|Таблица|Листинг)\s+\S", re.IGNORECASE
)


@dataclass
class LintIssue:
    severity: str
    message: str
    location: str = ""
    rule: str = ""
    suppressed: bool = False

    def __str__(self) -> str:
        where = f" ({self.location})" if self.location else ""
        mark = " [suppressed]" if self.suppressed else ""
        return f"{self.severity.upper()}: {self.message}{where}{mark}"


def _where(element) -> str:
    from .md import element_location

    return element_location(element)


def _iter_text(elements):
    for e in elements:
        if e["type"] in ("para", "list_item") or e["type"] in _CAPTION_KIND:
            yield e.get("text", ""), _where(e)
        elif e["type"] == "table":
            where = _where(e)
            for cell in e.get("header", ()):
                yield cell, where
            for row in e.get("rows", ()):
                for cell in row:
                    yield cell, where


def _defined_keys(elements):
    keys: dict[str, set[str]] = {}
    issues: list[LintIssue] = []
    for e in elements:
        kind = None
        key = None
        if e["type"] in _CAPTION_KIND:
            kind = _CAPTION_KIND[e["type"]]
            key = crossref.extract_key(e.get("text", ""))
        elif e["type"] == "math_block":
            kind = crossref.FORMULA
            key = crossref.extract_key(e.get("number", "") or "")
        if not kind or not key:
            continue
        bucket = keys.setdefault(kind, set())
        if key in bucket:
            issues.append(
                LintIssue(
                    "error",
                    f"duplicate {kind} key '{key}'",
                    _where(e),
                    "duplicate-key",
                )
            )
        bucket.add(key)
    return keys, issues


def _defined_sources(elements):
    nums: set[int] = set()
    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = e["text"].strip().upper().startswith(_SOURCES_HEADING)
            continue
        if not in_sources:
            continue
        if e["type"] == "list_item":
            digits = re.sub(r"\D", "", e.get("marker", ""))
            if digits:
                nums.add(int(digits))
        elif e["type"] == "para":
            m = re.match(r"^\s*(\d+)[.)]", e.get("text", ""))
            if m:
                nums.add(int(m.group(1)))
    return nums


def _check_keyed_citations(elements) -> list[LintIssue]:
    issues: list[LintIssue] = []
    _keynum, definitions = bibliography.scan(elements)
    if not definitions:
        return issues

    cited: set[str] = set()
    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = e["text"].strip().upper().startswith(_SOURCES_HEADING)
            continue
        if in_sources:
            continue
        for text, where, *_ in _iter_text([e]):
            for token in bibliography.KEYED_CITE_RE.finditer(text):
                for key in bibliography.citation_keys(token.group(0)):
                    cited.add(key)
                    if key not in definitions:
                        issues.append(
                            LintIssue(
                                "error",
                                f"keyed citation [{{{key}}}] has no source "
                                f"definition",
                                where,
                                "unknown-citation",
                            )
                        )
    for key in definitions:
        if key not in cited:
            issues.append(
                LintIssue(
                    "warning",
                    f"source '{{{key}}}' is never cited",
                    rule="uncited-source",
                )
            )
    return issues


_LONG_PARAGRAPH_CHARS = 2000


def _referenced_keys(elements):
    refs: dict[str, set[str]] = {}
    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = e["text"].strip().upper().startswith(_SOURCES_HEADING)
            continue
        if in_sources or e["type"] not in ("para", "list_item"):
            continue
        for m in crossref.REFERENCE_RE.finditer(e.get("text", "")):
            kind = crossref._REF_PREFIX_TO_KIND.get(m.group(1).lower())
            if kind:
                refs.setdefault(kind, set()).add(m.group(2))
    return refs


def _check_dictionary_sort(elements) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for section, message in gost_sections.dictionary_sort_issues(elements):
        issues.append(
            LintIssue(
                "warning",
                f"{section}: {message}",
                rule="dictionary-order",
            )
        )
    return issues


def _check_appendix_letters(elements) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for heading, message in gost_sections.appendix_letter_issues(elements):
        issues.append(
            LintIssue(
                "warning",
                f"appendix heading {heading!r}: {message}",
                rule="appendix-letter",
            )
        )
    return issues


def _skipable_between(i: int, elements: list) -> int:
    j = i
    while j < len(elements):
        et = elements[j]["type"]
        if et == "hrule":
            j += 1
            continue
        if et == "para" and not (elements[j].get("text") or "").strip():
            j += 1
            continue
        break
    return j


def _check_layout(elements) -> list[LintIssue]:
    issues: list[LintIssue] = []
    n = len(elements)
    for i, e in enumerate(elements):
        et = e["type"]
        where = _where(e)
        if et == "para" and _GLUED_CAPTION_RE.match((e.get("text") or "").strip()):
            issues.append(
                LintIssue(
                    "warning",
                    "image and caption merged into one paragraph, "
                    "so neither reaches the document",
                    where,
                    "caption-spacing",
                )
            )
        if et == "figure_caption":
            j = i - 1
            while j >= 0 and elements[j]["type"] in ("hrule",):
                j -= 1
            while j >= 0 and elements[j]["type"] == "para" and not (
                elements[j].get("text") or ""
            ).strip():
                j -= 1
            if j < 0 or elements[j]["type"] != "image":
                issues.append(
                    LintIssue(
                        "warning",
                        "figure caption must immediately follow an image",
                        where,
                        "caption-order",
                    )
                )
        if et == "image":
            j = _skipable_between(i + 1, elements)
            if j >= n or elements[j]["type"] != "figure_caption":
                issues.append(
                    LintIssue(
                        "warning",
                        "image must be immediately followed by a figure caption",
                        where,
                        "caption-order",
                    )
                )
        if et == "table":
            j = i - 1
            while j >= 0 and elements[j]["type"] in ("hrule",):
                j -= 1
            while j >= 0 and elements[j]["type"] == "para" and not (
                elements[j].get("text") or ""
            ).strip():
                j -= 1
            if j < 0 or elements[j]["type"] != "table_caption":
                issues.append(
                    LintIssue(
                        "warning",
                        "table must be preceded by a table caption",
                        where,
                        "caption-order",
                    )
                )
            header = e.get("header") or []
            ncol = len(header)
            for ri, row in enumerate(e.get("rows") or []):
                if len(row) != ncol:
                    issues.append(
                        LintIssue(
                            "error",
                            f"table row {ri + 1} has {len(row)} "
                            f"column{'' if len(row) == 1 else 's'}, "
                            f"header has {ncol}",
                            where,
                            "table-columns",
                        )
                    )
        if et == "code" and e.get("include") is not None:
            if e.get("include_error"):
                issues.append(
                    LintIssue(
                        "error",
                        f"@listing {e['include']}: {e['include_error']}",
                        where,
                        "listing-file",
                    )
                )
            elif not e.get("lines"):
                issues.append(
                    LintIssue(
                        "warning",
                        f"@listing {e['include']} is empty, "
                        f"nothing will be inserted",
                        where,
                        "listing-file",
                    )
                )
        if et == "code":
            j = i - 1
            while j >= 0 and elements[j]["type"] in ("hrule",):
                j -= 1
            while j >= 0 and elements[j]["type"] == "para" and not (
                elements[j].get("text") or ""
            ).strip():
                j -= 1
            if j < 0 or elements[j]["type"] != "listing_caption":
                issues.append(
                    LintIssue(
                        "warning",
                        "code block must be preceded by a listing caption",
                        where,
                        "caption-order",
                    )
                )
    return issues


def _check_gost_compliance(elements) -> list[LintIssue]:
    issues: list[LintIssue] = []
    for heading, message in gost_compliance.structural_heading_issues(elements):
        issues.append(
            LintIssue(
                "warning",
                f"heading {heading!r}: {message}",
                rule="structural-heading",
            )
        )
    for kind, message in gost_compliance.numbering_gap_issues(elements):
        issues.append(
            LintIssue("warning", f"{kind}: {message}", rule="numbering-gap")
        )
    return issues


def _advisory_checks(elements) -> list[LintIssue]:
    issues: list[LintIssue] = []

    defined_keys, _ = _defined_keys(elements)
    referenced = _referenced_keys(elements)
    for kind, keys in defined_keys.items():
        for key in sorted(keys):
            if key not in referenced.get(kind, set()):
                issues.append(
                    LintIssue(
                        "warning",
                        f"{kind} '{key}' is never referenced in the text",
                        rule="unreferenced-object",
                    )
                )

    for e in elements:
        if e["type"] == "para" and len(e.get("text", "")) > _LONG_PARAGRAPH_CHARS:
            issues.append(
                LintIssue(
                    "warning",
                    f"very long paragraph ({len(e['text'])} chars)",
                    _where(e),
                    "long-paragraph",
                )
            )

    headings = [e for e in elements if e["type"] == "heading"]
    index = {id(e): i for i, e in enumerate(elements)}
    for h in headings:
        i = index[id(h)]
        nxt = elements[i + 1] if i + 1 < len(elements) else None
        if (
            nxt is not None
            and nxt["type"] == "heading"
            and nxt["level"] <= h["level"]
        ):
            issues.append(
                LintIssue(
                    "warning",
                    f"section '{h['text'].strip()}' has no body text",
                    _where(h),
                    "empty-section",
                )
            )
    return issues


def lint_elements(
    elements,
    *,
    advisory: bool = True,
    strict: bool = False,
) -> list[LintIssue]:
    issues: list[LintIssue] = []

    defined_keys, dup_issues = _defined_keys(elements)
    issues.extend(dup_issues)
    issues.extend(_check_keyed_citations(elements))
    issues.extend(_check_appendix_letters(elements))
    issues.extend(_check_dictionary_sort(elements))
    issues.extend(_check_layout(elements))
    issues.extend(_check_gost_compliance(elements))

    sources = _defined_sources(elements)

    for text, where in _iter_text(elements):
        for m in crossref.REFERENCE_RE.finditer(text):
            prefix = m.group(1).lower()
            key = m.group(2)
            kind = crossref._REF_PREFIX_TO_KIND.get(prefix)
            if kind is None:
                continue
            if key not in defined_keys.get(kind, set()):
                issues.append(
                    LintIssue(
                        "error",
                        f"reference [{m.group(1)}:{key}] has no matching "
                        f"{kind} caption",
                        where,
                        "unknown-reference",
                    )
                )
        if _COMMA_CITE_RE.search(text):
            issues.append(
                LintIssue(
                    "warning",
                    "comma citation form like [1, 2] is not a GOST citation "
                    "and will be left as plain text",
                    where,
                    "comma-citation",
                )
            )
        for m in _SPACED_RANGE_RE.finditer(text):
            issues.append(
                LintIssue(
                    "warning",
                    f"{m.group(0)!r} looks like a range; "
                    "the spaces are kept as typed",
                    where,
                    "spaced-range",
                )
            )
        if sources:
            from .bibliography import NUMERIC_CITE_RE

            for m in NUMERIC_CITE_RE.finditer(text):
                for num in bibliography.cite_numbers(m.group(0)[1:-1]):
                    if num not in sources:
                        issues.append(
                            LintIssue(
                                "warning",
                                f"citation [{num}] has no entry in the source "
                                f"list",
                                where,
                                "unknown-citation",
                            )
                        )

    if advisory:
        issues.extend(_advisory_checks(elements))
    if strict:
        issues = [
            LintIssue("error", i.message, i.location, i.rule)
            if i.severity == "warning"
            else i
            for i in issues
        ]
    return _mark_suppressed(issues, elements)


def _mark_suppressed(issues: list[LintIssue], elements) -> list[LintIssue]:
    from . import suppress
    from .md import element_location, element_suppressions

    by_location: dict[str, tuple[str, ...]] = {}
    file_wide: dict[str, tuple[str, ...]] = {}
    for element in elements:
        patterns = element_suppressions(element)
        if not patterns:
            continue
        where = element_location(element)
        by_location[where] = by_location.get(where, ()) + patterns
        file = where.split(":", 1)[0]
        file_wide[file] = file_wide.get(file, ()) + patterns

    if not by_location:
        return issues
    for issue in issues:
        patterns = by_location.get(issue.location)
        if not patterns and not issue.location:
            patterns = tuple(dict.fromkeys(sum(file_wide.values(), ())))
        hit = suppress.matching(patterns, issue.message, issue.rule)
        if hit is not None:
            issue.suppressed = True
            suppress.mark_used(hit, issue.location)
    return issues


def lint_markdown(
    path: str,
    *,
    advisory: bool = True,
    strict: bool = False,
    listings_root=None,
) -> list[LintIssue]:
    from . import md

    return lint_elements(
        md.parse_md(path, listings_root),
        advisory=advisory,
        strict=strict,
    )
