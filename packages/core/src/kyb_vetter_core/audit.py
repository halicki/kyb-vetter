"""Audit trail: one event per tool invocation, success or failure (ADR-0013)."""

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any, cast
from uuid import uuid4
lazy from collections.abc import Callable

from kyb_vetter_core.errors import (
    InvalidIdentifierError,
    QuotaExhaustedError,
    RegistryError,
    UserLimitExceededError,
)
from kyb_vetter_core.storage.ports import AuditEvent

if TYPE_CHECKING:
    from pydantic import BaseModel

    from kyb_vetter_core.storage.ports import AuditStore
    from kyb_vetter_core.verification import SourceReceipt

ERROR_INVALID_INPUT = "INVALID_INPUT"
ERROR_QUOTA_GUARD = "QUOTA_GUARD"
ERROR_USER_LIMIT = "USER_LIMIT"


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


def error_code(exc: BaseException) -> str:
    match exc:
        case InvalidIdentifierError():
            return ERROR_INVALID_INPUT
        case QuotaExhaustedError():
            return ERROR_QUOTA_GUARD
        case UserLimitExceededError():
            return ERROR_USER_LIMIT
        case RegistryError() if exc.code is not None:
            return exc.code
    return type(exc).__name__


class AuditRecorder:
    def __init__(self, store: AuditStore, *, now: Callable[[], datetime] = utcnow) -> None:
        self._store = store
        self._now = now

    async def history(self, nip: str, *, principal: str, limit: int) -> list[AuditEvent]:
        return await self._store.history(nip, principal=principal, limit=limit)

    @staticmethod
    def digest(result: BaseModel) -> str:
        """SHA-256 of the canonical JSON of a result model."""
        canonical = json.dumps(
            result.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
        )
        return sha256(canonical.encode()).hexdigest()

    async def record_success(
        self,
        *,
        principal: str,
        tool: str,
        nip: str | None,
        input: dict[str, Any],
        result: BaseModel,
    ) -> AuditEvent:
        sources = cast("tuple[SourceReceipt, ...]", tuple(getattr(result, "sources", ())))
        event = AuditEvent(
            id=uuid4(),
            ts=self._now(),
            principal=principal,
            tool=tool,
            nip=nip,
            input=input,
            outcome="ok",
            error_code=None,
            request_ids=tuple(s.request_id for s in sources if s.request_id is not None),
            sources=tuple(s.source for s in sources),
            response_sha256=self.digest(result),
            result=result.model_dump(mode="json"),
            from_cache=any(s.from_cache for s in sources),
        )
        await self._store.record(event)
        return event

    async def record_error(
        self,
        *,
        principal: str,
        tool: str,
        nip: str | None,
        input: dict[str, Any],
        exc: BaseException,
    ) -> AuditEvent:
        event = AuditEvent(
            id=uuid4(),
            ts=self._now(),
            principal=principal,
            tool=tool,
            nip=nip,
            input=input,
            outcome="error",
            error_code=error_code(exc),
            request_ids=(),
            sources=(),
            response_sha256=None,
            result=None,
            from_cache=False,
        )
        await self._store.record(event)
        return event
