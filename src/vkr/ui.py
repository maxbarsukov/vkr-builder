from __future__ import annotations

import json
import os
import random
import re
import shutil
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence, TextIO


QUIET = 0
NORMAL = 1
VERBOSE = 2
DEBUG = 3


INDENT = "    "
NAME_WIDTH = 12
LABEL_WIDTH = 10
LOCATION_WIDTH = 15
METRIC_WIDTH = 30
METRIC_END = len(INDENT) + 2 + METRIC_WIDTH
MIN_WIDTH = 46
MAX_WIDTH = 78


PERCENT_COL = 6
PERCENT_WIDTH = 4
DETAIL_COL = len(INDENT) + 1 + 1 + NAME_WIDTH + 1

ENGINE_NAMES = {"word": "Word", "libreoffice": "LibreOffice"}
IDLE_PHRASES = (
    "folio by folio",
    "inking the plates",
    "chasing footnotes",
    "numbering pages",
    "counting margins",
    "thinking",
    "measuring",
    "laying it out",
    "turning pages",
    "asking the engine",
    "shuffling pages",
    "doing sums",
    "pondering",
    "herding tables",
    "bribing {engine}",
    "summoning {engine}",
    "wrangling pages",
    "ruminating",
    "brewing",
    "counting angels",
    "summoning Markina T.A.",
    "Markining T.A.",
)
IDLE_PHRASE_SECONDS = 2.5

COUNTER_WIDTH = max(
    17,
    max(
        len(phrase.format(engine=max(ENGINE_NAMES.values(), key=len)))
        for phrase in IDLE_PHRASES
    ),
)
MIN_BAR = 16

FINDING_CAP = 10

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")


_EMOJI_RANGES = (
    (0x1F300, 0x1FAFF),
    (0x1F000, 0x1F2FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0xFE0F, 0xFE0F),
)

_NARROW_DINGBATS = frozenset("✓✗✔✘✕✖☐☑☒★☆☰☱☲☳☴☵☶☷⚑⚐⌁⌂⌘⌥⎇➔➜")


def char_width(char: str) -> int:
    code = ord(char)
    if unicodedata.combining(char) or unicodedata.category(char) in ("Mn", "Me", "Cf"):
        return 0
    if unicodedata.east_asian_width(char) in ("W", "F"):
        return 2
    if char in _NARROW_DINGBATS:
        return 1
    if any(low <= code <= high for low, high in _EMOJI_RANGES):
        return 2
    return 1


def text_width(text: str) -> int:
    return sum(char_width(c) for c in _ANSI_RE.sub("", text))


@dataclass(frozen=True)
class Symbols:
    ok: str
    fail: str
    warn: str
    skip: str
    rule: str
    bar_full: str
    bar_empty: str
    arrow: str
    bullet: str
    dot: str
    spinner: tuple[str, ...]


UNICODE = Symbols(
    ok="✓",
    fail="✗",
    warn="▲",
    skip="─",
    rule="─",
    bar_full="━",
    bar_empty="─",
    arrow="→",
    bullet="•",
    dot="·",
    spinner=("⠋", "⠙", "⠹", "⠸", "⠼",
             "⠴", "⠦", "⠧", "⠇", "⠏"),
)

ASCII = Symbols(
    ok="+",
    fail="x",
    warn="!",
    skip="-",
    rule="-",
    bar_full="=",
    bar_empty="-",
    arrow="->",
    bullet="*",
    dot="-",
    spinner=("|", "/", "-", "\\"),
)


class Palette:
    _CODES = {
        "reset": "\x1b[0m",
        "bold": "\x1b[1m",
        "dim": "\x1b[90m",
        "title": "\x1b[1;36m",
        "name": "",
        "value": "",
        "ok": "\x1b[32m",
        "warn": "\x1b[33m",
        "fail": "\x1b[31m",
        "live": "\x1b[36m",
        "path": "\x1b[36m",
    }

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled

    def __call__(self, style: str, text: str) -> str:
        if not self.enabled or not text:
            return text
        code = self._CODES.get(style)
        return f"{code}{text}{self._CODES['reset']}" if code else text

    def name(self, text: str) -> str:
        return self("name", text)

    def dim(self, text: str) -> str:
        return self("dim", text)

    def bold(self, text: str) -> str:
        return self("bold", text)

    def ok(self, text: str) -> str:
        return self("ok", text)

    def warn(self, text: str) -> str:
        return self("warn", text)

    def fail(self, text: str) -> str:
        return self("fail", text)

    def path(self, text: str) -> str:
        return self("path", text)


