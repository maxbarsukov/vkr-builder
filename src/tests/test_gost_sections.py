from vkr import gost_sections
from vkr import md
from vkr import md_lint


def test_dictionary_sort_key_russian_order():
    assert gost_sections.dictionary_sort_key("Балет – art") < gost_sections.dictionary_sort_key(
        "Сталь – metal"
    )


def test_sort_dictionary_sections_reorders_entries():
    elements = [
        {"type": "heading", "level": 1, "text": "ТЕРМИНЫ И ОПРЕДЕЛЕНИЯ"},
        {"type": "para", "text": "Сталь – metal"},
        {"type": "para", "text": "Балет – art"},
    ]
    sorted_el = gost_sections.sort_dictionary_sections(elements)
    texts = [e["text"] for e in sorted_el if e["type"] == "para"]
    assert texts == ["Балет – art", "Сталь – metal"]


def test_dictionary_sort_issues_detects_unsorted():
    elements = [
        {"type": "heading", "level": 1, "text": "СПИСОК СОКРАЩЕНИЙ И УСЛОВНЫХ ОБОЗНАЧЕНИЙ"},
        {"type": "para", "text": "ВКР – work"},
        {"type": "para", "text": "AST – tree"},
    ]
    issues = gost_sections.dictionary_sort_issues(elements)
    assert len(issues) == 1
    assert "alphabetical" in issues[0][1]


def test_appendix_forbidden_cyrillic_letter():
    assert gost_sections.appendix_letter_issue("О") is not None
    assert gost_sections.appendix_letter_issue("А") is None


def test_appendix_forbidden_latin_letter():
    assert gost_sections.appendix_letter_issue("I") is not None
    assert gost_sections.appendix_letter_issue("B") is None


def test_lint_reports_unsorted_dictionary(tmp_path):
    text = (
        "# СПИСОК СОКРАЩЕНИЙ И УСЛОВНЫХ ОБОЗНАЧЕНИЙ\n\n"
        "ВКР – work\n\n"
        "AST – tree\n"
    )
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    issues = md_lint.lint_elements(md.parse_md(str(src)))
    assert any("alphabetical order" in i.message for i in issues)


def test_lint_reports_invalid_appendix_letter(tmp_path):
    text = "# ПРИЛОЖЕНИЕ О\n\nBody.\n"
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    issues = md_lint.lint_elements(md.parse_md(str(src)))
    assert any(i.severity == "warning" and "appendix" in i.message for i in issues)


def test_lint_reports_duplicate_appendix_letter(tmp_path):
    text = (
        "# ПРИЛОЖЕНИЕ А\n\nOne.\n\n"
        "# ПРИЛОЖЕНИЕ А\n\nTwo.\n"
    )
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    issues = md_lint.lint_elements(md.parse_md(str(src)))
    assert any(i.severity == "warning" and "duplicate" in i.message for i in issues)


def test_appendix_toc_row_carries_its_title_without_brackets():
    from vkr.docx.toc import collapse_appendix_toc_rows

    headings = [
        (1, "ПРИЛОЖЕНИЕ В", "ПРИЛОЖЕНИЕ В"),
        (2, "Справочник конструкций разметки", "Справочник конструкций разметки"),
    ]
    rows = collapse_appendix_toc_rows(headings, [12, 12])

    assert [r[1] for r in rows] == ["ПРИЛОЖЕНИЕ В Справочник конструкций разметки"]


def test_an_appendix_without_a_title_stays_as_it_is():
    from vkr.docx.toc import collapse_appendix_toc_rows

    headings = [(1, "ПРИЛОЖЕНИЕ А", "ПРИЛОЖЕНИЕ А")]
    rows = collapse_appendix_toc_rows(headings, [7])

    assert [r[1] for r in rows] == ["ПРИЛОЖЕНИЕ А"]
