import datetime as dt
import os
import re
import shutil
import tempfile
import time
from collections import Counter
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path

from docx.shared import Cm

from .. import bibliography, crossref, docx_style, gost_sections, md
from ..md import element_location, element_suppressions
from ..element_summary import (
    format_element_summary,
    format_element_summary_compact,
)
from ..docx_style import (
    apply_typography_from_mapping,
    configure_style_names,
    create_vkr_document,
    reset_style_names_to_defaults,
    reset_typography_to_defaults,
)
from ..logging_setup import get_logger, set_source_location
from . import state
from .bookmarks import _build_xref_bookmarks, _prescan_bookmarks, _prescan_references
from .document import (
    apply_document_metadata,
    normalise_package_timestamps,
    package_timestamp,
    link_footer_to_section,
    resolve_image_path,
    setup_section_and_footer,
    write_footer_part,
)
from . import state
from .elements import (
    add_caption,
    add_code_block,
    add_image,
    add_math_block,
    add_table,
)
from .headings import (
    _is_introduction_subsection,
    _section_key,
    add_body_paragraph,
    add_dictionary_paragraph,
    add_heading_1,
    add_heading_2,
    add_heading_3,
    add_introduction_block_title,
    add_source_entry,
    collect_toc_headings,
)
from .lists import NumberingManager, _marker_kind, add_list_item
from .ooxml import clear_body
from .runs import set_run_font
from .state import log
from .toc import add_toc_entries, add_toc_heading, collapse_appendix_toc_rows

log = get_logger("docx")

def _safe_copy_output(src, dst):
    try:
        from .. import docx_build
        docx_build.shutil.copy(src, dst)
        return dst
    except PermissionError:
        target = Path(dst)
        alt = target.with_name(f"{target.stem}-new{target.suffix}")
        from .. import docx_build
        docx_build.shutil.copy(src, alt)
        log.warning(
            "could not write %s (is it open in Word?); saved to %s instead",
            dst, alt,
            extra={"rule": "output-locked"},
        )
        return alt

