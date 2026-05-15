"""discover_environment shape (cheap, no real SDK call)."""

from __future__ import annotations

from avp_openai_agent import discover_environment


def test_discover_environment_returns_known_provider(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    env = discover_environment()
    assert env.provider == "openai"
    assert env.base_url is None


def test_azure_provider_detected(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.openai.azure.com/")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    env = discover_environment()
    assert env.provider == "azure.openai"


def test_compatible_provider_for_unknown_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    env = discover_environment()
    assert env.provider == "openai-compatible"
