import pytest

from vkr import md, md_lint


@pytest.fixture
def workspace(tmp_path):
    listings = tmp_path / "code"
    listings.mkdir()
    (listings / "sample.py").write_text(
        "\n".join(f"line{i}" for i in range(1, 11)) + "\n", encoding="utf-8"
    )
    return tmp_path, listings


def _write(tmp_path, body):
    src = tmp_path / "doc.md"
    src.write_text(body, encoding="utf-8")
    return src


def _codes(elements):
    return [e for e in elements if e["type"] == "code"]


def test_whole_file_is_inserted(workspace):
    tmp_path, listings = workspace
    src = _write(tmp_path, "Листинг {a} - Файл\n@listing sample.py\n")
    code = _codes(md.parse_md(str(src), listings))[0]
    assert code["lines"] == [f"line{i}" for i in range(1, 11)]
    assert code["lang"] == "py"
    assert "include_error" not in code


def test_caption_is_not_swallowed_by_the_directive(workspace):
    tmp_path, listings = workspace
    src = _write(tmp_path, "Листинг {a} - Файл\n@listing sample.py\n")
    kinds = [e["type"] for e in md.parse_md(str(src), listings)]
    assert kinds == ["listing_caption", "code"]


def test_line_range(workspace):
    tmp_path, listings = workspace
    src = _write(tmp_path, "Листинг {a} - Кусок\n@listing sample.py:3-5\n")
    code = _codes(md.parse_md(str(src), listings))[0]
    assert code["lines"] == ["line3", "line4", "line5"]


def test_open_ended_range_runs_to_the_end(workspace):
    tmp_path, listings = workspace
    src = _write(tmp_path, "Листинг {a} - Хвост\n@listing sample.py:8-\n")
    code = _codes(md.parse_md(str(src), listings))[0]
    assert code["lines"] == ["line8", "line9", "line10"]


def test_directive_inside_a_fence_stays_literal(workspace):
    tmp_path, listings = workspace
    src = _write(
        tmp_path,
        "Листинг {a} - Синтаксис\n```text\n@listing sample.py\n```\n",
    )
    code = _codes(md.parse_md(str(src), listings))[0]
    assert code["lines"] == ["@listing sample.py"]
    assert code.get("include") is None


def test_location_points_at_the_directive_line(workspace):
    tmp_path, listings = workspace
    src = _write(
        tmp_path,
        "Абзац.\n\nЛистинг {a} - Файл\n@listing nope.py\n",
    )
    issues = md_lint.lint_elements(md.parse_md(str(src), listings))
    found = [i for i in issues if i.rule == "listing-file"]
    assert len(found) == 1
    assert found[0].location == "doc.md:4"


@pytest.mark.parametrize(
    "spec, fragment",
    [
        ("nope.py", "file not found"),
        ("../outside.py", "escapes the listings directory"),
        ("sample.py:99-100", "range starts at 99"),
        ("sample.py:5-2", "empty line range"),
        ("sample.py:0-3", "numbered from 1"),
        ("sample.py:0-", "numbered from 1"),
    ],
)
def test_bad_includes_are_lint_errors(workspace, spec, fragment):
    tmp_path, listings = workspace
    (tmp_path / "outside.py").write_text("secret\n", encoding="utf-8")
    src = _write(tmp_path, f"Листинг {{a}} - Плохо\n@listing {spec}\n")
    elements = md.parse_md(str(src), listings)
    assert _codes(elements)[0]["lines"] == []
    issues = [
        i
        for i in md_lint.lint_elements(elements)
        if i.rule == "listing-file"
    ]
    assert len(issues) == 1
    assert issues[0].severity == "error"
    assert fragment in issues[0].message


def test_empty_file_is_a_warning_not_an_error(workspace):
    tmp_path, listings = workspace
    (listings / "empty.txt").write_text("", encoding="utf-8")
    src = _write(tmp_path, "Листинг {a} - Пусто\n@listing empty.txt\n")
    issues = [
        i
        for i in md_lint.lint_elements(md.parse_md(str(src), listings))
        if i.rule == "listing-file"
    ]
    assert [i.severity for i in issues] == ["warning"]


