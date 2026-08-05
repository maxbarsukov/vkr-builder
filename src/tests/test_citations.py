from vkr import docx_build
from vkr import md
from tests.docx_inspect import read_docx

CITE_MD = """\
# 1 Test chapter

Single source [1]. Grouped sources [2; 3]. Range form [6-8].

# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ

1. Source one.
2. Source two.
3. Source three.
6. Source six.
7. Source seven.
8. Source eight.
"""


def test_citation_forms_render_and_link(tmp_path):
    src = tmp_path / "c.md"
    src.write_text(CITE_MD, encoding="utf-8")
    elements = md.parse_md(str(src))
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)

    text = read_docx(out).text

    assert "[1]" in text
    assert "[2; 3]" in text
    assert "[4\u20136]" in text, "числовой диапазон печатается средним тире"


def test_comma_form_is_not_a_citation(tmp_path):
    md_text = "# 1 T\n\nComma form [4, 5] stays as text.\n"
    src = tmp_path / "c.md"
    src.write_text(md_text, encoding="utf-8")
    elements = md.parse_md(str(src))
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)

    text = read_docx(out).text
    assert "[4, 5]" in text
    assert "[4; 5]" not in text


def test_prescan_expands_ranges():
    docx_build._prescan_references(
        [{"type": "para", "text": "see [6-8] and [2; 3]"}]
    )
    for n in ("2", "3", "6", "7", "8"):
        assert n in docx_build._REFERENCED_SOURCES


def test_cite_numbers_helper():
    assert docx_build._cite_numbers("1") == [1]
    assert docx_build._cite_numbers("2; 3") == [2, 3]
    assert docx_build._cite_numbers("6-8") == [6, 7, 8]
    assert docx_build._cite_numbers("5; 7-9") == [5, 7, 8, 9]
