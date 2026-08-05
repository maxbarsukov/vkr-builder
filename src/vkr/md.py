from __future__ import annotations

import os
import re
from typing import Any

from docx.oxml import OxmlElement

from . import suppress

FILE_MARKER_RE = re.compile(r"^\s*<!--\s*file:\s*(.+?)\s*-->\s*$")
_HTML_COMMENT_RE = re.compile(r"^\s*<!--.*-->\s*$", re.DOTALL)


def file_marker(name: str) -> str:
    return f"<!-- file: {name} -->"


SUPPRESS_RE = re.compile(
    r"^\s*<!--\s*@suppress(?P<scope>-file)?\b(?P<pattern>.*?)-->\s*$",
    re.IGNORECASE | re.DOTALL,
)


LISTING_INCLUDE_RE = re.compile(r"^@listing\s+(?P<spec>\S.*?)\s*$")
_LISTING_RANGE_RE = re.compile(r"^(?P<path>.+?):(?P<first>\d+)\s*-\s*(?P<last>\d*)$")


def parse_listing_include(line: str) -> dict[str, Any] | None:
    match = LISTING_INCLUDE_RE.match((line or "").strip())
    if match is None:
        return None
    return {
        "type": "code",
        "lang": "",
        "lines": [],
        "include": match.group("spec"),
    }


def _split_range(spec: str) -> tuple[str, int | None, int | None]:
    match = _LISTING_RANGE_RE.match(spec)
    if match is None:
        return spec, None, None
    last = match.group("last")
    return (
        match.group("path"),
        int(match.group("first")),
        int(last) if last else None,
    )


def _read_listing(element, root) -> str:
    from pathlib import Path

    rel, first, last = _split_range(element.get("include") or "")
    rel = rel.replace("\\", "/")
    if root is None:
        return "no listings directory is configured"
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        return f"path escapes the listings directory: {rel}"
    if not target.is_file():
        return f"file not found: {rel}"
    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return f"cannot read {rel}: {exc}"

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()

    if first is not None:
        if first < 1:
            return f"{rel} is numbered from 1, range starts at {first}"
        if first > len(lines):
            return (
                f"{rel} has {len(lines)} line{'' if len(lines) == 1 else 's'}, "
                f"range starts at {first}"
            )
        if last is not None and last < first:
            return f"empty line range {first}-{last} for {rel}"
        lines = lines[first - 1: last if last is not None else None]

    element["lines"] = lines
    element["lang"] = target.suffix.lstrip(".").lower()
    return ""


def resolve_listing_includes(elements, root) -> None:
    for element in elements:
        if element.get("include") is None:
            continue
        error = _read_listing(element, root)
        if error:
            element["include_error"] = error


def parse_suppress(line: str) -> tuple[str, str] | None:
    match = SUPPRESS_RE.match(line)
    if match is None:
        return None
    scope = "file" if match.group("scope") else "element"
    return scope, match.group("pattern").strip()


def is_suppressed(patterns, message: str, rule: str = "") -> bool:
    from .suppress import is_suppressed as _is_suppressed

    return _is_suppressed(patterns, message, rule)


def element_suppressions(element) -> tuple[str, ...]:
    return tuple(element.get("suppress") or ())


def element_location(element) -> str:
    src = element.get("src_file")
    line = element.get("src_line")
    if src and line:
        return f"{src}:{line}"
    if src:
        return str(src)
    if line:
        return f"line {line}"
    return ""


_GREEK = {
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ", "Epsilon": "Ε",
    "Zeta": "Ζ", "Eta": "Η", "Theta": "Θ", "Iota": "Ι", "Kappa": "Κ",
    "Lambda": "Λ", "Mu": "Μ", "Nu": "Ν", "Xi": "Ξ", "Omicron": "Ο",
    "Pi": "Π", "Rho": "Ρ", "Sigma": "Σ", "Tau": "Τ", "Upsilon": "Υ",
    "Phi": "Φ", "Chi": "Χ", "Psi": "Ψ", "Omega": "Ω",
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ",
    "lambda": "λ", "mu": "μ", "nu": "ν", "xi": "ξ", "omicron": "ο",
    "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ",
    "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω",
}