def build(
    md_path,
    output_path,
    typography=None,
    styles=None,
    image_max_width_cm=14.0,
    assets_root=None,
    listings_root=None,
    pagination_engine: str = "word",
    libreoffice_path: str | None = None,
    metadata=None,
    sort_dictionary_lists: bool = False,
    *,
    include_toc: bool = True,
    progress=None,
    table_continuation=None,
    dashes=None,
):
    _set_document_metadata(metadata)
    configure_style_names(styles)
    apply_typography_from_mapping(typography)
    docx_style.configure_table_continuation(table_continuation)
    docx_style.configure_dashes(dashes)
    assets_path = Path(assets_root).resolve() if assets_root else None
    from ..progress import BuildReporter

    prog = progress if progress is not None else BuildReporter(enabled=False)
    try:
        crossref.reset_warning_state()
        from .. import bibliography as bib
        from ..progress import (
            PHASE_TABLES,
            PHASE_TOC,
            PHASE_WRITE,
            estimate_build_work,
        )

        bib.reset_warning_state()
        prog.read()

        parse_t0 = time.monotonic()
        elements = md.parse_md(md_path, listings_root)
        if sort_dictionary_lists:
            elements = gost_sections.sort_dictionary_sections(elements)
            log.debug("Sorted dictionary sections (abbreviations and terms).")
        counts = Counter(e["type"] for e in elements)
        summary = format_element_summary(counts)
        elapsed = time.monotonic() - parse_t0
        log.debug(
            "Parsed %d elements in %.1fs: %s",
            len(elements), elapsed, summary,
        )
        prog.read_done(
            format_element_summary_compact(counts) or f"{len(elements)} elements"
        )

        headings = collect_toc_headings(elements) if include_toc else []
        table_numbers = _compute_table_numbers(elements)
        has_tables = any(e.get("type") == "table" for e in elements)
        n_tables = sum(1 for e in elements if e.get("type") == "table")
        table_rows = sum(len(e["rows"]) for e in elements if e.get("type") == "table")
        if include_toc:
            log.info("Table of contents: %d headings to paginate.", len(headings))
        if has_tables:
            log.info(
                "Tables: %d with %d data rows in total.", n_tables, table_rows
            )
        do_continuation = docx_style.TABLE_CONTINUATION_ENABLED and has_tables
        if do_continuation:
            log.debug("Table continuation: enabled.")

        max_passes = 1
        if include_toc or do_continuation:
            max_passes = estimate_build_work(
                elements,
                include_toc=include_toc,
                do_continuation=do_continuation,
                n_toc_headings=len(headings),
            ).layout_passes
        prog.layout(max_passes, pagination_engine)

        table_splits: dict[int, tuple[int, ...]] = {}
        processed_fragments: set[tuple[int, int]] = set()
        continuation_done = not do_continuation
        page_map = None
        tmp_dir = tempfile.mkdtemp(prefix="vkr_build_")
        last_build_path = None

        pass_num = 0
        use_word_build = (
            pagination_engine == "word" and (include_toc or do_continuation)
        )
        from ..pagination import open_word_build_session

        word_build_cm = (
            open_word_build_session()
            if use_word_build
            else nullcontext()
        )
        def _phase_progress(phase: str, low: float, high: float, unit: str = ""):
            def report(done: int, total: int) -> None:
                share = (done / total) if total else 1.0
                prog.layout_pass(
                    pass_num, max_passes, phase,
                    progress=low + (high - low) * min(1.0, share),
                    counter=f"{done}/{total} {unit}" if unit and total else "",
                )

            return report

        with word_build_cm as word_build:
            while True:
                pass_num += 1
                max_passes = max(max_passes, pass_num)
                prog.layout_pass(pass_num, max_passes, PHASE_WRITE)
                tmp_path = os.path.join(tmp_dir, f"vkr_iter_{pass_num}.docx")
                log.debug(
                    "Layout pass %d: building %s (splits=%s, processed=%d fragment(s))",
                    pass_num, tmp_path, table_splits, len(processed_fragments),
                )
                toc_entries = None
                if include_toc and page_map is not None:
                    toc_entries = collapse_appendix_toc_rows(headings, page_map)
                log.debug(
                    "Pass %d: writing DOCX (%d continuation break(s) so far)...",
                    pass_num, sum(len(v) for v in table_splits.values()),
                )
                build_t0 = time.monotonic()
                _build_pass(
                    tmp_path,
                    elements,
                    toc_entries=toc_entries,
                    image_max_width_cm=image_max_width_cm,
                    assets_root=assets_path,
                    include_toc=include_toc,
                    table_splits=table_splits,
                    table_numbers=table_numbers,
                )
                log.debug(
                    "Pass %d: DOCX written in %.1fs -> %s",
                    pass_num, time.monotonic() - build_t0, tmp_path,
                )
                last_build_path = tmp_path

                changed = False
                need_word_layout = (
                    word_build is not None
                    and (
                        include_toc
                        or (do_continuation and not continuation_done)
                    )
                )

                if need_word_layout:
                    layout_t0 = time.monotonic()
                    prog.layout_pass(
                        pass_num, max_passes, PHASE_WRITE, progress=0.25
                    )
                    word_build.load_document(tmp_path)
                    if include_toc:
                        prog.layout_pass(
                            pass_num, max_passes, PHASE_TOC, progress=0.45
                        )
                        log.debug(
                            "Pass %d: measuring heading pages (bookmarks, "
                            "%d heading(s))...",
                            pass_num, len(headings),
                        )
                        toc_t0 = time.monotonic()
                        new_page_map = word_build.detect_heading_pages(
                            headings,
                            expected_printed_page_one=int(
                                docx_style.PAGE_NUMBERING_DISPLAY_START
                            ),
                            on_progress=_phase_progress(PHASE_TOC, 0.45, 0.7, "headings"),
                        )
                        log.debug(
                            "Pass %d: heading pagination finished in %.1fs.",
                            pass_num, time.monotonic() - toc_t0,
                        )
                        if new_page_map:
                            log.debug(
                                "Pass %d: detected pages for %d headings. "
                                "First heading at printed page %s.",
                                pass_num, len(new_page_map), new_page_map[0],
                            )
                        else:
                            log.debug(
                                "Pass %d: no headings for TOC pagination.",
                                pass_num,
                            )
                        if new_page_map != page_map:
                            changed = True
                        page_map = new_page_map

                    if do_continuation and not continuation_done:
                        prog.layout_pass(
                            pass_num, max_passes, PHASE_TABLES, progress=0.7
                        )
                        log.debug(
                            "Pass %d: table continuation (same Word session)...",
                            pass_num,
                        )
                        cont_t0 = time.monotonic()
                        try:
                            expected = len(
                                _enumerate_table_fragments(
                                    elements, table_splits
                                )
                            )
                            if word_build.fragment_count() != expected:
                                log.warning(
                                    "table continuation skipped: found %d table "
                                    "fragments, expected %d",
                                    word_build.fragment_count(), expected,
                                    extra={"rule": "table-continuation"},
                                )
                                continuation_done = True
                            else:
                                new_splits, split_made, processed_fragments = (
                                    _run_table_continuation_step(
                                        elements,
                                        table_splits,
                                        processed_fragments,
                                        word_build,
                                        _phase_progress(PHASE_TABLES, 0.7, 1.0, "tables"),
                                    )
                                )
                                if split_made:
                                    table_splits = new_splits
                                    changed = True
                                    n_cont = sum(
                                        len(v) for v in table_splits.values()
                                    )
                                    log.debug(
                                        "Pass %d: inserted continuation break; "
                                        "%d break(s) total.",
                                        pass_num, n_cont,
                                    )
                                else:
                                    continuation_done = True
                                    log.debug(
                                        "Pass %d: all table fragments fit on "
                                        "single pages (%d processed).",
                                        pass_num, len(processed_fragments),
                                    )
                        except Exception as exc:
                            log.warning(
                                "table continuation failed: %s",
                                exc,
                                extra={"rule": "table-continuation"},
                            )
                            continuation_done = True
                        else:
                            log.debug(
                                "Pass %d: table continuation finished in %.1fs.",
                                pass_num, time.monotonic() - cont_t0,
                            )

                    log.debug(
                        "Pass %d: Word layout pass finished in %.1fs.",
                        pass_num, time.monotonic() - layout_t0,
                    )
                else:
                    if include_toc:
                        from .. import docx_build
                        prog.layout_pass(
                            pass_num, max_passes, PHASE_TOC, progress=0.45
                        )
                        log.debug(
                            "Pass %d: measuring heading pages (%s, %d heading(s))...",
                            pass_num, pagination_engine, len(headings),
                        )
                        toc_t0 = time.monotonic()
                        new_page_map = docx_build.detect_heading_pages(
                            tmp_path,
                            headings,
                            on_progress=_phase_progress(PHASE_TOC, 0.45, 0.7, "headings"),
                            engine=pagination_engine,
                            expected_printed_page_one=int(
                                docx_style.PAGE_NUMBERING_DISPLAY_START
                            ),
                            libreoffice_path=libreoffice_path,
                            skip_paragraph_styles=docx_style.lo_pagination_skip_paragraph_styles(),
                        )
                        log.debug(
                            "Pass %d: heading pagination finished in %.1fs.",
                            pass_num, time.monotonic() - toc_t0,
                        )
                        if new_page_map:
                            log.debug(
                                "Pass %d: detected pages for %d headings. "
                                "First heading at printed page %s.",
                                pass_num, len(new_page_map), new_page_map[0],
                            )
                        else:
                            log.debug("Pass %d: no headings for TOC pagination.", pass_num)
                        if new_page_map != page_map:
                            changed = True
                        page_map = new_page_map

                    if do_continuation and not continuation_done:
                        from .. import docx_build
                        prog.layout_pass(
                            pass_num, max_passes, PHASE_TABLES, progress=0.7
                        )
                        log.debug(
                            "Pass %d: table continuation step (%s)...",
                            pass_num, pagination_engine,
                        )
                        cont_t0 = time.monotonic()
                        try:
                            with docx_build.open_table_pagination_session(
                                tmp_path,
                                engine=pagination_engine,
                                libreoffice_path=libreoffice_path,
                            ) as session:
                                expected = len(
                                    _enumerate_table_fragments(elements, table_splits)
                                )
                                if session.fragment_count() != expected:
                                    log.warning(
                                        "table continuation skipped: found %d table "
                                        "fragments, expected %d",
                                        session.fragment_count(), expected,
                                        extra={"rule": "table-continuation"},
                                    )
                                    continuation_done = True
                                else:
                                    new_splits, split_made, processed_fragments = (
                                        _run_table_continuation_step(
                                            elements,
                                            table_splits,
                                            processed_fragments,
                                            session,
                                            _phase_progress(PHASE_TABLES, 0.7, 1.0, "tables"),
                                        )
                                    )
                                    if split_made:
                                        table_splits = new_splits
                                        changed = True
                                        n_cont = sum(len(v) for v in table_splits.values())
                                        log.debug(
                                            "Pass %d: inserted continuation break; "
                                            "%d break(s) total.",
                                            pass_num, n_cont,
                                        )
                                    else:
                                        continuation_done = True
                                        log.debug(
                                            "Pass %d: all table fragments fit on "
                                            "single pages (%d processed).",
                                            pass_num, len(processed_fragments),
                                        )
                        except Exception as exc:
                            log.warning(
                                "table continuation failed: %s",
                                exc,
                                extra={"rule": "table-continuation"},
                            )
                            continuation_done = True
                        else:
                            log.debug(
                                "Pass %d: table continuation step finished in %.1fs.",
                                pass_num, time.monotonic() - cont_t0,
                            )

                if not include_toc and not do_continuation:
                    break
                if not do_continuation and include_toc and pass_num >= 6:
                    if changed:
                        log.warning(
                            "table of contents did not stabilise after 6 passes",
                            extra={"rule": "toc-unstable"},
                        )
                    break
                if not changed:
                    log.debug("Layout stable after pass %d; stopping.", pass_num)
                    break
        if pass_num > 1:
            log.debug("Layout converged in %d passes", pass_num)
        n_cont = sum(len(v) for v in table_splits.values())
        if n_cont:
            log.debug("%d table continuation break(s)", n_cont)
        prog.layout_done(pass_num, n_cont)
        if last_build_path is None:
            raise RuntimeError("build: failed to produce a temporary DOCX")
        prog.save()
        saved_path = _safe_copy_output(last_build_path, output_path)
        normalise_package_timestamps(
            saved_path, package_timestamp(state._DOC_METADATA)
        )
        log.debug("Written: %s", saved_path)
        prog.save_done(saved_path)
        return saved_path
    except Exception as exc:
        prog.fail(str(exc) or exc.__class__.__name__)
        raise
    finally:
        set_source_location()
        _set_document_metadata(None)
        reset_typography_to_defaults()
        reset_style_names_to_defaults()
        docx_style.reset_table_continuation_to_defaults()
        try:
            shutil.rmtree(tmp_dir, ignore_errors=True)
        except (OSError, NameError):
            pass

