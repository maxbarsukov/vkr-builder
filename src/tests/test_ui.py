import io
import json
import re
import time
import unicodedata

from vkr import mascots, ui


def _console(verbosity: int = ui.NORMAL) -> tuple[ui.Console, io.StringIO]:
    buf = io.StringIO()
    con = ui.Console(buf)
    con.configure(verbosity=verbosity, color=False, unicode=False)
    return con, buf


def test_header_names_the_launcher_command_and_context(monkeypatch):
    monkeypatch.setattr(ui, "_program", "vkr-builder.bat")
    con, buf = _console()
    con.header("build", "example", "word engine")
    text = buf.getvalue()
    assert "vkr-builder.bat build" in text
    assert "example - word engine" in text
    assert text.startswith("\n")


def test_step_renders_glyph_name_and_time():
    con, buf = _console()
    step = con.step("merge", "collecting")
    step.finish("10 files")
    line = [ln for ln in buf.getvalue().splitlines() if ln.strip()][0]
    assert line.startswith("    + merge")
    assert "10 files" in line
    assert line.rstrip().endswith("s")


def test_failed_and_skipped_steps_use_their_own_glyphs():
    con, buf = _console()
    con.step("lint").fail("2 errors")
    con.step("merge").skip("reusing bundle")
    text = buf.getvalue()
    assert "x lint" in text
    assert "2 errors" in text
    assert "- merge" in text


def test_starting_a_step_closes_the_previous_one():
    con, buf = _console()
    con.step("merge", "working")
    con.step("lint", "working")
    con.step("done").finish()
    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 3
    assert all(ln.lstrip().startswith("+") for ln in lines)


def test_issues_are_counted_and_shown():
    con, buf = _console()
    con.issue("warning", "unknown reference [fig:k]")
    con.issue("error", "missing markdown file")
    assert (con.warnings, con.errors) == (1, 1)
    text = buf.getvalue()
    assert "! unknown reference [fig:k]" in text
    assert "x missing markdown file" in text


def test_footer_reports_counts_and_outputs():
    con, buf = _console()
    con.issue("warning", "something")
    con.footer_ok(
        "build finished", artifacts=[("document", "out.docx")], elapsed=12.0
    )
    text = buf.getvalue()
    assert "+ build finished in 12s - 1 warning" in text
    assert "document   out.docx" in text


def test_footer_hides_a_trivial_duration():
    con, buf = _console()
    con.footer_ok("done", elapsed=0.01)
    assert "in " not in buf.getvalue()


def test_failure_footer_shows_detail_and_hint():
    con, buf = _console()
    con.footer_fail("build failed", detail="Word is not available", hint="vkr doctor")
    text = buf.getvalue()
    assert "x build failed" in text
    assert "Word is not available" in text
    assert "try  vkr doctor" in text


def test_quiet_prints_errors_only():
    con, buf = _console(ui.QUIET)
    con.header("build", "example")
    con.step("merge").finish("10 files")
    con.issue("warning", "ignorable")
    con.issue("error", "fatal")
    text = buf.getvalue()
    assert "vkr build" not in text
    assert "merge" not in text
    assert "ignorable" not in text
    assert "fatal" in text
    assert con.warnings == 1


def test_notes_need_verbose():
    con, buf = _console()
    con.note("extra detail")
    assert buf.getvalue() == ""

    con, buf = _console(ui.VERBOSE)
    con.note("extra detail")
    assert "extra detail" in buf.getvalue()


def test_blank_lines_never_double_up():
    con, buf = _console()
    con.header("stats", "example")
    con.section("structure")
    assert "\n\n\n" not in buf.getvalue()


def test_metrics_align_labels_and_values():
    con, buf = _console()
    con.metric("headings", "28")
    con.metric("words", "1 619", "estimated")
    lines = buf.getvalue().splitlines()
    assert lines[0].endswith("28")
    assert lines[0].index("28") == lines[1].index("1 619") + len("1 619") - 2
    assert "estimated" in lines[1]


def test_formatting_helpers():
    assert ui.fmt_duration(0.4) == "0.4s"
    assert ui.fmt_duration(21.4) == "21s"
    assert ui.fmt_duration(75) == "1m15s"
    assert ui.fmt_size(512) == "512 B"
    assert ui.fmt_size(96 * 1024) == "96 KB"
    assert ui.fmt_size(3 * 1024 * 1024) == "3.0 MB"
    assert ui.fmt_count(12837) == "12 837"
    assert ui.plural(1, "file") == "1 file"
    assert ui.plural(3, "pass", "passes") == "3 passes"


