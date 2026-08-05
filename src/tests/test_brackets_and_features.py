import re

from vkr import docx_build
from vkr import md
from tests.docx_inspect import read_docx


def _build(tmp_path, text):
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    elements = md.parse_md(str(src))
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)
    return read_docx(out)


def test_unknown_numeric_bracket_stays_plain_text(tmp_path):
    view = _build(
        tmp_path,
        "# 1 Chapter\n\nYear [2024] is not a citation.\n\n"
        "# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ\n\n"
        "1. Only source.\n",
    )
    assert "2024" in view.text
    assert 'w:anchor="src_2024"' not in view.document_xml


def test_escaped_brackets_render_literally(tmp_path):
    view = _build(
        tmp_path,
        "# 1 Chapter\n\nUse \\[note\\] and \\{key\\} in prose.\n",
    )
    assert "[note]" in view.text
    assert "{key}" in view.text


def test_formula_text_reference_is_clickable(tmp_path):
    view = _build(
        tmp_path,
        "# 1 Chapter\n\n"
        r"\[ E = m c^2 \]" + "\n{speed}\n\n"
        "Formula (1) shows energy.\n",
    )
    assert "Formula (1)" in view.text
    assert re.search(r'w:hyperlink[^>]*w:anchor="[^"]*speed', view.document_xml)
