from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from vkr import config, engines, mascots, suppress, ui
from vkr.logging_setup import get_logger, setup_logging
from vkr.merge import merge_markdown_files
from vkr.paths import project_root

log = get_logger("main")

_COMMANDS = (
    "build", "merge", "docx", "pdf", "validate", "lint", "stats", "preview",
    "diagnose", "watch", "init", "profiles", "doctor", "help",
)


def _ui() -> ui.Console:
    return ui.console()


def _prog() -> str:
    return ui.program_name()


def _cmd_hint(command: str) -> str:
    return f"{_prog()} {command}"


def _arrow() -> str:
    return _ui().symbols.arrow


def _bundle_md(cfg: config.BuildConfig) -> Path:
    return cfg.profile.markdown_dir / "_bundle.md"


def _do_merge(cfg: config.BuildConfig) -> Path:
    merge_markdown_files(
        cfg.profile.markdown_dir,
        cfg.profile.markdown_files,
        _bundle_md(cfg),
    )
    return _bundle_md(cfg)


def _chdir_build() -> None:
    os.chdir(project_root())


def _resolve_config_paths(args) -> tuple[Path | None, Path | None]:
    root = project_root()
    cfg_path = Path(args.config) if args.config else None
    if cfg_path is not None and not cfg_path.is_absolute():
        cfg_path = (root / cfg_path).resolve()

    defaults_path = Path(args.defaults) if args.defaults else None
    if defaults_path is not None and not defaults_path.is_absolute():
        defaults_path = (root / defaults_path).resolve()
    return cfg_path, defaults_path


def _load_cfg(args) -> config.BuildConfig:
    cfg_path, defaults_path = _resolve_config_paths(args)
    return config.load_build_config(
        cfg_path, defaults_path=defaults_path, profile=args.profile
    )


