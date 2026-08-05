from vkr import docx_build, diagnostics, md


def test_diagnose_finds_consecutive_headings(tmp_path):
    src = tmp_path / "bad.md"
    src.write_text(
        "# 1 Chapter\n\n## Section A\n\n## Section B\n\nBody under B.\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.docx"
    elements = md.parse_md(str(src))
    docx_build._build_pass(str(out), elements, None, include_toc=False)

    issues = diagnostics.diagnose_docx(out)
    messages = [i.message for i in issues]
    assert any("consecutive headings" in m.lower() for m in messages)


def test_diagnose_finds_figure_caption_mismatch(tmp_path):
    src = tmp_path / "fig.md"
    src.write_text(
        "# 1 Chapter\n\n![x](assets/missing.png)\n\nРисунок {a} – Caption one.\n\n"
        "Рисунок {b} – Caption two.\n",
        encoding="utf-8",
    )
    out = tmp_path / "fig.docx"
    elements = md.parse_md(str(src))
    docx_build._build_pass(str(out), elements, None, include_toc=False)

    issues = diagnostics.diagnose_docx(out)
    messages = " ".join(i.message for i in issues).lower()
    assert "caption" in messages