_MANUAL_TABLE_NUM_RE = re.compile(
    r"^Таблица\s+([0-9A-Za-zА-ЯЁа-яё]+(?:\.[0-9A-Za-zА-ЯЁа-яё]+)?)\s*[–—-]",
    re.IGNORECASE,
)


def _caption_number(text, key_map, key):
    if key:
        num = key_map.get(key)
        if num is not None:
            return num
    m = _MANUAL_TABLE_NUM_RE.match((text or "").strip())
    return m.group(1) if m else None


def _compute_table_numbers(elements) -> list[str | None]:
    xref = crossref.build_number_map(elements)
    table_map = xref.get(crossref.TABLE, {})
    numbers: list[str | None] = []
    last_text: str | None = None
    last_key: str | None = None
    for e in elements:
        et = e.get("type")
        if et == "table_caption":
            last_text = e.get("text", "")
            last_key = crossref.extract_key(last_text)
        elif et == "table":
            numbers.append(_caption_number(last_text, table_map, last_key))
            last_text = None
            last_key = None
    return numbers


@dataclass(frozen=True)
class _TableFragment:
    table_ord: int
    section: int
    row_start: int
    row_end: int
    docx_frag_idx: int


def _table_section_indices(elements) -> list[int]:
    sec = 0
    out: list[int] = []
    for e in elements:
        if e.get("type") == "heading" and e.get("level") == 1:
            sec += 1
        elif e.get("type") == "table":
            out.append(sec)
    return out


