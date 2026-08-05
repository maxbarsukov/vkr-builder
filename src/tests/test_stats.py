from vkr import md
from vkr.stats_report import collect_stats


def test_collect_stats_counts_sources_and_chapters(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(
        """# 1 First chapter

Body text here.

# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ

1. Source one.
2. Source two.
""",
        encoding="utf-8",
    )
    elements = md.parse_md(str(src))
    stats = collect_stats(elements)
    assert stats.chapters == 1
    assert stats.sources == 2
    assert stats.paragraphs >= 1
    assert stats.estimated_pages >= 1


def _stats(tmp_path, text):
    src = tmp_path / "doc.md"
    src.write_text(text, encoding="utf-8")
    return collect_stats(md.parse_md(str(src)))


def test_top_level_headings_are_split_into_their_kinds(tmp_path):
    stats = _stats(
        tmp_path,
        "# ВВЕДЕНИЕ\n\nText.\n\n"
        "# 1 First chapter\n\nText.\n\n"
        "# 2 Second chapter\n\nText.\n\n"
        "# ЗАКЛЮЧЕНИЕ\n\nText.\n\n"
        "# ПРИЛОЖЕНИЕ А\n\nText.\n\n"
        "# ПРИЛОЖЕНИЕ Б\n\nText.\n",
    )
    assert (stats.sections, stats.chapters, stats.appendices) == (2, 2, 2)


def test_words_count_tables_listings_and_captions(tmp_path):
    base = "# 1 Chapter\n\nOne two three four five.\n"
    prose = _stats(tmp_path, base)

    table = _stats(
        tmp_path,
        base + "\nТаблица {t} - Шесть семь\n\n"
        "| Восемь | Девять |\n|---|---|\n| десять | одиннадцать |\n",
    )
    listing = _stats(
        tmp_path, base + "\nЛистинг {l} - Двенадцать\n\n```python\nx = 1\n```\n"
    )

    assert table.words == prose.words + 5 + 4
    assert listing.words == prose.words + 4 + 3
    assert table.characters > prose.characters


def test_page_estimate_accounts_for_more_than_prose(tmp_path):
    prose = "# 1 Chapter\n\n" + ("слово " * 250) + "\n"
    plain = _stats(tmp_path, prose)

    figures = "".join(
        f"\n![x](assets/{i}.png)\n\nРисунок {{f{i}}} - Caption\n" for i in range(6)
    )
    illustrated = _stats(tmp_path, prose + figures)

    assert illustrated.figures == 6
    assert illustrated.estimated_pages > plain.estimated_pages


def test_a_new_section_costs_a_page_break(tmp_path):
    body = "\n\n".join("Абзац текста номер %d." % i for i in range(10))
    one = _stats(tmp_path, f"# ВВЕДЕНИЕ\n\n{body}\n")
    many = _stats(
        tmp_path,
        f"# ВВЕДЕНИЕ\n\n{body}\n\n# ЗАКЛЮЧЕНИЕ\n\nX.\n\n# ПРИЛОЖЕНИЕ А\n\nY.\n",
    )
    assert many.estimated_pages > one.estimated_pages


def test_sources_are_counted_in_either_citation_style(tmp_path):
    numbered = _stats(
        tmp_path,
        "# 1 Chapter\n\nAs in [1] and [2].\n\n"
        "# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ\n\n"
        "1. First source.\n2. Second source.\n",
    )
    keyed = _stats(
        tmp_path,
        "# 1 Chapter\n\nAs in [{one}] and [{two}].\n\n"
        "# СПИСОК ИСПОЛЬЗОВАННЫХ ИСТОЧНИКОВ\n\n"
        "{one} First source.\n\n{two} Second source.\n",
    )
    assert (numbered.sources, keyed.sources) == (2, 2)
