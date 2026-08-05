import time

from vkr.watch import DebouncedTrigger


def test_debounced_trigger_calls_once():
    calls = {"n": 0}

    def rebuild():
        calls["n"] += 1

    trigger = DebouncedTrigger(rebuild, debounce_ms=100)
    trigger.notify()
    trigger.notify()
    time.sleep(0.25)
    assert calls["n"] == 1


def test_com_is_initialised_for_the_thread_that_will_use_word(monkeypatch):
    import sys
    import types

    calls = []
    fake = types.ModuleType("pythoncom")
    fake.CoInitialize = lambda: calls.append("init")
    fake.CoUninitialize = lambda: calls.append("uninit")
    monkeypatch.setitem(sys.modules, "pythoncom", fake)

    from vkr.word_com import com_initialised

    with com_initialised("test"):
        calls.append("work")
    assert calls == ["init", "work", "uninit"]


def test_a_thread_that_already_has_com_is_left_alone(monkeypatch):
    import sys
    import types

    calls = []
    fake = types.ModuleType("pythoncom")

    def _refuse():
        raise OSError("RPC_E_CHANGED_MODE")

    fake.CoInitialize = _refuse
    fake.CoUninitialize = lambda: calls.append("uninit")
    monkeypatch.setitem(sys.modules, "pythoncom", fake)

    from vkr.word_com import com_initialised

    with com_initialised("test"):
        calls.append("work")
    assert calls == ["work"]


def test_two_changes_never_rebuild_at_the_same_time():
    import threading
    import time

    from vkr.watch import DebouncedTrigger

    overlaps = []
    running = threading.Lock()

    def rebuild():
        if not running.acquire(blocking=False):
            overlaps.append(1)
            return
        time.sleep(0.2)
        running.release()

    trigger = DebouncedTrigger(rebuild, debounce_ms=50)
    trigger.notify()
    time.sleep(0.12)
    trigger.notify()
    time.sleep(0.6)

    assert overlaps == []


def test_a_rebuild_will_not_ship_markdown_that_build_would_refuse(tmp_path, monkeypatch):
    import types

    from vkr import cli, watch

    markdown = tmp_path / "md"
    markdown.mkdir()
    (markdown / "01-ch.md").write_text(
        "# 1 Глава\n\nТекст.\n\n"
        "Таблица {t} - Демонстрация\n\n"
        "| Конструкция | Смысл |\n|---|---|\n| [рис:k] | ссылка |\n",
        encoding="utf-8",
    )
    out = tmp_path / "out.docx"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"active_profile: t\nprofiles:\n  t:\n    docx: {out}\n"
        "    markdown_dir: md\n    markdown_files:\n      - 01-ch.md\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(watch, "require_watchdog", lambda: None)
    monkeypatch.setattr(watch, "run_watch", lambda paths, rebuild, **kw: rebuild())

    cli._cmd_watch(
        types.SimpleNamespace(
            config=str(config_path), defaults=None, profile=None,
            pagination_engine="libreoffice",
        )
    )

    assert not out.exists(), "a broken reference must stop the rebuild, not ship"


def test_stopping_waits_for_the_rebuild_in_flight(monkeypatch):
    import threading
    import time

    from vkr import watch as watch_mod

    order = []

    def rebuild():
        time.sleep(0.3)
        order.append("rebuild finished")

    trigger = watch_mod.DebouncedTrigger(rebuild, debounce_ms=50)
    trigger.notify()
    time.sleep(0.15)
    assert trigger.busy()

    trigger.wait_idle()
    order.append("watch stopped")
    assert order == ["rebuild finished", "watch stopped"]


def test_a_change_seen_at_the_last_moment_is_not_acted_on():
    from vkr.watch import DebouncedTrigger

    import time

    fired = []
    trigger = DebouncedTrigger(lambda: fired.append(1), debounce_ms=100)
    trigger.notify()
    trigger.cancel()
    time.sleep(0.3)

    assert fired == []
    assert not trigger.busy()


