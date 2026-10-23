"""Google Cloud Storage blob store (google-cloud-storage, run in a thread).

Not unit-tested: the client needs real credentials and a bucket. Covered by a
`live` test and by the deployed worker (ADR-0016); excluded from coverage.
"""

import asyncio

from google.cloud import storage


class GcsBlobStore:
    def __init__(self, bucket_name: str, *, client: storage.Client | None = None) -> None:
        self._client = client or storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    async def get(self, name: str) -> bytes | None:
        blob = self._bucket.blob(name)

        def download() -> bytes | None:
            return bytes(blob.download_as_bytes()) if blob.exists() else None

        return await asyncio.to_thread(download)

    async def put(self, name: str, data: bytes) -> None:
        blob = self._bucket.blob(name)
        await asyncio.to_thread(blob.upload_from_string, data, "application/octet-stream")

    async def exists(self, name: str) -> bool:
        return bool(await asyncio.to_thread(self._bucket.blob(name).exists))
