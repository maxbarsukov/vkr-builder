from vkr import md
from vkr import md_lint


def _lint(tmp_path, text):
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    return md_lint.lint_elements(md.parse_md(str(src)))


def test_clean_document_has_no_issues(tmp_path):
    text = (
        "# 1 Chapter\n\n"
        "See figure [рис:a].\n\n"
        "![x](assets/a.png)\n\n"
        "Рисунок {a} - Caption\n"
    )
    issues = _lint(tmp_path, text)
    assert [str(i) for i in issues] == []


def test_undefined_reference_is_error(tmp_path):
    text = "# 1 Chapter\n\nSee figure [рис:missing].\n"
    issues = _lint(tmp_path, text)
    assert any(i.severity == "error" and "missing" in i.message for i in issues)


def test_undefined_reference_in_a_table_cell_is_error(tmp_path):
    text = (
        "# 1 Chapter\n\n"
        "| Syntax | Meaning |\n"
        "|---|---|\n"
        "| [рис:missing] | a reference |\n"
    )
    issues = _lint(tmp_path, text)
    assert any(
        i.rule == "unknown-reference" and "рис:missing" in i.message
        and i.severity == "error"
        for i in issues
    )


def test_undefined_reference_in_a_caption_is_error(tmp_path):
    text = (
        "# 1 Chapter\n\n"
        "![x](assets/a.png)\n\n"
        "Рисунок {a} - See also [табл:missing]\n"
    )
    issues = _lint(tmp_path, text)
    assert any(
        i.rule == "unknown-reference" and "табл:missing" in i.message
        and i.severity == "error"
        for i in issues
    )


def test_a_suppress_directive_covers_the_table_it_sits_on(tmp_path):
    from vkr import suppress

    suppress.reset()
    text = (
        "# 1 Chapter\n\n"
        "<!-- @suppress unknown-reference -->\n\n"
        "| Syntax | Meaning |\n"
        "|---|---|\n"
        "| [рис:k] | a reference |\n"
    )
    issues = _lint(tmp_path, text)
    flagged = [i for i in issues if i.rule == "unknown-reference"]

    assert flagged and all(i.suppressed for i in flagged)
    assert suppress.unused((suppress.MARKDOWN,)) == []


def test_duplicate_key_is_error(tmp_path):
    text = (
        "# 1 Chapter\n\n"
        "![x](assets/a.png)\n\n"
        "Рисунок {a} - First\n\n"
        "![y](assets/b.png)\n\n"
        "Рисунок {a} - Second\n"
    )
    issues = _lint(tmp_path, text)
    assert any(i.severity == "error" and "duplicate" in i.message for i in issues)


def test_comma_citation_is_warning(tmp_path):
    text = "# 1 Chapter\n\nAccording to [1, 2] this holds.\n"
    issues = _lint(tmp_path, text)
    assert any(i.severity == "warning" and "comma" in i.message for i in issues)


def test_a_spaced_range_is_warning(tmp_path):
    text = "# 1 Chapter\n\nНа страницах 6 - 7 сказано многое.\n"
    issues = _lint(tmp_path, text)
    assert any(i.rule == "spaced-range" and i.severity == "warning" for i in issues)


def test_a_tight_range_is_not_reported(tmp_path):
    text = "# 1 Chapter\n\nНа страницах 6-7 сказано многое.\n"
    issues = _lint(tmp_path, text)
    assert not any(i.rule == "spaced-range" for i in issues)


def test_issue_carries_its_source_location(tmp_path):
    text = (
        md.file_marker("04-chapter.md") + "\n\n"
        "# 1 Chapter\n\nSee figure [рис:missing].\n"
    )
    issues = _lint(tmp_path, text)
    located = [i for i in issues if i.location.startswith("04-chapter.md:")]
    assert located, [(i.message, i.location) for i in issues]
    assert "04-chapter.md" not in located[0].message
    assert "(04-chapter.md:" in str(located[0])


def test_unknown_source_citation_is_warning(tmp_path):
    text = (
        "# 1 Chapter\n\nAs in [9].\n\n"
        "# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ\n\n"
        "1. Only one source.\n"
    )
    issues = _lint(tmp_path, text)
    assert any(
        i.severity == "warning" and "source list" in i.message for i in issues
    )


def test_orphan_caption_is_advisory_warning(tmp_path):
    text = (
        "# 1 Chapter\n\nNo reference here.\n\n"
        "![x](assets/a.png)\n\n"
        "Рисунок {a} - Caption\n"
    )
    issues = _lint(tmp_path, text)
    assert any(
        i.severity == "warning" and "never referenced" in i.message
        for i in issues
    )
    quiet = md_lint.lint_elements(
        md.parse_md(str((tmp_path / "doc.md"))), advisory=False
    )
    assert not any("never referenced" in i.message for i in quiet)


def test_empty_section_is_advisory_warning(tmp_path):
    text = "# 1 Chapter\n\n## 1.1 First\n\n## 1.2 Second\n\nBody.\n"
    issues = _lint(tmp_path, text)
    assert any(
        i.severity == "warning" and "no body text" in i.message for i in issues
    )


def test_table_column_mismatch_is_error(tmp_path):
    text = (
        "# 1 Chapter\n\n"
        "Таблица {t} - Demo\n\n"
        "| A | B |\n"
        "|---|---|\n"
        "| 1 | 2 | 3 |\n"
    )
    issues = _lint(tmp_path, text)
    assert any(i.severity == "error" and "columns" in i.message for i in issues)


def test_lint_strict_upgrades_warnings(tmp_path):
    text = "# Random\n\nBody.\n"
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    from vkr import md
    from vkr import md_lint

    issues = md_lint.lint_elements(md.parse_md(str(src)), advisory=False, strict=True)
    assert any(i.severity == "error" for i in issues)




def test_an_image_glued_to_its_caption_is_reported(tmp_path):
    text = "![i](f.png)\nРисунок {a} - Подпись\n\nСм. [рис:a].\n"
    issues = _lint(tmp_path, text)
    assert any(i.rule == "caption-spacing" for i in issues)


def test_a_blank_line_before_the_caption_is_correct_and_silent(tmp_path):
    text = "![i](f.png)\n\nРисунок {a} - Подпись\n\nСм. [рис:a].\n"
    assert not any(i.rule == "caption-spacing" for i in _lint(tmp_path, text))


def test_a_spaced_range_at_the_end_of_a_sentence_is_caught(tmp_path):
    text = "# 1 Chapter\n\nСказано на страницах 6 - 7.\n"
    assert any(i.rule == "spaced-range" for i in _lint(tmp_path, text)), (
        "точка после числа — не повод пропустить диапазон"
    )