def _table_row_counts(elements) -> list[int]:
    return [len(e["rows"]) for e in elements if e.get("type") == "table"]


def _enumerate_table_fragments(
    elements,
    table_splits: dict[int, tuple[int, ...]],
) -> list[_TableFragment]:
    sections = _table_section_indices(elements)
    row_counts = _table_row_counts(elements)
    frags: list[_TableFragment] = []
    docx_idx = 0
    for t, n_rows in enumerate(row_counts):
        breaks = sorted(table_splits.get(t, ()))
        bounds = [0] + breaks + [n_rows]
        sec = sections[t] if t < len(sections) else 0
        for i in range(len(bounds) - 1):
            frags.append(
                _TableFragment(t, sec, bounds[i], bounds[i + 1], docx_idx)
            )
            docx_idx += 1
    return frags


def _first_row_on_next_page(get_page, n_rows: int) -> int | None:
    if n_rows <= 1:
        return None
    first = get_page(0)
    last = get_page(n_rows - 1)
    if last == first:
        return None
    log.debug(
        "Binary search for page break among %d rows (pages %d..%d)",
        n_rows, first, last,
    )
    lo, hi = 1, n_rows - 1
    while lo < hi:
        mid = (lo + hi) // 2
        mid_pg = get_page(mid)
        log.debug("Binary search: row %d -> page %d (lo=%d hi=%d)", mid, mid_pg, lo, hi)
        if mid_pg > first:
            hi = mid
        else:
            lo = mid + 1
    result = lo if get_page(lo) > first else None
    log.debug("Binary search result: split before local row %s", result)
    return result


