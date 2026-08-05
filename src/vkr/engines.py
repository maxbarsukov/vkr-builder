from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass

AUTO = "auto"
WORD = "word"
LIBREOFFICE = "libreoffice"

ENGINES = (WORD, LIBREOFFICE)
ENGINE_CHOICES = (AUTO, WORD, LIBREOFFICE)

_cache: dict[str, object] = {}


class EngineNotAvailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EngineStatus:
    name: str
    available: bool
    detail: str


def clear_cache() -> None:
    _cache.clear()


def word_status() -> EngineStatus:
    if "word" in _cache:
        return _cache["word"]
    status = _detect_word()
    _cache["word"] = status
    return status


def _detect_word() -> EngineStatus:
    if sys.platform != "win32":
        return EngineStatus(WORD, False, "Windows only")
    if importlib.util.find_spec("win32com") is None:
        return EngineStatus(WORD, False, "pywin32 is not installed")
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "Word.Application"):
            pass
    except OSError:
        return EngineStatus(WORD, False, "Microsoft Word is not installed")
    except Exception as exc:
        return EngineStatus(WORD, False, f"could not query the registry: {exc}")
    return EngineStatus(WORD, True, _word_version() or "installed")


def _word_version() -> str:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, r"Word.Application\CurVer"
        ) as key:
            cur_ver, _ = winreg.QueryValueEx(key, "")
        version = str(cur_ver).rsplit(".", 1)[-1]
        return f"Word {version}" if version.isdigit() else "installed"
    except Exception:
        return ""


def libreoffice_status(configured_path: str | None = None) -> EngineStatus:
    key = f"libreoffice:{configured_path or ''}"
    if key in _cache:
        return _cache[key]
    status = _detect_libreoffice(configured_path)
    _cache[key] = status
    return status


def _detect_libreoffice(configured_path: str | None) -> EngineStatus:
    from .pagination import resolve_libreoffice_path

    try:
        path = resolve_libreoffice_path(configured_path)
    except FileNotFoundError:
        return EngineStatus(LIBREOFFICE, False, "LibreOffice is not installed")
    except Exception as exc:
        return EngineStatus(LIBREOFFICE, False, str(exc))
    return EngineStatus(LIBREOFFICE, True, path)


def statuses(configured_path: str | None = None) -> list[EngineStatus]:
    return [word_status(), libreoffice_status(configured_path)]


def installed(configured_path: str | None = None) -> list[str]:
    return [s.name for s in statuses(configured_path) if s.available]


def resolve(requested: str | None, *, libreoffice_path: str | None = None) -> str:
    name = (requested or AUTO).strip().lower()
    if name in ENGINES:
        return name
    if name != AUTO:
        raise ValueError(
            f"expected one of {', '.join(ENGINE_CHOICES)} (got {requested!r})"
        )

    for status in statuses(libreoffice_path):
        if status.available:
            return status.name

    raise EngineNotAvailable(
        "no layout engine found: install Microsoft Word (with pywin32) or "
        "LibreOffice, or set build.libreoffice_path in config.yaml"
    )


def describe(resolved: str, requested: str | None) -> str:
    was_auto = (requested or AUTO).strip().lower() == AUTO
    return f"{resolved} engine (auto)" if was_auto else f"{resolved} engine"
