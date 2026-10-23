from kyb_vetter_core.storage.memory import (
    MemoryApiKeyStore,
    MemoryAuditStore,
    MemoryCacheStore,
    MemoryQuotaStore,
)

from .contract import apikey_contract, audit_contract, cache_contract, quota_contract


async def test_memory_apikey_store_contract() -> None:
    await apikey_contract(MemoryApiKeyStore())


async def test_memory_quota_store_contract() -> None:
    await quota_contract(MemoryQuotaStore())


async def test_memory_audit_store_contract() -> None:
    await audit_contract(MemoryAuditStore())


async def test_memory_cache_store_contract() -> None:
    await cache_contract(MemoryCacheStore())
