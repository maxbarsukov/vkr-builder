from __future__ import annotations

import re

from .logging_setup import get_logger

log = get_logger("bibliography")

_seen_warnings: set[str] = set()


def reset_warning_state() -> None:
    _seen_warnings.clear()


def _warn_once(key: str, message: str, *args, rule: str = "") -> None:
    if key in _seen_warnings:
        return
    _seen_warnings.add(key)
    log.warning(message, *args, extra={"rule": rule})

SOURCES_HEADING = "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ"

KEYED_CITE_RE = re.compile(
    r"\[\s*\{[\w\-]+\}(?:\s*;\s*\{[\w\-]+\})*\s*\]"
)
_KEY_RE = re.compile(r"\{([\w\-]+)\}")
_SOURCE_DEF_RE = re.compile(r"^\s*\{([\w\-]+)\}\s*(.*)$", re.DOTALL)

NUMERIC_CITE_RE = re.compile(
    r"\[\s*\d+(?:\s*[-\u2013]\s*\d+)?(?:\s*;\s*\d+(?:\s*[-\u2013]\s*\d+)?)*\s*\]"
)
_NUMERIC_SOURCE_PARA_RE = re.compile(r"^\s*(\d+)[.)]\s*(.*)$", re.S)


def citation_keys(text: str) -> list[str]:
    return _KEY_RE.findall(text or "")


def cite_numbers(inner: str) -> list[int]:
    nums: list[int] = []
    for item in inner.split(";"):
        item = item.strip()
        rng = re.match(r"^(\d+)\s*[-\u2013]\s*(\d+)$", item)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if a <= b:
                nums.extend(range(a, b + 1))
            else:
                nums.extend(range(b, a + 1))
        elif item.isdigit():
            nums.append(int(item))
    return nums


def numbers_in_citation_token(token: str) -> list[int]:
    if not token or len(token) < 3:
        return []
    return cite_numbers(token[1:-1])


def _is_sources_heading(text: str) -> bool:
    return text.strip().upper().startswith(SOURCES_HEADING)


def _source_text_of(element: dict) -> str:
    return element.get("text", "")


def _has_keyed_markers(elements: list[dict]) -> bool:
    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = _is_sources_heading(e.get("text", ""))
            continue
        if e["type"] not in ("para", "list_item"):
            continue
        text = _source_text_of(e)
        if in_sources:
            if _SOURCE_DEF_RE.match(text):
                return True
            continue
        if KEYED_CITE_RE.search(text):
            return True
    return False


def scan(elements: list[dict]) -> tuple[dict[str, int], dict[str, str]]:
    mention_order: list[str] = []
    seen: set[str] = set()
    definitions: dict[str, str] = {}

    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = _is_sources_heading(e.get("text", ""))
            continue
        if e["type"] not in ("para", "list_item"):
            continue
        text = _source_text_of(e)
        if in_sources:
            m = _SOURCE_DEF_RE.match(text)
            if m:
                key = m.group(1)
                if key in definitions:
                    _warn_once(
                        f"dup:{key}",
                        "duplicate source key %r in the source list",
                        key,
                        rule="duplicate-source",
                    )
                definitions[key] = m.group(2).strip()
            continue
        for token in KEYED_CITE_RE.finditer(text):
            for key in citation_keys(token.group(0)):
                if key not in seen:
                    seen.add(key)
                    mention_order.append(key)

    ordered = [k for k in mention_order if k in definitions]
    for key in definitions:
        if key not in seen:
            _warn_once(
                f"uncited:{key}",
                "source %r in the list is never cited",
                key,
                rule="uncited-source",
            )
            ordered.append(key)
    for key in mention_order:
        if key not in definitions:
            _warn_once(
                f"missing:{key}",
                "citation {%s} has no entry in the source list",
                key,
                rule="unknown-citation",
            )

    keynum = {key: i + 1 for i, key in enumerate(ordered)}
    return keynum, definitions


def active(keynum: dict[str, int], definitions: dict[str, str]) -> bool:
    return bool(keynum or definitions)


def rebuild_elements(
    elements: list[dict], keynum: dict[str, int], definitions: dict[str, str]
) -> list[dict]:
    num_to_key = {n: k for k, n in keynum.items()}
    new_entries: list[dict] = []
    for num in sorted(num_to_key):
        key = num_to_key[num]
        new_entries.append(
            {
                "type": "list_item",
                "marker_type": "number",
                "marker": f"{num}.",
                "text": definitions[key],
                "level": 0,
            }
        )

    out: list[dict] = []
    in_sources = False
    inserted = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = _is_sources_heading(e.get("text", ""))
            out.append(e)
            continue
        if in_sources and e["type"] in ("para", "list_item"):
            if not inserted:
                out.extend(new_entries)
                inserted = True
            continue
        out.append(e)
    return out


def _parse_numeric_sources(elements: list[dict]) -> dict[int, str]:
    sources: dict[int, str] = {}
    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = _is_sources_heading(e.get("text", ""))
            continue
        if not in_sources:
            continue
        if e["type"] == "list_item":
            digits = re.sub(r"\D", "", e.get("marker", ""))
            if digits:
                num = int(digits)
                text = e.get("text", "").strip()
                if num in sources:
                    log.warning(
                        "duplicate source number %d in the source list",
                        num,
                        extra={"rule": "duplicate-source"},
                    )
                sources[num] = text
        elif e["type"] == "para":
            m = _NUMERIC_SOURCE_PARA_RE.match(e.get("text", ""))
            if m:
                num = int(m.group(1))
                text = m.group(2).strip()
                if num in sources:
                    log.warning(
                        "duplicate source number %d in the source list",
                        num,
                        extra={"rule": "duplicate-source"},
                    )
                sources[num] = text
    return sources


