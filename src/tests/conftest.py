import sys
from pathlib import Path

import pytest

_TESTS_DIR = Path(__file__).resolve().parent
_SRC_DIR = _TESTS_DIR.parent
PROJECT_ROOT = _SRC_DIR.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from vkr import engines
from vkr.paths import set_project_root

set_project_root(PROJECT_ROOT)

EXAMPLE_DIR = PROJECT_ROOT / "example"
FIXTURES_DIR = _TESTS_DIR / "fixtures"

_WORD = engines.word_status()
WORD_AVAILABLE = _WORD.available

requires_word = pytest.mark.skipif(
    not WORD_AVAILABLE, reason=f"Microsoft Word is not usable here: {_WORD.detail}"
)


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def example_dir() -> Path:
    return EXAMPLE_DIR


@pytest.fixture(scope="session")
def sample_md_path() -> Path:
    return FIXTURES_DIR / "sample.md"
