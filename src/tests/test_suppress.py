import io
import pathlib
import re

import pytest

from vkr import logging_setup, md, md_lint, suppress, ui


@pytest.fixture(autouse=True)
def _clean_registry():
    suppress.reset()
    yield
    suppress.reset()


def _lint(tmp_path, text):
    src = tmp_path / "doc.md"
    src.write_text(md.file_marker("01-ch.md") + "\n\n" + text, encoding="utf-8")
    return md_lint.lint_markdown(str(src))


def test_directive_forms_are_recognised():
    assert md.parse_suppress("<!-- @suppress -->") == ("element", "")
    assert md.parse_suppress("<!-- @suppress unknown reference -->") == (
        "element",
        "unknown reference",
    )
    assert md.parse_suppress("<!-- @suppress-file -->") == ("file", "")
    assert md.parse_suppress("  <!--  @SUPPRESS   caption  -->  ") == (
        "element",
        "caption",
    )
    assert md.parse_suppress("<!-- file: 01-ch.md -->") is None
    assert md.parse_suppress("regular text") is None


def test_a_directive_attaches_to_the_next_element_only(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(
        "# 1 Chapter\n\n<!-- @suppress -->\n\nMarked.\n\nNot marked.\n",
        encoding="utf-8",
    )
    elements = md.parse_md(str(src))
    by_text = {e.get("text"): md.element_suppressions(e) for e in elements}
    assert by_text["Marked."] == ("",)
    assert by_text["Not marked."] == ()
    assert by_text["1 Chapter"] == ()


def test_the_file_form_covers_everything_after_it(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(
        "# 1 Chapter\n\n<!-- @suppress-file caption -->\n\nOne.\n\nTwo.\n",
        encoding="utf-8",
    )
    elements = md.parse_md(str(src))
    by_text = {e.get("text"): md.element_suppressions(e) for e in elements}
    assert by_text["One."] == ("caption",)
    assert by_text["Two."] == ("caption",)
    assert by_text["1 Chapter"] == ()


def test_suppressions_do_not_cross_into_the_next_file(tmp_path):
    src = tmp_path / "bundle.md"
    src.write_text(
        md.file_marker("01-a.md") + "\n\n<!-- @suppress-file -->\n\nFirst.\n\n"
        + md.file_marker("02-b.md") + "\n\nSecond.\n",
        encoding="utf-8",
    )
    elements = md.parse_md(str(src))
    by_text = {e.get("text"): md.element_suppressions(e) for e in elements}
    assert by_text["First."] == ("",)
    assert by_text["Second."] == ()


def test_the_directive_leaves_no_text_in_the_document(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(
        "# 1 Chapter\n\n<!-- @suppress -->\n\nBody.\n", encoding="utf-8"
    )
    elements = md.parse_md(str(src))
    assert [e["type"] for e in elements] == ["heading", "para"]
    assert all("@suppress" not in (e.get("text") or "") for e in elements)


def test_pattern_matching_is_a_case_insensitive_substring():
    assert md.is_suppressed(("",), "anything at all")
    assert md.is_suppressed(("unknown reference",), "unknown reference [fig:k]")
    assert md.is_suppressed(("REFERENCE",), "unknown reference [fig:k]")
    assert not md.is_suppressed(("caption",), "unknown reference [fig:k]")
    assert not md.is_suppressed((), "unknown reference [fig:k]")


def test_lint_marks_the_covered_finding_and_leaves_the_rest(tmp_path):
    issues = _lint(
        tmp_path,
        "# 1 Chapter\n\nSee [рис:nope].\n\n<!-- @suppress -->\n\nAnd [табл:nope].\n",
    )
    by_message = {i.message: i for i in issues}
    figure = next(i for m, i in by_message.items() if "рис:nope" in m)
    table = next(i for m, i in by_message.items() if "табл:nope" in m)
    assert figure.suppressed is False
    assert table.suppressed is True


def test_lint_honours_the_pattern(tmp_path):
    issues = _lint(
        tmp_path,
        "# 1 Chapter\n\n<!-- @suppress listing -->\n\n"
        "See [рис:nope] and [лист:nope].\n",
    )
    suppressed = [i for i in issues if i.suppressed]
    live = [i for i in issues if not i.suppressed]
    assert len(suppressed) == 1 and "лист:nope" in suppressed[0].message
    assert len(live) == 1 and "рис:nope" in live[0].message


def test_a_suppressed_issue_still_says_so_in_text(tmp_path):
    issues = _lint(
        tmp_path, "# 1 Chapter\n\n<!-- @suppress -->\n\nSee [рис:nope].\n"
    )
    assert "[suppressed]" in str(issues[0])


def _console():
    buf = io.StringIO()
    con = ui.Console(buf)
    con.configure(verbosity=ui.NORMAL, color=False, unicode=False)
    return con, buf


def test_console_counts_a_suppressed_finding_without_printing_it():
    con, buf = _console()
    con.finding(ui.Finding("warning", "unknown reference", suppressed=True))
    con.finding(ui.Finding("warning", "a real one"))
    text = buf.getvalue()
    assert "unknown reference" not in text
    assert "a real one" in text
    assert (con.warnings, con.suppressed) == (1, 1)


def test_the_footer_admits_that_something_was_suppressed():
    con, buf = _console()
    con.finding(ui.Finding("error", "silenced", suppressed=True))
    con.footer_ok("build finished")
    assert "1 suppressed" in buf.getvalue()
    assert con.errors == 0


def test_a_rule_name_silences_whatever_the_wording_is():
    con, buf = _console()
    con.finding(
        ui.Finding(
            "warning",
            "unknown reference [рис:k]",
            rule="unknown-reference",
            suppressed=suppress.is_suppressed(
                ("unknown-reference",), "unknown reference [рис:k]", "unknown-reference"
            ),
        )
    )
    assert buf.getvalue() == ""
    assert con.suppressed == 1


def test_rule_names_and_message_text_both_work():
    patterns = ("unknown-reference",)
    assert suppress.is_suppressed(patterns, "anything at all", "unknown-reference")
    assert not suppress.is_suppressed(patterns, "caption must follow", "caption-order")
    assert suppress.is_suppressed(("caption must",), "caption must follow", "caption-order")


def test_every_rule_used_in_the_code_is_documented():
    from vkr import diagnostics, md_lint

    used = set()
    for path in (md_lint.__file__, diagnostics.__file__):
        text = pathlib.Path(path).read_text(encoding="utf-8")
        used |= set(re.findall(r'rule="([a-z][a-z-]+)"', text))
        used |= set(re.findall(r'^\s+"([a-z]+-[a-z-]+)",$', text, re.M))
    unknown = {r for r in used if r not in suppress.RULES}
    assert not unknown, f"undocumented rules: {sorted(unknown)}"


def test_every_rule_is_listed_once_and_has_a_stage():
    seen = [rule for group in suppress._BY_STAGE.values() for rule in group]

    assert sorted(seen) == sorted(suppress.RULES)
    assert len(seen) == len(set(seen))
    for rule in suppress.RULES:
        assert suppress.stages_of(rule)
    assert set(suppress._ALSO_RAISED_BY) <= set(suppress.RULES)


def test_a_rule_raised_twice_waits_for_both_of_its_stages():
    suppress.reset()
    suppress.register("unknown-reference", "element", "10-appendix.md:11")

    assert suppress.unused((suppress.MARKDOWN,)) == []
    assert [
        d.pattern for d in suppress.unused((suppress.MARKDOWN, suppress.BUILD))
    ] == ["unknown-reference"]


def test_a_build_only_rule_is_never_blamed_by_lint():
    suppress.reset()
    suppress.register("unknown-key", "element", "04-chapter1.md:10")

    assert suppress.stages_of("unknown-key") == frozenset({suppress.BUILD})
    assert suppress.unused((suppress.MARKDOWN,)) == []


def test_a_directive_is_not_blamed_by_a_command_that_never_ran_its_stage():
    suppress.reset()
    suppress.register("image", "element", "04-chapter1.md:10")

    assert suppress.unused((suppress.MARKDOWN,)) == []
    assert [d.pattern for d in suppress.unused((suppress.BUILD,))] == ["image"]
    assert [d.pattern for d in suppress.unused()] == ["image"]


def test_a_phrase_waits_for_a_run_that_covers_everything():
    suppress.reset()
    suppress.register("could not read", "element", "04-chapter1.md:10")

    assert suppress.unused((suppress.MARKDOWN, suppress.BUILD)) == []
    every = (suppress.MARKDOWN, suppress.BUILD, suppress.DOCUMENT)
    assert [d.pattern for d in suppress.unused(every)] == ["could not read"]


def test_a_misspelled_rule_name_is_reported_straight_away():
    suppress.reset()
    suppress.register("unknown-referense", "element", "04-chapter1.md:10")

    assert [
        d.pattern for d in suppress.unused((suppress.MARKDOWN,))
    ] == ["unknown-referense"]


def test_unused_directives_are_reported_with_their_own_location(tmp_path):
    suppress.reset()
    src = tmp_path / "doc.md"
    src.write_text(
        md.file_marker("01-ch.md") + "\n\n"
        "# 1 Chapter\n\n<!-- @suppress unknown-reference -->\n\n"
        "See [рис:nope].\n\n<!-- @suppress caption-order -->\n\nPlain text.\n",
        encoding="utf-8",
    )
    md_lint.lint_markdown(str(src))

    unused = suppress.unused()
    assert [d.pattern for d in unused] == ["caption-order"]
    assert unused[0].location == "01-ch.md:7"
    suppress.reset()


def test_a_directive_that_fired_is_not_reported(tmp_path):
    suppress.reset()
    src = tmp_path / "doc.md"
    src.write_text(
        md.file_marker("01-ch.md") + "\n\n"
        "# 1 Chapter\n\n<!-- @suppress unknown-reference -->\n\nSee [рис:nope].\n",
        encoding="utf-8",
    )
    md_lint.lint_markdown(str(src))
    assert suppress.unused() == []
    suppress.reset()


def test_build_warnings_inherit_the_suppressions_of_their_element(monkeypatch):
    con, buf = _console()
    monkeypatch.setattr(ui, "_console", con)
    logging_setup.setup_logging(ui.NORMAL)
    log = logging_setup.get_logger("crossref")
    try:
        logging_setup.set_source_location("10-appendix.md:11", ("unknown reference",))
        log.warning("unknown reference [рис:k]")
        log.warning("could not insert image assets/x.png")
    finally:
        logging_setup.set_source_location()

    text = buf.getvalue()
    assert "unknown reference" not in text
    assert "could not insert image" in text
    assert (con.warnings, con.suppressed) == (1, 1)


def test_a_word_that_resembles_no_rule_is_taken_at_face_value():
    assert suppress.misspelled_rule("bookmark") is None
    assert suppress.misspelled_rule("unknown-referense") == "unknown-reference"
    assert suppress.misspelled_rule("image") is None

    suppress.reset()
    suppress.register("bookmark", "element", "04-ch.md:10")
    assert suppress.unused((suppress.MARKDOWN,)) == []


def test_a_directive_works_glued_to_what_it_covers(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text(
        "# 1 Chapter\n\n<!-- @suppress unknown-reference -->\nSee [рис:nope].\n",
        encoding="utf-8",
    )
    elements = md.parse_md(str(src))
    para = next(e for e in elements if e["type"] == "para")

    assert md.element_suppressions(para) == ("unknown-reference",)
    assert "@suppress" not in para["text"]


def test_directives_stack_however_they_are_spaced(tmp_path):
    forms = {
        "glued": "<!-- @suppress a -->\n<!-- @suppress b -->\nBody.\n",
        "spaced": "<!-- @suppress a -->\n\n<!-- @suppress b -->\n\nBody.\n",
        "mixed": "<!-- @suppress a -->\n<!-- @suppress b -->\n\nBody.\n",
    }
    for name, text in forms.items():
        src = tmp_path / f"{name}.md"
        src.write_text("# 1 Chapter\n\n" + text, encoding="utf-8")
        para = next(
            e for e in md.parse_md(str(src)) if e["type"] == "para"
        )
        assert md.element_suppressions(para) == ("a", "b"), name
        assert para["text"] == "Body.", name


def test_a_plain_comment_above_a_paragraph_still_disappears(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text("# 1 Chapter\n\n<!-- a note -->\nBody.\n", encoding="utf-8")
    para = next(e for e in md.parse_md(str(src)) if e["type"] == "para")

    assert para["text"] == "Body."
    assert md.element_suppressions(para) == ()