def _abs_path(value: str | Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (project_root() / path).resolve()


def _count_issues(issues) -> tuple[int, int, int]:
    live = [i for i in issues if not getattr(i, "suppressed", False)]
    errors = sum(1 for i in live if i.severity == "error")
    return errors, len(live) - errors, len(issues) - len(live)


def _report_issues(issues, source: str = "") -> tuple[int, int, int]:
    for issue in issues:
        _ui().finding(
            ui.Finding(
                severity="error" if issue.severity == "error" else "warning",
                message=issue.message,
                location=getattr(issue, "location", "") or "",
                source=source,
                rule=getattr(issue, "rule", "") or "",
                suppressed=getattr(issue, "suppressed", False),
            )
        )
    return _count_issues(issues)


def _report_unused_suppressions(*stages: str) -> None:
    con = _ui()
    for directive in suppress.unused(stages):
        shown = f'@suppress {directive.pattern}'.rstrip()
        hint = ""
        if directive.pattern and not suppress.known_rule(directive.pattern):
            meant = suppress.misspelled_rule(directive.pattern)
            hint = (
                f"; did you mean {meant}?" if meant
                else "; it is not a rule name, so it was matched as message text"
            )
        con.issue(
            "warning",
            f"{shown} matched nothing{hint}",
            location=directive.location,
            source="suppress",
        )


def _issue_summary(
    errors: int, warnings: int, suppressed: int = 0, clean: str = "no issues"
) -> str:
    parts = []
    if errors:
        parts.append(ui.plural(errors, "error"))
    if warnings:
        parts.append(ui.plural(warnings, "warning"))
    summary = ui.join_facts(parts) or clean
    if suppressed:
        summary = f"{summary}, {suppressed} suppressed"
    return summary


def _close_issue_step(
    step: ui.Step, errors: int, warnings: int, suppressed: int = 0
) -> None:
    detail = _issue_summary(errors, warnings, suppressed)
    if errors:
        step.fail(detail)
    elif warnings:
        step.warn(detail)
    else:
        step.finish(detail)


def _engine(cfg: config.BuildConfig, args) -> tuple[str, str]:
    requested = (
        getattr(args, "pagination_engine", None) or cfg.build.pagination_engine
    )
    resolved = engines.resolve(
        requested, libreoffice_path=cfg.build.libreoffice_path
    )
    return resolved, engines.describe(resolved, requested)


def _pdf_engine(cfg: config.BuildConfig, args, fallback: str) -> str:
    requested = getattr(args, "pdf_engine", None) or cfg.build.pdf_engine
    if not requested:
        return fallback
    return engines.resolve(requested, libreoffice_path=cfg.build.libreoffice_path)


def _no_engine(exc: engines.EngineNotAvailable) -> int:
    _ui().footer_fail(
        "no layout engine available",
        detail=str(exc),
        hint=_cmd_hint("doctor"),
    )
    return 1


def _step_preflight(cfg: config.BuildConfig, args, engine: str) -> bool:
    from vkr import env_check

    con = _ui()
    step = con.step("checks", "environment")
    pdf_enabled = args.pdf if args.pdf is not None else cfg.build.pdf
    pdf_engine = _pdf_engine(cfg, args, engine)
    results = env_check.run_checks(
        pagination_engine=engine,
        libreoffice_path=cfg.build.libreoffice_path,
        pdf=bool(pdf_enabled),
        pdf_engine=pdf_engine,
    )
    failures = [r for r in results if r.required and not r.ok]
    missing = [
        cfg.profile.markdown_dir / rel
        for rel in cfg.profile.markdown_files
        if not (cfg.profile.markdown_dir / rel).is_file()
    ]

    if failures or missing:
        step.fail(
            _issue_summary(len(failures) + len(missing), 0, clean="unavailable")
        )
        for res in failures:
            con.issue("error", f"{res.display} is not available: {res.detail}")
        for path in missing:
            con.issue("error", f"markdown file not found: {ui.fmt_path(path)}")
        return False

    required = sum(1 for r in results if r.required)
    step.finish(f"{ui.plural(required, 'check')} passed")
    for res in results:
        con.note(f"{res.display}: {res.detail}")
    return True


def _step_merge(cfg: config.BuildConfig) -> Path:
    step = _ui().step("merge", "collecting markdown")
    bundle = _do_merge(cfg)
    step.finish(
        f"{ui.plural(len(cfg.profile.markdown_files), 'file')} "
        f"{_arrow()} {bundle.name}"
    )
    return bundle


def _step_lint(bundle: Path, cfg: config.BuildConfig) -> int:
    from vkr import md_lint

    step = _ui().step("lint", "checking markdown")
    issues = md_lint.lint_markdown(
        str(bundle),
        advisory=False,
        strict=cfg.lint.strict,
        listings_root=cfg.profile.listings_root,
    )
    errors, warnings, suppressed = _count_issues(issues)
    _close_issue_step(step, errors, warnings, suppressed)
    _report_issues(issues, "lint")
    return errors


def _run_document_build(
    cfg: config.BuildConfig,
    engine: str,
    args,
    reporter,
    *,
    source: Path,
    output: Path,
    include_toc: bool = True,
    sort_lists: bool | None = None,
    with_metadata: bool = True,
) -> Path:
    from vkr import docx_build

    return docx_build.build(
        str(source),
        str(output),
        typography=cfg.style.typography.to_flat(),
        styles=cfg.style.word_styles.to_mapping(),
        image_max_width_cm=cfg.style.max_image_width_cm,
        assets_root=cfg.profile.images_dir,
        listings_root=cfg.profile.listings_root,
        pagination_engine=engine,
        libreoffice_path=cfg.build.libreoffice_path,
        metadata=cfg.metadata.to_mapping() if with_metadata else None,
        sort_dictionary_lists=(
            cfg.build.sort_dictionary_lists if sort_lists is None else sort_lists
        ),
        include_toc=include_toc,
        table_continuation=cfg.style.tables.to_mapping(),
        dashes=cfg.style.dashes.to_mapping(),
        progress=reporter,
    )


def _step_pdf(
    cfg: config.BuildConfig,
    args,
    engine: str,
    reporter,
    docx_path: Path,
    pdf_path: Path | None = None,
    *,
    with_metadata: bool = True,
) -> Path | None:
    from vkr import pdf_export

    pdf_engine = _pdf_engine(cfg, args, engine)
    reporter.pdf(pdf_engine)
    try:
        out = pdf_export.export_pdf(
            docx_path,
            pdf_path,
            engine=pdf_engine,
            libreoffice_path=cfg.build.libreoffice_path,
            metadata=cfg.metadata.to_mapping() if with_metadata else None,
        )
    except Exception as exc:
        reporter.fail("export failed")
        _ui().issue("error", f"PDF export failed: {exc}")
        return None
    reporter.pdf_done(out)
    return out


def _report_build_failure(reporter, exc: Exception, title: str) -> int:
    con = _ui()
    reporter.fail("failed")
    if isinstance(exc, PermissionError):
        con.footer_fail(
            "cannot write the output file",
            detail=str(exc),
            hint="close the document in Word and run the command again",
        )
    else:
        con.footer_fail(title, detail=str(exc), hint=_cmd_hint("doctor"))
    log.debug("%s", title, exc_info=True)
    return 1


def _pdf_wanted(cfg: config.BuildConfig, args) -> bool:
    if args is not None and getattr(args, "pdf", None) is not None:
        return bool(args.pdf)
    return bool(cfg.build.pdf)


def _size_hint(path: Path) -> str:
    size = ui.file_size(path)
    return f"  {ui.fmt_size(size)}" if size is not None else ""


def _cmd_build(args) -> int:
    from vkr.progress import create_build_reporter

    con = _ui()
    cfg = _load_cfg(args)
    try:
        engine, engine_label = _engine(cfg, args)
    except engines.EngineNotAvailable as exc:
        con.header("build", cfg.profile_name)
        return _no_engine(exc)
    bundle = _bundle_md(cfg)

    con.header("build", cfg.profile_name, engine_label)
    con.field(
        "source",
        f"{ui.fmt_path(cfg.profile.markdown_dir)}  "
        f"{ui.plural(len(cfg.profile.markdown_files), 'file')}",
    )
    con.field("output", ui.fmt_path(cfg.profile.docx))
    con.blank()

    if not args.no_preflight and not args.skip_docx:
        if not _step_preflight(cfg, args, engine):
            con.footer_fail(
                "build stopped before starting",
                detail="the environment or the input files are not ready",
                hint=_cmd_hint("doctor"),
            )
            return 1

    if not args.skip_merge:
        _step_merge(cfg)
    elif not bundle.is_file():
        con.footer_fail(
            "build stopped before starting",
            detail=f"--skip-merge was given but {ui.fmt_path(bundle)} does not exist",
            hint=_cmd_hint("merge"),
        )
        return 1
    else:
        con.step("merge").skip(f"reusing {bundle.name}")

    stages: list[str] = []
    if not args.no_preflight and bundle.is_file():
        stages.append(suppress.MARKDOWN)
        if _step_lint(bundle, cfg):
            con.footer_fail(
                "build stopped by lint errors",
                detail=(
                    "fix the markdown above, or mark a deliberate one with "
                    "<!-- @suppress rule -->"
                ),
                hint=f"{_cmd_hint('build')} --no-preflight",
            )
            return 1

    if args.skip_docx:
        _report_unused_suppressions(*stages)
        con.footer_ok(
            "markdown merged",
            artifacts=[("bundle", bundle)],
            elapsed=con.elapsed,
        )
        return 0

    reporter = create_build_reporter(enabled=con.reporting)
    try:
        saved = _run_document_build(
            cfg, engine, args, reporter,
            source=bundle, output=cfg.profile.docx,
        )
    except Exception as exc:
        return _report_build_failure(reporter, exc, "build failed")
    finally:
        _remove_bundle(bundle)
    stages.append(suppress.BUILD)

    if _pdf_wanted(cfg, args):
        if _step_pdf(cfg, args, engine, reporter, saved) is None:
            con.footer_fail("PDF export failed", hint=_cmd_hint("doctor"))
            return 1

    if getattr(args, "diagnose", False) or cfg.build.diagnose:
        _step_diagnose(cfg, saved, engine, check_orphans=False)
        stages.append(suppress.DOCUMENT)

    _report_unused_suppressions(*stages)
    con.footer_ok(
        "build finished", artifacts=reporter.outputs, elapsed=con.elapsed
    )
    return 0


def _remove_bundle(bundle: Path) -> None:
    try:
        bundle.unlink()
    except OSError as exc:
        log.debug("Could not delete %s: %s", bundle, exc)


def _step_diagnose(
    cfg: config.BuildConfig,
    docx_path: Path,
    engine: str,
    *,
    check_orphans: bool,
) -> int:
    from vkr import diagnostics

    step = _ui().step("diagnose", "inspecting document")
    issues = diagnostics.run_diagnostics(
        docx_path,
        pagination_engine=engine,
        libreoffice_path=cfg.build.libreoffice_path,
        check_orphans=check_orphans,
    )
    errors, warnings, suppressed = _count_issues(issues)
    _close_issue_step(step, errors, warnings, suppressed)
    _report_issues(issues, "diagnose")
    return errors


def _cmd_docx(args) -> int:
    from vkr.progress import create_build_reporter

    con = _ui()
    cfg = _load_cfg(args)
    try:
        engine, engine_label = _engine(cfg, args)
    except engines.EngineNotAvailable as exc:
        con.header("docx", cfg.profile_name)
        return _no_engine(exc)
    bundle = _bundle_md(cfg)

    con.header("docx", cfg.profile_name, engine_label)
    con.field("source", ui.fmt_path(bundle))
    con.field("output", ui.fmt_path(cfg.profile.docx))
    con.blank()

    if not bundle.is_file():
        con.footer_fail(
            "nothing to build",
            detail=f"no merged bundle at {ui.fmt_path(bundle)}",
            hint=_cmd_hint("merge"),
        )
        return 1

    reporter = create_build_reporter(enabled=con.reporting)
    try:
        saved = _run_document_build(
            cfg, engine, args, reporter,
            source=bundle, output=cfg.profile.docx,
        )
    except Exception as exc:
        return _report_build_failure(reporter, exc, "build failed")
    finally:
        _remove_bundle(bundle)

    if _pdf_wanted(cfg, args):
        if _step_pdf(cfg, args, engine, reporter, saved) is None:
            con.footer_fail("PDF export failed", hint=_cmd_hint("doctor"))
            return 1

    _report_unused_suppressions(suppress.BUILD)
    con.footer_ok(
        "document built", artifacts=reporter.outputs, elapsed=con.elapsed
    )
    return 0


def _cmd_merge(args) -> int:
    con = _ui()
    cfg = _load_cfg(args)
    con.header("merge", cfg.profile_name)
    con.field("source", ui.fmt_path(cfg.profile.markdown_dir))
    con.blank()
    bundle = _step_merge(cfg)
    con.footer_ok(
        "markdown merged",
        artifacts=[("bundle", bundle)],
        elapsed=con.elapsed,
    )
    return 0


def _preview_output_path(md_path: Path, output: str | Path | None) -> Path:
    if output:
        return _abs_path(output)
    return md_path.parent / f"{md_path.stem}.preview.docx"


def _preview_pdf_path(md_path: Path) -> Path:
    return md_path.parent / f"{md_path.stem}.preview.pdf"


def _cmd_preview(args) -> int:
    from vkr.progress import create_build_reporter

    con = _ui()
    cfg = _load_cfg(args)
    md_path = _abs_path(args.markdown)
    try:
        engine, engine_label = _engine(cfg, args)
    except engines.EngineNotAvailable as exc:
        con.header("preview", md_path.name)
        return _no_engine(exc)
    out = _preview_output_path(md_path, args.output)

    con.header("preview", md_path.name, engine_label)
    con.field("source", ui.fmt_path(md_path))
    con.field("output", ui.fmt_path(out))
    con.blank()

    if not md_path.is_file():
        con.footer_fail(
            "nothing to preview",
            detail=f"markdown file not found: {ui.fmt_path(md_path)}",
        )
        return 1

    reporter = create_build_reporter(enabled=con.reporting)
    try:
        saved = _run_document_build(
            cfg, engine, args, reporter,
            source=md_path, output=out,
            include_toc=False, sort_lists=False, with_metadata=False,
        )
    except Exception as exc:
        return _report_build_failure(reporter, exc, "preview failed")

    if _pdf_wanted(cfg, args):
        if _step_pdf(
            cfg, args, engine, reporter, saved, _preview_pdf_path(md_path),
            with_metadata=False,
        ) is None:
            con.footer_fail("PDF export failed", hint=_cmd_hint("doctor"))
            return 1

    _report_unused_suppressions(suppress.BUILD)
    con.footer_ok(
        "preview ready", artifacts=reporter.outputs, elapsed=con.elapsed
    )
    return 0


def _cmd_pdf(args) -> int:
    from vkr import pdf_export

    con = _ui()
    cfg = _load_cfg(args)
    docx_path = _abs_path(args.docx) if args.docx else cfg.profile.docx
    requested = (
        args.pdf_engine or cfg.build.pdf_engine or cfg.build.pagination_engine
    )
    try:
        engine = engines.resolve(
            requested, libreoffice_path=cfg.build.libreoffice_path
        )
    except engines.EngineNotAvailable as exc:
        con.header("pdf")
        return _no_engine(exc)
    pdf_path = _abs_path(args.output) if args.output else None

    con.header("pdf", engines.describe(engine, requested))
    con.field("source", ui.fmt_path(docx_path))
    con.blank()

    if not docx_path.is_file():
        con.footer_fail(
            "nothing to convert",
            detail=f"DOCX not found: {ui.fmt_path(docx_path)}",
            hint=_cmd_hint("build"),
        )
        return 1

    step = con.step("export", f"converting via {engine}")
    try:
        out = pdf_export.export_pdf(
            docx_path,
            pdf_path,
            engine=engine,
            libreoffice_path=cfg.build.libreoffice_path,
            metadata=cfg.metadata.to_mapping(),
        )
    except Exception as exc:
        step.fail("export failed")
        con.footer_fail("PDF export failed", detail=str(exc), hint=_cmd_hint("doctor"))
        return 1
    step.finish(f"{ui.fmt_path(out)}{_size_hint(out)}")
    con.footer_ok(
        "PDF exported",
        artifacts=[("pdf", out)],
        elapsed=con.elapsed,
    )
    return 0


def _cmd_validate(args) -> int:
    con = _ui()
    cfg = _load_cfg(args)
    con.header("validate", cfg.profile_name)
    con.field(
        "config",
        ui.fmt_path(cfg.user_config_path)
        if cfg.user_config_path is not None
        else "built-in defaults",
    )
    con.field("markdown", ui.fmt_path(cfg.profile.markdown_dir))
    con.blank()

    problems = 0
    md_root = cfg.profile.markdown_dir.resolve()
    missing: list[str] = []
    for rel in cfg.profile.markdown_files:
        path = (md_root / rel).resolve()
        if not path.is_relative_to(md_root):
            con.issue("error", f"markdown path escapes markdown_dir: {rel}")
            problems += 1
            continue
        if not path.is_file():
            missing.append(rel)
            problems += 1

    con.result(
        not missing,
        "markdown",
        f"{ui.plural(len(cfg.profile.markdown_files), 'file')} listed"
        + (f", {len(missing)} missing" if missing else ", all present"),
    )
    for rel in missing:
        con.issue("error", f"missing markdown file: {rel}")

    images = cfg.profile.images_dir
    if images is not None:
        ok = images.is_dir()
        con.result(
            ok,
            "images",
            ui.fmt_path(images) if ok else "directory not found",
            failure="warn",
        )
        if not ok:
            con.warnings += 1

    listings = cfg.profile.listings_dir
    if listings is not None:
        ok = listings.is_dir()
        con.result(
            ok,
            "listings",
            ui.fmt_path(listings) if ok else "directory not found",
            failure="warn",
        )
        if not ok:
            con.warnings += 1

    con.result(True, "output", ui.fmt_path(cfg.profile.docx))

    if problems:
        con.footer_fail(
            "configuration is not usable",
            detail=ui.plural(problems, "problem") + " found",
            hint=_cmd_hint("init"),
        )
        return 1
    con.footer_ok("configuration is valid", elapsed=con.elapsed)
    return 0


def _cmd_lint(args) -> int:
    from vkr import md_lint

    con = _ui()
    cfg = _load_cfg(args)
    con.header("lint", cfg.profile_name)
    con.field("markdown", ui.fmt_path(cfg.profile.markdown_dir))
    con.blank()

    bundle = _step_merge(cfg)
    step = con.step("lint", "checking markdown")
    try:
        issues = md_lint.lint_markdown(
            str(bundle), listings_root=cfg.profile.listings_root
        )
    finally:
        _remove_bundle(bundle)

    errors, warnings, suppressed = _count_issues(issues)
    _close_issue_step(step, errors, warnings, suppressed)
    _report_issues(issues, "lint")
    _report_unused_suppressions(suppress.MARKDOWN)

    if errors:
        con.footer_fail(
            "lint found errors",
            detail=_issue_summary(errors, warnings, suppressed),
        )
        return 1
    if warnings or con.warnings:
        con.footer_warn("lint finished", elapsed=con.elapsed)
        return 0
    con.footer_ok("markdown is clean", elapsed=con.elapsed)
    return 0


def _cmd_stats(args) -> int:
    from vkr import md
    from vkr.stats_report import collect_stats

    con = _ui()
    cfg = _load_cfg(args)
    con.header("stats", cfg.profile_name)

    bundle = _do_merge(cfg)
    try:
        elements = md.parse_md(str(bundle), cfg.profile.listings_root)
    finally:
        _remove_bundle(bundle)
    stats = collect_stats(elements)

    blocks = (
        ("structure", (
            ("sections", stats.sections, ""),
            ("chapters", stats.chapters, ""),
            ("appendices", stats.appendices, ""),
            ("headings", stats.headings, ""),
            ("paragraphs", stats.paragraphs, ""),
            ("list items", stats.list_items, ""),
        )),
        ("objects", (
            ("figures", stats.figures, ""),
            ("tables", stats.tables, ""),
            ("listings", stats.listings, ""),
            ("formulas", stats.formulas, ""),
            ("sources", stats.sources, ""),
        )),
        ("volume", (
            ("words", stats.words, ""),
            ("characters", stats.characters, ""),
            ("pages", stats.estimated_pages, "estimated"),
        )),
    )

    art = mascots.roomy()
    rows = sum(2 + len(metrics) for _, metrics in blocks)
    con.start_aside(art, top=max(0, (rows - len(art)) // 2))

    for title, metrics in blocks:
        con.section(title)
        for label, value, hint in metrics:
            con.metric(label, ui.fmt_count(value), hint)

    failed = _stats_thresholds(cfg, stats)
    if failed:
        con.footer_warn("document is below the configured targets")
        return 0
    con.footer_ok("statistics collected", elapsed=con.elapsed)
    return 0


def _stats_thresholds(cfg: config.BuildConfig, stats) -> int:
    con = _ui()
    checks: list[tuple[bool, str, str]] = []

    if cfg.stats.min_sources is not None:
        ok = stats.sources >= cfg.stats.min_sources
        checks.append(
            (ok, "sources", f"{stats.sources} of {cfg.stats.min_sources} required")
        )

    page_min, page_max = cfg.stats.page_min, cfg.stats.page_max
    if page_min is not None or page_max is not None:
        low = page_min is not None and stats.estimated_pages < page_min
        high = page_max is not None and stats.estimated_pages > page_max
        span = f"{page_min or 0}-{page_max}" if page_max else f"{page_min}+"
        checks.append(
            (not (low or high), "pages", f"{stats.estimated_pages} against {span}")
        )

    if not checks:
        return 0
    con.section("targets")
    failed = 0
    for ok, label, detail in checks:
        con.result(ok, label, detail, failure="warn")
        if not ok:
            failed += 1
            con.warnings += 1
    return failed


def _cmd_diagnose(args) -> int:
    con = _ui()
    docx_path = _abs_path(args.docx)
    cfg = _load_cfg(args)
    try:
        engine, engine_label = _engine(cfg, args)
    except engines.EngineNotAvailable as exc:
        con.header("diagnose", docx_path.name)
        return _no_engine(exc)

    con.header("diagnose", docx_path.name, engine_label)
    con.field("document", ui.fmt_path(docx_path))
    con.blank()

    if not docx_path.is_file():
        con.footer_fail(
            "nothing to diagnose",
            detail=f"DOCX not found: {ui.fmt_path(docx_path)}",
            hint=_cmd_hint("build"),
        )
        return 1

    errors = _step_diagnose(
        cfg, docx_path, engine, check_orphans=not args.no_orphans
    )
    if errors:
        con.footer_fail("document has problems")
        return 1
    if con.warnings:
        con.footer_warn("document reviewed", elapsed=con.elapsed)
        return 0
    con.footer_ok("document looks good", elapsed=con.elapsed)
    return 0


def _cmd_doctor(args) -> int:
    from vkr import env_check

    con = _ui()
    cfg = _load_cfg(args)
    requested = args.pagination_engine or cfg.build.pagination_engine
    pdf_requested = args.pdf_engine or cfg.build.pdf_engine or requested

    con.header("doctor", f"{requested} engine")
    con.start_aside(mascots.PEEKING, top=1)
    results = env_check.run_checks(
        pagination_engine=requested,
        libreoffice_path=cfg.build.libreoffice_path,
        pdf=True,
        pdf_engine=pdf_requested,
    )
    for res in results:
        con.result(
            res.ok,
            res.display,
            res.detail,
            failure="fail" if res.required else "warn",
        )

    failed = [r for r in results if r.required and not r.ok]
    if failed:
        con.footer_fail(
            ui.plural(len(failed), "check") + " failed",
            detail="install what is missing and run doctor again",
            hint=next(
                (r.remedy for r in failed if r.remedy),
                "pip install -r requirements.txt",
            ),
        )
        return 1
    if any(not r.ok for r in results):
        con.footer_warn("ready, with one engine missing", elapsed=con.elapsed)
        return 0
    con.footer_ok("everything is ready", elapsed=con.elapsed)
    return 0


def _cmd_watch(args) -> int:
    from vkr import watch
    from vkr.progress import create_build_reporter

    con = _ui()
    cfg = _load_cfg(args)
    try:
        engine, engine_label = _engine(cfg, args)
    except engines.EngineNotAvailable as exc:
        con.header("watch", cfg.profile_name)
        return _no_engine(exc)
    content_dirs = [
        d
        for d in (cfg.profile.images_dir, cfg.profile.listings_root)
        if d is not None
    ]
    paths = watch.collect_watch_paths(
        cfg.profile.markdown_dir,
        cfg.profile.markdown_files,
        content_dirs,
    )

    con.header("watch", cfg.profile_name, engine_label)
    con.field("watching", ui.fmt_path(cfg.profile.markdown_dir))
    con.field("output", ui.fmt_path(cfg.profile.docx))
    con.blank()

    def rebuild() -> None:
        con.begin_section()
        con.line()
        reporter = create_build_reporter(enabled=con.reporting)
        bundle = _bundle_md(cfg)
        try:
            _do_merge(cfg)
            if _step_lint(bundle, cfg):
                con.footer_fail(
                    "rebuild stopped by lint errors",
                    detail=(
                        "fix the markdown above, or mark a deliberate one "
                        "with <!-- @suppress rule -->"
                    ),
                )
                return
            saved = _run_document_build(
                cfg, engine, args, reporter,
                source=bundle, output=cfg.profile.docx,
            )
        except Exception as exc:
            _report_build_failure(reporter, exc, "rebuild failed")
            return
        finally:
            _remove_bundle(bundle)

        if _pdf_wanted(cfg, args):
            if _step_pdf(cfg, args, engine, reporter, saved) is None:
                con.footer_fail("PDF export failed", hint=_cmd_hint("doctor"))
                return
        con.footer_ok(
            "rebuilt", artifacts=reporter.outputs, elapsed=con.elapsed
        )

    try:
        watch.require_watchdog()
    except RuntimeError as exc:
        con.footer_fail(
            "watch is unavailable",
            detail=str(exc),
            hint="pip install watchdog",
        )
        return 1

    con.result(
        True,
        "ready",
        f"{ui.plural(len(paths), 'path')} watched {con.symbols.dot} Ctrl+C to stop",
    )
    watch.run_watch(
        paths,
        rebuild,
        debounce_ms=cfg.watch.debounce_ms,
        content_roots=watch.content_roots(content_dirs),
        on_finishing=lambda: con.bullet(
            "finishing the rebuild in progress; Ctrl+C again to stop now"
        ),
    )
    con.footer_ok("watch stopped")
    return 0


_CONFIG_TEMPLATE = """\
# User config for vkr-builder. Merged on top of config.defaults.yaml.
# All settings: config.defaults.yaml | CLI: see "help"

active_profile: example

profiles:
  example:
    docx: example/VKR-example.docx
    markdown_dir: example/md
    images_dir: example/images
    listings_dir: example/listings
    markdown_files:
      - 01-abbreviations.md
      - 02-terms.md
      - 03-introduction.md
      - 04-chapter1.md
      - 05-chapter2.md
      - 06-conclusion.md
      - 07-sources.md
      - 08-appendix-a.md
      - 09-appendix-b.md
      - 10-appendix-c.md

build:
  # auto = use whatever is installed: Word first, else LibreOffice.
  pagination_engine: auto

# Optional overrides (see config.defaults.yaml):
#
# build:
#   pdf: false
#   sort_dictionary_lists: false
#
# metadata:
#   title: Thesis title
#   author: Your Name
#   language: ru-RU
#
# style:
#   tables:
#     continuation: true
"""


def _cmd_init(args) -> int:
    con = _ui()
    dst = project_root() / "config.yaml"
    con.header("init")
    con.blank()

    if dst.exists() and not args.force:
        con.result(False, "config", f"{ui.fmt_path(dst)} already exists")
        con.footer_fail(
            "config was not written",
            detail="an existing config.yaml is never overwritten silently",
            hint=_cmd_hint("init --force"),
        )
        return 1

    dst.write_text(_CONFIG_TEMPLATE, encoding="utf-8")
    con.result(True, "config", ui.fmt_path(dst))
    con.section("next")
    con.bullet("edit config.yaml: point the profile at your markdown")
    con.bullet(f"{_cmd_hint('doctor')}    check that Word or LibreOffice is reachable")
    con.bullet(f"{_cmd_hint('build')}     merge the markdown and build the DOCX")
    con.footer_ok("project ready", artifacts=[("config", dst)])
    return 0


def _cmd_profiles(args) -> int:
    con = _ui()
    stdout = ui.out()
    cfg_path, defaults_path = _resolve_config_paths(args)
    raw, _base, _defaults_file, _user_file = config.load_merged_config(
        cfg_path, defaults_path=defaults_path
    )
    profiles = raw.get("profiles")
    active = raw.get("active_profile") or raw.get("default_profile")

    con.header("profiles", ui.fmt_path(cfg_path) if cfg_path else "defaults")
    if not isinstance(profiles, dict) or not profiles:
        stdout.line("default")
        con.footer_warn("no profiles defined; using built-in defaults")
        return 0

    palette = stdout.palette
    width = max(len(name) for name in profiles) + len(" (active)") + 2
    for name in sorted(profiles):
        marker = " (active)" if name == active else ""
        entry = profiles.get(name) or {}
        docx = entry.get("docx") if isinstance(entry, dict) else None
        files = entry.get("markdown_files") if isinstance(entry, dict) else None
        detail = ui.join_facts(
            [
                str(docx) if docx else "",
                ui.plural(len(files), "file") if isinstance(files, list) else "",
            ],
            f" {con.symbols.dot} ",
        )
        label = f"{name}{marker}"
        detail = ui.shorten(detail, con.width - len(ui.INDENT) - width)
        stdout.line(
            "    " + palette.bold(f"{label:<{width}}") + palette.dim(detail)
        )
    con.footer_ok(ui.plural(len(profiles), "profile") + " defined")
    return 0


def _global_option_strings() -> set[str]:
    common = argparse.ArgumentParser(add_help=False)
    _add_common_args(common)
    opts: set[str] = set()
    for action in common._actions:
        opts.update(action.option_strings)
    return opts


def _format_action_key(action: argparse.Action) -> str:
    if action.option_strings:
        return ", ".join(action.option_strings)
    metavar = action.metavar or action.dest
    if isinstance(metavar, tuple):
        return " ".join(str(m) for m in metavar)
    return str(metavar)


def _action_help_text(action: argparse.Action) -> str:
    help_text = action.help or ""
    if action.choices:
        choices = " | ".join(str(c) for c in action.choices)
        if help_text:
            return f"{help_text} ({choices})"
        return choices
    return help_text


def _command_option_entries(
    subparser: argparse.ArgumentParser,
    *,
    global_opts: set[str],
) -> list[tuple[str, str]]:
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for action in subparser._actions:
        if action.dest in ("help", "func"):
            continue
        key = _format_action_key(action)
        if key in seen:
            continue
        if action.option_strings and all(o in global_opts for o in action.option_strings):
            continue
        seen.add(key)
        entries.append((key, _action_help_text(action)))
    return entries


def _format_aligned_lines(
    entries: list[tuple[str, str]],
    indent: str,
    *,
    min_col: int = 22,
    max_col: int = 34,
) -> list[str]:
    if not entries:
        return []
    col = max(len(key) for key, _ in entries)
    col = max(min_col, min(col, max_col))
    return [f"{indent}{key:<{col}}  {help}" for key, help in entries]


def _subcommand_short_help(
    subparsers_action: argparse._SubParsersAction,
    name: str,
) -> str:
    for choice in subparsers_action._choices_actions:
        if choice.dest == name:
            return choice.help or ""
    return ""


def _global_entries() -> list[tuple[str, str]]:
    common = argparse.ArgumentParser(add_help=False)
    _add_common_args(common)
    return [
        (_format_action_key(action), action.help or "")
        for action in common._actions
        if action.option_strings
    ]


def _split_entries(
    sub: argparse.ArgumentParser,
) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
    global_opts = _global_option_strings()
    entries = _command_option_entries(sub, global_opts=global_opts)
    positional = [e for e in entries if not e[0].startswith("-")]
    options = [e for e in entries if e[0].startswith("-")]
    return positional, options


def _print_overview(parser: argparse.ArgumentParser) -> None:
    stdout = ui.out()
    p = stdout.palette
    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )

    stdout.line()
    stdout.line("  " + p.bold(parser.description or ""))
    stdout.line()
    stdout.line("  " + p.dim("Usage") + f"  {_prog()} <command> [options]")
    stdout.line()

    stdout.line("  " + p.dim("Global options"))
    for line in _format_aligned_lines(_global_entries(), "    "):
        stdout.line(line)

    stdout.line()
    stdout.line("  " + p.dim("Commands"))
    cmd_col = max(len(n) for n in subparsers_action.choices if n != "help")
    cmd_col = max(cmd_col, 8)
    for name in sorted(subparsers_action.choices):
        if name == "help":
            continue
        sub = subparsers_action.choices[name]
        short = _subcommand_short_help(subparsers_action, name)
        stdout.line(f"    {p.bold(f'{name:<{cmd_col}}')}  {short}")
        positional, options = _split_entries(sub)
        for line in _format_aligned_lines(positional + options, "      "):
            stdout.line(line)
        stdout.line()
    stdout.line(
        "  Run "
        + p.bold(f"{_prog()} help <command>")
        + " for one command in full."
    )
    stdout.line()


def _print_command_help(
    name: str,
    sub: argparse.ArgumentParser,
    parser: argparse.ArgumentParser,
) -> None:
    stdout = ui.out()
    p = stdout.palette
    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    positional, options = _split_entries(sub)
    usage = " ".join(
        [f"{_prog()} {name}"]
        + [f"<{key}>" for key, _ in positional]
        + ["[options]"]
    )

    stdout.line()
    stdout.line("  " + p.bold(f"{_prog()} {name}"))
    stdout.line()
    stdout.line("    " + _subcommand_short_help(subparsers_action, name))
    stdout.line()
    stdout.line("  " + p.dim("Usage") + "  " + usage)

    if positional:
        stdout.line()
        stdout.line("  " + p.dim("Arguments"))
        for line in _format_aligned_lines(positional, "    "):
            stdout.line(line)
    if options:
        stdout.line()
        stdout.line("  " + p.dim("Options"))
        for line in _format_aligned_lines(options, "    "):
            stdout.line(line)

    stdout.line()
    stdout.line("  " + p.dim("Global options"))
    for line in _format_aligned_lines(_global_entries(), "    "):
        stdout.line(line)
    stdout.line()


def _cmd_help(args) -> int:
    parser = _build_parser()
    if not args.command:
        _print_overview(parser)
        return 0

    subparsers_action = next(
        a for a in parser._actions if isinstance(a, argparse._SubParsersAction)
    )
    sub = subparsers_action.choices.get(args.command)
    if sub is None:
        _ui().footer_fail(
            f"unknown command: {args.command}",
            detail="known commands: " + ", ".join(sorted(_COMMANDS)),
            hint=_cmd_hint("help"),
        )
        return 1
    _print_command_help(args.command, sub, parser)
    return 0


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=None,
        help="User YAML config (default: config.yaml in the project folder)",
    )
    parser.add_argument(
        "--defaults",
        default=None,
        help="System YAML config (default: config.defaults.yaml)",
    )
    parser.add_argument(
        "--profile",
        default=None,
        help="Build profile from 'profiles' in the config (default: active_profile)",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Show per-step details"
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show the full internal trace (Word COM, layout passes)",
    )
    parser.add_argument(
        "-q", "--quiet", action="store_true", help="Print errors only"
    )
    parser.add_argument(
        "--no-color", action="store_true", help="Disable colour and live redraw"
    )
    parser.add_argument(
        "--ascii", action="store_true", help="Use ASCII glyphs only"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the report as one JSON document on stdout instead",
    )


def _add_pdf_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--pdf",
        action="store_true",
        default=None,
        help="Also export a PDF next to the DOCX (overrides build.pdf)",
    )
    parser.add_argument(
        "--pdf-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="PDF export engine (default: build.pdf_engine, else the layout engine)",
    )


