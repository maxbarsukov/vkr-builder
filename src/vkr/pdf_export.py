from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Literal

from .logging_setup import get_logger
from .pagination import resolve_libreoffice_path
from .pdf_metadata import apply_pdf_metadata
from .word_com import open_word_document, word_application

log = get_logger("pdf")

PdfEngine = Literal["word", "libreoffice"]

_ENGINES: frozenset[str] = frozenset({"word", "libreoffice"})


def normalize_pdf_engine(name: str) -> PdfEngine:
    from . import engines

    try:
        return engines.resolve(name)
    except ValueError as exc:
        raise ValueError(f"build.pdf_engine: {exc}") from None


def default_pdf_path(docx_path: str | Path) -> Path:
    return Path(docx_path).with_suffix(".pdf")


def export_pdf(
    docx_path: str | Path,
    pdf_path: str | Path | None = None,
    *,
    engine: str = "libreoffice",
    libreoffice_path: str | None = None,
    metadata: dict | None = None,
) -> Path:
    docx_path = Path(docx_path).resolve()
    if not docx_path.is_file():
        raise FileNotFoundError(f"DOCX not found: {docx_path}")
    out = Path(pdf_path).resolve() if pdf_path else default_pdf_path(docx_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    eng = normalize_pdf_engine(engine)
    if eng == "word":
        _export_pdf_word(docx_path, out)
    else:
        _export_pdf_libreoffice(docx_path, out, libreoffice_path)

    apply_pdf_metadata(out, metadata)
    return out


_WD_EXPORT_FORMAT_PDF = 17
_WD_EXPORT_CREATE_HEADING_BOOKMARKS = 1


def _export_pdf_word(docx_path: Path, pdf_path: Path) -> None:
    log.debug("PDF export (Word): %s -> %s", docx_path, pdf_path)
    with word_application(purpose="pdf-export") as word:
        with open_word_document(
            word, docx_path, purpose="pdf-export"
        ) as doc:
            log.debug(
                "Word COM [pdf-export]: ExportAsFixedFormat(%s)", pdf_path
            )
            doc.ExportAsFixedFormat(
                OutputFileName=str(pdf_path),
                ExportFormat=_WD_EXPORT_FORMAT_PDF,
                CreateBookmarks=_WD_EXPORT_CREATE_HEADING_BOOKMARKS,
                DocStructureTags=True,
            )
    if not pdf_path.is_file():
        raise RuntimeError(f"pdf_engine=word: PDF was not created: {pdf_path}")
    log.debug("PDF written: %s", pdf_path)


def _export_pdf_libreoffice(
    docx_path: Path, pdf_path: Path, libreoffice_path: str | None
) -> None:
    soffice = resolve_libreoffice_path(libreoffice_path)
    out_dir = pdf_path.parent
    produced = out_dir / (docx_path.stem + ".pdf")
    before = _fingerprint(produced)
    if before is not None and not os.access(produced, os.W_OK):
        raise RuntimeError(
            f"pdf_engine=libreoffice: the PDF already there cannot be written to: "
            f"{produced}"
        )

    last_err = ""
    for attempt in range(3):
        if attempt:
            time.sleep(3.0)
        result = _run_soffice_convert(soffice, docx_path, out_dir)
        last_err = (result.stderr or result.stdout or "").strip()
        if result.returncode != 0:
            continue
        if _fingerprint(produced) not in (None, before):
            break
    else:
        raise RuntimeError(
            f"pdf_engine=libreoffice: PDF was not written: {produced}"
            + _why_not_written(produced, before)
            + (f" ({last_err})" if last_err else "")
        )

    if produced != pdf_path:
        os.replace(produced, pdf_path)
    log.debug("PDF written: %s", pdf_path)


def _fingerprint(path: Path) -> tuple[int, int] | None:
    try:
        stat = path.stat()
    except OSError:
        return None
    return stat.st_mtime_ns, stat.st_size


def _why_not_written(produced: Path, before: tuple[int, int] | None) -> str:
    if before is None or not produced.is_file():
        return ""
    if not os.access(produced, os.W_OK):
        return " (the file already there cannot be written to)"
    return " (the file already there was left untouched)"


def _run_soffice_convert(soffice, docx_path: Path, out_dir: Path):
    profile_dir = tempfile.mkdtemp(prefix="vkr_lo_pdf_")
    try:
        user_install = Path(profile_dir).resolve().as_uri()
        cmd = [
            soffice,
            "--headless",
            "--norestore",
            f"-env:UserInstallation={user_install}",
            "--convert-to",
            "pdf",
            "--outdir",
            str(out_dir),
            str(docx_path),
        ]
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
            timeout=180,
        )
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)
