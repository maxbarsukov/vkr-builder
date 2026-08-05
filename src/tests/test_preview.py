from docx import Document

from vkr import docx_build


def test_preview_builds_single_chapter_without_toc(tmp_path):
    chapter = tmp_path / "chapter.md"
    chapter.write_text("# 1 Preview chapter\n\nSample paragraph.\n", encoding="utf-8")
    out = tmp_path / "preview.docx"

    docx_build.build(
        str(chapter),
        str(out),
        include_toc=False,
        pagination_engine="word",
    )

    assert out.is_file()
    doc = Document(str(out))
    texts = [p.text for p in doc.paragraphs if p.text.strip()]
    assert any("Preview chapter" in t for t in texts)
    assert not any("СОДЕРЖАНИЕ" in t for t in texts)
