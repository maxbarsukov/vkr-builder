from __future__ import annotations

import re

ABBREVIATIONS_HEADING = "СПИСОК СОКРАЩЕНИЙ И УСЛОВНЫХ ОБОЗНАЧЕНИЙ"
TERMS_HEADING = "ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ"

DICTIONARY_HEADINGS = frozenset({ABBREVIATIONS_HEADING, TERMS_HEADING})

STRUCTURAL_HEADINGS = frozenset(
    {
        ABBREVIATIONS_HEADING,
        TERMS_HEADING,
        "ВВЕДЕНИЕ",
        "ЗАКЛЮЧЕНИЕ",
        "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ",
    }
)

APPENDIX_FORBIDDEN_CYRILLIC = frozenset("ЁЗЙОЧЬЫЪ")
APPENDIX_FORBIDDEN_LATIN = frozenset("IO")

_APPENDIX_H1_RE = re.compile(
    r"^\s*ПРИЛОЖЕНИЕ\s+([А-ЯЁA-Z])\b",
    re.IGNORECASE,
)

_DICT_TERM_RE = re.compile(
    r"^\s*(.+?)\s+[–—\-]\s+",
    re.UNICODE,
)

_RU_SORT_ALPHABET = "АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ"
_RU_SORT_RANK = {ch: i for i, ch in enumerate(_RU_SORT_ALPHABET)}
_LATIN_SORT_RANK = {chr(ord("A") + i): i for i in range(26)}


def section_key(text: str | None) -> str:
    return (text or "").strip().upper()


def is_dictionary_heading(text: str | None) -> bool:
    return section_key(text) in DICTIONARY_HEADINGS


def dictionary_entry_types() -> frozenset[str]:
    return frozenset({"para", "list_item"})


def extract_dictionary_term(text: str) -> str:
    line = (text or "").strip()
    if not line:
        return ""
    m = _DICT_TERM_RE.match(line)
    if m:
        return m.group(1).strip()
    return line


def _char_sort_rank(ch: str) -> tuple[int, int]:
    c = ch.casefold()
    if c == "ё":
        c = "е"
    if "а" <= c <= "я":
        return (0, _RU_SORT_RANK.get(c.upper(), 999))
    if "a" <= c <= "z":
        return (1, _LATIN_SORT_RANK.get(c.upper(), 999))
    if c.isdigit():
        return (2, ord(c))
    return (3, ord(c))


def _term_script_group(term: str) -> int:
    has_cyr = False
    has_lat = False
    for ch in term:
        c = ch.casefold()
        if c == "ё" or ("а" <= c <= "я"):
            has_cyr = True
        elif "a" <= c <= "z":
            has_lat = True
    if has_cyr and has_lat:
        return 2
    if has_cyr:
        return 1
    return 0


def dictionary_sort_key(text: str) -> tuple[int, tuple[tuple[int, int], ...], str]:
    term = extract_dictionary_term(text)
    normalized = term.casefold().replace("ё", "е")
    ranks = tuple(_char_sort_rank(c) for c in normalized)
    return (_term_script_group(term), ranks, normalized)


def extract_appendix_letter(heading_text: str) -> str | None:
    m = _APPENDIX_H1_RE.match((heading_text or "").strip())
    return m.group(1).upper() if m else None


def appendix_letter_issue(letter: str) -> str | None:
    if not letter:
        return "appendix letter is empty"
    ch = letter.strip().upper()
    if len(ch) != 1:
        return f"appendix letter must be a single character, got {letter!r}"
    if "А" <= ch <= "Я" or ch == "Ё":
        if ch in APPENDIX_FORBIDDEN_CYRILLIC:
            return (
                f"appendix letter {ch!r} is not allowed "
                f"(forbidden Russian letters: "
                f"{''.join(sorted(APPENDIX_FORBIDDEN_CYRILLIC))})"
            )
        return None
    if "A" <= ch <= "Z":
        if ch in APPENDIX_FORBIDDEN_LATIN:
            return (
                f"appendix letter {ch!r} is not allowed "
                f"(forbidden Latin letters: "
                f"{''.join(sorted(APPENDIX_FORBIDDEN_LATIN))})"
            )
        return None
    return f"appendix letter {ch!r} must be Cyrillic or Latin"


def _is_dictionary_entry(element: dict) -> bool:
    if element.get("type") not in dictionary_entry_types():
        return False
    return bool((element.get("text") or "").strip())


def sort_dictionary_sections(elements: list[dict]) -> list[dict]:
    out: list[dict] = []
    i = 0
    n = len(elements)
    while i < n:
        e = elements[i]
        out.append(e)
        if (
            e.get("type") == "heading"
            and e.get("level") == 1
            and is_dictionary_heading(e.get("text"))
        ):
            i += 1
            span_start = len(out)
            span_end_idx = i
            while span_end_idx < n:
                nxt = elements[span_end_idx]
                if nxt.get("type") == "heading" and nxt.get("level") == 1:
                    break
                span_end_idx += 1
            span = elements[i:span_end_idx]
            entry_indices = [
                j for j, el in enumerate(span) if _is_dictionary_entry(el)
            ]
            if entry_indices:
                entries = [span[j] for j in entry_indices]
                entries.sort(key=lambda el: dictionary_sort_key(el.get("text", "")))
                it = iter(entries)
                new_span = []
                for j, el in enumerate(span):
                    if j in entry_indices:
                        new_span.append(next(it))
                    else:
                        new_span.append(el)
                out.extend(new_span)
            else:
                out.extend(span)
            i = span_end_idx
            continue
        i += 1
    return out


def dictionary_sort_issues(elements: list[dict]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    current_section: str | None = None
    entries: list[str] = []

    def flush() -> None:
        nonlocal entries, current_section
        if not current_section or len(entries) < 2:
            entries = []
            return
        keys = [dictionary_sort_key(t) for t in entries]
        sorted_keys = sorted(keys)
        if keys != sorted_keys:
            issues.append(
                (
                    current_section,
                    "dictionary entries are not in alphabetical order "
                    f"({len(entries)} items)",
                )
            )
        entries = []

    for e in elements:
        if e.get("type") == "heading" and e.get("level") == 1:
            flush()
            current_section = (
                section_key(e.get("text"))
                if is_dictionary_heading(e.get("text"))
                else None
            )
            continue
        if current_section and _is_dictionary_entry(e):
            entries.append(e.get("text", ""))
    flush()
    return issues


def appendix_letter_issues(elements: list[dict]) -> list[tuple[str, str]]:
    issues: list[tuple[str, str]] = []
    seen: dict[str, str] = {}

    for e in elements:
        if e.get("type") != "heading" or e.get("level") != 1:
            continue
        text = (e.get("text") or "").strip()
        letter = extract_appendix_letter(text)
        if letter is None:
            continue
        msg = appendix_letter_issue(letter)
        if msg:
            issues.append((text, msg))
            continue
        if letter in seen:
            issues.append(
                (
                    text,
                    f"duplicate appendix letter {letter!r} "
                    f"(first used in {seen[letter]!r})",
                )
            )
        else:
            seen[letter] = text
    return issues
