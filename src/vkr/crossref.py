from __future__ import annotations

import re

from .logging_setup import get_logger

log = get_logger("crossref")

_seen_warnings: set[str] = set()


def reset_warning_state() -> None:
    _seen_warnings.clear()


def _warn_once(key: str, message: str, *args, rule: str = "") -> None:
    if key in _seen_warnings:
        return
    _seen_warnings.add(key)
    log.warning(message, *args, extra={"rule": rule})

FIGURE = "figure"
TABLE = "table"
LISTING = "listing"
FORMULA = "formula"

_KIND_BY_ELEMENT = {
    "figure_caption": FIGURE,
    "table_caption": TABLE,
    "listing_caption": LISTING,
}

_KEY_RE = re.compile(r"\{([\w\-]+)\}")

_APPENDIX_HEADING_RE = re.compile(r"^\s*ПРИЛОЖЕНИЕ\s+([А-Я])\b", re.IGNORECASE)

_REF_PREFIX_TO_KIND = {
    "рис": FIGURE,
    "fig": FIGURE,
    "figure": FIGURE,
    "pic": FIGURE,
    "picture": FIGURE,
    "image": FIGURE,
    "табл": TABLE,
    "tbl": TABLE,
    "table": TABLE,
    "лист": LISTING,
    "lst": LISTING,
    "listing": LISTING,
    "code": LISTING,
    "форм": FORMULA,
    "eq": FORMULA,
    "eqn": FORMULA,
    "formula": FORMULA,
    "equation": FORMULA,
}
_REF_RE = re.compile(
    r"\[("
    + "|".join(sorted(_REF_PREFIX_TO_KIND, key=len, reverse=True))
    + r")\s*:\s*([\w\-]+)\]",
    re.IGNORECASE,
)


def _extract_key(text: str | None) -> str | None:
    m = _KEY_RE.search(text or "")
    return m.group(1) if m else None


def extract_key(text: str | None) -> str | None:
    return _extract_key(text)


REFERENCE_RE = _REF_RE


def reference_target(match: re.Match, maps: dict) -> tuple[str, str, str] | None:
    kind = _REF_PREFIX_TO_KIND[match.group(1).lower()]
    key = match.group(2)
    num = maps.get(kind, {}).get(key)
    if num is None:
        return None
    display = f"({num})" if kind == FORMULA else num
    return kind, key, display


def build_number_map(elements) -> dict[str, dict[str, str]]:
    maps: dict[str, dict[str, str]] = {
        FIGURE: {},
        TABLE: {},
        LISTING: {},
        FORMULA: {},
    }
    global_counters = {FIGURE: 0, TABLE: 0, LISTING: 0, FORMULA: 0}
    appendix_counters: dict[tuple[str, str], int] = {}
    current_appendix: str | None = None

    for e in elements:
        et = e.get("type")
        if et == "heading" and e.get("level") == 1:
            m = _APPENDIX_HEADING_RE.match(e.get("text", "") or "")
            current_appendix = m.group(1).upper() if m else None
            continue
        if et in _KIND_BY_ELEMENT:
            kind = _KIND_BY_ELEMENT[et]
            key = _extract_key(e.get("text", ""))
        elif et == "math_block":
            kind = FORMULA
            key = _extract_key(e.get("number") or "")
        else:
            continue
        if not key:
            continue
        if key in maps[kind]:
            log.warning(
                "duplicate %s key %r; keeping the first number",
                kind,
                key,
                extra={"rule": "duplicate-key"},
            )
            continue
        if current_appendix:
            ck = (current_appendix, kind)
            appendix_counters[ck] = appendix_counters.get(ck, 0) + 1
            maps[kind][key] = f"{current_appendix}.{appendix_counters[ck]}"
        else:
            global_counters[kind] += 1
            maps[kind][key] = str(global_counters[kind])
    return maps


def render_caption_label(text: str, maps: dict, kind: str) -> str:
    def repl(m: re.Match) -> str:
        key = m.group(1)
        num = maps.get(kind, {}).get(key)
        if num is None:
            _warn_once(
                f"caption:{kind}:{key}",
                "unknown %s key %r in a caption",
                kind,
                key,
                rule="unknown-key",
            )
            return m.group(0)
        return num

    return _KEY_RE.sub(repl, text or "")


def resolve_formula_number(number: str | None, maps: dict) -> str | None:
    if not number:
        return number
    key = _extract_key(number)
    if not key:
        return number
    num = maps.get(FORMULA, {}).get(key)
    if num is None:
        _warn_once(
            f"formula:{key}", "unknown formula key %r", key, rule="unknown-key"
        )
        return number
    return f"({num})"


def resolve_references(text: str, maps: dict) -> str:
    if not text or "[" not in text:
        return text

    def repl(m: re.Match) -> str:
        kind = _REF_PREFIX_TO_KIND[m.group(1).lower()]
        key = m.group(2)
        num = maps.get(kind, {}).get(key)
        if num is None:
            token = m.group(0)
            _warn_once(
                f"ref:{token}",
                "unknown reference %s",
                token,
                rule="unknown-reference",
            )
            return m.group(0)
        return f"({num})" if kind == FORMULA else num

    return _REF_RE.sub(repl, text)