class _Parser(argparse.ArgumentParser):
    def error(self, message: str):
        _ui().footer_fail(
            f"cannot read the command line: {message}",
            hint=_cmd_hint("help"),
        )
        raise SystemExit(2)

    def exit(self, status: int = 0, message: str | None = None):
        if message:
            _ui().footer_fail(message.strip())
        raise SystemExit(status)


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    _add_common_args(common)

    parser = _Parser(
        prog=_prog(),
        description="Merge markdown and build a thesis DOCX.",
        add_help=False,
    )
    sub = parser.add_subparsers(dest="command", parser_class=_Parser)

    p_build = sub.add_parser(
        "build",
        parents=[common],
        add_help=False,
        help="Merge markdown and build the DOCX",
    )
    p_build.add_argument(
        "--pagination-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="Layout engine (default: build.pagination_engine, normally auto)",
    )
    p_build.add_argument(
        "--skip-merge",
        action="store_true",
        help="Do not merge markdown; build from the existing bundle",
    )
    p_build.add_argument(
        "--skip-docx", action="store_true", help="Only merge markdown; do not build DOCX"
    )
    p_build.add_argument(
        "--no-preflight",
        action="store_true",
        help="Skip the dependency/engine pre-flight checks",
    )
    p_build.add_argument(
        "--diagnose",
        action="store_true",
        help="Run post-build quality diagnostics on the DOCX",
    )
    _add_pdf_args(p_build)
    p_build.set_defaults(func=_cmd_build)

    p_merge = sub.add_parser(
        "merge",
        parents=[common],
        add_help=False,
        help="Merge markdown into the bundle only",
    )
    p_merge.set_defaults(func=_cmd_merge)

    p_docx = sub.add_parser(
        "docx",
        parents=[common],
        add_help=False,
        help="Build the DOCX from an existing bundle",
    )
    p_docx.add_argument(
        "--pagination-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="Layout engine (default: build.pagination_engine, normally auto)",
    )
    _add_pdf_args(p_docx)
    p_docx.set_defaults(func=_cmd_docx)

    p_pdf = sub.add_parser(
        "pdf",
        parents=[common],
        add_help=False,
        help="Convert a DOCX file to PDF",
    )
    p_pdf.add_argument(
        "docx",
        nargs="?",
        default=None,
        help="Input DOCX (default: profile docx from config)",
    )
    p_pdf.add_argument(
        "-o", "--output",
        default=None,
        help="Output PDF path (default: same name as the DOCX)",
    )
    _add_pdf_args(p_pdf)
    p_pdf.set_defaults(func=_cmd_pdf)

    p_validate = sub.add_parser(
        "validate",
        parents=[common],
        add_help=False,
        help="Validate the config and input files",
    )
    p_validate.set_defaults(func=_cmd_validate)

    p_lint = sub.add_parser(
        "lint",
        parents=[common],
        add_help=False,
        help="Check Markdown for authoring mistakes",
    )
    p_lint.set_defaults(func=_cmd_lint)

    p_stats = sub.add_parser(
        "stats",
        parents=[common],
        add_help=False,
        help="Report document statistics",
    )
    p_stats.set_defaults(func=_cmd_stats)

    p_preview = sub.add_parser(
        "preview",
        parents=[common],
        add_help=False,
        help="Build a single-chapter preview DOCX",
    )
    p_preview.add_argument(
        "markdown",
        help="Markdown file to preview (e.g. example/md/04-chapter1.md)",
    )
    p_preview.add_argument(
        "-o", "--output",
        default=None,
        help="Output DOCX path (default: <input>.preview.docx next to the source .md)",
    )
    p_preview.add_argument(
        "--pagination-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="Layout engine for table continuation",
    )
    _add_pdf_args(p_preview)
    p_preview.set_defaults(func=_cmd_preview)

    p_diagnose = sub.add_parser(
        "diagnose",
        parents=[common],
        add_help=False,
        help="Report document quality issues in a DOCX",
    )
    p_diagnose.add_argument(
        "docx",
        help="Path to the DOCX file to inspect",
    )
    p_diagnose.add_argument(
        "--pagination-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="Engine for orphan/widow checks (default: build.pagination_engine)",
    )
    p_diagnose.add_argument(
        "--no-orphans",
        action="store_true",
        help="Skip orphan/widow line checks",
    )
    p_diagnose.set_defaults(func=_cmd_diagnose)

    p_watch = sub.add_parser(
        "watch",
        parents=[common],
        add_help=False,
        help="Rebuild automatically when Markdown changes",
    )
    p_watch.add_argument(
        "--pagination-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="Layout engine (default: build.pagination_engine, normally auto)",
    )
    _add_pdf_args(p_watch)
    p_watch.set_defaults(func=_cmd_watch)

    p_init = sub.add_parser(
        "init",
        parents=[common],
        add_help=False,
        help="Write a fresh config.yaml template",
    )
    p_init.add_argument(
        "--force", action="store_true", help="Overwrite an existing config.yaml"
    )
    p_init.set_defaults(func=_cmd_init)

    p_profiles = sub.add_parser(
        "profiles",
        parents=[common],
        add_help=False,
        help="List the profiles defined in the config",
    )
    p_profiles.set_defaults(func=_cmd_profiles)

    p_doctor = sub.add_parser(
        "doctor",
        parents=[common], add_help=False,
        help="Check Python dependencies and the build engines",
    )
    p_doctor.add_argument(
        "--pagination-engine",
        choices=engines.ENGINE_CHOICES,
        default=None,
        help="Engine to check (default: build.pagination_engine)",
    )
    _add_pdf_args(p_doctor)
    p_doctor.set_defaults(func=_cmd_doctor)

    p_help = sub.add_parser(
        "help",
        parents=[common],
        add_help=False,
        help="Show usage information",
    )
    p_help.add_argument(
        "command",
        nargs="?",
        choices=[c for c in _COMMANDS if c != "help"],
        help="Show help for a specific command",
    )
    p_help.set_defaults(func=_cmd_help)

    return parser


