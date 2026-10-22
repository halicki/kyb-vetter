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
"""Working project name. Placeholder until the brand is decided."""

DEFAULT_DOMAIN = "localhost"
"""Placeholder; the real domain is injected per environment (APP_DOMAIN)."""

DEFAULT_MF_BASE_URL = "https://wykazpodatnikowvat.mf.gov.pl"
"""VAT white-list API host since 2026-10-15 (ADR-0009). Test env: wykazpodatnikowvat-test.mf.gov.pl."""

DEFAULT_KRS_BASE_URL = "https://api-krs.ms.gov.pl"
"""National Court Register open API."""

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
    """Product / project name used in user-facing strings and resource names."""

    domain: str = DEFAULT_DOMAIN
    """Public hostname the hosted service is reachable at."""

    mf_base_url: str = DEFAULT_MF_BASE_URL
    """Base URL of the Ministry of Finance white-list API (no trailing slash)."""

    krs_base_url: str = DEFAULT_KRS_BASE_URL
    """Base URL of the KRS API (no trailing slash)."""

    http_timeout_s: float = 10.0
    """Per-request timeout for registry calls, in seconds."""

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
    def user_agent(self) -> str:
        """``User-Agent`` sent to registries, e.g. ``kyb-vetter/0.1.0``."""
        return f"{self.project_name}/{version('kyb-vetter-core')}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance (construct ``Settings()`` directly in tests)."""
    return Settings()
