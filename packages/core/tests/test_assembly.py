from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
import respx

from kyb_vetter_core.assembly import build_verification_service
from kyb_vetter_core.clients import whitelist as whitelist_module
from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import QuotaExhaustedError
from kyb_vetter_core.quota import BUCKET_SEARCH
from kyb_vetter_core.storage import Stores, open_stores
from kyb_vetter_core.storage.memory import MemoryAuditStore, MemoryCacheStore, MemoryQuotaStore

from .test_verification import KRS, MF, NIP, ORLEN_KRS, TODAY


@pytest.fixture
def mock_api() -> Iterator[respx.MockRouter]:
    with respx.mock(assert_all_called=False) as router:
        yield router


async def test_open_stores_without_database_url_is_in_memory_and_not_persistent() -> None:
    async with open_stores(Settings(database_url=None)) as stores:
        assert stores.persistent is False
        assert isinstance(stores.quota, MemoryQuotaStore)
        assert isinstance(stores.audit, MemoryAuditStore)
        assert isinstance(stores.cache, MemoryCacheStore)


async def test_assembled_service_caches_guards_and_audits(
    mock_api: respx.MockRouter, fixture_json: Callable[[str], Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(
        mf_base_url=MF, krs_base_url=KRS, project_name="unit-test", database_url=None
    )
    wl = fixture_json("whitelist/search_found")
    wl["result"]["subject"]["krs"] = ORLEN_KRS
    wl_route = mock_api.get(f"{MF}/api/search/nip/{NIP}").respond(200, json=wl)
    krs_route = mock_api.get(f"{KRS}/api/krs/OdpisAktualny/{ORLEN_KRS}").respond(
        200, json=fixture_json(f"krs/{ORLEN_KRS}")
    )
    stores = Stores(
        quota=MemoryQuotaStore(),
        audit=MemoryAuditStore(),
        cache=MemoryCacheStore(),
        persistent=False,
    )

    async with httpx.AsyncClient() as http:
        service = build_verification_service(http, settings, stores, today=lambda: TODAY)
        first = await service.verify_company(NIP)
        second = await service.verify_company(NIP)
        history = await service.verification_history(NIP)

    assert wl_route.call_count == 1
    assert krs_route.call_count == 1
    assert first.sources[0].from_cache is False
    assert second.sources[0].from_cache is True
    assert await stores.quota.usage(BUCKET_SEARCH, TODAY) == 1
    assert [e.from_cache for e in history.entries] == [True, False]
    assert history.persistent is False


async def test_assembled_service_refuses_when_guard_is_exhausted(
    mock_api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(
        mf_base_url=MF, krs_base_url=KRS, project_name="unit-test", database_url=None
    )
    stores = Stores(
        quota=MemoryQuotaStore(),
        audit=MemoryAuditStore(),
        cache=MemoryCacheStore(),
        persistent=False,
    )
    await stores.quota.exhaust(BUCKET_SEARCH, TODAY, limit=90)
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    async with httpx.AsyncClient() as http:
        service = build_verification_service(http, settings, stores, today=lambda: TODAY)
        with pytest.raises(QuotaExhaustedError):
            await service.verify_company(NIP)
        history = await service.verification_history(NIP)

    assert not route.called
    assert history.entries[0].error_code == "QUOTA_GUARD"