def _verbosity(args) -> int:
    if getattr(args, "debug", False):
        return ui.DEBUG
    if getattr(args, "quiet", False):
        return ui.QUIET
    if getattr(args, "verbose", False):
        return ui.VERBOSE
    return ui.NORMAL


_HELP_FLAGS = ("-h", "--help", "-?", "/?")


def _help_request(argv: list[str]) -> tuple[bool, str | None]:
    if not any(a in _HELP_FLAGS for a in argv):
        return False, None
    command = next((a for a in argv if a in _COMMANDS and a != "help"), None)
    return True, command


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)

    wants_help, help_command = _help_request(argv)
    if wants_help:
        ui.configure(verbosity=ui.NORMAL)
        return _cmd_help(argparse.Namespace(command=help_command))

    if argv and not argv[0].startswith("-") and argv[0] not in _COMMANDS:
        ui.configure(verbosity=ui.NORMAL)
        _ui().footer_fail(
            f"unknown command: {argv[0]}",
            detail="commands: " + ", ".join(sorted(_COMMANDS)),
            hint=_cmd_hint("help"),
        )
        return 2

    if not argv or argv[0] not in _COMMANDS:
        argv = ["build"] + argv

    parser = _build_parser()
    args = parser.parse_args(argv)

    verbosity = _verbosity(args)
    con = ui.configure(
        verbosity=verbosity,
        color=False if getattr(args, "no_color", False) else None,
        unicode=False if getattr(args, "ascii", False) else None,
        json_output=getattr(args, "json", False),
    )
    setup_logging(verbosity)
    suppress.reset()
    _chdir_build()

    try:
        return args.func(args)
    except config.ConfigError as exc:
        con.footer_fail("configuration error", detail=str(exc), hint=_cmd_hint("validate"))
        return 1
    except FileNotFoundError as exc:
        con.footer_fail("a required file is missing", detail=str(exc))
        return 1
    except PermissionError as exc:
        con.footer_fail(
            "cannot write the output file",
            detail=str(exc),
            hint="close the document in Word and run the command again",
        )
        return 1
    except KeyboardInterrupt:
        con.footer_warn("cancelled")
        return 130
    finally:
        ui.close()
