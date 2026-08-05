from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass

from . import engines


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    label: str = ""
    required: bool = True
    remedy: str = ""

    @property
    def display(self) -> str:
        return self.label or self.name


def _module_available(mod: str) -> bool:
    return importlib.util.find_spec(mod) is not None


def check_platform() -> CheckResult:
    import platform

    parts = [platform.system() or sys.platform]
    release = platform.release()
    if release:
        parts.append(release)
    machine = platform.machine()
    detail = " ".join(parts)
    if machine:
        detail = f"{detail} ({machine})"
    return CheckResult("platform", True, detail, label="system", required=False)


def check_python() -> CheckResult:
    ok = sys.version_info >= (3, 10)
    version = (
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    return CheckResult(
        "Python >= 3.10",
        ok,
        version if ok else f"{version} (3.10 or newer required)",
        label="python",
    )


def check_python_docx() -> CheckResult:
    ok = _module_available("docx")
    return CheckResult(
        "python-docx", ok, "installed" if ok else "missing", label="python-docx"
    )


def check_pyyaml() -> CheckResult:
    ok = _module_available("yaml")
    return CheckResult(
        "PyYAML", ok, "installed" if ok else "missing", label="pyyaml"
    )


def engine_remedy(name: str, libreoffice_path: str | None = None) -> str:
    if name == engines.LIBREOFFICE:
        if libreoffice_path:
            return "fixing build.libreoffice_path in config.yaml"
        if sys.platform.startswith("linux"):
            return "sudo apt install libreoffice-writer"
        return "installing LibreOffice from libreoffice.org"
    if name == engines.WORD:
        if sys.platform != "win32":
            return ""
        if not _module_available("win32com"):
            return "pip install pywin32"
        return "installing Microsoft Word"
    return ""


def check_installed_engines(libreoffice_path: str | None) -> list[CheckResult]:
    return [
        CheckResult(
            status.name,
            status.available,
            status.detail,
            required=False,
            remedy=(
                "" if status.available
                else engine_remedy(status.name, libreoffice_path)
            ),
        )
        for status in engines.statuses(libreoffice_path)
    ]


def check_uno_bridge(libreoffice_path: str | None) -> CheckResult:
    from .pagination import uno_bridge_python

    try:
        python_path = uno_bridge_python(libreoffice_path)
    except FileNotFoundError:
        return CheckResult(
            "uno bridge",
            False,
            "no Python with the UNO bridge",
            label="uno",
            remedy=(
                "sudo apt install python3-uno"
                if sys.platform.startswith("linux")
                else "reinstalling LibreOffice, whose installer bundles one"
            ),
        )
    return CheckResult("uno bridge", True, python_path, label="uno")


def _paginates_with_libreoffice(engine: str, libreoffice_path: str | None) -> bool:
    requested = (engine or engines.AUTO).strip().lower()
    try:
        resolved = engines.resolve(requested, libreoffice_path=libreoffice_path)
    except (engines.EngineNotAvailable, ValueError):
        return False
    if resolved != engines.LIBREOFFICE:
        return False
    return any(
        status.available
        for status in engines.statuses(libreoffice_path)
        if status.name == engines.LIBREOFFICE
    )


def check_pagination_engine(engine: str, libreoffice_path: str | None) -> CheckResult:
    return _engine_check("pagination", engine, libreoffice_path)


def check_pdf_engine(engine: str, libreoffice_path: str | None) -> CheckResult:
    return _engine_check("pdf", engine, libreoffice_path)


def _engine_check(kind: str, engine: str, libreoffice_path: str | None) -> CheckResult:
    from . import ui

    requested = (engine or engines.AUTO).strip().lower()
    try:
        resolved = engines.resolve(requested, libreoffice_path=libreoffice_path)
    except (engines.EngineNotAvailable, ValueError) as exc:
        return CheckResult(
            f"{kind}: {requested}",
            False,
            str(exc),
            label=kind,
            remedy=engine_remedy(requested, libreoffice_path),
        )

    status = next(
        (s for s in engines.statuses(libreoffice_path) if s.name == resolved), None
    )
    symbols = ui.console().symbols
    parts = []
    if requested == engines.AUTO:
        parts.append(f"auto {symbols.arrow} {resolved}")
    else:
        parts.append(resolved)
    if status is not None:
        parts.append(status.detail)
    available = status.available if status is not None else True
    return CheckResult(
        f"{kind}: {resolved}",
        available,
        f" {symbols.dot} ".join(parts),
        label=kind,
        remedy="" if available else engine_remedy(resolved, libreoffice_path),
    )


def run_checks(
    *,
    pagination_engine: str,
    libreoffice_path: str | None,
    pdf: bool = False,
    pdf_engine: str | None = None,
) -> list[CheckResult]:
    results = [
        check_platform(),
        check_python(),
        check_python_docx(),
        check_pyyaml(),
        *check_installed_engines(libreoffice_path),
        check_pagination_engine(pagination_engine, libreoffice_path),
    ]
    if _paginates_with_libreoffice(pagination_engine, libreoffice_path):
        results.append(check_uno_bridge(libreoffice_path))
    if pdf:
        results.append(
            check_pdf_engine(pdf_engine or pagination_engine, libreoffice_path)
        )
    return results