def test_without_a_listings_root_the_include_is_reported(workspace):
    tmp_path, _ = workspace
    src = _write(tmp_path, "Листинг {a} - Файл\n@listing sample.py\n")
    code = _codes(md.parse_md(str(src), None))[0]
    assert "no listings directory is configured" in code["include_error"]


def test_suppress_silences_the_rule(workspace):
    tmp_path, listings = workspace
    src = _write(
        tmp_path,
        "Листинг {a} - Плохо\n<!-- @suppress listing-file -->\n@listing nope.py\n",
    )
    issues = [
        i
        for i in md_lint.lint_elements(md.parse_md(str(src), listings))
        if i.rule == "listing-file"
    ]
    assert [i.suppressed for i in issues] == [True]


def test_trailing_suppress_does_not_leak_into_the_caption(workspace):
    tmp_path, listings = workspace
    src = _write(
        tmp_path,
        "Листинг {a} - Плохо\n<!-- @suppress listing-file -->\n@listing nope.py\n",
    )
    caption = next(
        e for e in md.parse_md(str(src), listings)
        if e["type"] == "listing_caption"
    )
    assert "@suppress" not in caption["text"]


def test_included_listing_renders_into_the_docx(workspace, tmp_path):
    from vkr import docx_build

    src_dir, listings = workspace
    src = _write(src_dir, "Листинг {a} - Файл\n@listing sample.py:1-3\n")
    out = tmp_path / "out.docx"
    docx_build.build(
        str(src), str(out), listings_root=listings, include_toc=False
    )

    import docx

    doc = docx.Document(str(out))
    text = "\n".join(
        cell.text
        for table in doc.tables
        for row in table.rows
        for cell in row.cells
    )
    assert "line1" in text and "line3" in text
    assert "line4" not in text


def test_config_reads_the_listings_dir(tmp_path):
    from vkr import config

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "active_profile: p\n\nprofiles:\n  p:\n"
        "    docx: out.docx\n    markdown_dir: md\n"
        "    images_dir: images\n    listings_dir: code\n"
        "    markdown_files:\n      - a.md\n",
        encoding="utf-8",
    )
    profile = config.load_build_config(cfg).profile
    assert profile.listings_dir == (tmp_path / "code").resolve()
    assert profile.listings_root == (tmp_path / "code").resolve()


def test_listings_root_falls_back_to_images_dir(tmp_path):
    from vkr import config

    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "active_profile: p\n\nprofiles:\n  p:\n"
        "    docx: out.docx\n    markdown_dir: md\n"
        "    images_dir: images\n"
        "    markdown_files:\n      - a.md\n",
        encoding="utf-8",
    )
    profile = config.load_build_config(cfg).profile
    assert profile.listings_dir is None
    assert profile.listings_root == (tmp_path / "images").resolve()


def test_watch_follows_the_listings_directory(tmp_path):
    from vkr import watch

    md_dir = tmp_path / "md"
    md_dir.mkdir()
    (md_dir / "a.md").write_text("x", encoding="utf-8")
    listings = tmp_path / "code"
    listings.mkdir()

    paths = watch.collect_watch_paths(md_dir, ["a.md"], [listings])
    assert listings.resolve() in paths
    assert listings.resolve() in watch.content_roots([listings])


def test_watch_ignores_a_listings_directory_that_is_not_there(tmp_path):
    from vkr import watch

    assert watch.content_roots([tmp_path / "gone", None]) == []


def test_a_windows_style_path_resolves_everywhere(workspace):
    tmp_path, listings = workspace
    (listings / "sub").mkdir()
    (listings / "sub" / "b.py").write_text("y = 2\n", encoding="utf-8")
    src = _write(tmp_path, "Листинг {a} - Файл\n@listing sub\\b.py\n")
    code = _codes(md.parse_md(str(src), listings))[0]
    assert code["lines"] == ["y = 2"]
