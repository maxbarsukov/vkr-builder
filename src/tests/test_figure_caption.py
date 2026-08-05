from docx.enum.text import WD_ALIGN_PARAGRAPH

from vkr import docx_build
from vkr import md

FIGURE_MD = """\
# 1 Test

Some text before the figure.

![Test figure](assets/missing.png)

Рисунок 1 – Test figure caption
"""


def test_figure_caption_is_centered(tmp_path):
    src = tmp_path / "fig.md"
    src.write_text(FIGURE_MD, encoding="utf-8")
    elements = md.parse_md(str(src))
    out = tmp_path / "out.docx"
    docx_build._build_pass(str(out), elements, None, assets_root=None)

    from docx import Document

    doc = Document(str(out))
    caption = next(
        p for p in doc.paragraphs if "Test figure caption" in p.text
    )
    assert caption.alignment == WD_ALIGN_PARAGRAPH.CENTER
