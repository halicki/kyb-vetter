"""API keys for the REST API (ADR-0019).

A key is shown once, in clear, as ``<prefix>.<secret>``: the 8-character
prefix locates the record, the SHA-256 of the whole string is what we store.
Keys carry ~256 bits of entropy, so a fast hash is enough (bcrypt-style
stretching protects weak passwords, not random secrets). A key belongs to a
principal (the user's ``sub`` from the identity provider), so REST and MCP
calls of the same person share one history and one daily budget.
"""

import hmac
import secrets
from hashlib import sha256
from typing import TYPE_CHECKING
from uuid import uuid4

from kyb_vetter_core.storage.ports import ApiKeyRecord

if TYPE_CHECKING:
    from datetime import datetime

    from kyb_vetter_core.storage.ports import ApiKeyStore

PREFIX_BYTES = 6  # token_urlsafe(6) -> 8 characters
SECRET_BYTES = 32


def hash_key(plaintext: str) -> str:
    return sha256(plaintext.encode()).hexdigest()


def generate_api_key(principal: str, name: str, *, now: datetime) -> tuple[str, ApiKeyRecord]:
    """A fresh key for ``principal`` and the record to persist; the plaintext is never stored."""
    prefix = secrets.token_urlsafe(PREFIX_BYTES)
    plaintext = f"{prefix}.{secrets.token_urlsafe(SECRET_BYTES)}"
    record = ApiKeyRecord(
        id=uuid4(),
        principal=principal,
        name=name,
        prefix=prefix,
        key_hash=hash_key(plaintext),
        created_at=now,
        revoked_at=None,
        last_used_at=None,
    )
    return plaintext, record


async def authenticate_api_key(
    store: ApiKeyStore, plaintext: str, *, now: datetime
) -> ApiKeyRecord | None:
    """The record behind ``plaintext`` when it is well-formed, known, matching and not revoked.

    A match records ``last_used_at``; any refusal leaves the record untouched.
    """
    prefix, dot, _secret = plaintext.partition(".")
    if not dot or not prefix:
        return None
    record = await store.find_by_prefix(prefix)
    if record is None or record.revoked_at is not None:
        return None
    if not hmac.compare_digest(record.key_hash, hash_key(plaintext)):
        return None
    await store.touch(record.id, used_at=now)
    return record.model_copy(update={"last_used_at": now})
