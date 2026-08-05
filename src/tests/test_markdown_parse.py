from collections import Counter

from vkr import md
from vkr.merge import merge_markdown_files


def test_sample_element_types(sample_md_path):
    elements = md.parse_md(str(sample_md_path))
    counts = Counter(e["type"] for e in elements)

    assert counts["heading"] == 5
    assert counts["para"] >= 1
    assert counts["list_item"] == 4
    assert counts["table"] == 1
    assert counts["table_caption"] == 1
    assert counts["code"] == 1
    assert counts["listing_caption"] == 1


def test_sample_heading_levels(sample_md_path):
    elements = md.parse_md(str(sample_md_path))
    levels = [e["level"] for e in elements if e["type"] == "heading"]
    assert 1 in levels and 2 in levels and 3 in levels


def test_sample_table_shape(sample_md_path):
    elements = md.parse_md(str(sample_md_path))
    table = next(e for e in elements if e["type"] == "table")
    assert table["header"] == ["Column A", "Column B"]
    assert len(table["rows"]) == 2
    assert all(len(row) == 2 for row in table["rows"])


def test_file_markers_attribute_source(tmp_path):
    bundle = tmp_path / "bundle.md"
    bundle.write_text(
        md.file_marker("01-intro.md") + "\n\n"
        "# 1 Intro\n\nText one.\n\n"
        + md.file_marker("02-body.md") + "\n\n"
        "# 2 Body\n\nText two.\n",
        encoding="utf-8",
    )
    elements = md.parse_md(str(bundle))
    assert all("<!--" not in e.get("text", "") for e in elements)
    by_file = {e.get("src_file") for e in elements}
    assert by_file == {"01-intro.md", "02-body.md"}
    intro = next(e for e in elements if e.get("text") == "Text one.")
    assert intro["src_file"] == "01-intro.md"


def test_line_numbers_are_relative_to_the_source_file(tmp_path):
    first = "# 1 Intro\n\nText one.\n\nSecond paragraph.\n"
    second = "# 2 Body\n\nText two.\n"
    (tmp_path / "01-intro.md").write_text(first, encoding="utf-8")
    (tmp_path / "02-body.md").write_text(second, encoding="utf-8")

    bundle = tmp_path / "bundle.md"
    merge_markdown_files(tmp_path, ["01-intro.md", "02-body.md"], bundle)
    elements = md.parse_md(str(bundle))

    where = {
        e["text"]: (e["src_file"], e["src_line"])
        for e in elements
        if e.get("text") and e.get("src_line")
    }
    assert where["Text one."] == ("01-intro.md", 3)
    assert where["Second paragraph."] == ("01-intro.md", 5)
    assert where["2 Body"] == ("02-body.md", 1)
    assert where["Text two."] == ("02-body.md", 3)

    assert first.splitlines()[2] == "Text one."
    assert second.splitlines()[2] == "Text two."


def test_a_single_file_is_numbered_and_named_as_itself(tmp_path):
    chapter = tmp_path / "04-chapter1.md"
    chapter.write_text("# 1 Chapter\n\nBody text.\n", encoding="utf-8")
    elements = md.parse_md(str(chapter))
    body = next(e for e in elements if e.get("text") == "Body text.")
    assert (body["src_file"], body["src_line"]) == ("04-chapter1.md", 3)


def test_single_line_display_math():
    block = [r"\[ E = m c^2 \]"]
    assert md.is_display_math_block(block)
    latex, number = md.parse_display_math_block(block)
    assert latex == "E = m c^2"
    assert number is None


def test_single_line_display_math_with_number():
    block = [r"\[ E = m c^2 \]", "(1)"]
    assert md.is_display_math_block(block)
    latex, number = md.parse_display_math_block(block)
    assert latex == "E = m c^2"
    assert number == "(1)"


def test_multiline_display_math_still_works():
    block = [r"\[", "E = m c^2", r"\]"]
    assert md.is_display_math_block(block)
    latex, number = md.parse_display_math_block(block)
    assert latex == "E = m c^2"
    assert number is None


def test_example_files_parse_without_error(example_dir):
    md_files = sorted((example_dir / "md").glob("*.md"))
    assert md_files, "example/md must contain markdown files"
    for path in md_files:
        elements = md.parse_md(str(path))
        assert isinstance(elements, list)
        assert elements, f"{path.name} produced no elements"


def test_caption_separator_keeps_the_authors_dash_and_spaces_it(tmp_path):
    src = tmp_path / "caps.md"
    src.write_text(
        "# 1 Test\n\n"
        "Рисунок 1 - Figure\n\n"
        "Таблица {t} – Table\n\n"
        "Листинг {l} — Listing\n",
        encoding="utf-8",
    )
    elements = md.parse_md(str(src))
    captions = [e["text"] for e in elements if e["type"].endswith("_caption")]
    assert captions == [
        "Рисунок 1 - Figure",
        "Таблица {t} – Table",
        "Листинг {l} — Listing",
    ], "разбор сохраняет знак автора; выбор тире делает сборка по style.dashes"


def test_a_comment_after_a_paragraph_does_not_reach_the_text(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(
        "Обычный абзац текста.\n<!-- заметка для себя -->\n\nВторой абзац.\n",
        encoding="utf-8",
    )
    texts = [e["text"] for e in md.parse_md(str(src)) if e["type"] == "para"]
    assert texts == ["Обычный абзац текста.", "Второй абзац."]
