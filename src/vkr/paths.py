from __future__ import annotations

import os
from pathlib import Path

_PROJECT_ROOT: Path | None = None


def set_project_root(path: Path) -> None:
    global _PROJECT_ROOT
    _PROJECT_ROOT = path.resolve()


def project_root() -> Path:
    if _PROJECT_ROOT is not None:
        return _PROJECT_ROOT
    env = os.environ.get("VKR_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parents[2]
