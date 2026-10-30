"""Runtime configuration.

This module is the SINGLE place in the code base where the product name is
spelled out (see ADR-0004). Nothing else may hard-code it: build strings,
URLs, resource names and connector names from ``Settings`` instead, so that a
rebrand is a change to one line here plus one Terraform variable.

Environment variables use the neutral ``APP_`` prefix on purpose, so that
variable names survive a rebrand too.
"""

from functools import lru_cache
from importlib.metadata import version
from typing import Literal
from urllib.parse import urlsplit

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PROJECT_NAME = "kyb-vetter"
DEFAULT_PRODUCT_NAME = "KYB Vetter"
"""Working project name. Placeholder until the brand is decided."""

DEFAULT_DOMAIN = "localhost"
"""Placeholder; the real domain is injected per environment (APP_DOMAIN)."""

DEFAULT_MF_BASE_URL = "https://wykazpodatnikowvat.mf.gov.pl"
"""VAT white-list API host since 2026-10-15 (ADR-0009). Test env: wykazpodatnikowvat-test.mf.gov.pl."""

DEFAULT_KRS_BASE_URL = "https://api-krs.ms.gov.pl"
"""National Court Register open API."""

DEFAULT_USER_LIMIT_VERIFY = 200
DEFAULT_USER_LIMIT_CHECK = 500
"""Per-user daily call budgets (ADR-0019); 0 disables a limit."""

RegistryEnvironment = Literal["production", "test"]

PRODUCTION_REGISTRY_HOSTS: frozenset[str] = frozenset(
    urlsplit(url).netloc for url in (DEFAULT_MF_BASE_URL, DEFAULT_KRS_BASE_URL)
)
"""Hosts whose answers are legally meaningful; everything else is a sandbox or a mock."""


def registry_environment(host: str) -> RegistryEnvironment:
    """Classify the host a registry answer came from, so results from the MF test
    environment (synthetic companies) are never mistaken for the real register."""
    return "production" if host in PRODUCTION_REGISTRY_HOSTS else "test"


class Settings(BaseSettings):
    """Process-wide settings, read from the environment once at startup."""

    model_config = SettingsConfigDict(env_prefix="APP_", frozen=True, extra="ignore")

    project_name: str = DEFAULT_PROJECT_NAME
    product_name: str = DEFAULT_PRODUCT_NAME
    """Display name shown to users (MCP server identity, OpenAPI title); the slug stays for
    resources and the user agent."""

    website_url: str | None = None
    """Public website (documentation, privacy policy) advertised in the MCP server identity."""
    """Product / project name used in user-facing strings and resource names."""

    domain: str = DEFAULT_DOMAIN
    """Public hostname the hosted service is reachable at."""

    mf_base_url: str = DEFAULT_MF_BASE_URL
    """Base URL of the Ministry of Finance white-list API (no trailing slash)."""

    krs_base_url: str = DEFAULT_KRS_BASE_URL
    """Base URL of the KRS API (no trailing slash)."""

    http_timeout_s: float = 10.0
    """Per-request timeout for registry calls, in seconds."""

    database_url: str | None = None
    """SQLAlchemy async URL (``postgresql+asyncpg://...``). Unset = in-memory storage, not persistent."""

    extra_allowed_hosts: list[str] = []
    """Additional ``Host`` values accepted by the hosted transport (JSON list in APP_EXTRA_ALLOWED_HOSTS)."""

    host_check: bool = True
    """Reject requests whose ``Host`` is not allow-listed (DNS-rebinding protection). Off behind
    a TLS-terminating platform such as Cloud Run, where the hostname is fixed by the platform."""

    flatfile_bucket: str | None = None
    """GCS bucket holding the daily flat-file index (APP_FLATFILE_BUCKET); worker writes, service reads."""

    flatfile_dir: str | None = None
    """Local directory used instead of a bucket (APP_FLATFILE_DIR); in-memory when both are unset."""

    mf_flatfile_base_url: str = "https://wykazpodatnikowvat.mf.gov.pl/plikplaski"
    """Where the ministry publishes ``YYYYMMDD.7z`` (APP_MF_FLATFILE_BASE_URL)."""

    auth_issuer: str | None = None
    """OAuth authorization server that issues our access tokens (APP_AUTH_ISSUER), kept verbatim
    because the ``iss`` claim is compared as a string (Auth0 ends with ``/``). Unset = no auth."""

    auth_audience: str | None = None
    """Resource identifier the tokens must carry in ``aud`` (APP_AUTH_AUDIENCE); defaults to the
    public MCP URL. This is also the RFC 9728 ``resource`` the server advertises."""

    user_daily_limit_verify: int = DEFAULT_USER_LIMIT_VERIFY
    """``verify_company`` calls per user per day (APP_USER_DAILY_LIMIT_VERIFY); 0 = unlimited."""

    user_daily_limit_check: int = DEFAULT_USER_LIMIT_CHECK
    """``check_bank_account`` calls per user per day (APP_USER_DAILY_LIMIT_CHECK); 0 = unlimited."""

    log_format: Literal["text", "json"] = "text"
    """``json`` emits one Cloud Logging record per line (APP_LOG_FORMAT); ``text`` for terminals."""

    trace_export: Literal["none", "gcp"] = "none"
    """``gcp`` ships OpenTelemetry spans to Cloud Trace via OTLP (APP_TRACE_EXPORT)."""

    gcp_project: str | None = None
    """Google Cloud project id (APP_GCP_PROJECT): trace correlation in logs and the OTLP target."""

    @field_validator("mf_base_url", "krs_base_url")
    @classmethod
    def _strip_trailing_slash(cls, value: str) -> str:
        return value.rstrip("/")

    @property
    def public_base_url(self) -> str:
        """Base URL of the hosted service; plain http only for localhost."""
        scheme = "http" if self.domain == "localhost" else "https"
        return f"{scheme}://{self.domain}"

    @property
    def auth_enabled(self) -> bool:
        return self.auth_issuer is not None

    @property
    def auth_jwks_url(self) -> str:
        """JWKS endpoint of the issuer (OIDC discovery location), e.g. ``https://idp/.well-known/jwks.json``."""
        return f"{(self.auth_issuer or '').rstrip('/')}/.well-known/jwks.json"

    @property
    def auth_resource_url(self) -> str:
        """Our OAuth resource identifier: ``auth_audience`` or ``<public_base_url>/mcp``."""
        return self.auth_audience or f"{self.public_base_url}/mcp"

    @property
    def user_agent(self) -> str:
        """``User-Agent`` sent to registries, e.g. ``kyb-vetter/0.1.0``."""
        return f"{self.project_name}/{version('kyb-vetter-core')}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance (construct ``Settings()`` directly in tests)."""
    return Settings()
