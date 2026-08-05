from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import ui

PHASE_WRITE = "writing document"
PHASE_TOC = "numbering contents"
PHASE_TABLES = "fitting tables"

_TABLE_ROWS_PER_PAGE = 28
_TOC_HEADINGS_PER_EXTRA_PASS = 25


@dataclass(frozen=True)
class BuildWorkEstimate:
    layout_passes: int
    toc_passes: int
    continuation_passes: int
    estimated_table_splits: int


def _table_row_counts(elements: list[dict[str, Any]]) -> list[int]:
    return [len(e.get("rows") or []) for e in elements if e.get("type") == "table"]


def _estimate_table_splits(row_counts: list[int]) -> int:
    splits = 0
    for rows in row_counts:
        if rows <= _TABLE_ROWS_PER_PAGE:
            continue
        pages = (rows + _TABLE_ROWS_PER_PAGE - 1) // _TABLE_ROWS_PER_PAGE
        splits += max(0, pages - 1)
    return splits


def _estimate_toc_passes(n_headings: int) -> int:
    if n_headings <= 0:
        return 1
    extra = max(0, (n_headings - 1) // _TOC_HEADINGS_PER_EXTRA_PASS)
    return 2 + extra


def estimate_build_work(
    elements: list[dict[str, Any]],
    *,
    include_toc: bool,
    do_continuation: bool,
    n_toc_headings: int | None = None,
) -> BuildWorkEstimate:
    if n_toc_headings is None:
        n_toc_headings = sum(1 for e in elements if e.get("type") == "heading")
    row_counts = _table_row_counts(elements)
    estimated_splits = _estimate_table_splits(row_counts) if do_continuation else 0

    toc_passes = _estimate_toc_passes(n_toc_headings) if include_toc else 1
    cont_passes = (1 + estimated_splits) if do_continuation else 1

    if not include_toc and not do_continuation:
        layout_passes = 1
    elif include_toc and do_continuation:
        layout_passes = max(toc_passes, cont_passes) + (
            1 if estimated_splits > 0 and n_toc_headings > 0 else 0
        )
    elif include_toc:
        layout_passes = toc_passes
    else:
        layout_passes = cont_passes

    return BuildWorkEstimate(
        layout_passes=max(1, layout_passes),
        toc_passes=toc_passes,
        continuation_passes=cont_passes,
        estimated_table_splits=estimated_splits,
    )


class BuildReporter:
    def __init__(
        self, *, enabled: bool = True, console: ui.Console | None = None
    ) -> None:
        self._enabled = enabled
        self._console = console or ui.console()
        self._step: ui.Step | None = None
        self._outputs: list[tuple[str, Path]] = []
        self._passes = 1

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def outputs(self) -> list[tuple[str, Path]]:
        return list(self._outputs)


    def _begin(self, name: str, detail: str = "") -> None:
        if not self._enabled:
            return
        self._step = self._console.step(name, detail)

    def _end(self, detail: str = "") -> None:
        if self._step is not None:
            self._step.finish(detail)
            self._step = None


    def read(self, detail: str = "parsing markdown") -> None:
        self._begin("markdown", detail)

    def read_done(self, detail: str) -> None:
        self._end(detail)

    def layout(self, total_passes: int, engine: str = "") -> None:
        self._passes = max(1, total_passes)
        self._begin("layout", "preparing")
        if self._step is not None:
            self._step.engine = ui.ENGINE_NAMES.get(engine, "")
            self._step.update(fraction=0.0)

    def layout_pass(
        self,
        pass_num: int,
        total_passes: int,
        phase: str,
        *,
        progress: float = 0.0,
        counter: str = "",
    ) -> None:
        if self._step is None:
            return
        self._passes = max(1, total_passes, pass_num)
        label = phase
        if self._passes > 1:
            dot = self._console.symbols.dot
            label = f"pass {pass_num}/{self._passes} {dot} {phase}"
        done = (pass_num - 1 + max(0.0, min(1.0, progress))) / self._passes
        self._step.update(label, fraction=min(0.99, done), counter=counter)

    def layout_done(self, passes: int, table_breaks: int = 0) -> None:
        facts = [ui.plural(passes, "pass", "passes")]
        if table_breaks:
            facts.append(ui.plural(table_breaks, "table break"))
        self._end(ui.join_facts(facts))

    def save(self) -> None:
        self._begin("document", "writing file")

    def save_done(self, path: str | Path) -> None:
        path = Path(path)
        self._outputs.append(("document", path))
        self._end(_path_detail(path))

    def pdf(self, engine: str) -> None:
        self._begin("pdf", f"exporting via {engine}")

    def pdf_done(self, path: str | Path) -> None:
        path = Path(path)
        self._outputs.append(("pdf", path))
        self._end(_path_detail(path))


    def fail(self, detail: str = "failed") -> None:
        if self._step is not None:
            self._step.fail(detail)
            self._step = None

    def close(self) -> None:
        self._end()


def _path_detail(path: Path) -> str:
    size = ui.file_size(path)
    shown = ui.fmt_path(path)
    return f"{shown}  {ui.fmt_size(size)}" if size is not None else shown


def create_build_reporter(*, enabled: bool = True) -> BuildReporter:
    return BuildReporter(enabled=enabled)