def scan_numeric(elements: list[dict]) -> tuple[dict[int, int], dict[int, str]]:
    definitions = _parse_numeric_sources(elements)
    if not definitions:
        return {}, {}

    mention_order: list[int] = []
    seen: set[int] = set()
    in_sources = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = _is_sources_heading(e.get("text", ""))
            continue
        if in_sources or e["type"] not in ("para", "list_item"):
            continue
        for token in NUMERIC_CITE_RE.finditer(e.get("text", "")):
            for num in numbers_in_citation_token(token.group(0)):
                if num not in seen:
                    seen.add(num)
                    mention_order.append(num)

    ordered = [n for n in mention_order if n in definitions]
    for num in sorted(definitions):
        if num not in seen:
            _warn_once(
                f"uncited:{num}",
                "source %d in the list is never cited",
                num,
                rule="uncited-source",
            )
            ordered.append(num)
    for num in mention_order:
        if num not in definitions:
            _warn_once(
                f"missing:{num}",
                "citation [%d] has no entry in the source list",
                num,
                rule="unknown-citation",
            )

    old_to_new = {old: i + 1 for i, old in enumerate(ordered)}
    new_sources = {old_to_new[old]: definitions[old] for old in ordered}
    return old_to_new, new_sources


def numeric_active(old_to_new: dict[int, int], new_sources: dict[int, str]) -> bool:
    return bool(old_to_new and new_sources)


def _format_citation_numbers(nums: list[int]) -> str:
    unique = sorted(set(nums))
    if not unique:
        return ""
    if len(unique) == 1:
        return str(unique[0])
    if unique == list(range(unique[0], unique[-1] + 1)):
        lo, hi = unique[0], unique[-1]
        return f"{lo}-{hi}" if lo != hi else str(lo)
    return "; ".join(str(n) for n in unique)


def remap_citation_token(token: str, old_to_new: dict[int, int]) -> str:
    inner = token[1:-1]
    out_parts: list[str] = []
    for item in inner.split(";"):
        item = item.strip()
        rng = re.match(r"^(\d+)\s*[-\u2013]\s*(\d+)$", item)
        if rng:
            a, b = int(rng.group(1)), int(rng.group(2))
            if a > b:
                a, b = b, a
            old_nums = list(range(a, b + 1))
            if not all(n in old_to_new for n in old_nums):
                return token
            new_nums = [old_to_new[n] for n in old_nums]
            out_parts.append(_format_citation_numbers(new_nums))
        elif item.isdigit():
            n = int(item)
            if n not in old_to_new:
                return token
            out_parts.append(str(old_to_new[n]))
        else:
            return token
    return "[" + "; ".join(out_parts) + "]"


def rewrite_citations_in_text(text: str, old_to_new: dict[int, int]) -> str:
    if not text or "[" not in text:
        return text

    def repl(m: re.Match) -> str:
        return remap_citation_token(m.group(0), old_to_new)

    return NUMERIC_CITE_RE.sub(repl, text)


def _map_text(element: dict, transform) -> dict:
    kind = element["type"]
    if kind in ("para", "list_item") or kind.endswith("_caption"):
        out = dict(element)
        out["text"] = transform(element.get("text", ""))
        return out
    if kind == "table":
        out = dict(element)
        if element.get("header"):
            out["header"] = [transform(c) for c in element["header"]]
        if element.get("rows"):
            out["rows"] = [[transform(c) for c in row] for row in element["rows"]]
        return out
    return element


def rewrite_elements_citations(
    elements: list[dict], old_to_new: dict[int, int]
) -> list[dict]:
    return [
        _map_text(e, lambda t: rewrite_citations_in_text(t, old_to_new))
        for e in elements
    ]


def render_keyed_citations_outside_prose(
    elements: list[dict], keynum: dict[str, int]
) -> list[dict]:
    def render(text: str) -> str:
        def repl(match):
            keys = citation_keys(match.group(0))
            if any(k not in keynum for k in keys):
                return match.group(0)
            nums = sorted({keynum[k] for k in keys})
            return "[" + "; ".join(str(n) for n in nums) + "]"

        return KEYED_CITE_RE.sub(repl, text or "")

    return [
        _map_text(e, render)
        if e["type"] == "table" or e["type"].endswith("_caption")
        else e
        for e in elements
    ]


def rebuild_numeric_elements(
    elements: list[dict],
    old_to_new: dict[int, int],
    new_sources: dict[int, str],
) -> list[dict]:
    elements = rewrite_elements_citations(elements, old_to_new)
    new_entries: list[dict] = []
    for num in sorted(new_sources):
        new_entries.append(
            {
                "type": "list_item",
                "marker_type": "number",
                "marker": f"{num}.",
                "text": new_sources[num],
                "level": 0,
            }
        )

    out: list[dict] = []
    in_sources = False
    inserted = False
    for e in elements:
        if e["type"] == "heading":
            in_sources = _is_sources_heading(e.get("text", ""))
            out.append(e)
            continue
        if in_sources and e["type"] in ("para", "list_item"):
            if not inserted:
                out.extend(new_entries)
                inserted = True
            continue
        out.append(e)
    return out


def prepare_elements(
    elements: list[dict],
) -> tuple[list[dict], set[int], dict[str, int]]:
    if _has_keyed_markers(elements):
        keynum, definitions = scan(elements)
        if active(keynum, definitions):
            elements = rebuild_elements(elements, keynum, definitions)
            elements = render_keyed_citations_outside_prose(elements, keynum)
            return elements, set(keynum.values()), keynum

    old_to_new, new_sources = scan_numeric(elements)
    if numeric_active(old_to_new, new_sources):
        elements = rebuild_numeric_elements(elements, old_to_new, new_sources)
        return elements, set(new_sources), {}

    return elements, set(), {}
