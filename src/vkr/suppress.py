from __future__ import annotations

import difflib
from dataclasses import dataclass

MARKDOWN = "markdown"
BUILD = "build"
DOCUMENT = "document"

_BY_STAGE: dict[str, dict[str, str]] = {
    MARKDOWN: {
    "unknown-reference": "a [рис:key] reference with no caption to point at",
    "duplicate-key": "the same caption or formula key used twice",
    "unknown-citation": "a citation with no entry in the source list",
    "uncited-source": "a source in the list that the text never cites",
    "unreferenced-object": "a figure, table or listing the text never refers to",
    "caption-order": "a caption on the wrong side of its figure, table or listing",
    "caption-spacing": "an image and its caption glued into one paragraph",
    "comma-citation": "the [1, 2] citation form, which GOST does not allow",
    "spaced-range": "a numeric range written with spaces around the dash",
    "table-columns": "a table row with a different column count than its header",
    "long-paragraph": "a paragraph past the length limit",
    "empty-section": "a heading with no body text under it",
    "structural-heading": "a level-1 heading that is not a GOST section name",
    "numbering-gap": "a gap in explicit figure, table or listing numbers",
    "dictionary-order": "abbreviations or terms out of alphabetical order",
    "appendix-letter": "an invalid or repeated appendix letter",
    "listing-file": "an @listing file that could not be read or was empty",
    },
    BUILD: {
    "unknown-key": "a caption or formula key that nothing defines",
    "duplicate-source": "the same source number or key twice in the list",
    "image": "an image that could not be read or inserted",
    "metadata": "document metadata that could not be parsed or applied",
    "table-continuation": "a table that could not be split across pages",
    "toc-unstable": "page numbers that kept moving between layout passes",
    "heading-mismatch": "headings in the document that differ from the markdown",
    "page-numbering": "a printed page number that differs from the config",
    "output-locked": "an output file held open by another program",
    "unknown-element": "a markdown element the builder does not know",
    },
    DOCUMENT: {
    "figure-captions": "figures and figure captions that do not add up",
    "table-captions": "table captions that do not add up",
    "empty-heading": "a heading with no text",
    "orphan-widow": "a line left alone at a page boundary",
    },
}

RULES: dict[str, str] = {
    rule: text for group in _BY_STAGE.values() for rule, text in group.items()
}

_ALSO_RAISED_BY: dict[str, frozenset[str]] = {
    "unknown-reference": frozenset({BUILD}),
    "unknown-citation": frozenset({BUILD}),
    "uncited-source": frozenset({BUILD}),
    "listing-file": frozenset({BUILD}),
}


@dataclass(frozen=True)
class Directive:
    pattern: str
    scope: str
    location: str

    @property
    def file(self) -> str:
        return self.location.split(":", 1)[0] if self.location else ""


_directives: dict[tuple[str, str], Directive] = {}
_used: set[tuple[str, str]] = set()


def reset() -> None:
    _directives.clear()
    _used.clear()


def register(pattern: str, scope: str, location: str) -> None:
    _directives[(pattern, location)] = Directive(pattern, scope, location)


def mark_used(pattern: str, location: str) -> None:
    file = location.split(":", 1)[0] if location else ""
    for key, directive in _directives.items():
        if directive.pattern == pattern and (not file or directive.file == file):
            _used.add(key)


def misspelled_rule(pattern: str) -> str | None:
    name = (pattern or "").strip().lower()
    if not name or name in RULES:
        return None
    close = difflib.get_close_matches(name, RULES, n=1, cutoff=0.8)
    return close[0] if close else None


def stages_of(pattern: str) -> frozenset[str]:
    name = (pattern or "").strip().lower()
    for stage, group in _BY_STAGE.items():
        if name in group:
            return frozenset({stage}) | _ALSO_RAISED_BY.get(name, frozenset())
    return frozenset()


def _had_its_chance(pattern: str, stages) -> bool:
    raised_in = stages_of(pattern)
    if raised_in:
        return raised_in <= set(stages)
    if misspelled_rule(pattern):
        return True
    return set(_BY_STAGE) <= set(stages)


def unused(stages=None) -> list[Directive]:
    return [
        directive
        for key, directive in _directives.items()
        if key not in _used
        and (stages is None or _had_its_chance(directive.pattern, stages))
    ]


def matching(patterns, message: str, rule: str = "") -> str | None:
    text = (message or "").lower()
    rule_name = (rule or "").lower()
    for pattern in patterns or ():
        clean = pattern.strip().lower()
        if not clean:
            return pattern
        if rule_name and clean == rule_name:
            return pattern
        if clean in text:
            return pattern
    return None


def is_suppressed(patterns, message: str, rule: str = "") -> bool:
    return matching(patterns, message, rule) is not None


def known_rule(name: str) -> bool:
    return name.strip().lower() in RULES


def rule_list() -> str:
    return ", ".join(sorted(RULES))
