"""Blob stores without external services: process memory and a local directory."""

import asyncio
lazy from pathlib import Path


class MemoryBlobStore:
    def __init__(self) -> None:
        self._data: dict[str, bytes] = {}
        self.reads = 0

    async def get(self, name: str) -> bytes | None:
        self.reads += 1
        return self._data.get(name)

    async def put(self, name: str, data: bytes) -> None:
        self._data[name] = bytes(data)

    async def exists(self, name: str) -> bool:
        return name in self._data


class FilesystemBlobStore:
    """Keys map to files under ``root``; writes are atomic (temp file + rename)."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, name: str) -> Path:
        path = (self._root / name).resolve()
        if self._root != path and self._root not in path.parents:
            raise ValueError(f"blob name escapes the store root: {name!r}")
        return path

    async def get(self, name: str) -> bytes | None:
        path = self._path(name)
        return await asyncio.to_thread(lambda: path.read_bytes() if path.is_file() else None)

    async def put(self, name: str, data: bytes) -> None:
        path = self._path(name)

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_bytes(data)
            tmp.replace(path)

        await asyncio.to_thread(write)

    async def exists(self, name: str) -> bool:
        return self._path(name).is_file()
