import pytest

from kyb_vetter_core import __version__
from kyb_vetter_core.config import (
    DEFAULT_DOMAIN,
    DEFAULT_PROJECT_NAME,
    Settings,
    get_settings,
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