def _run_table_continuation_step(
    elements,
    table_splits: dict[int, tuple[int, ...]],
    processed: set[tuple[int, int]],
    session,
    on_progress=None,
) -> tuple[dict[int, tuple[int, ...]], bool, set[tuple[int, int]]]:
    frags = _enumerate_table_fragments(elements, table_splits)
    new_splits = dict(table_splits)
    sections = sorted({f.section for f in frags})
    log.debug(
        "Table continuation step: %d fragment(s) in chapter(s) %s",
        len(frags), sections,
    )

    checked = 0
    for sec in sections:
        sec_frags = sorted(
            (f for f in frags if f.section == sec),
            key=lambda f: f.docx_frag_idx,
        )
        for frag in sec_frags:
            checked += 1
            if on_progress is not None:
                on_progress(checked, len(frags))
            key = (frag.table_ord, frag.row_start)
            if key in processed:
                log.debug(
                    "Skip processed fragment table #%d [%d:%d)",
                    frag.table_ord, frag.row_start, frag.row_end,
                )
                continue

            n = frag.row_end - frag.row_start
            if n <= 0:
                processed.add(key)
                continue

            if frag.docx_frag_idx >= session.fragment_count():
                log.warning(
                    "table continuation: no document fragment #%d for table %d",
                    frag.docx_frag_idx, frag.table_ord,
                    extra={"rule": "table-continuation"},
                )
                continue

            if n > session.fragment_row_count(frag.docx_frag_idx):
                log.warning(
                    "table continuation: row count mismatch on table #%d "
                    "fragment [%d:%d)",
                    frag.table_ord, frag.row_start, frag.row_end,
                    extra={"rule": "table-continuation"},
                )
                continue

            first_pg = session.row_page(frag.docx_frag_idx, 0)
            last_pg = session.row_page(frag.docx_frag_idx, n - 1)
            log.debug(
                "Check fragment table #%d [%d:%d) docx#%d: pages %d (first) .. %d (last)",
                frag.table_ord, frag.row_start, frag.row_end,
                frag.docx_frag_idx, first_pg, last_pg,
            )
            if first_pg == last_pg:
                processed.add(key)
                log.debug(
                    "Table continuation: chapter %d, table #%d rows [%d:%d) "
                    "fit on page %d.",
                    sec, frag.table_ord, frag.row_start, frag.row_end, first_pg,
                )
                continue

            split_local = _first_row_on_next_page(
                lambda r, idx=frag.docx_frag_idx: session.row_page(idx, r),
                n,
            )
            if split_local is None:
                log.warning(
                    "table continuation: no page break found in table "
                    "#%d fragment [%d:%d)",
                    frag.table_ord, frag.row_start, frag.row_end,
                    extra={"rule": "table-continuation"},
                )
                processed.add(key)
                continue

            brk = frag.row_start + split_local
            cur = tuple(sorted(new_splits.get(frag.table_ord, ())))
            new_splits[frag.table_ord] = tuple(sorted(cur + (brk,)))
            processed.add(key)
            log.debug(
                "Table continuation: chapter %d, table #%d, break before "
                "row %d (pages %d→%d).",
                sec, frag.table_ord, brk, first_pg, last_pg,
            )
            log.debug(
                "Table continuation: splits for table #%d -> %s",
                frag.table_ord, new_splits[frag.table_ord],
            )
            return new_splits, True, processed

    return new_splits, False, processed


