"""Runtime configuration.

This module is the SINGLE place in the code base where the product name is
spelled out (see ADR-0004). Nothing else may hard-code it: build strings,
URLs, resource names and connector names from ``Settings`` instead, so that a
rebrand is a change to one line here plus one Terraform variable.

Environment variables use the neutral ``APP_`` prefix on purpose, so that
variable names survive a rebrand too.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_PROJECT_NAME = "kyb-vetter"
"""Working project name. Placeholder until the brand is decided."""

DEFAULT_DOMAIN = "localhost"
"""Placeholder; the real domain is injected per environment (APP_DOMAIN)."""


class Settings(BaseSettings):
    """Process-wide settings, read from the environment once at startup."""

    model_config = SettingsConfigDict(env_prefix="APP_", frozen=True, extra="ignore")

    project_name: str = DEFAULT_PROJECT_NAME
    """Product / project name used in user-facing strings and resource names."""

    domain: str = DEFAULT_DOMAIN
    """Public hostname the hosted service is reachable at."""

    @property
    def public_base_url(self) -> str:
        """Base URL of the hosted service; plain http only for localhost."""
        scheme = "http" if self.domain == "localhost" else "https"
        return f"{scheme}://{self.domain}"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached settings instance (construct ``Settings()`` directly in tests)."""
    return Settings()
