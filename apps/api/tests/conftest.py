import copy
import json
from collections.abc import AsyncGenerator, Callable, Iterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from kyb_vetter_api.app import build_app
from kyb_vetter_core.apikeys import generate_api_key
from kyb_vetter_core.config import Settings

CORE_FIXTURES = Path(__file__).resolve().parents[3] / "packages" / "core" / "tests" / "fixtures"
MF = "https://mf.example"
KRS = "https://krs.example"
NIP = "1234563218"
NRB = "61109010140000071219812874"
BASE = "http://api.test"


@pytest.fixture
def fixture_json() -> Callable[[str], Any]:
    def load(relative: str) -> Any:
        return copy.deepcopy(
            json.loads((CORE_FIXTURES / f"{relative}.json").read_text(encoding="utf-8"))
        )

    return load


@pytest.fixture
def settings() -> Settings:
    return Settings(mf_base_url=MF, krs_base_url=KRS, project_name="unit-test-api")


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        router.route(host="api.test").pass_through()
        yield router


@pytest.fixture
def wl_found(fixture_json: Callable[[str], Any]) -> dict[str, Any]:
    payload = fixture_json("whitelist/search_found")
    payload["result"]["subject"]["krs"] = None
    payload["result"]["subject"]["name"] = "ORLEN S.A."
    return payload


@asynccontextmanager
async def serve(
    settings: Settings, *, principal: str = "auth0|alice"
) -> AsyncGenerator[tuple[httpx.AsyncClient, str]]:
    """The app with its lifespan entered, an ASGI client, and a fresh API key for ``principal``."""
    app = build_app(settings)
    async with app.router.lifespan_context(app):
        plaintext, record = generate_api_key(principal, "test", now=datetime.now(tz=UTC))
        await app.state.stores.apikeys.insert(record)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE
        ) as client:
            yield client, plaintext