def _compute_table_splits(
    elements,
    current_splits: dict[int, tuple[int, ...]],
    fragment_pages: list[list[int]],
) -> dict[int, tuple[int, ...]]:
    row_counts = [len(e["rows"]) for e in elements if e.get("type") == "table"]
    n_tables = len(row_counts)

    expected = sum(len(current_splits.get(t, ())) + 1 for t in range(n_tables))
    if len(fragment_pages) != expected:
        log.warning(
            "table continuation: found %d fragments, expected %d; "
            "keeping the current splits",
            len(fragment_pages), expected,
            extra={"rule": "table-continuation"},
        )
        return dict(current_splits)

    new_splits: dict[int, tuple[int, ...]] = {}
    fi = 0
    for t in range(n_tables):
        breaks = sorted(current_splits.get(t, ()))
        bounds = [0] + breaks + [row_counts[t]]
        n_frag = len(breaks) + 1
        row_pages: list[int] = []
        ok = True
        for f in range(n_frag):
            seg = fragment_pages[fi + f]
            if len(seg) != bounds[f + 1] - bounds[f]:
                ok = False
            row_pages.extend(int(x) for x in seg)
        fi += n_frag
        if not ok or len(row_pages) != row_counts[t]:
            log.warning(
                "table continuation: row count mismatch on table #%d; "
                "keeping the current splits", t,
                extra={"rule": "table-continuation"},
            )
            if breaks:
                new_splits[t] = tuple(breaks)
            continue
        nb = [i for i in range(1, len(row_pages)) if row_pages[i] > row_pages[i - 1]]
        if nb:
            new_splits[t] = tuple(nb)
    return new_splits


def _set_document_metadata(metadata) -> None:
    from .. import docx_build as db

    value = dict(metadata) if metadata else None
    state._DOC_METADATA = value
    db._DOC_METADATA = value


def _sync_facade_state() -> None:
    from .. import docx_build as db

    for name in ("_DOC_METADATA",):
        if name in db.__dict__:
            setattr(state, name, db.__dict__[name])


