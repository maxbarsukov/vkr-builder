from __future__ import annotations

import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent
_SRC = _PROJECT_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from vkr.paths import set_project_root

set_project_root(_PROJECT_ROOT)

from vkr.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
