import json
from datetime import UTC, datetime, timedelta

from kyb_vetter_core.flatfile.index import FlatFileIndex
from kyb_vetter_core.flatfile.provider import (
    LATEST_KEY,
    FlatFileProvider,
    index_key,
    latest_manifest,
)
from kyb_vetter_core.storage.blobs import MemoryBlobStore

NOW = datetime(2026, 10, 23, 8, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> datetime:
        return self.now


def make_index(date: str) -> FlatFileIndex:
    return FlatFileIndex.build(
        date=date, transformations=1, source_sha512="cd" * 64, active=[], exempt=[], masks=[]
    )


async def publish(blobs: MemoryBlobStore, index: FlatFileIndex) -> None:
    await blobs.put(index_key(index.date), index.to_bytes())
    await blobs.put(LATEST_KEY, json.dumps(latest_manifest(index)).encode())


async def test_no_manifest_means_no_index() -> None:
    provider = FlatFileProvider(MemoryBlobStore(), now=Clock())
    assert await provider.current() is None


async def test_loads_index_named_by_manifest_and_caches_it() -> None:
    blobs = MemoryBlobStore()
    clock = Clock()
    await publish(blobs, make_index("20261023"))
    provider = FlatFileProvider(blobs, now=clock)

    first = await provider.current()
    blobs.reads = 0
    second = await provider.current()

    assert first is not None
    assert first.date == "20261023"
    assert second is first
    assert blobs.reads == 0  # within the refresh window nothing is fetched


async def test_refreshes_when_manifest_changes_after_the_window() -> None:
    blobs = MemoryBlobStore()
    clock = Clock()
    await publish(blobs, make_index("20261023"))
    provider = FlatFileProvider(blobs, now=clock, refresh_every=timedelta(minutes=15))
    await provider.current()

    await publish(blobs, make_index("20261024"))
    clock.now = NOW + timedelta(minutes=5)
    stale = await provider.current()
    assert stale is not None
    assert stale.date == "20261023"
    clock.now = NOW + timedelta(minutes=16)
    fresh = await provider.current()
    assert fresh is not None
    assert fresh.date == "20261024"


async def test_corrupt_manifest_or_index_yields_none_and_keeps_last_good() -> None:
    blobs = MemoryBlobStore()
    clock = Clock()
    await publish(blobs, make_index("20261023"))
    provider = FlatFileProvider(blobs, now=clock, refresh_every=timedelta(minutes=1))
    good = await provider.current()

    await blobs.put(LATEST_KEY, b"{not json")
    clock.now = NOW + timedelta(minutes=2)
    assert await provider.current() is good

    await blobs.put(
        LATEST_KEY, json.dumps({"date": "20261099", "object": "flatfile/20261099.idx"}).encode()
    )
    clock.now = NOW + timedelta(minutes=4)
    assert await provider.current() is good


async def test_manifest_pointing_at_a_missing_object_keeps_previous_index() -> None:
    blobs = MemoryBlobStore()
    clock = Clock()
    await publish(blobs, make_index("20261023"))
    provider = FlatFileProvider(blobs, now=clock, refresh_every=timedelta(minutes=1))
    good = await provider.current()

    await blobs.put(
        LATEST_KEY, json.dumps({"date": "20261024", "object": "flatfile/missing.idx"}).encode()
    )
    clock.now = NOW + timedelta(minutes=2)
    assert await provider.current() is good


async def test_unchanged_manifest_after_the_window_keeps_the_loaded_index() -> None:
    blobs = MemoryBlobStore()
    clock = Clock()
    await publish(blobs, make_index("20261023"))
    provider = FlatFileProvider(blobs, now=clock, refresh_every=timedelta(minutes=1))
    first = await provider.current()

    clock.now = NOW + timedelta(minutes=2)
    blobs.reads = 0
    assert await provider.current() is first
    assert blobs.reads == 1  # only the manifest was re-read
