"""Hosted transport: Streamable HTTP (stateless, JSON responses) plus a health endpoint.

The SDK builds the Starlette app and owns its lifespan (session manager → server
lifespan → stores and HTTP clients). DNS-rebinding protection is on by default for
local runs and switched off by ``APP_HOST_CHECK=false`` behind Cloud Run (ADR-0015).
"""

from typing import TYPE_CHECKING

from mcp.server.transport_security import TransportSecuritySettings
from opentelemetry.instrumentation.starlette import StarletteInstrumentor
from starlette.responses import JSONResponse

from kyb_vetter_core.telemetry import current_provider
from kyb_vetter_mcp.auth import resource_metadata
from kyb_vetter_mcp.server import build_server

if TYPE_CHECKING:
    from kyb_vetter_mcp.server import AppState

if TYPE_CHECKING:
    from starlette.applications import Starlette
    from starlette.requests import Request

    from kyb_vetter_core.config import Settings

MCP_PATH = "/mcp"
HEALTH_PATH = "/health"  # not /healthz: Google Front End intercepts that exact path on Cloud Run
PRM_ROOT_PATH = "/.well-known/oauth-protected-resource"
"""RFC 9728 fallback location; the SDK serves the path-scoped variant (``.../mcp``) itself."""


def allowed_hosts(settings: Settings) -> list[str]:
    """Hosts accepted in the ``Host`` header: the configured domain, loopback, plus extras from env."""
    hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    if settings.domain and settings.domain != "localhost":
        hosts.append(settings.domain)
    hosts.extend(settings.extra_allowed_hosts)
    return hosts


def build_http_app(settings: Settings) -> Starlette:
    states: list[AppState] = []
    server = build_server(settings, on_state=states.append)

    @server.custom_route(HEALTH_PATH, methods=["GET"], include_in_schema=False)
    async def healthz(_request: Request) -> JSONResponse:
        index = await states[0].flatfile.current() if states else None
        return JSONResponse(
            {
                "status": "ok",
                "name": settings.project_name,
                "persistent": settings.database_url is not None,
                "flat_file": {
                    "loaded": index is not None,
                    "date": None if index is None else index.date,
                },
            }
        )

    if settings.auth_enabled:
        document = resource_metadata(settings).model_dump(mode="json", exclude_none=True)

        @server.custom_route(PRM_ROOT_PATH, methods=["GET"], include_in_schema=False)
        async def prm_root(_request: Request) -> JSONResponse:
            return JSONResponse(document, headers={"Cache-Control": "public, max-age=3600"})

    app = server.streamable_http_app(
        streamable_http_path=MCP_PATH,
        json_response=True,
        stateless_http=True,
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=settings.host_check,
            allowed_hosts=allowed_hosts(settings),
            allowed_origins=[],
        ),
    )
    # Request spans; with no provider installed this is a no-op.
    StarletteInstrumentor.instrument_app(app, tracer_provider=current_provider())
    return app