def fmt_duration(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    if seconds < 10:
        return f"{seconds:.1f}s"
    if seconds < 60:
        return f"{seconds:.0f}s"
    minutes, rest = divmod(int(round(seconds)), 60)
    return f"{minutes}m{rest:02d}s"


def fmt_size(size: int | float) -> str:
    size = float(size)
    if size < 1024:
        return f"{int(size)} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def fmt_count(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def fmt_path(path: str | Path) -> str:
    p = Path(path)
    try:
        from .paths import project_root

        root = project_root()
    except Exception:
        return str(p)
    try:
        return str(p.resolve().relative_to(root.resolve())).replace(os.sep, "/")
    except (ValueError, OSError):
        return str(p)


def file_size(path: str | Path) -> int | None:
    try:
        return Path(path).stat().st_size
    except OSError:
        return None


def join_facts(parts: Iterable[str], sep: str = ", ") -> str:
    return sep.join(p for p in parts if p)


def plural(count: int, one: str, many: str | None = None) -> str:
    word = one if count == 1 else (many or one + "s")
    return f"{count} {word}"


def _clip(text: str, room: int) -> str:
    if room <= 0:
        return ""
    width = 0
    for i, char in enumerate(text):
        width += char_width(char)
        if width > room:
            return text[:i]
    return text


def shorten(text: str, room: int) -> str:
    if room <= 4 or text_width(text) <= room:
        return text
    if "/" in text or "\\" in text:
        tail = ""
        for char in reversed(text):
            if text_width(tail) + char_width(char) > room - 3:
                break
            tail = char + tail
        return "..." + tail
    return _clip(text, room - 3).rstrip() + "..."


@dataclass(frozen=True)
class Finding:
    severity: str
    message: str
    location: str = ""
    source: str = ""
    rule: str = ""
    suppressed: bool = False

    def key(self) -> tuple[str, str, str]:
        return (self.severity, self.location, self.message)

    def to_json(self) -> dict[str, Any]:
        data = {"severity": self.severity, "message": self.message}
        if self.location:
            data["location"] = self.location
        if self.rule:
            data["rule"] = self.rule
        if self.source:
            data["source"] = self.source
        if self.suppressed:
            data["suppressed"] = True
        return data


@dataclass
class Recorder:
    command: str = ""
    context: list[str] = field(default_factory=list)
    fields: dict[str, str] = field(default_factory=dict)
    steps: list[dict[str, Any]] = field(default_factory=list)
    findings: list[dict[str, Any]] = field(default_factory=list)
    metrics: dict[str, dict[str, str]] = field(default_factory=dict)
    checks: list[dict[str, Any]] = field(default_factory=list)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
    result: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        document = {
            "command": self.command,
            "context": self.context,
            "fields": self.fields,
            "steps": self.steps,
            "findings": self.findings,
            "artifacts": self.artifacts,
            "result": self.result,
        }
        if self.metrics:
            document["metrics"] = self.metrics
        if self.checks:
            document["checks"] = self.checks
        return document


class Console:
    def __init__(
        self, stream: TextIO | None = None, *, is_stdout: bool = False
    ) -> None:
        self._explicit_stream = stream
        self._is_stdout = is_stdout
        self.verbosity = NORMAL
        self._color: bool | None = None
        self._unicode: bool | None = None
        self._lock = threading.RLock()
        self._live: list[str] = []
        self._live_width = 0
        self._step: Step | None = None
        self._frame = 0
        self._ticker: threading.Thread | None = None
        self._stop = threading.Event()
        self.warnings = 0
        self.errors = 0
        self.suppressed = 0
        self._seen: dict[tuple[str, str, str], int] = {}
        self._shown = 0
        self._suppressed = 0
        self._section = ""
        self._aside: list[str] = []
        self._aside_column = 0
        self._last_blank = False
        self._t0 = time.monotonic()
        self.recorder: Recorder | None = None


    def configure(
        self,
        *,
        verbosity: int | None = None,
        color: bool | None = None,
        unicode: bool | None = None,
        stream: TextIO | None = None,
        record: bool = False,
    ) -> "Console":
        if verbosity is not None:
            self.verbosity = verbosity
        if stream is not None:
            self._explicit_stream = stream
        self._color = color
        self._unicode = unicode
        self.recorder = Recorder() if record else None
        self._last_blank = False
        self.begin_section()
        _widen(self.stream)
        return self

    def begin_section(self) -> None:
        self.warnings = 0
        self.errors = 0
        self.suppressed = 0
        self._seen = {}
        self._shown = 0
        self._suppressed = 0
        self._section = ""
        self._t0 = time.monotonic()

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    @property
    def reporting(self) -> bool:
        return self.verbosity > QUIET or self.recorder is not None

    @property
    def stream(self) -> TextIO:
        if self._explicit_stream is not None:
            return self._explicit_stream
        return sys.stdout if self._is_stdout else sys.stderr

    @property
    def interactive(self) -> bool:
        stream = self.stream
        try:
            if not stream.isatty() or os.environ.get("TERM") == "dumb":
                return False
        except Exception:
            return False
        if stream is sys.__stdout__ or stream is sys.__stderr__:
            return _vt_enabled(self._is_stdout)
        return True

    @property
    def palette(self) -> Palette:
        if self._color is not None:
            return Palette(self._color)
        if os.environ.get("NO_COLOR") is not None:
            return Palette(False)
        if os.environ.get("FORCE_COLOR"):
            return Palette(True)
        return Palette(self.interactive)

    @property
    def symbols(self) -> Symbols:
        if self._unicode is not None:
            return UNICODE if self._unicode else ASCII
        if os.environ.get("VKR_ASCII"):
            return ASCII
        encoding = (getattr(self.stream, "encoding", None) or "").lower()
        if not encoding:
            return ASCII
        try:
            UNICODE.ok.encode(encoding)
            UNICODE.spinner[0].encode(encoding)
            UNICODE.bar_full.encode(encoding)
        except (LookupError, UnicodeEncodeError):
            return ASCII
        return UNICODE

    @property
    def width(self) -> int:
        try:
            columns = shutil.get_terminal_size(fallback=(MAX_WIDTH, 24)).columns
        except Exception:
            columns = MAX_WIDTH
        return max(MIN_WIDTH, min(columns - 1, MAX_WIDTH))


    def _write_lines(self, lines: Sequence[str]) -> None:
        stream = self.stream
        with self._lock:
            lines = list(lines)
            while lines and lines[0] == "" and self._last_blank:
                lines.pop(0)
            if not lines:
                return
            self._erase_live()
            for line in lines:
                stream.write(line + "\n")
            self._last_blank = lines[-1] == ""
            self._paint_live()
            try:
                stream.flush()
            except Exception:
                pass

    def line(self, text: str = "") -> None:
        if self.verbosity <= QUIET:
            return
        self._write_lines([text])

    def line_always(self, text: str) -> None:
        self._write_lines([text])

    def blank(self) -> None:
        self.line("")


    def header(self, command: str, *context: str) -> None:
        if self.recorder is not None:
            self.recorder.command = command
            self.recorder.context = [c for c in context if c]
        if self.verbosity <= QUIET:
            return
        p, s = self.palette, self.symbols
        title = f"{program_name()} {command}"
        right = f" {s.dot} ".join(c for c in context if c)
        width = self.width
        used = 2 + text_width(title) + 1 + (text_width(right) + 2 if right else 0)
        fill = max(1, width - used)
        rule = s.rule * fill
        text = "  " + p("title", title) + " " + p.dim(rule)
        if right:
            text += "  " + p.dim(right)
        self._write_lines(["", text, ""])

    def footer_ok(
        self,
        message: str,
        *,
        artifacts: Sequence[tuple[str, str | Path]] = (),
        elapsed: float | None = None,
    ) -> None:
        self._footer(self.symbols.ok, "ok", "ok", message, artifacts, elapsed)

    def footer_warn(
        self,
        message: str,
        *,
        artifacts: Sequence[tuple[str, str | Path]] = (),
        elapsed: float | None = None,
    ) -> None:
        self._footer(self.symbols.warn, "warn", "warning", message, artifacts, elapsed)

    def _footer(
        self,
        glyph: str,
        style: str,
        status: str,
        message: str,
        artifacts: Sequence[tuple[str, str | Path]],
        elapsed: float | None,
    ) -> None:
        self._record_result(status, message, elapsed, artifacts)
        self._report_artifacts(artifacts)
        if self.verbosity <= QUIET:
            return
        rows = [(label, _artifact_detail(path)) for label, path in artifacts]
        p = self.palette
        tail = ""
        counts = self._issue_counts()
        if elapsed is not None and elapsed >= 0.5:
            tail = f" in {fmt_duration(elapsed)}"
        headline = f"{message}{tail}"
        if counts:
            headline = f"{headline} {self.symbols.dot} {counts}"
        lines = ["", "  " + p(style, glyph) + " " + p.bold(headline)]
        for label, value in rows:
            lines.append(
                "    " + p.dim(f"{label:<{LABEL_WIDTH}}") + " " + p.path(value)
            )
        lines.append("")
        self._write_lines(lines)

    def footer_fail(self, message: str, *, detail: str = "", hint: str = "") -> None:
        self._record_result("failed", message, None, (), detail=detail, hint=hint)
        p, s = self.palette, self.symbols
        lines = ["", "  " + p.fail(s.fail) + " " + p.bold(message)]
        if detail:
            for chunk in str(detail).splitlines():
                lines.append("    " + p("value", chunk))
        if hint:
            lines.append("")
            lines.append("    " + p.dim("try") + "  " + p("live", hint))
        lines.append("")
        self._write_lines(lines)

    def _issue_counts(self) -> str:
        parts = []
        if self.errors:
            parts.append(plural(self.errors, "error"))
        if self.warnings:
            parts.append(plural(self.warnings, "warning"))
        if self._suppressed:
            parts.append(f"{self._suppressed} not shown")
        if self.suppressed:
            parts.append(f"{self.suppressed} suppressed")
        return ", ".join(parts)

    def _record_result(
        self,
        status: str,
        message: str,
        elapsed: float | None,
        artifacts: Sequence[tuple[str, str | Path]],
        *,
        detail: str = "",
        hint: str = "",
    ) -> None:
        if self.recorder is None:
            return
        result: dict[str, Any] = {
            "status": status,
            "message": message,
            "warnings": self.warnings,
            "errors": self.errors,
            "suppressed": self.suppressed,
        }
        if elapsed is not None:
            result["seconds"] = round(elapsed, 3)
        if detail:
            result["detail"] = detail
        if hint:
            result["hint"] = hint
        self.recorder.result = result
        self.recorder.artifacts = [
            {"kind": label, "path": str(Path(path).resolve()), "bytes": file_size(path)}
            for label, path in artifacts
        ]

    def _report_artifacts(self, artifacts: Sequence[tuple[str, str | Path]]) -> None:
        if self.verbosity > QUIET or self.recorder is not None or not artifacts:
            return
        for _label, path in artifacts:
            out().line_always(str(Path(path).resolve()))


    def field(self, label: str, value: str, hint: str = "") -> None:
        if self.recorder is not None:
            self.recorder.fields[label] = value
        if self.verbosity <= QUIET:
            return
        p = self.palette
        text = INDENT + p.dim(_pad(label, LABEL_WIDTH)) + " " + p("value", value)
        if hint:
            text += "  " + p.dim(hint)
        self._write_lines([text])

    def start_aside(self, art, top: int = 0) -> None:
        self._aside = []
        if self.verbosity <= QUIET or not art:
            return
        widest = max(text_width(line) for line in art)
        room = self.width - METRIC_END
        if room < widest + 2:
            return
        self._aside_column = METRIC_END + (room - widest) // 2
        self._aside = [""] * max(0, top) + list(art)

    def _with_aside(self, text: str) -> str:
        if not self._aside:
            return text
        art = self._aside.pop(0)
        if not art:
            return text
        pad = self._aside_column - text_width(text)
        if pad < 1 or text_width(text) + pad + text_width(art) > self.width:
            self._aside = []
            return text
        return text + " " * pad + self.palette.dim(art)

    def section(self, title: str) -> None:
        self._section = title
        if self.verbosity <= QUIET:
            return
        self._write_lines(
            [
                self._with_aside(""),
                self._with_aside(INDENT + self.palette.dim(title)),
            ]
        )

    def metric(self, label: str, value: str, hint: str = "") -> None:
        if self.recorder is not None:
            self.recorder.metrics.setdefault(self._section or "metrics", {})[
                label
            ] = value
        if self.verbosity <= QUIET:
            return
        p = self.palette
        pad = max(1, METRIC_WIDTH - text_width(label) - text_width(value))
        text = INDENT + "  " + p("value", label) + " " * pad + p.bold(value)
        if hint:
            text += "  " + p.dim(hint)
        self._write_lines([self._with_aside(text)])

    def bullet(self, text: str, *, style: str = "value") -> None:
        if self.verbosity <= QUIET:
            return
        p, s = self.palette, self.symbols
        self._write_lines([INDENT + p.dim(s.bullet) + " " + p(style, text)])

    def result(
        self, ok: bool, label: str, detail: str = "", *, failure: str = "fail"
    ) -> None:
        if self.recorder is not None:
            self.recorder.checks.append(
                {"name": label, "ok": ok, "detail": detail}
            )
        if self.verbosity <= QUIET and ok:
            return
        p, s = self.palette, self.symbols
        if ok:
            glyph, style = s.ok, "ok"
        elif failure == "warn":
            glyph, style = s.warn, "warn"
        else:
            glyph, style = s.fail, "fail"
        text = INDENT + p(style, glyph) + " " + p.name(_pad(label, NAME_WIDTH))
        if detail:
            text += " " + p.dim(detail)
        self._write_lines([self._with_aside(text)])

    def note(self, text: str) -> None:
        if self.verbosity < VERBOSE:
            return
        p, s = self.palette, self.symbols
        self._write_lines([INDENT + p.dim(f"{s.dot} {text}")])

    def debug(self, text: str, source: str = "") -> None:
        if self.verbosity < DEBUG:
            return
        p = self.palette
        prefix = f"{source} " if source else ""
        self._write_lines([INDENT + p.dim(f"  {prefix}{text}")])

    def issue(
        self,
        severity: str,
        message: str,
        *,
        location: str = "",
        source: str = "",
    ) -> None:
        self.finding(
            Finding(
                severity="error" if severity == "error" else "warning",
                message=str(message),
                location=location,
                source=source,
            )
        )

    def finding(self, item: Finding) -> None:
        p, s = self.palette, self.symbols
        if item.suppressed:
            self.suppressed += 1
            if self.recorder is not None:
                self.recorder.findings.append(item.to_json())
            return
        is_error = item.severity == "error"
        if is_error:
            self.errors += 1
            glyph, style = s.fail, "fail"
        else:
            self.warnings += 1
            glyph, style = s.warn, "warn"

        if self.recorder is not None:
            self.recorder.findings.append(item.to_json())

        seen = self._seen.get(item.key(), 0)
        self._seen[item.key()] = seen + 1
        if seen:
            self._suppressed += 1
            return
        if self.verbosity <= QUIET and not is_error:
            return
        if self.verbosity < VERBOSE and not is_error and self._shown >= FINDING_CAP:
            self._suppressed += 1
            if self._suppressed == 1:
                self._write_lines([
                    INDENT + p.dim(
                        f"{s.dot} more findings follow; run with -v to see them all"
                    )
                ])
            return

        self._shown += 1
        lines = item.message.splitlines() or [""]
        head = INDENT + p(style, glyph) + " "
        if item.location:
            head += p.dim(_pad(item.location, LOCATION_WIDTH)) + " "
        out = [head + p("value", lines[0])]
        for extra in lines[1:]:
            out.append(INDENT + "  " + p.dim(extra))
        self._write_lines(out)


    def step(self, name: str, detail: str = "") -> "Step":
        with self._lock:
            if self._step is not None:
                self._step.finish()
            step = Step(self, name, detail)
            self._step = step
            if self.verbosity > QUIET and self.interactive:
                self._start_ticker()
                self._refresh()
            return step

    def _finish_step(
        self, step: "Step", glyph: str, style: str, detail: str, outcome: str
    ) -> None:
        with self._lock:
            if self._step is not step:
                return
            self._step = None
            self._stop_ticker()
            if self.recorder is not None:
                self.recorder.steps.append({
                    "name": step.name,
                    "outcome": outcome,
                    "detail": detail,
                    "seconds": round(step.elapsed, 3),
                })
            self._erase_live()
            if self.verbosity <= QUIET:
                return
            self._write_lines([
                self._compose_step(
                    glyph, style, step.name, detail, step.elapsed, done=True
                )
            ])

    def _refresh(self) -> None:
        with self._lock:
            if not self.interactive or self.verbosity <= QUIET:
                return
            self._erase_live()
            self._paint_live()
            try:
                self.stream.flush()
            except Exception:
                pass


    def _render_live(self) -> list[str]:
        step = self._step
        if step is None or not self.interactive or self.verbosity <= QUIET:
            return []
        s = self.symbols
        glyph = s.spinner[self._frame % len(s.spinner)]
        line = self._compose_step(
            glyph, "live", step.name, step.live_detail(), step.elapsed
        )
        if step.fraction is None:
            return [line]
        return [line, self._bar_line(step)]

    def _bar_line(self, step: "Step") -> str:
        p, s = self.palette, self.symbols
        fraction = max(0.0, min(1.0, step.fraction or 0.0))
        pct = f"{int(fraction * 100)}%"

        counter_width = COUNTER_WIDTH
        width = self.width - DETAIL_COL - counter_width - 2
        if width < MIN_BAR:
            counter_width = 0
            width = max(0, self.width - DETAIL_COL)

        filled = int(round(width * fraction))
        bar = p("live", s.bar_full * filled) + p.dim(s.bar_empty * (width - filled))
        text = step.counter or step.idle_phrase()
        counter = (
            "  " + p.dim(_pad_left(shorten(text, counter_width), counter_width))
            if counter_width
            else ""
        )
        head = _pad(" " * PERCENT_COL + _pad(pct, PERCENT_WIDTH), DETAIL_COL)
        return (head + bar + counter).rstrip()

    def _compose_step(
        self,
        glyph: str,
        style: str,
        name: str,
        detail: str,
        elapsed: float,
        *,
        done: bool = False,
    ) -> str:
        p = self.palette
        width = self.width
        time_text = fmt_duration(elapsed)
        name_field = _pad(name, NAME_WIDTH)
        head_width = len(INDENT) + char_width(glyph) + 1 + text_width(name_field) + 1
        room = width - head_width - len(time_text) - 2
        detail = shorten(detail or "", room)
        pad = max(1, width - head_width - text_width(detail) - len(time_text))
        name_style = "name" if done else "bold"
        return (
            INDENT
            + p(style, glyph)
            + " "
            + p(name_style, name_field)
            + " "
            + p("value", detail)
            + " " * pad
            + p.dim(time_text)
        )

    def _erase_live(self) -> None:
        if not self._live:
            return
        stream = self.stream
        width = max(1, self.width)
        rows = sum(max(1, -(-text_width(line) // width)) for line in self._live)
        stream.write("\r\x1b[2K")
        for _ in range(rows - 1):
            stream.write("\x1b[A\x1b[2K")
        self._live = []
        self._live_width = 0

    def _paint_live(self) -> None:
        lines = self._render_live()
        if not lines:
            return
        stream = self.stream
        stream.write("\n".join(lines))
        self._live = lines
        self._live_width = self.width


    def _start_ticker(self) -> None:
        if self._ticker is not None:
            return
        self._stop.clear()
        self._ticker = threading.Thread(target=self._tick, daemon=True)
        self._ticker.start()

    def _stop_ticker(self) -> None:
        self._stop.set()
        self._ticker = None

    def _tick(self) -> None:
        while not self._stop.wait(0.09):
            with self._lock:
                if self._step is None:
                    break
                self._frame += 1
                self._refresh()


    def close(self) -> None:
        with self._lock:
            if self._step is not None:
                self._step.finish()
            self._stop_ticker()
            self._erase_live()
            try:
                self.stream.flush()
            except Exception:
                pass


class Step:
    def __init__(self, console: Console, name: str, detail: str) -> None:
        self._console = console
        self.name = name
        self.detail = detail
        self.status = ""
        self.fraction: float | None = None
        self.counter = ""
        self.engine = ""
        self._rng = random.Random()
        self._bag: list[str] = []
        self._phrase = ""
        self._phrase_slot = -1
        self._t0 = time.monotonic()
        self._finished = False


    @property
    def elapsed(self) -> float:
        return time.monotonic() - self._t0

    def live_detail(self) -> str:
        return self.status or self.detail

    def idle_phrase(self) -> str:
        if not IDLE_PHRASES:
            return ""
        slot = int(self.elapsed / IDLE_PHRASE_SECONDS)
        if slot != self._phrase_slot:
            self._phrase_slot = slot
            if not self._bag:
                self._bag = list(IDLE_PHRASES)
                self._rng.shuffle(self._bag)
                if len(self._bag) > 1 and self._bag[-1] == self._phrase:
                    self._bag[0], self._bag[-1] = self._bag[-1], self._bag[0]
            self._phrase = self._bag.pop()
        return self._phrase.format(engine=self.engine or "the engine")

    def update(
        self,
        status: str | None = None,
        *,
        fraction: float | None = None,
        detail: str | None = None,
        counter: str | None = None,
    ) -> None:
        if status is not None:
            self.status = status
        if detail is not None:
            self.detail = detail
        if counter is not None:
            self.counter = counter
        if fraction is not None:
            share = max(0.0, min(1.0, fraction))
            self.fraction = share if self.fraction is None else max(self.fraction, share)
        self._console._refresh()


    def finish(self, detail: str | None = None) -> None:
        if self._finished:
            return
        self._finished = True
        s = self._console.symbols
        self._console._finish_step(
            self, s.ok, "ok", self.detail if detail is None else detail, "ok"
        )

    def warn(self, detail: str = "") -> None:
        if self._finished:
            return
        self._finished = True
        s = self._console.symbols
        self._console._finish_step(self, s.warn, "warn", detail, "warning")

    def skip(self, detail: str = "skipped") -> None:
        if self._finished:
            return
        self._finished = True
        s = self._console.symbols
        self._console._finish_step(self, s.skip, "dim", detail, "skipped")

    def fail(self, detail: str = "failed") -> None:
        if self._finished:
            return
        self._finished = True
        s = self._console.symbols
        self._console._finish_step(self, s.fail, "fail", detail, "failed")


    def __enter__(self) -> "Step":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        if exc_type is not None:
            self.fail(str(exc) or exc_type.__name__)
        else:
            self.finish()
        return False


_VT_STATE: dict[bool, bool] = {}


def _vt_enabled(is_stdout: bool) -> bool:
    if sys.platform != "win32":
        return True
    cached = _VT_STATE.get(is_stdout)
    if cached is not None:
        return cached
    ok = False
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11 if is_stdout else -12)
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            enable_vt = 0x0004
            ok = bool(
                mode.value & enable_vt
                or kernel32.SetConsoleMode(handle, mode.value | enable_vt)
            )
    except (AttributeError, OSError, ValueError):
        ok = False
    _VT_STATE[is_stdout] = ok
    return ok


def _widen(stream: TextIO) -> None:
    if stream is not sys.__stdout__ and stream is not sys.__stderr__:
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (OSError, ValueError, AttributeError):
        pass


_program = ""


def program_name() -> str:
    global _program
    if _program:
        return _program
    _program = os.environ.get("VKR_PROG", "").strip()
    if not _program:
        argv0 = Path(sys.argv[0] or "").name
        if argv0 == "main.py":
            _program = "python main.py"
        elif argv0.startswith("vkr-builder"):
            _program = argv0
        else:
            _program = (
                "vkr-builder.bat" if sys.platform == "win32" else "./vkr-builder.sh"
            )
    return _program


def set_program_name(name: str) -> None:
    global _program
    _program = name


def _pad(text: str, width: int) -> str:
    return text + " " * max(0, width - text_width(text))


def _pad_left(text: str, width: int) -> str:
    return " " * max(0, width - text_width(text)) + text


def _artifact_detail(path: str | Path) -> str:
    size = file_size(path)
    shown = fmt_path(path)
    return f"{shown}   {fmt_size(size)}" if size is not None else shown


_console = Console()
_stdout = Console(is_stdout=True)


def console() -> Console:
    return _console


def out() -> Console:
    return _stdout


def configure(
    *,
    verbosity: int = NORMAL,
    color: bool | None = None,
    unicode: bool | None = None,
    json_output: bool = False,
) -> Console:
    if json_output:
        verbosity = QUIET
    _stdout.configure(verbosity=verbosity, color=color, unicode=unicode)
    return _console.configure(
        verbosity=verbosity, color=color, unicode=unicode, record=json_output
    )


def close() -> None:
    _console.close()
    recorder = _console.recorder
    if recorder is not None:
        _stdout.line_always(
            json.dumps(recorder.to_json(), ensure_ascii=False, indent=2)
        )
        _console.recorder = None
