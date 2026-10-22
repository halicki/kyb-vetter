import copy
import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
import respx
from mcp import Client

from kyb_vetter_core.config import Settings
from kyb_vetter_mcp.server import build_server

CORE_FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "core" / "tests" / "fixtures"
MF = "https://mf.example"
KRS = "https://krs.example"
NIP = "1234563218"
NRB = "61109010140000071219812874"
ORLEN_KRS = "0000028860"


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    def load(relative: str) -> Any:
        return copy.deepcopy(
            json.loads((CORE_FIXTURES / f"{relative}.json").read_text(encoding="utf-8"))
        )

    return load


@pytest.fixture
def settings() -> Settings:
    return Settings(mf_base_url=MF, krs_base_url=KRS, project_name="unit-test-connector")


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


type ClientFactory = Callable[[], Client]


@pytest.fixture
def mcp_client(settings: Settings) -> ClientFactory:
    """Factory, not an async fixture: the SDK client must enter and exit in the same task."""

    def factory() -> Client:
        return Client(build_server(settings), raise_exceptions=True)

    return factory


@pytest.fixture
def wl_found(fixture_json: Callable[[str], Any]) -> dict[str, Any]:
    payload = fixture_json("whitelist/search_found")
    payload["result"]["subject"]["krs"] = ORLEN_KRS
    payload["result"]["subject"]["name"] = "ORLEN S.A."
    return payload