_DOUBLE_WIDTH_IN_TERMINALS = "⚠❗‼⚡⭐❌✅⛔♻⌛⏳⏰"


def test_status_glyphs_occupy_exactly_one_column():
    glyphs = (
        ui.UNICODE.ok,
        ui.UNICODE.fail,
        ui.UNICODE.warn,
        ui.UNICODE.skip,
        ui.UNICODE.bullet,
        ui.UNICODE.dot,
        *ui.UNICODE.spinner,
    )
    for glyph in glyphs:
        assert len(glyph) == 1, glyph
        assert unicodedata.east_asian_width(glyph) not in ("W", "F"), glyph
        assert glyph not in _DOUBLE_WIDTH_IN_TERMINALS, glyph


def test_status_rows_line_up_whatever_the_outcome():
    buf = io.StringIO()
    con = ui.Console(buf)
    con.configure(verbosity=ui.NORMAL, color=False, unicode=True)
    con.step("lint").finish("no issues")
    con.step("diagnose").warn("1 warning")
    con.step("pdf").fail("export failed")

    ok_line, warn_line, fail_line = buf.getvalue().splitlines()
    assert ok_line.index("no issues") == warn_line.index("1 warning")
    assert ok_line.index("no issues") == fail_line.index("export failed")
    assert len(ok_line) == len(warn_line) == len(fail_line)


def test_ascii_fallback_for_a_narrow_encoding():
    buf = io.StringIO()
    con = ui.Console(buf)
    con.configure(verbosity=ui.NORMAL, color=False, unicode=False)
    assert con.symbols is ui.ASCII
    con.configure(verbosity=ui.NORMAL, color=False, unicode=True)
    assert con.symbols is ui.UNICODE


def test_colour_can_be_forced_off():
    con, buf = _console()
    con.step("merge").finish("done")
    assert "\x1b[" not in buf.getvalue()


class _Tty(io.StringIO):
    def isatty(self) -> bool:
        return True


def _live_console() -> tuple[ui.Console, _Tty]:
    buf = _Tty()
    con = ui.Console(buf)
    con.configure(verbosity=ui.NORMAL, color=False, unicode=False)
    return con, buf


def test_live_step_redraws_in_place():
    con, buf = _live_console()
    step = con.step("layout", "starting")
    step.update("pass 1/3 - writing document", fraction=0.1)
    step.update("pass 2/3 - fitting tables", fraction=0.5)
    step.finish("3 passes")

    text = buf.getvalue()
    assert "\x1b[2K" in text
    assert "===" in text
    assert text.rstrip().endswith("s")
    assert text.count("+ layout") == 1


def test_the_bar_line_carries_the_percent_and_the_counter():
    con, buf = _console()
    con.step("markdown").finish("28 headings")
    finished = buf.getvalue().splitlines()[0]

    live, _ = _live_console()
    step = live.step("layout", "pass 2/3 - fitting tables")
    step.update(fraction=0.46, counter="3/8 tables")
    head, bar_line = [_strip(line) for line in live._render_live()]

    assert head.startswith("    | layout       pass 2/3")
    assert head.rstrip().endswith("s")
    assert len(head) == len(finished)
    assert head.index("layout") == bar_line.index("46%") == ui.PERCENT_COL
    assert head.index("pass 2/3") == bar_line.index("=") == ui.DETAIL_COL
    assert bar_line.endswith("3/8 tables")
    assert len(bar_line) == len(finished)
    assert not re.search(r"\d+(\.\d+)?s$", bar_line)


def test_the_bar_keeps_its_length_when_the_counter_text_changes():
    con, _ = _live_console()
    step = con.step("layout", "working")

    step.update(fraction=0.5, counter="3/8 tables")
    short = _strip(con._render_live()[1])
    step.update(fraction=0.5, counter="34/120 headings")
    long = _strip(con._render_live()[1])

    assert short.count("=") == long.count("=")
    assert len(short) == len(long)


