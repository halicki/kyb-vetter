"""Admin commands for REST API keys (ADR-0020).

``issue`` writes the key in clear exactly once (it is never stored or shown
again); ``list`` shows prefixes and metadata only; ``revoke`` disables a key
by its prefix. Output goes to the given stream (stdout from the CLI; this is
the worker, not the MCP stdio channel).
"""

from typing import TYPE_CHECKING, TextIO

from kyb_vetter_core.apikeys import generate_api_key

if TYPE_CHECKING:
    from datetime import datetime

    from kyb_vetter_core.storage.ports import ApiKeyStore


async def issue_key(
    store: ApiKeyStore, *, principal: str, name: str, now: datetime, out: TextIO
) -> str:
    plaintext, record = generate_api_key(principal, name, now=now)
    await store.insert(record)
    out.write(f"# key for {principal} ({name}); shown once, store it now\n{plaintext}\n")
    return plaintext


async def list_keys(store: ApiKeyStore, *, principal: str, out: TextIO) -> None:
    keys = await store.list_for(principal)
    if not keys:
        out.write("no keys\n")
        return
    for k in keys:
        state = "active" if k.revoked_at is None else f"revoked {k.revoked_at.isoformat()}"
        used = "never" if k.last_used_at is None else k.last_used_at.isoformat()
        out.write(
            f"{k.prefix}\t{k.name}\tcreated {k.created_at.isoformat()}\t{state}\tlast used {used}\n"
        )


async def revoke_key(store: ApiKeyStore, *, prefix: str, now: datetime) -> bool:
    record = await store.find_by_prefix(prefix)
    if record is None:
        return False
    await store.revoke(record.id, revoked_at=now)
    return True
