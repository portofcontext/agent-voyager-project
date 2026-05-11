"""`_provider_from_env` resolves `gen_ai.provider.name` for agent_started.

The OpenAI Agents SDK speaks the OpenAI API by default. With
`OPENAI_BASE_URL` (or its legacy alias `OPENAI_API_BASE`) overridden,
it can speak to OpenAI-compatible backends (Azure OpenAI, Together,
OpenRouter, local Ollama, …). This unit pins the resolution rules so a
supervisor reading the trajectory can answer "which backend served this
run" without guessing.
"""

from __future__ import annotations

from avp_openai_agent.translator import _provider_from_env


def test_default_when_no_env_set(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert _provider_from_env() == "openai"


def test_official_api_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert _provider_from_env() == "openai"


def test_azure_openai(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://my-resource.openai.azure.com/")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert _provider_from_env() == "azure.openai"


def test_azure_inferred_from_host_keyword(monkeypatch) -> None:
    """Some Azure deployments use custom DNS that doesn't include
    `openai.azure.com` literally but does include `azure`. We err on
    the side of tagging those as Azure rather than `openai-compatible`."""
    monkeypatch.setenv("OPENAI_BASE_URL", "https://azure-internal.example.org/v1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert _provider_from_env() == "azure.openai"


def test_openai_compatible_for_unknown_base_url(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    assert _provider_from_env() == "openai-compatible"


def test_legacy_alias_openai_api_base(monkeypatch) -> None:
    """OPENAI_API_BASE is the legacy spelling some users still set;
    the SDK reads it as a fallback. Honor it here for consistency."""
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    assert _provider_from_env() == "openai"


def test_new_alias_wins_over_legacy(monkeypatch) -> None:
    """If both env vars are set the new one (OPENAI_BASE_URL) wins —
    matches the SDK's own resolution order."""
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.openai.com/v1")
    assert _provider_from_env() == "openai-compatible"