def test_nothing_on_the_bar_line_moves_between_redraws():
    con, _ = _live_console()
    step = con.step("layout", "working")

    shapes = set()
    counter_ends = set()
    for fraction, counter in [
        (0.0, ""),
        (0.08, ""),
        (0.54, "16/23 headings"),
        (1.0, "8/8 tables"),
    ]:
        step.update(fraction=fraction, counter=counter)
        line = _strip(con._render_live()[1])
        bar_start = min(line.index(c) for c in "=-" if c in line)
        shapes.add((line.count("=") + line.count("-"), bar_start))
        if counter:
            counter_ends.add(len(line))

    assert len(shapes) == 1, shapes
    assert len(counter_ends) == 1, counter_ends


def test_a_phase_with_nothing_to_count_says_something_instead():
    con, _ = _live_console()
    step = con.step("layout", "pass 1/3 - writing document")
    step.engine = "Word"

    step.update(fraction=0.3)
    idle = _strip(con._render_live()[1])
    assert idle.rstrip().endswith(step._phrase.format(engine="Word"))

    step.update(fraction=0.3, counter="3/8 tables")
    assert _strip(con._render_live()[1]).rstrip().endswith("3/8 tables")


def test_the_phrase_is_held_for_its_window_then_changes():
    con, _ = _live_console()
    step = con.step("layout", "working")
    step.update(fraction=0.3)

    first = step.idle_phrase()
    assert step.idle_phrase() == first

    seen = [first]
    for slot in range(1, 12):
        step._t0 = time.monotonic() - slot * ui.IDLE_PHRASE_SECONDS - 0.1
        seen.append(step.idle_phrase())

    assert all(a != b for a, b in zip(seen, seen[1:]))
    assert len(set(seen)) > 3
    assert set(seen) <= {p.format(engine="the engine") for p in ui.IDLE_PHRASES}


def test_the_phrase_names_the_engine_in_use():
    con, _ = _live_console()
    step = con.step("layout", "working")
    step._phrase = "summoning {engine}"
    step._phrase_slot = 0

    step.engine = "Word"
    assert step.idle_phrase() == "summoning Word"
    step.engine = "LibreOffice"
    assert step.idle_phrase() == "summoning LibreOffice"
    step.engine = ""
    assert step.idle_phrase() == "summoning the engine"


def test_every_phrase_fits_the_field_it_is_drawn_in():
    longest_engine = max([*ui.ENGINE_NAMES.values(), "the engine"], key=len)
    for phrase in ui.IDLE_PHRASES:
        rendered = phrase.format(engine=longest_engine)
        assert len(rendered) <= ui.COUNTER_WIDTH, rendered


def test_a_narrow_window_drops_the_counter_before_the_bar(monkeypatch):
    con, _ = _live_console()
    step = con.step("layout", "working")
    step.update(fraction=0.5, counter="34/120 headings")

    monkeypatch.setattr(type(con), "width", property(lambda self: 46))
    bar_line = _strip(con._render_live()[1])
    assert "34/120" not in bar_line
    assert bar_line.count("=") + bar_line.count("-") >= ui.MIN_BAR


def test_a_warning_during_a_live_step_lands_above_it():
    con, buf = _live_console()
    step = con.step("layout", "working")
    step.update(fraction=0.5)
    con.issue("warning", "unknown reference")
    step.finish("done")

    lines = [ln for ln in _strip(buf.getvalue()).splitlines() if ln.strip()]
    assert any("! unknown reference" in ln for ln in lines)
    assert lines.index([ln for ln in lines if "! unknown" in ln][0]) < len(lines) - 1


def test_close_clears_a_running_step():
    con, buf = _live_console()
    con.step("layout", "working").update(fraction=0.3)
    con.close()
    assert "+ layout" in buf.getvalue()


def _strip(text: str) -> str:
    return ui._ANSI_RE.sub("", text)


def test_progress_never_goes_backwards():
    con, _ = _live_console()
    step = con.step("layout", "working")
    step.update(fraction=0.85)
    step.update(fraction=0.67)
    assert step.fraction == 0.85
    step.update(fraction=0.9)
    assert step.fraction == 0.9


def test_a_repeated_finding_is_reported_once():
    con, buf = _console()
    for _ in range(3):
        con.issue("warning", "unknown reference [fig:k]")
    assert buf.getvalue().count("unknown reference") == 1
    assert con.warnings == 3
    con.footer_warn("done")
    assert "2 not shown" in buf.getvalue()


