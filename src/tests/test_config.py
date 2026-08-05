import pytest

from vkr import config
from vkr.config import ConfigError, WordNamesConfig


def test_load_example_profile(project_root):
    cfg_path = project_root / "config.yaml"
    cfg = config.load_build_config(str(cfg_path))

    assert cfg.profile_name == "example"
    assert len(cfg.profile.markdown_files) == 10
    assert cfg.profile.docx.name == "VKR-example.docx"
    assert cfg.profile.docx.parent == (project_root / "example").resolve()
    assert cfg.profile.markdown_dir == (project_root / "example" / "md").resolve()
    assert cfg.profile.images_dir == (project_root / "example" / "images").resolve()


def test_defaults_only_pagination_engine(project_root):
    cfg_path = project_root / "config.yaml"
    cfg = config.load_build_config(str(cfg_path))
    assert cfg.build.pagination_engine in ("auto", "word", "libreoffice")


def test_unknown_profile_raises(project_root):
    cfg_path = project_root / "config.yaml"
    with pytest.raises(ConfigError):
        config.load_build_config(str(cfg_path), profile="does-not-exist")


def test_deep_merge_overrides_nested():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    override = {"a": {"y": 20, "z": 30}}
    merged = config._deep_merge(base, override)
    assert merged == {"a": {"x": 1, "y": 20, "z": 30}, "b": 3}


def test_word_styles_reject_unknown_key():
    with pytest.raises(ConfigError):
        config._parse_word_styles({"not_a_real_style": "X"})


def test_word_styles_defaults_roundtrip():
    names = WordNamesConfig().to_mapping()
    assert names["heading_1"] == "Heading 1"
    assert "body" in names


def test_missing_user_config_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        config.load_build_config(str(tmp_path / "nope.yaml"))


def test_build_pdf_defaults_off():
    cfg = config._parse_build({})
    assert cfg.pdf is False
    assert cfg.pdf_engine is None


def test_build_pdf_options_parsed():
    cfg = config._parse_build(
        {"build": {"pdf": True, "pdf_engine": "libreoffice"}}
    )
    assert cfg.pdf is True
    assert cfg.pdf_engine == "libreoffice"


def test_build_pdf_rejects_bad_engine():
    with pytest.raises(ConfigError):
        config._parse_build({"build": {"pdf_engine": "ghostscript"}})


def test_build_pdf_rejects_non_bool():
    with pytest.raises(ConfigError):
        config._parse_build({"build": {"pdf": "yes"}})


def test_metadata_absent_is_empty():
    meta = config._parse_metadata({})
    assert meta.to_mapping() == {}


def test_metadata_parsed_and_filtered():
    meta = config._parse_metadata(
        {"metadata": {"title": "T", "author": "A", "subject": None}}
    )
    mapping = meta.to_mapping()
    assert mapping == {"title": "T", "author": "A"}


def test_metadata_dates_accept_a_date_or_a_date_with_a_time():
    import yaml

    forms = {
        "created: 2026-01-15": "2026-01-15",
        "created: 2026-01-15 10:30:00": "2026-01-15 10:30:00",
        "created: 2026-01-15T10:30:00": "2026-01-15 10:30:00",
        'created: "2026-01-15"': "2026-01-15",
        'created: "15.01.2026"': "15.01.2026",
    }
    for line, expected in forms.items():
        raw = yaml.safe_load("metadata:\n  " + line)
        assert config._parse_metadata(raw).created == expected, line


def test_metadata_dates_keep_the_instant_when_an_offset_is_given():
    import datetime as dt
    import yaml

    from vkr.docx.document import parse_meta_datetime

    raw = yaml.safe_load("metadata:\n  modified: 2026-01-15 10:30:00+03:00")
    parsed = parse_meta_datetime(config._parse_metadata(raw).modified)

    assert parsed == dt.datetime(2026, 1, 15, 7, 30, 0)
    assert parsed.tzinfo is None


def test_metadata_rejects_unknown_key():
    with pytest.raises(ConfigError):
        config._parse_metadata({"metadata": {"nope": "x"}})


def test_style_page_number_from_defaults(project_root):
    cfg = config.load_build_config(str(project_root / "config.yaml"))
    assert cfg.style.typography.page_number_from == config.default_page_number_from()


def test_style_page_number_from_override():
    style = config._parse_style(
        {"style": {"page": {"number_from": 10}, "figures": {}}}
    )
    assert style.typography.page_number_from == 10


def test_style_page_number_from_rejects_invalid():
    with pytest.raises(ConfigError):
        config._flatten_style_block({"page": {"number_from": 0}, "figures": {}})


def test_metadata_rejects_non_string():
    with pytest.raises(ConfigError):
        config._parse_metadata({"metadata": {"title": 5}})


def test_build_sort_dictionary_lists_default(project_root):
    cfg = config.load_build_config(str(project_root / "config.yaml"))
    assert cfg.build.sort_dictionary_lists is False


def test_lint_defaults():
    cfg = config._parse_lint({})
    assert cfg.strict is False


def test_stats_defaults():
    cfg = config._parse_stats({})
    assert cfg.min_sources is None
    assert cfg.page_min is None


def test_watch_debounce_defaults_and_overrides():
    assert config._parse_watch({}).debounce_ms == 1000
    assert config._parse_watch({"watch": {"debounce_ms": 2500}}).debounce_ms == 2500
    assert config._parse_watch({"watch": {"debounce_ms": None}}).debounce_ms == 1000


def test_watch_rejects_nonsense():
    for block in ({"debounce_ms": 0}, {"debounce_ms": 999999},
                  {"debounce_ms": "fast"}, {"debounce_ms": True}):
        with pytest.raises(config.ConfigError):
            config._parse_watch({"watch": block})
    with pytest.raises(config.ConfigError):
        config._parse_watch({"watch": {"debounce": 500}})
    with pytest.raises(config.ConfigError):
        config._parse_watch({"watch": 500})


def test_the_shipped_defaults_carry_a_watch_section(project_root):
    cfg = config.load_build_config(project_root / "config.yaml")
    assert cfg.watch.debounce_ms >= 50