_FORMULA_NUMBER_RE = re.compile(r"^\s*(?:\(\s*\d+(?:\.\d+)?\s*\)|\{[\w\-]+\})\s*$")

_SINGLE_LINE_DISPLAY_RE = re.compile(r"^\\\[(?P<body>.*?)\\\]$")

_MATH_VAL = "{http://schemas.openxmlformats.org/officeDocument/2006/math}val"

_BIG_OPERATORS = {
    "sum": "\u2211",
    "prod": "\u220f",
    "int": "\u222b",
    "iint": "\u222c",
    "oint": "\u222e",
    "bigcup": "\u22c3",
    "bigcap": "\u22c2",
}

_CMD_SYMBOLS = {
    "times": "×",
    "cdot": "·",
    "approx": "≈",
    "leq": "≤",
    "geq": "≥",
    "neq": "≠",
    "pm": "±",
    "infty": "∞",
    "rightarrow": "→",
    "leftarrow": "←",
    "Rightarrow": "⇒",
    "Leftarrow": "⇐",
    "ldots": "…",
    "dots": "…",
    "quad": " ",
    "qquad": "  ",
    "%": "%",
}


def split_text_and_math(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    i = 0
    n = len(text)
    plain_start = 0

    while i < n:
        if text[i] == "\\" and i + 1 < n and text[i + 1] == "(":
            if i > plain_start:
                out.append(("text", text[plain_start:i]))
            j = i + 2
            depth = 0
            while j < n:
                if text.startswith("\\)", j) and depth == 0:
                    out.append(("math", text[i + 2 : j]))
                    j += 2
                    break
                ch = text[j]
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                j += 1
            else:
                i += 1
                continue
            i = j
            plain_start = i
            continue

        if text[i] == "$" and not (i > 0 and text[i - 1] == "\\"):
            if i > plain_start:
                out.append(("text", text[plain_start:i]))
            j = i + 1
            while j < n:
                if text[j] == "$" and (j == 0 or text[j - 1] != "\\"):
                    out.append(("math", text[i + 1 : j]))
                    i = j + 1
                    plain_start = i
                    break
                j += 1
            else:
                plain_start = i
                i += 1
            continue

        i += 1

    if plain_start < n:
        out.append(("text", text[plain_start:n]))
    return out


def is_display_math_block(block: list[str]) -> bool:
    if not block:
        return False
    first = block[0].strip()
    last = block[-1].strip()
    if first == r"\[" and last == r"\]":
        return True
    if first == r"\[" and len(block) >= 3:
        if block[-2].strip() == r"\]" and _FORMULA_NUMBER_RE.match(last):
            return True
    if _SINGLE_LINE_DISPLAY_RE.match(first):
        if len(block) == 1:
            return True
        if len(block) == 2 and _FORMULA_NUMBER_RE.match(last):
            return True
    if first.startswith("$$") and last.endswith("$$"):
        return True
    return False


def parse_display_math_block(block: list[str]) -> tuple[str, str | None]:
    first = block[0].strip()
    last = block[-1].strip()
    if first == r"\[":
        if last == r"\]":
            latex = " ".join(line.strip() for line in block[1:-1]).strip()
            return latex, None
        if len(block) >= 3 and block[-2].strip() == r"\]" and _FORMULA_NUMBER_RE.match(last):
            latex = " ".join(line.strip() for line in block[1:-2]).strip()
            return latex, last.strip()
    m_single = _SINGLE_LINE_DISPLAY_RE.match(first)
    if m_single:
        latex = m_single.group("body").strip()
        if len(block) >= 2 and _FORMULA_NUMBER_RE.match(last):
            return latex, last.strip()
        return latex, None
    full = "\n".join(block).strip()
    if full.startswith("$$") and full.endswith("$$"):
        return full[2:-2].strip(), None
    return full.strip(), None


def parse_display_math_latex(block: list[str]) -> str:
    latex, _ = parse_display_math_block(block)
    return latex


class _LatexParser:
    def __init__(self, s: str) -> None:
        self.s = s.strip()
        self.i = 0
        self.n = len(self.s)

    def parse(self) -> list[Any]:
        return self._parse_nodes(stop_at_brace=False)

    def _parse_nodes(self, *, stop_at_brace: bool) -> list[Any]:
        nodes: list[Any] = []
        while self.i < self.n:
            self._skip_space()
            if self.i >= self.n:
                break
            if stop_at_brace and self.s[self.i] == "}":
                break
            atom = self._parse_atom()
            if atom is None:
                break
            atom = self._attach_scripts(atom)
            bigop = _split_bigop(atom)
            if bigop is not None:
                chr_sym, sub, sup = bigop
                operand = self._parse_nodes(stop_at_brace=stop_at_brace)
                nodes.append(("nary", chr_sym, sub, sup, operand))
                break
            nodes.append(atom)
        return nodes

    def _skip_space(self) -> None:
        while self.i < self.n and self.s[self.i] in " \t\n\r":
            self.i += 1

    def _attach_scripts(self, base: Any) -> Any:
        sub: Any | None = None
        sup: Any | None = None
        while True:
            self._skip_space()
            if self.i < self.n and self.s[self.i] == "^":
                self.i += 1
                sup = self._parse_atom()
                continue
            if self.i < self.n and self.s[self.i] == "_":
                self.i += 1
                sub = self._parse_atom()
                continue
            break
        if sub is not None and sup is not None:
            return ("subsup", base, sub, sup)
        if sub is not None:
            return ("sub", base, sub)
        if sup is not None:
            return ("sup", base, sup)
        return base

    def _parse_atom(self) -> Any | None:
        self._skip_space()
        if self.i >= self.n:
            return None
        ch = self.s[self.i]
        if ch == "\\":
            return self._parse_command()
        if ch == "{":
            return ("group", self._parse_group_nodes())
        if ch in "+-=(),.;:|":
            self.i += 1
            return ("text", ch)
        if ch == "%":
            self.i += 1
            return ("text", "%")
        self.i += 1
        return ("text", ch)

    def _parse_group_nodes(self) -> list[Any]:
        assert self.s[self.i] == "{"
        self.i += 1
        nodes = self._parse_nodes(stop_at_brace=True)
        if self.i < self.n and self.s[self.i] == "}":
            self.i += 1
        return nodes

    def _parse_braced_group(self) -> list[Any]:
        self._skip_space()
        if self.i < self.n and self.s[self.i] == "{":
            return self._parse_group_nodes()
        atom = self._parse_atom()
        return [atom] if atom is not None else []

    def _parse_command(self) -> Any:
        self.i += 1
        start = self.i
        while self.i < self.n and self.s[self.i].isalpha():
            self.i += 1
        name = self.s[start : self.i] if self.i > start else ""

        if not name and self.i < self.n:
            sym = self.s[self.i]
            self.i += 1
            if sym in _CMD_SYMBOLS:
                return ("text", _CMD_SYMBOLS[sym])
            return ("text", sym)

        if name in ("left", "right"):
            self._skip_space()
            if self.i < self.n and self.s[self.i] in "([{|.":
                self.i += 1
            return ("text", "")
        if name == "frac":
            num = self._parse_braced_group()
            den = self._parse_braced_group()
            return ("frac", ("group", num), ("group", den))
        if name in ("mathrm", "text", "operatorname"):
            return ("mathrm", self._parse_braced_group())
        if name in _BIG_OPERATORS:
            return ("bigop", _BIG_OPERATORS[name])
        if name in _GREEK:
            return ("text", _GREEK[name])
        if name in _CMD_SYMBOLS:
            return ("text", _CMD_SYMBOLS[name])
        return ("text", name)


def parse_latex(latex: str) -> list[Any]:
    return _LatexParser(latex).parse()


def _mr(text: str, *, roman: bool = False) -> OxmlElement:
    r = OxmlElement("m:r")
    if roman:
        r_pr = OxmlElement("m:rPr")
        sty = OxmlElement("m:sty")
        sty.set("{http://schemas.openxmlformats.org/officeDocument/2006/math}val", "p")
        r_pr.append(sty)
        r.append(r_pr)
    t = OxmlElement("m:t")
    t.text = text
    if text != text.strip() or " " in text:
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    return r


def _nodes_to_omml(nodes: list[Any], *, roman: bool = False) -> list[OxmlElement]:
    out: list[OxmlElement] = []
    for node in nodes:
        out.extend(_node_to_omml(node, roman=roman))
    return out


def _is_bigop(node: Any) -> bool:
    return isinstance(node, tuple) and len(node) >= 2 and node[0] == "bigop"


def _split_bigop(node: Any) -> tuple[str, Any | None, Any | None] | None:
    if not isinstance(node, tuple) or not node:
        return None
    kind = node[0]
    if kind == "bigop":
        return node[1], None, None
    if kind == "sub" and _is_bigop(node[1]):
        return node[1][1], node[2], None
    if kind == "sup" and _is_bigop(node[1]):
        return node[1][1], None, node[2]
    if kind == "subsup" and _is_bigop(node[1]):
        return node[1][1], node[2], node[3]
    return None


def _nary_element(
    chr_sym: str,
    sub_node: Any | None,
    sup_node: Any | None,
    operand_nodes: list[Any] | tuple[Any, ...] = (),
) -> OxmlElement:
    nary = OxmlElement("m:nary")
    pr = OxmlElement("m:naryPr")
    chr_el = OxmlElement("m:chr")
    chr_el.set(_MATH_VAL, chr_sym)
    pr.append(chr_el)
    lim_loc = OxmlElement("m:limLoc")
    lim_loc.set(_MATH_VAL, "undOvr")
    pr.append(lim_loc)
    if sub_node is None:
        sub_hide = OxmlElement("m:subHide")
        sub_hide.set(_MATH_VAL, "1")
        pr.append(sub_hide)
    if sup_node is None:
        sup_hide = OxmlElement("m:supHide")
        sup_hide.set(_MATH_VAL, "1")
        pr.append(sup_hide)
    nary.append(pr)
    sub = OxmlElement("m:sub")
    if sub_node is not None:
        for el in _node_to_omml(sub_node):
            sub.append(el)
    sup = OxmlElement("m:sup")
    if sup_node is not None:
        for el in _node_to_omml(sup_node):
            sup.append(el)
    e = OxmlElement("m:e")
    for el in _nodes_to_omml(list(operand_nodes)):
        e.append(el)
    nary.append(sub)
    nary.append(sup)
    nary.append(e)
    return nary


def _node_to_omml(node: Any, *, roman: bool = False) -> list[OxmlElement]:
    kind = node[0]
    if kind == "text":
        txt = node[1]
        if not txt:
            return []
        return [_mr(txt, roman=roman)]
    if kind == "group":
        return _nodes_to_omml(node[1], roman=roman)
    if kind == "mathrm":
        return _nodes_to_omml(node[1], roman=True)
    if kind == "frac":
        f = OxmlElement("m:f")
        f_pr = OxmlElement("m:fPr")
        f_type = OxmlElement("m:type")
        f_type.set("{http://schemas.openxmlformats.org/officeDocument/2006/math}val", "bar")
        f_pr.append(f_type)
        f.append(f_pr)
        num = OxmlElement("m:num")
        den = OxmlElement("m:den")
        for el in _node_to_omml(node[1]):
            num.append(el)
        for el in _node_to_omml(node[2]):
            den.append(el)
        f.append(num)
        f.append(den)
        return [f]
    if kind == "bigop":
        return [_mr(node[1])]
    if kind == "nary":
        _, chr_sym, sub_node, sup_node, operand = node
        return [_nary_element(chr_sym, sub_node, sup_node, operand)]
    if kind == "sub":
        base = node[1]
        s_sub = OxmlElement("m:sSub")
        e = OxmlElement("m:e")
        sub = OxmlElement("m:sub")
        for el in _node_to_omml(base):
            e.append(el)
        for el in _node_to_omml(node[2]):
            sub.append(el)
        s_sub.append(e)
        s_sub.append(sub)
        return [s_sub]
    if kind == "sup":
        base = node[1]
        s_sup = OxmlElement("m:sSup")
        e = OxmlElement("m:e")
        sup = OxmlElement("m:sup")
        for el in _node_to_omml(base):
            e.append(el)
        for el in _node_to_omml(node[2]):
            sup.append(el)
        s_sup.append(e)
        s_sup.append(sup)
        return [s_sup]
    if kind == "subsup":
        base = node[1]
        s_ss = OxmlElement("m:sSubSup")
        e = OxmlElement("m:e")
        sub = OxmlElement("m:sub")
        sup = OxmlElement("m:sup")
        for el in _node_to_omml(base):
            e.append(el)
        for el in _node_to_omml(node[2]):
            sub.append(el)
        for el in _node_to_omml(node[3]):
            sup.append(el)
        s_ss.append(e)
        s_ss.append(sub)
        s_ss.append(sup)
        return [s_ss]
    return []


def latex_to_omath_element(latex: str) -> OxmlElement:
    nodes = parse_latex(latex)
    om = OxmlElement("m:oMath")
    for child in _nodes_to_omml(nodes):
        om.append(child)
    return om


def append_inline_math(paragraph, latex: str) -> None:
    try:
        o_math = latex_to_omath_element(latex)
    except Exception:
        paragraph.add_run(f"${latex}$")
        return
    paragraph._element.append(o_math)


def append_display_math(paragraph, latex: str) -> None:
    try:
        o_math = latex_to_omath_element(latex)
    except Exception:
        paragraph.add_run(latex)
        return
    o_math_para = OxmlElement("m:oMathPara")
    o_math_para_pr = OxmlElement("m:oMathParaPr")
    jc = OxmlElement("m:jc")
    jc.set("{http://schemas.openxmlformats.org/officeDocument/2006/math}val", "center")
    o_math_para_pr.append(jc)
    o_math_para.append(o_math_para_pr)
    o_math_para.append(o_math)
    paragraph._element.append(o_math_para)


import re
import json
import sys

_CAPTION_LABEL = (
    r"(?:\{[\w\-]+\}|[\wА-ЯЁа-яёA-Za-z0-9]+(?:\.[\wА-ЯЁа-яёA-Za-z0-9]+)?)"
)
FIGURE_CAPTION_RE = re.compile(
    rf"^(Рисунок\s+{_CAPTION_LABEL})\s*[—–-]\s*(.+)$",
    re.IGNORECASE,
)
TABLE_CAPTION_RE = re.compile(
    rf"^(Таблица\s+{_CAPTION_LABEL})\s*[—–-]\s*(.+)$",
    re.IGNORECASE,
)
LISTING_CAPTION_RE = re.compile(
    rf"^(Листинг\s+{_CAPTION_LABEL})\s*[—–-]\s*(.*)$",
    re.IGNORECASE,
)


_CAPTION_DASH_RE = re.compile(r"[—–-]")


def _normalize_caption_dash(text: str, pattern: re.Pattern) -> str:
    raw = (text or "").strip()
    m = pattern.match(raw)
    if not m:
        return text
    tail = raw[m.end(1):]
    found = _CAPTION_DASH_RE.search(tail)
    dash = found.group(0) if found else "\u2013"
    return f"{m.group(1).strip()} {dash} {m.group(2).strip()}"


def _dedupe_redundant_captions(elements):
    out = []
    i = 0
    n = len(elements)
    while i < n:
        el = elements[i]
        if el["type"] != "image":
            out.append(el)
            i += 1
            continue
        out.append(el)
        alt = (el.get("alt") or "").strip()
        j = i + 1
        kept_caption = False
        while j < n:
            nxt = elements[j]
            if nxt["type"] == "figure_caption":
                if not kept_caption:
                    out.append(nxt)
                    kept_caption = True
                j += 1
                continue
            if nxt["type"] == "para":
                nxt_text = (nxt.get("text") or "").strip()
                if alt and nxt_text == alt:
                    j += 1
                    continue
            break
        i = j
    return out


def split_blocks(lines):
    block = []
    in_code = False
    for line in lines:
        if in_code:
            block.append(line)
            if line.startswith("```"):
                in_code = False
                yield block
                block = []
            continue
        if line.startswith("```"):
            if block:
                yield block
                block = []
            in_code = True
            block.append(line)
            continue
        if LISTING_INCLUDE_RE.match(line.strip()):
            if block:
                yield block
                block = []
            yield [line]
            continue
        if line.strip() == "":
            if block:
                yield block
                block = []
        else:
            block.append(line)
    if block:
        yield block


def is_table_block(block):
    if len(block) < 2:
        return False
    if not block[0].lstrip().startswith("|"):
        return False
    sep = block[1].strip()
    if not sep.startswith("|"):
        return False
    cells = [c.strip() for c in sep.strip("|").split("|")]
    for c in cells:
        if not re.match(r"^:?-+:?$", c):
            return False
    return True


def parse_table(block):
    rows = []
    aligns = []
    for i, line in enumerate(block):
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if i == 1:
            for c in cells:
                if c.startswith(":") and c.endswith(":"):
                    aligns.append("center")
                elif c.endswith(":"):
                    aligns.append("right")
                else:
                    aligns.append("left")
            continue
        rows.append(cells)
    header = rows[0] if rows else []
    body = rows[1:] if len(rows) > 1 else []
    return {"type": "table", "header": header, "aligns": aligns, "rows": body}


def parse_block(block):
    if is_display_math_block(block):
        latex, number = parse_display_math_block(block)
        elt: dict = {"type": "math_block", "latex": latex}
        if number:
            elt["number"] = number
        yield elt
        return
    if block and block[0].startswith("```"):
        first = block[0].strip()
        lang = first[3:].strip()
        body = block[1:]
        if body and body[-1].startswith("```"):
            body = body[:-1]
        yield {"type": "code", "lang": lang, "lines": body}
        return
    if len(block) == 1:
        include = parse_listing_include(block[0])
        if include is not None:
            yield include
            return
    if len(block) == 1 and re.match(r"^-{3,}$", block[0].strip()):
        yield {"type": "hrule"}
        return
    if is_table_block(block):
        yield parse_table(block)
        return
    m = re.match(r"^(#{1,3})\s+(.*)$", block[0])
    if m:
        level = len(m.group(1))
        text = m.group(2).strip()
        if len(block) > 1:
            text += " " + " ".join(l.strip() for l in block[1:])
        yield {"type": "heading", "level": level, "text": text}
        return
    first_line = block[0].rstrip()
    bullet_re = re.compile(r"^([•\-–—*])\s+(.*)$")
    number_re = re.compile(r"^(\d{1,3}[\)\.])\s+(.*)$")
    letter_re = re.compile(r"^([а-яa-zA-Z][\)])\s+(.*)$")

    def detect_marker(line):
        line = line.lstrip()
        m = bullet_re.match(line)
        if m:
            return ("bullet", m.group(1), m.group(2))
        m = number_re.match(line)
        if m:
            return ("number", m.group(1), m.group(2))
        m = letter_re.match(line)
        if m:
            return ("letter", m.group(1), m.group(2))
        return None

    items = []
    cur_item = None
    is_list = False
    indent_stops = []

    def level_for(indent):
        while indent_stops and indent < indent_stops[-1]:
            indent_stops.pop()
        if not indent_stops or indent > indent_stops[-1]:
            indent_stops.append(indent)
        return len(indent_stops) - 1

    for line in block:
        stripped = line.lstrip()
        det = detect_marker(line)
        if det:
            indent = len(line) - len(line.lstrip())
            if cur_item is not None:
                items.append(cur_item)
            cur_item = {
                "marker_type": det[0],
                "marker": det[1],
                "text": det[2],
                "level": level_for(indent),
            }
            is_list = True
        else:
            if cur_item is not None:
                cur_item["text"] += " " + stripped
            else:
                is_list = False
                break
    if cur_item is not None and is_list:
        items.append(cur_item)
    if is_list and items:
        for it in items:
            yield {
                "type": "list_item",
                "marker_type": it["marker_type"],
                "marker": it["marker"],
                "text": it["text"],
                "level": it["level"],
            }
        return

    m = re.match(r"^!\[([^\]]*)\]\(([^)]+)\)\s*$", first_line)
    if m and len(block) == 1:
        alt = m.group(1).strip()
        path = m.group(2).strip()
        yield {"type": "image", "alt": alt, "path": path}
        if FIGURE_CAPTION_RE.match(alt):
            yield {"type": "figure_caption", "text": _normalize_caption_dash(alt, FIGURE_CAPTION_RE)}
        return

    joined = " ".join(l.strip() for l in block)

    if FIGURE_CAPTION_RE.match(joined):
        yield {"type": "figure_caption", "text": _normalize_caption_dash(joined, FIGURE_CAPTION_RE)}
        return
    if TABLE_CAPTION_RE.match(joined):
        yield {"type": "table_caption", "text": _normalize_caption_dash(joined, TABLE_CAPTION_RE)}
        return
    if LISTING_CAPTION_RE.match(joined):
        yield {"type": "listing_caption", "text": _normalize_caption_dash(joined, LISTING_CAPTION_RE)}
        return

    yield {"type": "para", "text": joined}


def parse_md(path, listings_root=None):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    lines = text.split("\n")
    out = []
    current_file = os.path.basename(path)
    file_base = 0
    line_no = 0
    file_suppress: list[str] = []
    next_suppress: list[str] = []
    for block in split_blocks(lines):
        try:
            idx = lines.index(block[0], line_no)
            line_no = idx + len(block)
            start_line = idx + 1
        except (ValueError, IndexError):
            start_line = None
        if len(block) == 1:
            fm = FILE_MARKER_RE.match(block[0])
            if fm:
                current_file = fm.group(1).strip()
                file_base = start_line + 1 if start_line is not None else 0
                file_suppress = []
                next_suppress = []
                continue
        peeled = 0
        while peeled < len(block):
            directive = parse_suppress(block[peeled])
            if directive is not None:
                scope, pattern = directive
                (file_suppress if scope == "file" else next_suppress).append(pattern)
                where_line = (start_line or 1) + peeled
                suppress.register(
                    pattern, scope, f"{current_file}:{max(1, where_line - file_base)}"
                )
                peeled += 1
                continue
            if _HTML_COMMENT_RE.match(block[peeled].strip()):
                peeled += 1
                continue
            break
        if peeled:
            block = block[peeled:]
            if start_line is not None:
                start_line += peeled
            if not block:
                continue

        trailing: list[tuple[str, str, int]] = []
        dropped = 0
        while len(block) - dropped > 1:
            at = len(block) - 1 - dropped
            directive = parse_suppress(block[at])
            if directive is not None:
                trailing.append((directive[0], directive[1], at))
                dropped += 1
                continue
            if _HTML_COMMENT_RE.match(block[at].strip()):
                dropped += 1
                continue
            break
        if dropped:
            block = block[: len(block) - dropped]

        block_suppress = tuple(file_suppress) + tuple(next_suppress)
        next_suppress = []

        for scope, pattern, at in reversed(trailing):
            (file_suppress if scope == "file" else next_suppress).append(pattern)
            where_line = (start_line or 1) + at
            suppress.register(
                pattern, scope, f"{current_file}:{max(1, where_line - file_base)}"
            )

        for el in parse_block(block):
            if current_file:
                el["src_file"] = current_file
            if start_line is not None:
                el["src_line"] = max(1, start_line - file_base)
            if block_suppress:
                el["suppress"] = block_suppress
            out.append(el)
    out = _dedupe_redundant_captions(out)
    resolve_listing_includes(out, listings_root)
    return out


if __name__ == "__main__":
    elements = parse_md(sys.argv[1])
    print(f"Total elements: {len(elements)}")
    print("\nFirst 30:")
    for el in elements[:30]:
        s = json.dumps(el, ensure_ascii=False)
        if len(s) > 200:
            s = s[:200] + "..."
        print("  ", s)
    print("\nElement type counts:")
    from collections import Counter
    counts = Counter(el["type"] for el in elements)
    for t, n in sorted(counts.items()):
        print(f"  {t}: {n}")
