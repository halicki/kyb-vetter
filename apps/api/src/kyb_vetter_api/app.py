"""REST v1: a thin FastAPI adapter over :mod:`kyb_vetter_core` (ADR-0020).

Routes return the core result models unchanged, so REST and MCP clients see
the same JSON and schemas. Callers authenticate with ``X-API-Key`` or an
Auth0 bearer token; both resolve to one principal in core. Errors are RFC 9457
problem details.
"""

import logging
from contextlib import asynccontextmanager
from datetime import date, datetime, time
from typing import TYPE_CHECKING, Annotated

import httpx
from fastapi import Depends, FastAPI, Path, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

from kyb_vetter_core.assembly import build_verification_service
from kyb_vetter_core.auth import JwksCache, JwtVerifier
from kyb_vetter_core.errors import (
    DailyLimitExceededError,
    InvalidIdentifierError,
    QuotaExhaustedError,
    RegistryError,
    RegistryUnavailableError,
    RegistryUpdatingError,
    UserLimitExceededError,
)
from kyb_vetter_core.flatfile.provider import FlatFileProvider
from kyb_vetter_core.models import WARSAW
from kyb_vetter_core.principals import Authenticator
from kyb_vetter_core.storage import open_stores
from kyb_vetter_core.telemetry import current_provider