def test_a_flood_of_warnings_is_capped_until_verbose():
    con, buf = _console()
    for i in range(ui.FINDING_CAP + 5):
        con.issue("warning", f"broken reference number {i}")
    shown = buf.getvalue().count("broken reference")
    assert shown == ui.FINDING_CAP
    assert "run with -v" in buf.getvalue()

    verbose, buf2 = _console(ui.VERBOSE)
    for i in range(ui.FINDING_CAP + 5):
        verbose.issue("warning", f"broken reference number {i}")
    assert buf2.getvalue().count("broken reference") == ui.FINDING_CAP + 5


def test_errors_are_never_capped():
    con, buf = _console()
    for i in range(ui.FINDING_CAP + 5):
        con.issue("error", f"missing file {i}")
    assert buf.getvalue().count("missing file") == ui.FINDING_CAP + 5


def test_finding_shows_where_it_came_from():
    con, buf = _console()
    con.issue("error", "reference has no caption", location="04-chapter.md:12")
    line = buf.getvalue().splitlines()[0]
    assert line.startswith("    x 04-chapter.md:12")
    assert line.endswith("reference has no caption")


def test_quiet_prints_produced_paths_to_stdout(tmp_path, monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(ui, "_stdout", ui.Console(stdout, is_stdout=True))
    con, buf = _console(ui.QUIET)
    docx = tmp_path / "out.docx"
    docx.write_bytes(b"x")
    con.footer_ok("build finished", artifacts=[("document", docx)])
    assert buf.getvalue() == ""
    assert stdout.getvalue().strip() == str(docx.resolve())


def test_json_mode_records_the_whole_report(tmp_path, monkeypatch):
    stdout = io.StringIO()
    monkeypatch.setattr(ui, "_stdout", ui.Console(stdout, is_stdout=True))
    monkeypatch.setattr(ui, "_console", ui.Console(io.StringIO()))
    ui.configure(verbosity=ui.NORMAL, color=False, unicode=False, json_output=True)
    con = ui.console()

    con.header("build", "example", "word engine")
    con.field("output", "example/VKR-example.docx")
    con.step("merge").finish("10 files")
    con.step("lint").warn("1 warning")
    con.issue("warning", "unknown reference", location="04-chapter.md:12")
    con.result(True, "python", "3.12.3")
    con.section("volume")
    con.metric("words", "1 619")
    docx = tmp_path / "out.docx"
    docx.write_bytes(b"xyz")
    con.footer_ok("build finished", artifacts=[("document", docx)], elapsed=2.0)
    ui.close()

    document = json.loads(stdout.getvalue())
    assert document["command"] == "build"
    assert document["context"] == ["example", "word engine"]
    assert document["fields"]["output"] == "example/VKR-example.docx"
    assert [s["name"] for s in document["steps"]] == ["merge", "lint"]
    assert document["steps"][1]["outcome"] == "warning"
    assert document["findings"] == [
        {
            "severity": "warning",
            "message": "unknown reference",
            "location": "04-chapter.md:12",
        }
    ]
    assert document["checks"][0] == {
        "name": "python", "ok": True, "detail": "3.12.3"
    }
    assert document["metrics"]["volume"]["words"] == "1 619"
    assert document["artifacts"][0]["bytes"] == 3
    assert document["result"]["status"] == "ok"
    assert document["result"]["warnings"] == 1


def test_display_width_counts_columns_not_code_points():
    assert ui.char_width("a") == 1
    assert ui.char_width("я") == 1
    assert ui.char_width("✓") == 1
    assert ui.char_width("▲") == 1
    assert ui.char_width("⚠") == 2
    assert ui.char_width("漢") == 2
    assert ui.char_width("́") == 0
    assert ui.text_width("\x1b[32mok\x1b[0m") == 2


def test_wide_characters_do_not_push_the_timing_column():
    con, buf = _console()
    con.configure(verbosity=ui.NORMAL, color=False, unicode=True)
    con.step("markdown").finish("28 headings")
    con.step("document").finish("漢字の文書.docx")
    plain, wide = buf.getvalue().splitlines()
    assert ui.text_width(plain) == ui.text_width(wide)


def test_live_region_survives_a_narrower_window(monkeypatch):
    con, buf = _live_console()
    monkeypatch.setattr(type(con), "width", property(lambda self: 60))
    step = con.step("layout", "x" * 50)
    step.update(fraction=0.5)
    monkeypatch.setattr(type(con), "width", property(lambda self: 30))
    step.finish("done")
    text = buf.getvalue()
    assert text.count("\x1b[A") >= 3
    assert _strip(text).rstrip().splitlines()[-1].lstrip().startswith("+ layout")


def test_a_warning_inherits_the_source_being_rendered(monkeypatch):
    from vkr import logging_setup

    con, buf = _console()
    monkeypatch.setattr(ui, "_console", con)
    logging_setup.setup_logging(ui.NORMAL)
    try:
        logging_setup.set_source_location("07-sources.md:42")
        logging_setup.get_logger("crossref").warning("unknown reference [fig:k]")
        logging_setup.set_source_location()
        logging_setup.get_logger("document").warning("could not set metadata")
    finally:
        logging_setup.set_source_location()

    located, plain = buf.getvalue().splitlines()
    assert located.startswith("    ! 07-sources.md:42")
    assert plain.startswith("    ! could not set metadata")


def _stats_console():
    import io

    buf = io.StringIO()
    con = ui.Console(buf)
    con.configure(verbosity=ui.NORMAL, color=False, unicode=False)
    return con, buf


def test_the_mascot_fills_the_empty_column_beside_the_metrics(monkeypatch):
    monkeypatch.setattr(ui.Console, "width", property(lambda self: 78))
    con, buf = _stats_console()
    con.start_aside(mascots.STRETCHING, top=1)
    con.section("structure")
    for label in ("sections", "chapters", "appendices"):
        con.metric(label, "5")

    lines = buf.getvalue().split("\n")
    drawn = [ln for ln in lines if ",-." in ln]
    assert drawn, buf.getvalue()
    assert all(ln.index(",-.") >= ui.METRIC_END for ln in drawn)
    assert all(ui.text_width(ln) <= 78 for ln in lines)
    assert any(ln.startswith(ui.INDENT + "  sections") for ln in lines)


def test_a_narrow_terminal_gets_the_numbers_and_no_cat(monkeypatch):
    monkeypatch.setattr(ui.Console, "width", property(lambda self: ui.MIN_WIDTH))
    con, buf = _stats_console()
    con.start_aside(mascots.STRETCHING)
    con.section("structure")
    con.metric("sections", "5")

    text = buf.getvalue()
    assert "sections" in text and "5" in text
    assert "vkr |" not in text


def test_an_unexpectedly_wide_row_makes_the_drawing_give_way(monkeypatch):
    monkeypatch.setattr(ui.Console, "width", property(lambda self: 78))
    con, buf = _stats_console()
    con.start_aside(mascots.PEEKING)
    con.result(True, "short", "ok")
    con.result(True, "wide", "a" * 60)
    con.result(True, "after", "ok")

    lines = [ln for ln in buf.getvalue().split("\n") if ln.strip()]
    assert "_._" in lines[0]
    assert all("`" not in ln for ln in lines[1:])
    drawn = [ln for ln in lines if "_._" in ln]
    assert all(ui.text_width(ln) <= 78 for ln in drawn)


def test_the_roomy_cats_all_fit_the_space_they_are_drawn_in():
    room = ui.MAX_WIDTH - ui.METRIC_END
    for art in mascots.ROOMY:
        assert art, "an empty drawing would consume rows and show nothing"
        assert max(ui.text_width(line) for line in art) + 2 <= room
        assert len(art) <= 20


def test_a_random_cat_is_one_of_the_three():
    import random

    picked = {id(mascots.roomy(random.Random(seed))) for seed in range(50)}
    assert picked <= {id(art) for art in mascots.ROOMY}
    assert len(picked) == len(mascots.ROOMY), "the choice never varies"


def test_a_row_past_the_drawing_column_never_shifts_it(monkeypatch):
    monkeypatch.setattr(ui.Console, "width", property(lambda self: 78))
    con, buf = _stats_console()
    con.start_aside(mascots.PEEKING, top=1)
    con.result(True, "system", "Linux 6.16.8-1-MANJARO (x86_64)")
    for label in ("python", "python-docx", "pyyaml", "word"):
        con.result(True, label, "installed")

    col = con._aside_column
    lines = [ln for ln in buf.getvalue().split("\n") if ln.strip()]

    assert "_._" not in lines[0], "the row too long for the column carries nothing"
    assert [ln[col:].rstrip() for ln in lines[1:5]] == [
        a.rstrip() for a in mascots.PEEKING
    ], buf.getvalue()
    assert all(ui.text_width(ln) <= 78 for ln in lines)
