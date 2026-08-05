from __future__ import annotations

import glob
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Literal

from .logging_setup import get_logger
from .word_com import (
    WD_ACTIVE_END_ADJUSTED_PAGE,
    WD_STATISTIC_PAGES,
    WordApplicationHost,
    WordHost,
    iter_content_tables,
    row_printed_page,
    word_document_session,
)

log = get_logger("pagination")

ProgressCallback = Callable[[int, int], None] | None

PaginationEngine = Literal["word", "libreoffice"]

_ENGINES: frozenset[str] = frozenset({"word", "libreoffice"})

_LO_WINDOWS_CANDIDATES = (
    r"C:\Program Files\LibreOffice\program\soffice.exe",
    r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
)


def normalize_pagination_engine(name: str) -> PaginationEngine:
    from . import engines

    try:
        return engines.resolve(name)
    except ValueError as exc:
        raise ValueError(f"build.pagination_engine: {exc}") from None


def resolve_libreoffice_path(configured: str | None = None) -> str:
    if configured:
        p = Path(configured).expanduser()
        if p.is_file():
            return str(p.resolve())
        raise FileNotFoundError(
            f"build.libreoffice_path: file not found: {configured}"
        )

    for candidate in _LO_WINDOWS_CANDIDATES:
        if os.path.isfile(candidate):
            return candidate

    for name in ("soffice", "soffice.exe", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found

    raise FileNotFoundError(
        "LibreOffice not found. Install LibreOffice or set build.libreoffice_path "
        "in config.yaml."
    )


def _lo_program_dir(soffice_path: str) -> str:
    return str(Path(soffice_path).resolve().parent)


_UNO_PROBE_CACHE: dict[str, bool] = {}


def _can_import_uno(python_path: str) -> bool:
    if python_path in _UNO_PROBE_CACHE:
        return _UNO_PROBE_CACHE[python_path]
    try:
        probe = subprocess.run(
            [python_path, "-c", "import uno"],
            capture_output=True,
            timeout=30,
        )
        ok = probe.returncode == 0
    except (OSError, subprocess.SubprocessError):
        ok = False
    _UNO_PROBE_CACHE[python_path] = ok
    return ok


def _lo_python_path(soffice_path: str) -> str:
    program = Path(soffice_path).resolve().parent
    for name in ("python.exe", "python"):
        candidate = program / name
        if candidate.is_file():
            return str(candidate)

    seen: set[str] = set()
    candidates = [shutil.which("python3"), shutil.which("python")]
    candidates += sorted(glob.glob("/usr/bin/python3.*"), reverse=True)
    candidates.append("/usr/bin/python3")
    for candidate in candidates:
        if not candidate or candidate in seen or not os.path.isfile(candidate):
            continue
        seen.add(candidate)
        if _can_import_uno(candidate):
            return candidate

    raise FileNotFoundError(
        "pagination_engine=libreoffice: no Python with the UNO bridge found "
        f"(looked next to {soffice_path} and in PATH). On Debian or Ubuntu "
        "install python3-uno; on Windows and macOS use the LibreOffice "
        "installer, which bundles one."
    )


def uno_bridge_python(libreoffice_path: str | None = None) -> str:
    return _lo_python_path(resolve_libreoffice_path(libreoffice_path))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _start_libreoffice_listener(soffice_path: str, port: int) -> subprocess.Popen:
    cmd = [
        soffice_path,
        "--headless",
        "--invisible",
        "--norestore",
        f"--accept=socket,host=127.0.0.1,port={port};urp;StarOffice.ServiceManager",
    ]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return proc


def _wait_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            try:
                s.connect(("127.0.0.1", port))
                return True
            except OSError:
                time.sleep(0.3)
    return False


def _run_lo_worker(
    worker_filename: str,
    docx_path: str,
    *,
    libreoffice_path: str | None = None,
    env_extra: dict[str, str] | None = None,
    timeout: int = 120,
):
    soffice = resolve_libreoffice_path(libreoffice_path)
    lo_python = _lo_python_path(soffice)
    worker = Path(__file__).resolve().parent / worker_filename
    if not worker.is_file():
        raise FileNotFoundError(f"{worker_filename} not found: {worker}")

    port = _free_port()
    log.debug(
        "LibreOffice worker %s: starting listener on port %d for %s",
        worker_filename, port, os.path.abspath(docx_path),
    )
    proc = _start_libreoffice_listener(soffice, port)
    try:
        if proc.poll() is not None:
            raise RuntimeError("pagination_engine=libreoffice: soffice failed to start")
        if not _wait_port(port, timeout=30.0):
            raise RuntimeError(
                "pagination_engine=libreoffice: UNO listener did not come up"
            )
        log.debug("LibreOffice worker %s: listener ready", worker_filename)

        env = os.environ.copy()
        env["LIBREOFFICE_SOCKET"] = str(port)
        env["PYTHONIOENCODING"] = "utf-8"
        if env_extra:
            env.update(env_extra)

        log.debug(
            "LibreOffice worker %s: running %s", worker_filename, worker.name
        )
        result = subprocess.run(
            [lo_python, str(worker), os.path.abspath(docx_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=timeout,
            cwd=str(worker.parent),
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            err_safe = err.encode("ascii", errors="backslashreplace").decode("ascii")
            raise RuntimeError(
                f"pagination_engine=libreoffice: worker exited with code "
                f"{result.returncode}: {err_safe}"
            )

        import json

        payload = json.loads(result.stdout.strip() or "[]")
        log.debug(
            "LibreOffice worker %s: finished (exit %d, %d top-level item(s))",
            worker_filename, result.returncode, len(payload),
        )
        return payload
    finally:
        if proc.poll() is None:
            log.debug("LibreOffice worker %s: terminating listener", worker_filename)
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _clean_paragraph_text(s: str) -> str:
    s = (s or "").replace("\x07", "")
    return s.replace("\r", "").replace("\n", "").replace("\x0b", "").strip()


def _paragraph_text_safe(para) -> str:
    try:
        return _clean_paragraph_text(para.Range.Text)
    except Exception:
        pass
    try:
        rng = para.Range
        runs = rng.Runs
        n = int(runs.Count)
        parts: list[str] = []
        for i in range(1, n + 1):
            try:
                parts.append(runs(i).Text)
            except Exception:
                continue
        return _clean_paragraph_text("".join(parts))
    except Exception:
        return ""


def _norm_heading_text(s: str) -> str:
    s = re.sub(r"\t\d+$", "", s or "")
    return s.strip().upper()


def _match_heading_pages(
    collected: list[tuple[int, str, int]],
    headings: list[tuple],
    *,
    engine_label: str,
) -> list[int]:
    result: list[int] = []
    used: set[int] = set()
    for i, item in enumerate(headings):
        lev, md_text = item[0], item[1]
        md_norm = _norm_heading_text(md_text)
        pg: int | None = None
        match_j: int | None = None
        for j, (c_lev, c_text, c_pg) in enumerate(collected):
            if j in used:
                continue
            if c_lev == lev and _norm_heading_text(c_text) == md_norm:
                pg = c_pg
                match_j = j
                break
        if pg is None and i < len(collected):
            c_lev, c_text, c_pg = collected[i]
            if i not in used:
                pg = c_pg
                match_j = i
                if c_lev != lev or _norm_heading_text(c_text) != md_norm:
                    log.warning(
                        "heading #%d does not match the document: "
                        "markdown (%s, %r), %s (%s, %r)",
                        i, lev, md_text, engine_label, c_lev, c_text,
                        extra={"rule": "heading-mismatch"},
                    )
        if pg is None:
            tail = result[-1] if result else 1
            log.warning(
                "document has fewer headings than the markdown "
                "(%d < %d); heading %d falls back to page %s",
                len(collected), len(headings), i, tail,
                extra={"rule": "heading-mismatch"},
            )
            result.append(tail)
            continue
        if match_j is not None:
            used.add(match_j)
        result.append(pg)

    if len(collected) > len(used):
        extra = len(collected) - len(used)
        if extra > 0:
            log.warning(
                "document has more headings (%d) than the markdown (%d); "
                "ignoring %d extra",
                len(collected), len(headings), extra,
                extra={"rule": "heading-mismatch"},
            )
    return result


def _heading_raw_key(item: tuple) -> str:
    if len(item) >= 3:
        return str(item[2]).strip()
    return str(item[1]).strip()


def _verify_printed_page_one(doc, expected_printed_page_one: int | None) -> None:
    if expected_printed_page_one is None:
        return
    try:
        r0 = doc.Range(0, 0)
        top_printed = int(r0.Information(WD_ACTIVE_END_ADJUSTED_PAGE))
        if top_printed != int(expected_printed_page_one):
            log.warning(
                "printed page number at the document start is %d, but "
                "style.page.number_from=%d",
                top_printed, int(expected_printed_page_one),
                extra={"rule": "page-numbering"},
            )
        else:
            log.debug(
                "Heading pagination (Word): printed page one is %d",
                top_printed,
            )
    except Exception as ex:
        log.warning(
            "could not verify the printed numbering start (page 1): %s", ex,
            extra={"rule": "page-numbering"},
        )


def _collect_heading_pages_word_bookmarks(
    doc,
    headings: list[tuple],
    on_progress: ProgressCallback = None,
) -> list[int]:
    from .docx.bookmarks import heading_bookmark_name

    pages: list[int] = []
    log.debug(
        "Heading pagination (Word): resolving %d heading(s) via bookmarks...",
        len(headings),
    )
    t0 = time.monotonic()
    for item in headings:
        lev, display = item[0], item[1]
        raw = _heading_raw_key(item)
        bm_name = heading_bookmark_name(raw)
        try:
            pg = int(
                doc.Bookmarks(bm_name).Range.Information(
                    WD_ACTIVE_END_ADJUSTED_PAGE
                )
            )
            log.debug(
                "Heading pagination (Word): bookmark %s H%d %r -> page %d",
                bm_name, lev, display[:60], pg,
            )
            log.debug(
                "Heading pagination (Word): bookmark %s raw=%r",
                bm_name, raw[:80],
            )
        except Exception as exc:
            tail = pages[-1] if pages else 1
            log.warning(
                "no bookmark %r for heading %r (%s); using page %s",
                bm_name, display[:60], exc, tail,
                extra={"rule": "heading-mismatch"},
            )
            pg = tail
        pages.append(pg)
        if on_progress is not None:
            on_progress(len(pages), len(headings))
    log.debug(
        "Heading pagination (Word): bookmarks resolved in %.1fs.",
        time.monotonic() - t0,
    )
    return pages


def detect_heading_pages_word(
    docx_path: str,
    headings: list[tuple],
    *,
    expected_printed_page_one: int | None = None,
    on_progress: ProgressCallback = None,
) -> list[int]:
    log.debug("Heading pagination (Word): start for %s", os.path.abspath(docx_path))
    with word_document_session(
        docx_path, purpose="heading-pages", repaginate=True
    ) as doc:
        try:
            doc.ComputeStatistics(WD_STATISTIC_PAGES)
            log.debug("Heading pagination (Word): page count statistics computed")
        except Exception as exc:
            log.debug(
                "Heading pagination (Word): ComputeStatistics failed: %s", exc
            )
        _verify_printed_page_one(doc, expected_printed_page_one)
        return _collect_heading_pages_word_bookmarks(doc, headings, on_progress)


def detect_heading_pages_libreoffice(
    docx_path: str,
    headings: list[tuple],
    *,
    libreoffice_path: str | None = None,
    expected_printed_page_one: int | None = None,
    skip_paragraph_styles: frozenset[str] | set[str] | None = None,
) -> list[int]:
    soffice = resolve_libreoffice_path(libreoffice_path)
    lo_python = _lo_python_path(soffice)
    worker = Path(__file__).resolve().parent / "pagination_lo_worker.py"
    if not worker.is_file():
        raise FileNotFoundError(f"pagination_lo_worker.py not found: {worker}")

    port = _free_port()
    proc = _start_libreoffice_listener(soffice, port)
    collected: list[tuple[int, str, int]] = []
    try:
        if proc.poll() is not None:
            raise RuntimeError(
                "pagination_engine=libreoffice: soffice failed to start"
            )
        if not _wait_port(port, timeout=30.0):
            raise RuntimeError(
                "pagination_engine=libreoffice: UNO listener did not come up"
            )

        env = os.environ.copy()
        env["LIBREOFFICE_SOCKET"] = str(port)
        env["PYTHONIOENCODING"] = "utf-8"
        if expected_printed_page_one is not None:
            env["VKR_EXPECTED_PAGE_ONE"] = str(int(expected_printed_page_one))
        if skip_paragraph_styles:
            import json

            env["VKR_SKIP_PARAGRAPH_STYLES"] = json.dumps(
                sorted(skip_paragraph_styles), ensure_ascii=True
            )

        result = subprocess.run(
            [lo_python, str(worker), os.path.abspath(docx_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=120,
            cwd=str(worker.parent),
        )
        if result.returncode != 0:
            err = (result.stderr or result.stdout or "").strip()
            err_safe = err.encode("ascii", errors="backslashreplace").decode("ascii")
            raise RuntimeError(
                f"pagination_engine=libreoffice: worker exited with code "
                f"{result.returncode}: {err_safe}"
            )

        import json

        raw = json.loads(result.stdout.strip() or "[]")
        for item in raw:
            collected.append(
                (int(item["level"]), str(item["text"]), int(item["page"]))
            )
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    return _match_heading_pages(collected, headings, engine_label="LibreOffice")


class TablePaginationSession:
    def fragment_count(self) -> int:
        raise NotImplementedError

    def fragment_row_count(self, fragment_index: int) -> int:
        raise NotImplementedError

    def row_page(self, fragment_index: int, data_row_index: int) -> int:
        raise NotImplementedError

    def close(self) -> None:
        return None

    def __enter__(self) -> TablePaginationSession:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class _WordTablePaginationSession(TablePaginationSession):
    def __init__(self, docx_path: str) -> None:
        self._purpose = "table-pagination"
        log.debug("Table pagination session (Word): opening %s", docx_path)
        self._host = WordHost(
            docx_path, purpose=self._purpose, repaginate=True
        )
        self._tables = iter_content_tables(self._host.doc, purpose=self._purpose)

    def fragment_count(self) -> int:
        return len(self._tables)

    def fragment_row_count(self, fragment_index: int) -> int:
        tbl = self._tables[fragment_index]
        return max(0, int(tbl.Rows.Count) - 1)

    def row_page(self, fragment_index: int, data_row_index: int) -> int:
        tbl = self._tables[fragment_index]
        pg = row_printed_page(tbl, data_row_index)
        log.debug(
            "Word COM [%s]: fragment %d row %d -> page %d",
            self._purpose, fragment_index, data_row_index, pg,
        )
        return pg

    def close(self) -> None:
        host = getattr(self, "_host", None)
        self._host = None
        self._tables = []
        if host is not None:
            log.debug("Table pagination session (Word): closing")
            host.close()


class WordBuildSession(TablePaginationSession):
    def __init__(self, docx_path: str | os.PathLike[str] | None = None) -> None:
        self._purpose = "build"
        self._app = WordApplicationHost(purpose=self._purpose)
        self._tables: list = []
        self._doc_path: str | None = None
        log.debug("Word build session: application started.")
        if docx_path is not None:
            self.load_document(docx_path)

    def load_document(self, docx_path: str | os.PathLike[str]) -> None:
        path = os.path.abspath(os.fspath(docx_path))
        log.debug("Word build session: loading %s", path)
        t0 = time.monotonic()
        doc = self._app.open_document(path, repaginate=True)
        try:
            doc.ComputeStatistics(WD_STATISTIC_PAGES)
        except Exception as exc:
            log.debug("Word build session: ComputeStatistics failed: %s", exc)
        self._tables = iter_content_tables(doc, purpose=self._purpose)
        self._doc_path = path
        log.debug(
            "Word build session: document ready in %.1fs (%d table fragment(s)).",
            time.monotonic() - t0, len(self._tables),
        )

    def detect_heading_pages(
        self,
        headings: list[tuple],
        *,
        expected_printed_page_one: int | None = None,
        on_progress: ProgressCallback = None,
    ) -> list[int]:
        doc = self._app.doc
        if doc is None:
            raise RuntimeError("Word build session: no document loaded")
        _verify_printed_page_one(doc, expected_printed_page_one)
        return _collect_heading_pages_word_bookmarks(doc, headings, on_progress)

    def fragment_count(self) -> int:
        return len(self._tables)

    def fragment_row_count(self, fragment_index: int) -> int:
        tbl = self._tables[fragment_index]
        return max(0, int(tbl.Rows.Count) - 1)

    def row_page(self, fragment_index: int, data_row_index: int) -> int:
        tbl = self._tables[fragment_index]
        pg = row_printed_page(tbl, data_row_index)
        log.debug(
            "Word COM [%s]: fragment %d row %d -> page %d",
            self._purpose, fragment_index, data_row_index, pg,
        )
        return pg

    def close(self) -> None:
        app = getattr(self, "_app", None)
        self._app = None
        self._tables = []
        self._doc_path = None
        if app is not None:
            log.debug("Word build session: shutting down.")
            app.close()


WordLayoutSession = WordBuildSession


def open_word_build_session() -> WordBuildSession:
    return WordBuildSession()


def open_word_layout_session(docx_path: str) -> WordBuildSession:
    return WordBuildSession(docx_path)


class _LibreOfficeTablePaginationSession(TablePaginationSession):
    def __init__(self, pages: list[list[int]]) -> None:
        self._pages = pages

    @classmethod
    def from_docx(
        cls,
        docx_path: str,
        *,
        libreoffice_path: str | None = None,
    ) -> _LibreOfficeTablePaginationSession:
        log.debug(
            "Table pagination session (LibreOffice): scanning %s",
            os.path.abspath(docx_path),
        )
        pages = detect_table_row_pages_libreoffice(
            docx_path, libreoffice_path=libreoffice_path
        )
        log.debug(
            "Table pagination session (LibreOffice): %d fragment(s) cached",
            len(pages),
        )
        return cls(pages)

    def fragment_count(self) -> int:
        return len(self._pages)

    def fragment_row_count(self, fragment_index: int) -> int:
        return len(self._pages[fragment_index])

    def row_page(self, fragment_index: int, data_row_index: int) -> int:
        pg = int(self._pages[fragment_index][data_row_index])
        log.debug(
            "LibreOffice [table-pagination]: fragment %d row %d -> page %d (cached)",
            fragment_index, data_row_index, pg,
        )
        return pg


def open_table_pagination_session(
    docx_path: str,
    *,
    engine: str = "word",
    libreoffice_path: str | None = None,
) -> TablePaginationSession:
    eng = normalize_pagination_engine(engine)
    log.debug(
        "open_table_pagination_session: engine=%s path=%s",
        eng, os.path.abspath(docx_path),
    )
    if eng == "word":
        return _WordTablePaginationSession(docx_path)
    return _LibreOfficeTablePaginationSession.from_docx(
        docx_path, libreoffice_path=libreoffice_path
    )


def detect_table_row_pages_word(docx_path: str) -> list[list[int]]:
    out: list[list[int]] = []
    log.debug("Table row scan (Word): start for %s", os.path.abspath(docx_path))
    with word_document_session(
        docx_path, purpose="table-row-scan", repaginate=True
    ) as doc:
        for tbl in iter_content_tables(doc, purpose="table-row-scan"):
            try:
                n_rows = int(tbl.Rows.Count)
            except Exception:
                continue
            pages: list[int] = []
            for r in range(2, n_rows + 1):
                try:
                    pg = int(
                        tbl.Rows(r).Range.Information(WD_ACTIVE_END_ADJUSTED_PAGE)
                    )
                except Exception:
                    pg = pages[-1] if pages else 1
                pages.append(pg)
                log.debug(
                    "Table row scan (Word): fragment %d data row %d -> page %d",
                    len(out), len(pages) - 1, pg,
                )
            out.append(pages)
    log.debug("Table row scan (Word): %d fragment(s)", len(out))
    return out


def detect_table_row_pages_libreoffice(
    docx_path: str,
    *,
    libreoffice_path: str | None = None,
) -> list[list[int]]:
    raw = _run_lo_worker(
        "pagination_lo_tables_worker.py",
        docx_path,
        libreoffice_path=libreoffice_path,
    )
    out: list[list[int]] = []
    for frag in raw:
        out.append([int(x) for x in frag])
    return out


def detect_table_row_pages(
    docx_path: str,
    *,
    engine: str = "word",
    libreoffice_path: str | None = None,
) -> list[list[int]]:
    eng = normalize_pagination_engine(engine)
    if eng == "word":
        return detect_table_row_pages_word(docx_path)
    return detect_table_row_pages_libreoffice(
        docx_path, libreoffice_path=libreoffice_path
    )


def detect_heading_pages(
    docx_path: str,
    headings: list[tuple],
    *,
    engine: str = "word",
    expected_printed_page_one: int | None = None,
    libreoffice_path: str | None = None,
    skip_paragraph_styles: frozenset[str] | set[str] | None = None,
    on_progress: ProgressCallback = None,
) -> list[int]:
    eng = normalize_pagination_engine(engine)
    if eng == "word":
        return detect_heading_pages_word(
            docx_path,
            headings,
            expected_printed_page_one=expected_printed_page_one,
            on_progress=on_progress,
        )
    return detect_heading_pages_libreoffice(
        docx_path,
        headings,
        libreoffice_path=libreoffice_path,
        expected_printed_page_one=expected_printed_page_one,
        skip_paragraph_styles=skip_paragraph_styles,
    )