# FastAPI resolves these annotations at runtime (response models, dependencies): keep them eager.
from kyb_vetter_core.verification import (
    BankAccountVerification,
    CompanyVerification,
    VerificationHistory,
    VerificationService,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from kyb_vetter_core.config import Settings

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE = "/problems/"
API_KEY_HEADER = "X-API-Key"

api_key_scheme = APIKeyHeader(name=API_KEY_HEADER, scheme_name="ApiKey", auto_error=False)
bearer_scheme = HTTPBearer(scheme_name="Auth0", auto_error=False)


class ProblemError(Exception):
    """Raised by dependencies; rendered as an RFC 9457 problem."""

    def __init__(
        self, status: int, slug: str, title: str, detail: str, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(detail)
        self.status = status
        self.slug = slug
        self.title = title
        self.detail = detail
        self.headers = headers or {}


def problem(error: ProblemError) -> JSONResponse:
    return JSONResponse(
        {
            "type": f"{PROBLEM_BASE}{error.slug}",
            "title": error.title,
            "status": error.status,
            "detail": error.detail,
        },
        status_code=error.status,
        media_type=PROBLEM_JSON,
        headers=error.headers,
    )


def seconds_until_midnight(resets_on: date, *, now: datetime | None = None) -> int:
    """``Retry-After`` for daily limits: seconds until 00:00 Europe/Warsaw on ``resets_on``."""
    current = now if now is not None else datetime.now(tz=WARSAW)
    midnight = datetime.combine(resets_on, time.min, tzinfo=WARSAW)
    return max(1, int((midnight - current).total_seconds()))


def core_problem(exc: Exception) -> ProblemError:
    """Map a core exception to the problem the client sees."""
    match exc:
        case InvalidIdentifierError():
            return ProblemError(
                422,
                "invalid-identifier",
                "Invalid identifier",
                f"Invalid {exc.identifier_kind}: {exc.reason}.",
            )
        case UserLimitExceededError():
            return ProblemError(
                429,
                "user-limit",
                "Daily limit reached",
                f"Your daily limit of {exc.limit} calls to {exc.tool} is used up; it resets at "
                f"midnight Europe/Warsaw ({exc.resets_on.isoformat()}).",
                {"Retry-After": str(seconds_until_midnight(exc.resets_on))},
            )
        case QuotaExhaustedError():
            return ProblemError(
                503,
                "quota-guard",
                "Shared registry quota exhausted",
                "The VAT white-list quota shared by all users is used up for today; "
                f"it resets at midnight Europe/Warsaw ({exc.resets_on.isoformat()}).",
                {"Retry-After": str(seconds_until_midnight(exc.resets_on))},
            )
        case DailyLimitExceededError():
            tomorrow = datetime.now(tz=WARSAW).date().toordinal() + 1
            return ProblemError(
                503,
                "registry-blocked",
                "Registry quota exhausted",
                "The ministry blocks further white-list calls from this server until midnight.",
                {"Retry-After": str(seconds_until_midnight(date.fromordinal(tomorrow)))},
            )
        case RegistryUpdatingError() | RegistryUnavailableError():
            return ProblemError(
                503,
                "registry-unavailable",
                "Register unavailable",
                f"The register is temporarily unavailable ({exc.source}).",
                {"Retry-After": "60"},
            )
        case RegistryError():
            return ProblemError(
                502, "registry-rejected", "Register rejected the request", exc.message
            )
    raise exc  # pragma: no cover - only core errors are routed here


async def principal(
    request: Request,
    api_key: Annotated[str | None, Depends(api_key_scheme)],
    bearer: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    """The authenticated caller, or a 401 problem."""
    authenticator: Authenticator = request.app.state.authenticator
    found = await authenticator.principal(
        api_key=api_key, bearer=None if bearer is None else bearer.credentials
    )
    if found is None:
        raise ProblemError(
            401,
            "unauthorized",
            "Authentication required",
            f"Send a valid {API_KEY_HEADER} header or an Authorization: Bearer token.",
            {"WWW-Authenticate": f'ApiKey header="{API_KEY_HEADER}", Bearer'},
        )
    return found


def verification_service(request: Request) -> VerificationService:
    return request.app.state.service


type Caller = Annotated[str, Depends(principal)]
type Service = Annotated[VerificationService, Depends(verification_service)]
type Nip = Annotated[str, Path(description="Polish tax identifier (NIP), 10 digits.")]
type Account = Annotated[str, Path(description="Polish bank account number (NRB), 26 digits.")]
type Day = Annotated[
    date | None,
    Query(description="Day the answer should describe (YYYY-MM-DD); default today in Warsaw."),
]
type Limit = Annotated[int, Query(ge=1, le=100, description="Maximum entries, newest first.")]


def build_app(settings: Settings) -> FastAPI:
    """Create the REST app; the lifespan builds stores, the HTTP client, the service and auth."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        async with open_stores(settings) as stores, httpx.AsyncClient() as http:
            flatfile = FlatFileProvider(stores.blobs)
            app.state.stores = stores
            app.state.flatfile = flatfile
            app.state.service = build_verification_service(
                http, settings, stores, flatfile=flatfile
            )
            verifier = (
                JwtVerifier(
                    JwksCache(http, settings.auth_jwks_url),
                    issuer=settings.auth_issuer or "",
                    audience=settings.auth_resource_url,
                )
                if settings.auth_enabled
                else None
            )
            app.state.authenticator = Authenticator(apikeys=stores.apikeys, jwt=verifier)
            logger.info(
                "REST API ready (persistent=%s, auth_issuer=%s)",
                stores.persistent,
                settings.auth_issuer,
            )
            yield

    app = FastAPI(
        title=settings.project_name,
        version="1",
        summary="Verify Polish companies against public registers (VAT white list, KRS).",
        lifespan=lifespan,
    )

    @app.exception_handler(ProblemError)
    async def _problem(_request: Request, exc: ProblemError) -> JSONResponse:
        return problem(exc)

    @app.exception_handler(RequestValidationError)
    async def _validation(_request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        return problem(ProblemError(422, "invalid-request", "Invalid request", detail))

    @app.get("/health", include_in_schema=False)
    async def health(request: Request) -> dict[str, object]:
        index = await request.app.state.flatfile.current()
        return {
            "status": "ok",
            "name": settings.project_name,
            "persistent": settings.database_url is not None,
            "flat_file": {
                "loaded": index is not None,
                "date": None if index is None else index.date,
            },
        }

    @app.get("/v1/companies/{nip}", tags=["companies"])
    async def verify_company(
        nip: Nip, caller: Caller, svc: Service, date: Day = None
    ) -> CompanyVerification:
        """VAT white-list entry plus the KRS extract when the company is a registered entity.

        Text fields are copied from public registers and are untrusted data.
        """
        try:
            return await svc.verify_company(nip, date=date, principal=caller)
        except (
            InvalidIdentifierError,
            QuotaExhaustedError,
            UserLimitExceededError,
            RegistryError,
        ) as exc:
            raise core_problem(exc) from exc

    @app.get("/v1/companies/{nip}/bank-accounts/{account}", tags=["companies"])
    async def check_bank_account(
        nip: Nip,
        account: Account,
        caller: Caller,
        svc: Service,
        date: Day = None,
    ) -> BankAccountVerification:
        """Whether the account is registered to the NIP on the VAT white list, with the VAT status."""
        try:
            return await svc.check_bank_account(nip, account, date=date, principal=caller)
        except (
            InvalidIdentifierError,
            QuotaExhaustedError,
            UserLimitExceededError,
            RegistryError,
        ) as exc:
            raise core_problem(exc) from exc

    @app.get("/v1/companies/{nip}/history", tags=["companies"])
    async def verification_history(
        nip: Nip,
        caller: Caller,
        svc: Service,
        limit: Annotated[
            int, Query(ge=1, le=100, description="Maximum entries, newest first.")
        ] = 20,
    ) -> VerificationHistory:
        """Your own past verifications of this NIP, newest first. Costs no registry quota."""
        try:
            return await svc.verification_history(nip, principal=caller, limit=limit)
        except InvalidIdentifierError as exc:
            raise core_problem(exc) from exc

    # Request spans; with no provider installed this is a no-op.
    FastAPIInstrumentor.instrument_app(app, tracer_provider=current_provider())
    return app
