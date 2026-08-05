import re

from vkr import bibliography
from vkr import docx_build
from vkr import md
from tests.docx_inspect import read_docx

KEYED_MD = """\
# 1 Introduction

First mention is [{beta}], later we add [{alpha}].

Again both [{alpha}; {beta}] together.

# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ

- {alpha} Alpha source text.
- {beta} Beta source text.
"""


def _parse(tmp_path, text):
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    return md.parse_md(str(src))


def test_scan_orders_by_first_mention(tmp_path):
    elements = _parse(tmp_path, KEYED_MD)
    keynum, definitions = bibliography.scan(elements)
    assert keynum == {"beta": 1, "alpha": 2}
    assert definitions["alpha"] == "Alpha source text."
    assert definitions["beta"] == "Beta source text."


def test_rebuild_replaces_sources_in_order(tmp_path):
    elements = _parse(tmp_path, KEYED_MD)
    keynum, definitions = bibliography.scan(elements)
    rebuilt = bibliography.rebuild_elements(elements, keynum, definitions)
    sources = [e for e in rebuilt if e["type"] == "list_item"]
    assert [s["marker"] for s in sources] == ["1.", "2."]
    assert sources[0]["text"] == "Beta source text."
    assert sources[1]["text"] == "Alpha source text."


def test_inactive_without_keys(tmp_path):
    elements = _parse(tmp_path, "# 1 Intro\n\nPlain text [1] only.\n")
    keynum, definitions = bibliography.scan(elements)
    assert not bibliography.active(keynum, definitions)


def test_keyed_citations_render_as_linked_numbers(tmp_path):
    elements = _parse(tmp_path, KEYED_MD)
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)

    view = read_docx(out)
    text = view.text
    assert "1. Beta source text." in text
    assert "2. Alpha source text." in text
    assert text.index("1. Beta") < text.index("2. Alpha")

    anchors = set(re.findall(r'<w:hyperlink w:anchor="(src_\d+)"', view.document_xml))
    assert {"src_1", "src_2"} <= anchors
    bookmarks = set(re.findall(r'<w:bookmarkStart[^>]*w:name="(src_\d+)"', view.document_xml))
    assert {"src_1", "src_2"} <= bookmarks


NUMERIC_MD = """\
# 1 Introduction

Cited as [3], then [1; 2].

# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ

1. First source.
2. Second source.
3. Third source.
"""


def test_numeric_scan_orders_by_first_mention(tmp_path):
    elements = _parse(tmp_path, NUMERIC_MD)
    old_to_new, new_sources = bibliography.scan_numeric(elements)
    assert old_to_new == {3: 1, 1: 2, 2: 3}
    assert new_sources[1] == "Third source."
    assert new_sources[2] == "First source."


def test_numeric_rebuild_reorders_sources_and_citations(tmp_path):
    elements = _parse(tmp_path, NUMERIC_MD)
    old_to_new, new_sources = bibliography.scan_numeric(elements)
    rebuilt = bibliography.rebuild_numeric_elements(elements, old_to_new, new_sources)
    intro = next(e for e in rebuilt if e.get("text", "").startswith("Cited"))
    assert "[1]" in intro["text"]
    assert "[2; 3]" in intro["text"]
    sources = [e for e in rebuilt if e["type"] == "list_item"]
    assert sources[0]["text"] == "Third source."
    assert sources[1]["text"] == "First source."


def test_range_remapped_to_semicolons_when_not_consecutive():
    old_to_new = {2: 1, 4: 2, 1: 3, 3: 4}
    assert bibliography.remap_citation_token("[1-3]", old_to_new) == "[1; 3; 4]"


def test_range_keeps_hyphen_when_consecutive_after_remap():
    old_to_new = {6: 4, 7: 5, 8: 6}
    assert bibliography.remap_citation_token("[6-8]", old_to_new) == "[4-6]"


def test_range_expands_all_sources_not_just_endpoints():
    old_to_new = {3: 1, 1: 2, 2: 3}
    assert bibliography.remap_citation_token("[1-3]", old_to_new) == "[1-3]"
