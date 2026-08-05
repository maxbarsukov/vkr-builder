import sys

from vkr import engines, env_check, pagination


def _pretend_libreoffice_is_the_engine(monkeypatch):
    monkeypatch.setattr(engines, "resolve", lambda *a, **kw: engines.LIBREOFFICE)
    monkeypatch.setattr(
        engines,
        "statuses",
        lambda *a, **kw: [engines.EngineStatus(engines.LIBREOFFICE, True, "soffice")],
    )


def test_core_dependencies_present():
    assert env_check.check_python().ok
    assert env_check.check_python_docx().ok
    assert env_check.check_pyyaml().ok


def test_run_checks_includes_pagination():
    results = env_check.run_checks(
        pagination_engine="libreoffice", libreoffice_path=None
    )
    names = [r.name for r in results]
    assert "pagination: libreoffice" in names
    assert not any(n.startswith("pdf:") for n in names)


def test_run_checks_adds_pdf_when_requested():
    results = env_check.run_checks(
        pagination_engine="libreoffice",
        libreoffice_path=None,
        pdf=True,
        pdf_engine="libreoffice",
    )
    assert any(n.startswith("pdf:") for n in [r.name for r in results])


def test_libreoffice_pagination_asks_for_the_uno_bridge(monkeypatch):
    _pretend_libreoffice_is_the_engine(monkeypatch)
    monkeypatch.setattr(
        pagination, "uno_bridge_python", lambda path=None: "/usr/bin/python3"
    )

    results = env_check.run_checks(
        pagination_engine="libreoffice", libreoffice_path=None
    )
    bridge = next(r for r in results if r.name == "uno bridge")

    assert bridge.ok
    assert bridge.detail == "/usr/bin/python3"


def test_libreoffice_without_the_bridge_fails_the_checks(monkeypatch):
    _pretend_libreoffice_is_the_engine(monkeypatch)

    def _missing(path=None):
        raise FileNotFoundError("no Python with the UNO bridge found")

    monkeypatch.setattr(pagination, "uno_bridge_python", _missing)

    results = env_check.run_checks(
        pagination_engine="libreoffice", libreoffice_path=None
    )
    bridge = next(r for r in results if r.name == "uno bridge")

    assert not bridge.ok
    assert bridge.required
    assert "UNO bridge" in bridge.detail
    assert bridge.remedy


def test_the_bridge_remedy_names_the_package_debian_keeps_it_in(monkeypatch):
    import sys

    _pretend_libreoffice_is_the_engine(monkeypatch)

    def _missing(path=None):
        raise FileNotFoundError("no Python with the UNO bridge found")

    monkeypatch.setattr(pagination, "uno_bridge_python", _missing)
    monkeypatch.setattr(sys, "platform", "linux")

    bridge = env_check.check_uno_bridge(None)

    assert bridge.remedy == "sudo apt install python3-uno"


def test_word_pagination_is_not_asked_about_the_bridge(monkeypatch):
    monkeypatch.setattr(engines, "resolve", lambda *a, **kw: engines.WORD)
    monkeypatch.setattr(
        engines,
        "statuses",
        lambda *a, **kw: [engines.EngineStatus(engines.WORD, True, "Word 16")],
    )

    results = env_check.run_checks(pagination_engine="word", libreoffice_path=None)

    assert not any(r.name == "uno bridge" for r in results)


def test_no_libreoffice_is_not_reported_as_a_missing_bridge(monkeypatch):
    monkeypatch.setattr(engines, "resolve", lambda *a, **kw: engines.LIBREOFFICE)
    monkeypatch.setattr(
        engines,
        "statuses",
        lambda *a, **kw: [
            engines.EngineStatus(
                engines.LIBREOFFICE, False, "LibreOffice is not installed"
            )
        ],
    )

    def _never_called(path=None):
        raise AssertionError("the bridge must not be probed without LibreOffice")

    monkeypatch.setattr(pagination, "uno_bridge_python", _never_called)

    results = env_check.run_checks(
        pagination_engine="libreoffice", libreoffice_path=None
    )

    assert not any(r.name == "uno bridge" for r in results)
    assert not any("uno" in r.remedy for r in results)
    assert any(
        r.remedy and not r.ok for r in results
    ), "the missing engine must still say what to do about it"


def test_a_configured_path_that_is_wrong_is_not_an_install_problem(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    assert env_check.engine_remedy(engines.LIBREOFFICE, "/nowhere/soffice") == (
        "fixing build.libreoffice_path in config.yaml"
    )
    assert env_check.engine_remedy(engines.LIBREOFFICE, None) == (
        "sudo apt install libreoffice-writer"
    )


def test_word_is_never_told_to_be_installed_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert env_check.engine_remedy(engines.WORD) == ""


def test_doctor_reports_the_os_because_the_bug_template_asks_for_it():
    import platform

    results = env_check.run_checks(pagination_engine="auto", libreoffice_path=None)
    system = next(r for r in results if r.name == "platform")

    assert system.detail.startswith(platform.system() or sys.platform)
    assert platform.machine() in system.detail


def test_the_platform_row_does_not_inflate_the_check_count():
    results = env_check.run_checks(pagination_engine="auto", libreoffice_path=None)
    system = next(r for r in results if r.name == "platform")

    assert system.ok, "it states a fact, it cannot fail"
    assert not system.required, "and must not be counted among the checks"
