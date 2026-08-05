from __future__ import annotations

from collections import Counter

_ELEMENT_SUMMARY_ORDER = (
    ("heading", "headings"),
    ("para", "paragraphs"),
    ("list_item", "list items"),
    ("table", "tables"),
    ("image", "figures"),
    ("code", "listings"),
    ("math_block", "formulas"),
)


_COMPACT_ORDER = (
    ("heading", "headings"),
    ("table", "tables"),
    ("image", "figures"),
    ("math_block", "formulas"),
)


def _summarise(counts: Counter, order) -> str:
    return ", ".join(
        f"{counts[key]} {label}" for key, label in order if counts.get(key)
    )


def format_element_summary(counts: Counter) -> str:
    return _summarise(counts, _ELEMENT_SUMMARY_ORDER)


def format_element_summary_compact(counts: Counter) -> str:
    return _summarise(counts, _COMPACT_ORDER)
