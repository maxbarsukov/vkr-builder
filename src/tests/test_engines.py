import pytest

from vkr import engines


@pytest.fixture(autouse=True)
def _clean_cache():
    engines.clear_cache()
    yield
    engines.clear_cache()


def _fake(word: bool, libreoffice: bool, monkeypatch):
    monkeypatch.setattr(
        engines,
        "word_status",
        lambda: engines.EngineStatus(
            engines.WORD, word, "Word 16" if word else "Microsoft Word is not installed"
        ),
    )
    monkeypatch.setattr(
        engines,
        "libreoffice_status",
        lambda configured_path=None: engines.EngineStatus(
            engines.LIBREOFFICE,
            libreoffice,
            "/usr/bin/soffice" if libreoffice else "LibreOffice is not installed",
        ),
    )


def test_auto_prefers_word_when_both_are_installed(monkeypatch):
    _fake(word=True, libreoffice=True, monkeypatch=monkeypatch)
    assert engines.resolve("auto") == "word"


def test_auto_falls_back_to_libreoffice(monkeypatch):
    _fake(word=False, libreoffice=True, monkeypatch=monkeypatch)
    assert engines.resolve("auto") == "libreoffice"


def test_auto_without_any_engine_says_so(monkeypatch):
    _fake(word=False, libreoffice=False, monkeypatch=monkeypatch)
    with pytest.raises(engines.EngineNotAvailable) as exc:
        engines.resolve("auto")
    assert "Word" in str(exc.value) and "LibreOffice" in str(exc.value)


def test_a_named_engine_is_honoured_even_if_detection_disagrees(monkeypatch):
    _fake(word=False, libreoffice=False, monkeypatch=monkeypatch)
    assert engines.resolve("word") == "word"
    assert engines.resolve("libreoffice") == "libreoffice"


def test_an_empty_engine_means_auto(monkeypatch):
    _fake(word=True, libreoffice=True, monkeypatch=monkeypatch)
    assert engines.resolve(None) == "word"
    assert engines.resolve("") == "word"
    assert engines.resolve("  AUTO  ") == "word"


def test_an_unknown_engine_is_rejected():
    with pytest.raises(ValueError) as exc:
        engines.resolve("ghostscript")
    assert "auto, word, libreoffice" in str(exc.value)


def test_describe_says_when_the_engine_was_chosen_automatically():
    assert engines.describe("word", "auto") == "word engine (auto)"
    assert engines.describe("word", None) == "word engine (auto)"
    assert engines.describe("libreoffice", "libreoffice") == "libreoffice engine"


def test_detection_runs_once(monkeypatch):
    calls = {"n": 0}

    def counted():
        calls["n"] += 1
        return engines.EngineStatus(engines.WORD, True, "Word 16")

    monkeypatch.setattr(engines, "_detect_word", counted)
    engines.word_status()
    engines.word_status()
    assert calls["n"] == 1

    engines.clear_cache()
    engines.word_status()
    assert calls["n"] == 2


def test_real_detection_answers_for_this_machine():
    statuses = engines.statuses()
    assert [s.name for s in statuses] == [engines.WORD, engines.LIBREOFFICE]
    for status in statuses:
        assert isinstance(status.available, bool)
        assert status.detail
    if engines.installed():
        assert engines.resolve("auto") in engines.ENGINES