def test_a_rebuild_exports_the_pdf_when_it_is_asked_for(tmp_path, monkeypatch):
    import types

    from vkr import cli, pdf_export, watch

    markdown = tmp_path / "md"
    markdown.mkdir()
    (markdown / "01-ch.md").write_text("# 1 Глава\n\nТекст.\n", encoding="utf-8")
    out = tmp_path / "out.docx"
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        f"active_profile: t\nprofiles:\n  t:\n    docx: {out}\n"
        "    markdown_dir: md\n    markdown_files:\n      - 01-ch.md\n",
        encoding="utf-8",
    )

    exported = []
    monkeypatch.setattr(watch, "require_watchdog", lambda: None)
    monkeypatch.setattr(watch, "run_watch", lambda paths, rebuild, **kw: rebuild())
    monkeypatch.setattr(
        cli, "_run_document_build", lambda *a, **kw: out
    )
    monkeypatch.setattr(
        pdf_export,
        "export_pdf",
        lambda docx, pdf=None, **kw: exported.append(docx) or tmp_path / "out.pdf",
    )
    (tmp_path / "out.pdf").write_bytes(b"%PDF-1.7\n")

    def _run(pdf):
        exported.clear()
        cli._cmd_watch(
            types.SimpleNamespace(
                config=str(config_path), defaults=None, profile=None,
                pagination_engine="libreoffice", pdf=pdf, pdf_engine="libreoffice",
            )
        )
        return list(exported)

    assert _run(True), "with --pdf the rebuild has to export one"
    assert _run(False) == [], "without it nothing is exported"


def test_saves_during_a_rebuild_collapse_into_one_more_pass():
    import time

    from vkr.watch import DebouncedTrigger

    builds = []

    def rebuild():
        builds.append(1)
        time.sleep(0.4)

    trigger = DebouncedTrigger(rebuild, debounce_ms=50)
    trigger.notify()
    time.sleep(0.15)
    for _ in range(5):
        trigger.notify()
        time.sleep(0.05)
    time.sleep(1.5)

    assert len(builds) == 2
    assert not trigger.busy()


def test_stopping_drops_the_pass_that_had_not_started():
    import time

    from vkr.watch import DebouncedTrigger

    builds = []

    def rebuild():
        builds.append(1)
        time.sleep(0.4)

    trigger = DebouncedTrigger(rebuild, debounce_ms=50)
    trigger.notify()
    time.sleep(0.15)
    trigger.notify()
    time.sleep(0.1)
    trigger.cancel()
    trigger.wait_idle()

    assert len(builds) == 1


def test_a_save_at_the_wrong_moment_is_not_forgotten():
    import threading
    import time

    from vkr.watch import DebouncedTrigger

    builds = []
    first = threading.Event()

    def rebuild():
        builds.append(1)
        if len(builds) == 1:
            first.set()
            time.sleep(0.3)

    trigger = DebouncedTrigger(rebuild, debounce_ms=50)
    trigger.notify()
    first.wait(1.0)
    trigger.notify()
    time.sleep(1.0)

    assert len(builds) == 2, "the change arrived and must be built"
    assert not trigger.busy()


def test_a_pass_that_handed_back_does_not_take_the_lock_again():
    from vkr.watch import DebouncedTrigger

    trigger = DebouncedTrigger(lambda: None, debounce_ms=50)
    real = trigger._state
    entered = []

    class _Counting:
        def __enter__(self):
            entered.append(1)
            return real.__enter__()

        def __exit__(self, *exc):
            return real.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(real, name)

    trigger._state = _Counting()
    trigger._fire()

    assert len(entered) == 2, (
        "once to start, once to hand back; a third would clear flags that by "
        "then belong to the pass after it"
    )
    assert not trigger.busy()


def test_a_sibling_directory_sharing_a_prefix_is_not_watched(tmp_path):
    from pathlib import Path

    watched = tmp_path / "code"
    sibling = tmp_path / "code2"
    watched.mkdir()
    sibling.mkdir()

    roots = {watched.resolve()}
    inside = (watched / "a.py").resolve()
    outside = (sibling / "a.py").resolve()

    assert any(inside.is_relative_to(r) for r in roots)
    assert not any(outside.is_relative_to(r) for r in roots)
    assert str(outside).startswith(str(watched)), (
        "the old string test would have matched this one"
    )
