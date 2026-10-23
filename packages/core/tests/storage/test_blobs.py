from pathlib import Path

from kyb_vetter_core.storage.blobs import FilesystemBlobStore, MemoryBlobStore
from kyb_vetter_core.storage.ports import BlobStore


async def blob_contract(store: BlobStore) -> None:
    assert await store.get("flatfile/latest.json") is None
    assert await store.exists("flatfile/latest.json") is False
    await store.put("flatfile/latest.json", b'{"date": "20261023"}')
    assert await store.exists("flatfile/latest.json") is True
    assert await store.get("flatfile/latest.json") == b'{"date": "20261023"}'
    await store.put("flatfile/latest.json", b"replaced")
    assert await store.get("flatfile/latest.json") == b"replaced"


async def test_memory_blob_store() -> None:
    await blob_contract(MemoryBlobStore())


async def test_filesystem_blob_store(tmp_path: Path) -> None:
    await blob_contract(FilesystemBlobStore(tmp_path / "blobs"))
    assert (tmp_path / "blobs" / "flatfile" / "latest.json").read_bytes() == b"replaced"


async def test_filesystem_blob_store_refuses_path_escape(tmp_path: Path) -> None:
    import pytest

    store = FilesystemBlobStore(tmp_path)
    with pytest.raises(ValueError, match="escapes"):
        await store.put("../outside", b"x")
