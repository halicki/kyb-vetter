"""Live smoke tests against the MF *test* host and the KRS API.

Excluded by default (`-m "not live"` in addopts). Run by hand, sparingly:

    uv run pytest -m live --no-cov packages/core/tests/live

Each run costs quota on the test host (undocumented limits) and about two KRS
requests. Never point these at the MF production host from CI.
"""

import httpx
import pytest

from kyb_vetter_core.clients.krs import KrsClient
from kyb_vetter_core.clients.whitelist import WhiteListClient
from kyb_vetter_core.config import Settings

pytestmark = pytest.mark.live

MF_TEST_HOST = "https://wykazpodatnikowvat-test.mf.gov.pl"
TEST_NIP = "3245174504"  # first NIP from the official test-data file
TEST_NRB = "70506405335016096312945164"  # first account from the official test-data file
ORLEN_KRS = "0000028860"


@pytest.fixture
def settings() -> Settings:
    return Settings(mf_base_url=MF_TEST_HOST)


async def test_whitelist_test_host_status_search_and_check(settings: Settings) -> None:
    async with httpx.AsyncClient() as http:
        client = WhiteListClient(http, settings)
        status = await client.status(TEST_NIP)
        search = await client.search(TEST_NIP)
        check = await client.check(TEST_NIP, TEST_NRB)

    assert status.receipt.request_id
    assert search.receipt.request_id
    assert check.receipt.request_id
    assert search.subject is None or search.subject.nip == TEST_NIP


async def test_krs_live_extract(settings: Settings) -> None:
    async with httpx.AsyncClient() as http:
        extract = await KrsClient(http, settings).get_extract(ORLEN_KRS)

    assert extract.name.startswith("ORLEN")
    assert extract.nip == "7740001454"
    assert extract.receipt.response_sha256
