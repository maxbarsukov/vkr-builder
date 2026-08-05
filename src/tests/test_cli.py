import sys
import types
from pathlib import Path

import pytest

from vkr import cli, config, ui
from vkr.paths import project_root, set_project_root


def _bundle_md() -> Path:
    cfg = config.load_build_config(project_root() / "config.yaml")
    return cfg.profile.markdown_dir / "_bundle.md"


class _Profile:
    def __init__(self, config_path: Path, bundle: Path) -> None:
        self.config = str(config_path)
        self.bundle = bundle


@pytest.fixture
def tiny_profile(tmp_path) -> _Profile:
    markdown_dir = tmp_path / "md"
    markdown_dir.mkdir()
    (markdown_dir / "01-chapter.md").write_text(
        "# 1 Глава\n\nАбзац текста для сборки.\n", encoding="utf-8"
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "active_profile: tiny\n"
        "profiles:\n"
        "  tiny:\n"
        f"    docx: {tmp_path / 'out.docx'}\n"
        "    markdown_dir: md\n"
        "    markdown_files:\n"
        "      - 01-chapter.md\n",
        encoding="utf-8",
    )
    return _Profile(config_path, markdown_dir / "_bundle.md")


def test_profiles_lists_active_example(capsys):
    rc = cli.main(["profiles", "--config", "config.yaml"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "example (active)" in out
    assert all(ui.text_width(line) <= ui.MAX_WIDTH for line in out.split("\n"))


def test_validate_ok():
    assert cli.main(["validate", "--config", "config.yaml"]) == 0


def test_unknown_profile_returns_error():
    rc = cli.main(
        ["build", "--config", "config.yaml", "--profile", "nope", "--skip-docx"]
    )
    assert rc == 1


def test_build_skip_docx_creates_bundle(tiny_profile):
    rc = cli.main(["build", "--config", tiny_profile.config, "--skip-docx"])
    assert rc == 0
    assert tiny_profile.bundle.is_file()


def test_default_command_is_build(tiny_profile):
    rc = cli.main(["--config", tiny_profile.config, "--skip-docx"])
    assert rc == 0
    assert tiny_profile.bundle.is_file()


def test_lint_clean_example():
    bundle = _bundle_md()
    try:
        assert cli.main(["lint", "--config", "config.yaml"]) == 0
    finally:
        if bundle.is_file():
            bundle.unlink()


def test_stats_runs(tiny_profile):
    assert cli.main(["stats", "--config", tiny_profile.config]) == 0


def test_doctor_returns_status():
    rc = cli.main(["doctor", "--config", "config.yaml"])
    assert rc in (0, 1)


def test_doctor_hints_with_the_remedy_of_what_failed(monkeypatch, capsys):
    from vkr import env_check

    monkeypatch.setattr(
        env_check,
        "run_checks",
        lambda **kw: [
            env_check.CheckResult(
                "uno bridge",
                False,
                "no Python with the UNO bridge",
                label="uno",
                remedy="sudo apt install python3-uno",
            )
        ],
    )

    rc = cli.main(["doctor", "--config", "config.yaml"])
    err = capsys.readouterr().err

    assert rc == 1
    assert "sudo apt install python3-uno" in err
    assert "pip install -r requirements.txt" not in err


def test_help_lists_commands(capsys):
    rc = cli.main(["help"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Commands" in out
    assert "build" in out
    assert "--profile" in out
    assert "Global options" in out
    for line in out.splitlines():
        if line.startswith("      --pagination-engine"):
            assert "  Layout engine" in line
            break
    else:
        raise AssertionError("expected aligned --pagination-engine line in help output")


def test_preview_output_paths(tmp_path):
    md = tmp_path / "example" / "md" / "04-chapter1.md"
    md.parent.mkdir(parents=True)
    md.write_text("# ch\n", encoding="utf-8")

    docx = cli._preview_output_path(md, None)
    assert docx == md.parent / "04-chapter1.preview.docx"
    assert cli._preview_pdf_path(md) == md.parent / "04-chapter1.preview.pdf"

    custom = cli._preview_output_path(md, tmp_path / "out" / "custom.docx")
    assert custom == (tmp_path / "out" / "custom.docx").resolve()


def test_help_subcommand(capsys):
    rc = cli.main(["help", "build"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "--skip-docx" in out
    assert "--pagination-engine" in out


def test_init_creates_config(tmp_path):
    real_root = project_root()
    set_project_root(tmp_path)
    try:
        args = types.SimpleNamespace(force=False)
        assert cli._cmd_init(args) == 0
        written = (tmp_path / "config.yaml").read_text(encoding="utf-8")
        assert "active_profile: example" in written

        assert cli._cmd_init(args) == 1

        args_force = types.SimpleNamespace(force=True)
        assert cli._cmd_init(args_force) == 0
    finally:
        set_project_root(real_root)


def _reset_program_name(monkeypatch, value=None):
    monkeypatch.setattr(ui, "_program", "")
    if value is None:
        monkeypatch.delenv("VKR_PROG", raising=False)
    else:
        monkeypatch.setenv("VKR_PROG", value)


def test_program_name_comes_from_the_launcher(monkeypatch):
    _reset_program_name(monkeypatch, "vkr-builder.bat")
    assert ui.program_name() == "vkr-builder.bat"

    _reset_program_name(monkeypatch, "./vkr-builder.sh")
    assert ui.program_name() == "./vkr-builder.sh"


def test_program_name_falls_back_to_the_documented_launcher(monkeypatch):
    _reset_program_name(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["main.py"])
    assert ui.program_name() == "python main.py"

    _reset_program_name(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["/usr/bin/pytest"])
    assert ui.program_name() in ("vkr-builder.bat", "./vkr-builder.sh")


def test_help_names_the_launcher_not_the_entry_point(monkeypatch, capsys):
    _reset_program_name(monkeypatch, "vkr-builder.bat")
    assert cli.main(["help"]) == 0
    out = capsys.readouterr().out
    assert "Usage  vkr-builder.bat <command> [options]" in out
    assert "main.py" not in out.replace("config.yaml next to main.py", "")


def test_dash_h_renders_the_same_help_as_the_help_command(monkeypatch, capsys):
    _reset_program_name(monkeypatch, "vkr-builder.bat")
    assert cli.main(["--help"]) == 0
    overview = capsys.readouterr().out
    assert cli.main(["help"]) == 0
    assert capsys.readouterr().out == overview

    assert cli.main(["build", "--help"]) == 0
    per_command = capsys.readouterr().out
    assert "vkr-builder.bat build" in per_command
    assert "--skip-docx" in per_command
    assert "usage:" not in per_command


def test_a_bad_flag_is_reported_as_a_failure_block(monkeypatch, capsys):
    _reset_program_name(monkeypatch, "vkr-builder.bat")
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["build", "--badflag"])
    assert exit_info.value.code == 2
    err = capsys.readouterr().err
    assert "cannot read the command line" in err
    assert "try  vkr-builder.bat help" in err
    assert "usage:" not in err


def test_an_unknown_command_is_named_as_such(monkeypatch, capsys):
    _reset_program_name(monkeypatch, "vkr-builder.bat")
    assert cli.main(["frobnicate"]) == 2
    err = capsys.readouterr().err
    assert "unknown command: frobnicate" in err
    assert "commands: build," in err


def test_build_reports_when_no_engine_is_installed(monkeypatch, capsys):
    from vkr import engines

    _reset_program_name(monkeypatch, "vkr-builder.bat")
    engines.clear_cache()
    monkeypatch.setattr(
        engines, "statuses",
        lambda configured_path=None: [
            engines.EngineStatus(engines.WORD, False, "Microsoft Word is not installed"),
            engines.EngineStatus(
                engines.LIBREOFFICE, False, "LibreOffice is not installed"
            ),
        ],
    )
    try:
        rc = cli.main(["build", "--config", "config.yaml"])
    finally:
        engines.clear_cache()
    err = capsys.readouterr().err
    assert rc == 1
    assert "no layout engine available" in err
    assert "try  vkr-builder.bat doctor" in err


def test_header_says_which_engine_auto_picked(monkeypatch, capsys, tiny_profile):
    from vkr import engines

    _reset_program_name(monkeypatch, "vkr-builder.bat")
    engines.clear_cache()
    monkeypatch.setattr(
        engines, "statuses",
        lambda configured_path=None: [
            engines.EngineStatus(engines.WORD, False, "not installed"),
            engines.EngineStatus(engines.LIBREOFFICE, True, "/usr/bin/soffice"),
        ],
    )
    try:
        assert cli.main(
            ["build", "--config", tiny_profile.config, "--skip-docx"]
        ) == 0
    finally:
        engines.clear_cache()
    assert "libreoffice engine (auto)" in capsys.readouterr().err
