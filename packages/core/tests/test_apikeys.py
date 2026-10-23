"""API keys for the REST API (ADR-0019): issued once in clear, stored hashed."""

from datetime import UTC, datetime, timedelta
from hashlib import sha256

from kyb_vetter_core.apikeys import authenticate_api_key, generate_api_key
from kyb_vetter_core.storage.memory import MemoryApiKeyStore

NOW = datetime(2026, 10, 23, 18, 0, tzinfo=UTC)
LATER = NOW + timedelta(hours=1)


def test_generated_key_is_prefix_dot_secret_and_only_its_hash_is_kept() -> None:
    plaintext, record = generate_api_key("auth0|alice", "ci bot", now=NOW)

    prefix, secret = plaintext.split(".")
    assert len(prefix) == 8
    assert len(secret) >= 40
    assert record.prefix == prefix
    assert record.key_hash == sha256(plaintext.encode()).hexdigest()
    assert plaintext not in record.model_dump_json()
    assert record.principal == "auth0|alice"
    assert record.name == "ci bot"
    assert record.created_at == NOW
    assert record.revoked_at is None
    assert record.last_used_at is None


def test_keys_are_unique() -> None:
    a, _ = generate_api_key("p", "a", now=NOW)
    b, _ = generate_api_key("p", "b", now=NOW)
    assert a != b
    assert a.split(".")[0] != b.split(".")[0]


async def test_authenticate_accepts_the_key_and_records_its_use() -> None:
    store = MemoryApiKeyStore()
    plaintext, record = generate_api_key("auth0|alice", "ci bot", now=NOW)
    await store.insert(record)

    found = await authenticate_api_key(store, plaintext, now=LATER)

    assert found is not None
    assert found.id == record.id
    assert found.principal == "auth0|alice"
    stored = await store.find_by_prefix(record.prefix)
    assert stored is not None
    assert stored.last_used_at == LATER


async def test_authenticate_refuses_wrong_secret_unknown_prefix_garbage_and_revoked() -> None:
    store = MemoryApiKeyStore()
    plaintext, record = generate_api_key("auth0|alice", "ci bot", now=NOW)
    await store.insert(record)
    prefix = record.prefix

    assert await authenticate_api_key(store, f"{prefix}.not-the-secret", now=LATER) is None
    assert await authenticate_api_key(store, "AAAAAAAA.whatever", now=LATER) is None
    assert await authenticate_api_key(store, "no-dot-at-all", now=LATER) is None
    assert await authenticate_api_key(store, "", now=LATER) is None
    stored = await store.find_by_prefix(prefix)
    assert stored is not None
    assert stored.last_used_at is None  # refusals never touch the record

    await store.revoke(record.id, revoked_at=LATER)
    assert await authenticate_api_key(store, plaintext, now=LATER) is None
