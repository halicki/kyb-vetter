from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, cast

import httpx
import pytest
import respx

from kyb_vetter_core.assembly import build_verification_service
from kyb_vetter_core.clients import whitelist as whitelist_module
from kyb_vetter_core.config import Settings
from kyb_vetter_core.errors import QuotaExhaustedError
from kyb_vetter_core.quota import BUCKET_SEARCH
from kyb_vetter_core.storage import Stores, open_stores
from kyb_vetter_core.storage.blobs import FilesystemBlobStore, MemoryBlobStore
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
        assert isinstance(stores.blobs, MemoryBlobStore)


async def test_open_stores_uses_a_directory_for_blobs_when_configured(tmp_path: Path) -> None:
    async with open_stores(Settings(database_url=None, flatfile_dir=str(tmp_path))) as stores:
        assert isinstance(stores.blobs, FilesystemBlobStore)
        await stores.blobs.put("flatfile/x", b"1")
        assert (tmp_path / "flatfile" / "x").exists()


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
        blobs=MemoryBlobStore(),
        persistent=False,
    )

    async with httpx.AsyncClient() as http:
        service = build_verification_service(http, settings, stores, today=lambda: TODAY)
        first = await service.verify_company(NIP)
        second = await service.verify_company(NIP)
        history = await service.verification_history(NIP, principal="local")

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
        blobs=MemoryBlobStore(),
        persistent=False,
    )
    await stores.quota.exhaust(BUCKET_SEARCH, TODAY, limit=90)
    route = mock_api.get(url__regex=r".*").respond(200, json={})

    async with httpx.AsyncClient() as http:
        service = build_verification_service(http, settings, stores, today=lambda: TODAY)
        with pytest.raises(QuotaExhaustedError):
            await service.verify_company(NIP)
        history = await service.verification_history(NIP, principal="local")

    assert not route.called
    assert history.entries[0].error_code == "QUOTA_GUARD"


async def test_open_stores_uses_gcs_when_a_bucket_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kyb_vetter_core.storage.gcs as gcs_module

    created: list[str] = []

    class FakeGcs(MemoryBlobStore):
        def __init__(self, bucket: str) -> None:
            super().__init__()
            created.append(bucket)

    monkeypatch.setattr(gcs_module, "GcsBlobStore", FakeGcs)
    async with open_stores(Settings(database_url=None, flatfile_bucket="bucket-1")) as stores:
        assert isinstance(stores.blobs, FakeGcs)
    assert created == ["bucket-1"]


async def test_assembled_service_answers_account_checks_from_the_flat_file(
    mock_api: respx.MockRouter, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    from kyb_vetter_core.flatfile.index import FlatFileIndex
    from kyb_vetter_core.flatfile.provider import LATEST_KEY, index_key, latest_manifest
    from kyb_vetter_core.flatfile.testing import ACTIVE_PAIRS, DATE, TRANSFORMATIONS, flat_file_json

    monkeypatch.setattr(whitelist_module, "today_in_warsaw", lambda: TODAY)
    settings = Settings(
        mf_base_url=MF, krs_base_url=KRS, project_name="unit-test", database_url=None
    )
    data = flat_file_json()
    index = FlatFileIndex.build(
        date=DATE,
        transformations=TRANSFORMATIONS,
        source_sha512="ab" * 64,
        active=cast("list[str]", data["skrotyPodatnikowCzynnych"]),
        exempt=[],
        masks=[],
    )
    blobs = MemoryBlobStore()
    await blobs.put(index_key(index.date), index.to_bytes())
    await blobs.put(LATEST_KEY, json.dumps(latest_manifest(index)).encode())
    stores = Stores(
        quota=MemoryQuotaStore(),
        audit=MemoryAuditStore(),
        cache=MemoryCacheStore(),
        blobs=blobs,
        persistent=False,
    )
    api = mock_api.get(url__regex=rf"{MF}/.*").respond(200, json={})
    nip, nrb = ACTIVE_PAIRS[0]

    async with httpx.AsyncClient() as http:
        service = build_verification_service(http, settings, stores, today=lambda: TODAY)
        result = await service.check_bank_account(nip, nrb)

    assert result.via == "flat_file"
    assert not api.called
