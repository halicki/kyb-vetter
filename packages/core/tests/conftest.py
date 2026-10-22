import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    """Load ``tests/fixtures/<relative path>.json``."""

    def load(relative: str) -> Any:
        return json.loads((FIXTURES / f"{relative}.json").read_text(encoding="utf-8"))

    return load
