import io

from vkr import ui
from vkr.progress import (
    PHASE_TABLES,
    PHASE_TOC,
    BuildReporter,
    create_build_reporter,
    estimate_build_work,
)


def _table(rows: int) -> dict:
    return {"type": "table", "rows": [[f"r{i}"] for i in range(rows)]}


def _reporter(enabled: bool = True) -> tuple[BuildReporter, io.StringIO]:
    buf = io.StringIO()
    con = ui.Console(buf)
    con.configure(verbosity=ui.NORMAL, color=False, unicode=False)
    return BuildReporter(enabled=enabled, console=con), buf


def test_estimate_simple_chapter():
    elements = [
        {"type": "heading", "text": "Chapter"},
        {"type": "paragraph", "text": "Hi"},
    ]
    est = estimate_build_work(elements, include_toc=False, do_continuation=False)
    assert est.layout_passes == 1


def test_estimate_table_continuation_from_row_counts():
    elements = [_table(60), _table(30), _table(10)]
    est = estimate_build_work(elements, include_toc=False, do_continuation=True)
    assert est.estimated_table_splits == 3
    assert est.layout_passes == 4


def test_estimate_grows_with_the_table_of_contents():
    elements = [{"type": "heading", "text": f"H{i}"} for i in range(60)]
    est = estimate_build_work(elements, include_toc=True, do_continuation=False)
    assert est.layout_passes >= 3


def test_reporter_renders_one_step_per_phase(tmp_path):
    docx = tmp_path / "out.docx"
    docx.write_bytes(b"x" * 2048)

    prog, buf = _reporter()
    prog.read()
    prog.read_done("28 headings, 4 tables")
    prog.layout(3)
    prog.layout_pass(2, 3, PHASE_TOC, progress=0.5)
    prog.layout_done(3, table_breaks=2)
    prog.save()
    prog.save_done(docx)

    lines = [ln for ln in buf.getvalue().splitlines() if ln.strip()]
    assert len(lines) == 3
    assert "+ markdown" in lines[0] and "28 headings, 4 tables" in lines[0]
    assert "+ layout" in lines[1] and "3 passes, 2 table breaks" in lines[1]
    assert "+ document" in lines[2] and "out.docx" in lines[2]
    assert "2 KB" in lines[2]


def test_reporter_lists_its_outputs(tmp_path):
    docx = tmp_path / "out.docx"
    docx.write_bytes(b"x")
    pdf = tmp_path / "out.pdf"
    pdf.write_bytes(b"x")

    prog, _ = _reporter()
    prog.save()
    prog.save_done(docx)
    prog.pdf("word")
    prog.pdf_done(pdf)
    assert [label for label, _ in prog.outputs] == ["document", "pdf"]
    assert [path.name for _, path in prog.outputs] == ["out.docx", "out.pdf"]


def test_reporter_marks_the_failing_step():
    prog, buf = _reporter()
    prog.layout(2)
    prog.layout_pass(1, 2, PHASE_TABLES)
    prog.fail("Word is not available")
    text = buf.getvalue()
    assert "x layout" in text
    assert "Word is not available" in text


def test_disabled_reporter_is_silent(tmp_path):
    prog, buf = _reporter(enabled=False)
    prog.read()
    prog.read_done("28 headings")
    prog.layout(2)
    prog.layout_pass(1, 2, PHASE_TOC)
    prog.layout_done(2)
    prog.save()
    prog.save_done(tmp_path / "out.docx")
    assert buf.getvalue() == ""
    assert prog.enabled is False


def test_create_build_reporter_defaults_to_enabled():
    assert create_build_reporter().enabled is True
    assert create_build_reporter(enabled=False).enabled is False
