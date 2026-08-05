from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from typing import Any, Iterator

from .logging_setup import get_logger

log = get_logger("word")

WD_ACTIVE_END_ADJUSTED_PAGE = 1
WD_PRINT_VIEW = 3
WD_STATISTIC_PAGES = 2


def _require_win32com():
    if sys.platform != "win32":
        raise RuntimeError(
            "pagination_engine=word: supported on Windows only "
            "(requires an installed Microsoft Word)."
        )
    try:
        import win32com.client

        return win32com.client
    except ImportError as e:
        raise RuntimeError(
            "pagination_engine=word: win32com module (pywin32) not found. "
            "Install it: pip install pywin32"
        ) from e


def _doc_stats(doc: Any) -> str:
    try:
        n_para = int(doc.Paragraphs.Count)
    except Exception:
        n_para = -1
    try:
        n_tbl = int(doc.Tables.Count)
    except Exception:
        n_tbl = -1
    return f"paragraphs={n_para}, tables={n_tbl}"


@contextmanager
def com_initialised(purpose: str) -> Iterator[None]:
    import pythoncom

    started = False
    try:
        pythoncom.CoInitialize()
        started = True
    except Exception as exc:
        log.debug("Word COM [%s]: CoInitialize() declined: %s", purpose, exc)
    try:
        yield
    finally:
        if started:
            pythoncom.CoUninitialize()


@contextmanager
def word_application(*, purpose: str) -> Iterator[Any]:
    win32com_client = _require_win32com()
    with com_initialised(purpose):
        log.debug("Word COM [%s]: DispatchEx(Application)", purpose)
        word = win32com_client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        log.debug(
            "Word COM [%s]: application ready (Visible=%s)", purpose, word.Visible
        )
        try:
            yield word
        finally:
            log.debug("Word COM [%s]: Quit()", purpose)
            try:
                word.Quit()
            except Exception as exc:
                log.debug("Word COM [%s]: Quit() raised %s", purpose, exc)


@contextmanager
def open_word_document(
    word: Any,
    docx_path: str | os.PathLike[str],
    *,
    purpose: str,
    read_only: bool = True,
    print_view: bool = True,
    repaginate: bool = False,
) -> Iterator[Any]:
    path = os.path.abspath(os.fspath(docx_path))
    log.debug("Word COM [%s]: Documents.Open(%s, ReadOnly=%s)", purpose, path, read_only)
    doc = word.Documents.Open(
        FileName=path,
        ReadOnly=read_only,
        ConfirmConversions=False,
        AddToRecentFiles=False,
    )
    log.debug("Word COM [%s]: document open (%s)", purpose, _doc_stats(doc))
    try:
        if print_view:
            doc.ActiveWindow.View.Type = WD_PRINT_VIEW
            log.debug("Word COM [%s]: view set to PrintLayout", purpose)
        if repaginate:
            try:
                doc.Repaginate()
                log.debug("Word COM [%s]: Repaginate() done", purpose)
            except Exception as exc:
                log.debug("Word COM [%s]: Repaginate() failed: %s", purpose, exc)
        yield doc
    finally:
        log.debug("Word COM [%s]: Close(SaveChanges=0)", purpose)
        doc.Close(SaveChanges=0)


@contextmanager
def word_document_session(
    docx_path: str | os.PathLike[str],
    *,
    purpose: str,
    read_only: bool = True,
    print_view: bool = True,
    repaginate: bool = False,
) -> Iterator[Any]:
    with word_application(purpose=purpose) as word:
        with open_word_document(
            word,
            docx_path,
            purpose=purpose,
            read_only=read_only,
            print_view=print_view,
            repaginate=repaginate,
        ) as doc:
            yield doc


class WordApplicationHost:
    def __init__(self, *, purpose: str) -> None:
        self._purpose = purpose
        self._app_ctx = word_application(purpose=purpose)
        self._word = self._app_ctx.__enter__()
        self._doc_ctx = None
        self._doc = None

    @property
    def word(self) -> Any:
        return self._word

    @property
    def doc(self) -> Any:
        return self._doc

    def open_document(
        self,
        docx_path: str | os.PathLike[str],
        *,
        read_only: bool = True,
        print_view: bool = True,
        repaginate: bool = False,
    ) -> Any:
        self.close_document()
        self._doc_ctx = open_word_document(
            self._word,
            docx_path,
            purpose=self._purpose,
            read_only=read_only,
            print_view=print_view,
            repaginate=repaginate,
        )
        self._doc = self._doc_ctx.__enter__()
        return self._doc

    def close_document(self) -> None:
        if self._doc_ctx is not None:
            self._doc_ctx.__exit__(None, None, None)
            self._doc_ctx = None
            self._doc = None

    def close(self) -> None:
        self.close_document()
        if self._app_ctx is not None:
            self._app_ctx.__exit__(None, None, None)
            self._app_ctx = None
            self._word = None


class WordHost:
    def __init__(
        self,
        docx_path: str | os.PathLike[str],
        *,
        purpose: str,
        read_only: bool = True,
        print_view: bool = True,
        repaginate: bool = False,
    ) -> None:
        self._host: WordApplicationHost | None = WordApplicationHost(purpose=purpose)
        self._host.open_document(
            docx_path,
            read_only=read_only,
            print_view=print_view,
            repaginate=repaginate,
        )

    @property
    def doc(self) -> Any:
        assert self._host is not None
        return self._host.doc

    @property
    def word(self) -> Any:
        assert self._host is not None
        return self._host.word

    def close(self) -> None:
        if self._host is not None:
            self._host.close()
            self._host = None


def row_printed_page(table: Any, data_row_index: int) -> int:
    word_row = int(data_row_index) + 2
    try:
        return int(table.Rows(word_row).Range.Information(WD_ACTIVE_END_ADJUSTED_PAGE))
    except Exception:
        return 1


def iter_content_tables(doc: Any, *, purpose: str) -> list[Any]:
    tables: list[Any] = []
    total = int(doc.Tables.Count)
    log.debug("Word COM [%s]: scanning %d table(s) for content tables", purpose, total)
    for idx in range(1, total + 1):
        tbl = doc.Tables(idx)
        try:
            is_content = bool(tbl.Rows(1).HeadingFormat)
        except Exception:
            is_content = False
        if is_content:
            try:
                n_rows = int(tbl.Rows.Count)
            except Exception:
                n_rows = -1
            log.debug(
                "Word COM [%s]: content table #%d (doc index %d, %d row(s))",
                purpose, len(tables), idx, n_rows,
            )
            tables.append(tbl)
        else:
            log.debug("Word COM [%s]: skip non-content table at index %d", purpose, idx)
    log.debug("Word COM [%s]: found %d content table fragment(s)", purpose, len(tables))
    return tables
