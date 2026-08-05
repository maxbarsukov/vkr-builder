import shutil

from .pagination import (
    detect_heading_pages,
    detect_table_row_pages,
    open_table_pagination_session,
    open_word_build_session,
    open_word_layout_session,
)
from .docx import (
    CITE_RE,
    STRUCTURAL_HEADINGS,
    _build_pass,
    _cite_numbers,
    _prescan_references,
    _safe_copy_output,
    build,
    collapse_appendix_toc_rows,
)
from .docx.state import (
    _DOC_METADATA,
    _REFERENCED_SOURCES,
)

__all__ = [
    "build",
    "_build_pass",
    "_safe_copy_output",
    "CITE_RE",
    "STRUCTURAL_HEADINGS",
    "collapse_appendix_toc_rows",
    "_DOC_METADATA",
    "_REFERENCED_SOURCES",
    "_cite_numbers",
    "_prescan_references",
    "detect_heading_pages",
    "detect_table_row_pages",
    "open_table_pagination_session",
    "open_word_layout_session",
    "open_word_build_session",
    "shutil",
]
