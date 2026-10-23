import pytest

from kyb_vetter_core import __version__
from kyb_vetter_core.config import (
    DEFAULT_DOMAIN,
    DEFAULT_PROJECT_NAME,
    Settings,
    get_settings,
    registry_environment,
)


def test_version_is_exposed() -> None:
    assert __version__


def test_defaults_without_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_PROJECT_NAME", raising=False)
    monkeypatch.delenv("APP_DOMAIN", raising=False)

    settings = Settings()

    assert settings.project_name == DEFAULT_PROJECT_NAME
    assert settings.domain == DEFAULT_DOMAIN
    assert settings.public_base_url == "http://localhost"


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_PROJECT_NAME", "acme-verify")
    monkeypatch.setenv("APP_DOMAIN", "mcp.acme.example")

    settings = Settings()

    assert settings.project_name == "acme-verify"
    assert settings.domain == "mcp.acme.example"
    assert settings.public_base_url == "https://mcp.acme.example"


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(Exception, match="frozen"):
        settings.project_name = "other"  # type: ignore[misc]


def test_get_settings_is_cached() -> None:
    get_settings.cache_clear()
    assert get_settings() is get_settings()


def test_registry_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_MF_BASE_URL", "APP_KRS_BASE_URL", "APP_HTTP_TIMEOUT_S"):
        monkeypatch.delenv(name, raising=False)

    settings = Settings()

    assert settings.mf_base_url == "https://wykazpodatnikowvat.mf.gov.pl"
    assert settings.krs_base_url == "https://api-krs.ms.gov.pl"
    assert settings.http_timeout_s == 10.0
    assert settings.user_agent.startswith(f"{DEFAULT_PROJECT_NAME}/")


def test_registry_settings_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_MF_BASE_URL", "https://wykazpodatnikowvat-test.mf.gov.pl/")
    monkeypatch.setenv("APP_HTTP_TIMEOUT_S", "2.5")

    settings = Settings()

    assert (
        settings.mf_base_url == "https://wykazpodatnikowvat-test.mf.gov.pl"
    )  # trailing slash stripped
    assert settings.http_timeout_s == 2.5


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("wykazpodatnikowvat.mf.gov.pl", "production"),
        ("api-krs.ms.gov.pl", "production"),
        ("wykazpodatnikowvat-test.mf.gov.pl", "test"),
        ("mf.example", "test"),
    ],
)
def test_registry_environment_knows_the_official_production_hosts(host: str, expected: str) -> None:
    assert registry_environment(host) == expected


def test_database_url_is_optional(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    assert Settings().database_url is None
    monkeypatch.setenv("APP_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app")
    assert Settings().database_url == "postgresql+asyncpg://app:app@localhost:5432/app"


def test_flat_file_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("APP_FLATFILE_BUCKET", "APP_FLATFILE_DIR", "APP_MF_FLATFILE_BASE_URL"):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.flatfile_bucket is None
    assert settings.flatfile_dir is None
    assert settings.mf_flatfile_base_url == "https://wykazpodatnikowvat.mf.gov.pl/plikplaski"
    monkeypatch.setenv("APP_FLATFILE_BUCKET", "bucket-1")
    assert Settings().flatfile_bucket == "bucket-1"


def test_auth_is_off_unless_an_issuer_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_AUTH_ISSUER", raising=False)
    monkeypatch.delenv("APP_AUTH_AUDIENCE", raising=False)

    settings = Settings(domain="mcp.acme.example")

    assert settings.auth_enabled is False
    assert settings.auth_resource_url == "https://mcp.acme.example/mcp"


def test_auth_settings_derive_jwks_and_audience_from_issuer_and_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_AUTH_ISSUER", "https://tenant.eu.auth0.com/")
    monkeypatch.delenv("APP_AUTH_AUDIENCE", raising=False)

    settings = Settings(domain="mcp.acme.example")

    assert settings.auth_enabled is True
    assert (
        settings.auth_issuer == "https://tenant.eu.auth0.com/"
    )  # kept verbatim: ``iss`` must match
    assert settings.auth_jwks_url == "https://tenant.eu.auth0.com/.well-known/jwks.json"
    assert settings.auth_resource_url == "https://mcp.acme.example/mcp"


def test_auth_audience_can_be_overridden_and_issuer_without_slash_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_AUTH_ISSUER", "https://idp.example")
    monkeypatch.setenv("APP_AUTH_AUDIENCE", "https://api.acme.example/mcp")

    settings = Settings(domain="mcp.acme.example")

    assert settings.auth_jwks_url == "https://idp.example/.well-known/jwks.json"
    assert settings.auth_resource_url == "https://api.acme.example/mcp"