def _build_pass(
    output_path,
    elements,
    toc_entries,
    *,
    image_max_width_cm=14.0,
    assets_root=None,
    include_toc: bool = True,
    table_splits=None,
    table_numbers=None,
):
    _sync_facade_state()
    state._BOOKMARK_ID[0] = 100
    table_splits = table_splits or {}
    table_numbers = table_numbers or []
    elements, state._KNOWN_SOURCE_NUMS, state._CITE_KEY_NUM = (
        bibliography.prepare_elements(elements)
    )
    state._XREF = crossref.build_number_map(elements)
    _build_xref_bookmarks()
    _prescan_references(elements)
    _prescan_bookmarks(elements)

    doc = create_vkr_document()
    clear_body(doc)
    setup_section_and_footer(doc)
    footer_rId = write_footer_part(doc)
    link_footer_to_section(doc, footer_rId)

    num_mgr = NumberingManager(doc)

    if include_toc:
        add_toc_heading(doc)
        if toc_entries is None:
            p = doc.add_paragraph(style=docx_style.STYLE_BODY)
            p.paragraph_format.first_line_indent = Cm(0)
            run = p.add_run("[Оглавление будет построено на втором проходе.]")
            set_run_font(run, font_name=docx_style.FONT_FAMILY, size_pt=docx_style.BODY_FONT_PT,
                         bold=False, italic=True,
                         color_rgb=(0x80, 0x80, 0x80))
        else:
            add_toc_entries(doc, toc_entries)

    current_top = None

    tbl_ord = 0
    current_list_kind = None
    current_num_id = None

    def reset_list():
        nonlocal current_list_kind, current_num_id
        current_list_kind = None
        current_num_id = None

    i = 0
    while i < len(elements):
        e = elements[i]
        et = e["type"]
        set_source_location(element_location(e), element_suppressions(e))

        if et == "hrule":
            i += 1
            continue

        if et == "heading":
            reset_list()
            level = e["level"]
            text = e["text"].strip()
            if level == 1:
                add_heading_1(doc, text)
                current_top = text
            elif level == 2:
                if _is_introduction_subsection(current_top, level):
                    add_introduction_block_title(doc, text)
                else:
                    in_appendix = _section_key(current_top).startswith("ПРИЛОЖЕНИЕ")
                    add_heading_2(doc, text, centered=in_appendix)
            elif level == 3:
                add_heading_3(doc, text)
            i += 1
            continue

        if et == "para":
            reset_list()
            txt = e["text"]
            sk = _section_key(current_top)
            if gost_sections.is_dictionary_heading(sk):
                add_dictionary_paragraph(doc, txt)
            elif sk == "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ":
                add_source_entry(doc, txt)
            else:
                add_body_paragraph(doc, txt)
            i += 1
            continue

        if et == "list_item":
            if _section_key(current_top) == "СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ":
                reset_list()
                src_num = re.sub(r"\D", "", e["marker"])
                full_text = f"{src_num}. {e['text']}"
                add_source_entry(doc, full_text)
                i += 1
                continue

            reset_list()
            run = []
            j = i
            while j < len(elements) and elements[j]["type"] == "list_item":
                run.append(elements[j])
                j += 1

            max_level = max(it.get("level", 0) for it in run)
            level_kinds = [None] * (max_level + 1)
            for it in run:
                lv = it.get("level", 0)
                if level_kinds[lv] is None:
                    level_kinds[lv] = _marker_kind(it["marker_type"], it["marker"])
            level_kinds = [k or "bullet-dash" for k in level_kinds]

            num_id = num_mgr.add_list(level_kinds)
            for it in run:
                add_list_item(doc, it["marker_type"], it["marker"], it["text"],
                              num_id=num_id, level=it.get("level", 0))
            i = j
            continue

        if et == "image":
            reset_list()
            img_path = resolve_image_path(e["path"], assets_root)
            add_image(doc, img_path, max_width_cm=image_max_width_cm)
            i += 1
            continue

        if et == "figure_caption":
            reset_list()
            add_caption(doc, e["text"], "figure")
            i += 1
            continue

        if et == "table_caption":
            reset_list()
            add_caption(doc, e["text"], "table")
            i += 1
            continue

        if et == "listing_caption":
            reset_list()
            add_caption(doc, e["text"], "listing")
            i += 1
            continue

        if et == "table":
            reset_list()
            header = [crossref.resolve_references(c, state._XREF) for c in e["header"]]
            rows = [
                [crossref.resolve_references(c, state._XREF) for c in r]
                for r in e["rows"]
            ]
            split_after = table_splits.get(tbl_ord, ())
            number = (
                table_numbers[tbl_ord] if tbl_ord < len(table_numbers) else None
            )
            add_table(
                doc, header, e["aligns"], rows,
                split_after=split_after, table_number=number,
            )
            tbl_ord += 1
            i += 1
            continue

        if et == "code":
            reset_list()
            if e.get("include_error"):
                log.warning(
                    "listing @listing %s not inserted: %s",
                    e["include"], e["include_error"],
                    extra={"rule": "listing-file"},
                )
            add_code_block(doc, e["lines"], e.get("lang", ""))
            i += 1
            continue

        if et == "math_block":
            reset_list()
            number = crossref.resolve_formula_number(e.get("number"), state._XREF)
            fkey = crossref.extract_key(e.get("number") or "")
            bm = state._XREF_BOOKMARKS.get(("formula", fkey)) if fkey else None
            add_math_block(doc, e["latex"], number, bookmark=bm)
            i += 1
            continue

        log.warning(
            "unknown element type %r: %s", et, e, extra={"rule": "unknown-element"}
        )
        i += 1

    set_source_location()
    apply_document_metadata(doc, state._DOC_METADATA)
    doc.save(output_path)
