from vkr import docx_build
from vkr import md
from tests.docx_inspect import read_docx

XREF_MD = """\
# 1 Test chapter

The architecture is shown in figure [рис:arch].

![Architecture](assets/missing1.png)

Рисунок {arch} - Architecture overview

The data model is shown in figure [рис:er].

![ER model](assets/missing2.png)

Рисунок {er} - ER model

Reading speed is given by formula [форм:speed]:

\\[
v = a + b
\\]
{speed}
"""


def test_keyed_captions_and_refs_resolve(tmp_path):
    src = tmp_path / "x.md"
    src.write_text(XREF_MD, encoding="utf-8")
    elements = md.parse_md(str(src))
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)

    view = read_docx(out)
    text = view.text

    assert "Рисунок 1 – Architecture overview" in text
    assert "Рисунок 2 – ER model" in text
    assert "shown in figure 1" in text
    assert "shown in figure 2" in text
    assert "formula (1)" in text
    assert "(1)" in text
    assert "[рис:" not in text
    assert "{arch}" not in text
    assert "{speed}" not in text


def test_references_are_clickable_hyperlinks(tmp_path):
    import re

    src = tmp_path / "x.md"
    src.write_text(XREF_MD, encoding="utf-8")
    elements = md.parse_md(str(src))
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)

    xml = read_docx(out).document_xml
    anchors = set(re.findall(r'<w:hyperlink w:anchor="([^"]+)"', xml))
    bookmarks = set(re.findall(r'<w:bookmarkStart[^>]*w:name="([^"]+)"', xml))

    xref_anchors = {a for a in anchors if a.startswith("_xr")}
    assert xref_anchors, "expected cross-reference hyperlinks"
    assert xref_anchors <= bookmarks
    assert any("formula" in a for a in xref_anchors)
