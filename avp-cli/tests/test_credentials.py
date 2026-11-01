"""Proxy credentials for the sandbox's Credential Vault."""

from typing import Any

import pytest
from conftest import Memory
from opensandbox.models.sandboxes import CredentialAuth, CredentialMatch

from avp.commission import Commission
from avp_cli.console import Failed
from avp_cli.runs import credentials
from avp_cli.vault import store


def commission(model: dict[str, Any], **fields: Any) -> Commission:
    return Commission.model_validate(
        {"avp_version": "0.1", "run_id": "r", "prompt": "hi", "model": model, **fields}
    )


def test_no_proxy_credential_needs_no_vault(memory: Memory) -> None:
    model = {"provider": "anthropic", "id": "m", "credential": {"env": "KEY"}}
    assert credentials.vault(commission(model)) is None


def test_api_key_header(memory: Memory) -> None:
    store.set_("ant", "sk-ant")
    model = {"provider": "anthropic", "id": "m", "credential": {"proxy": "ant"}}
    vault = credentials.vault(commission(model))
    assert vault is not None
    assert [(c.name, c.source.value) for c in vault.credentials] == [("ant", "sk-ant")]  # ty: ignore[unresolved-attribute]
    [binding] = vault.bindings
    assert binding.match == CredentialMatch(hosts=["api.anthropic.com"], schemes=["https"])
    assert binding.auth == CredentialAuth(type="apiKey", name="x-api-key", credential="ant")


def test_bearer_at_the_base_url(memory: Memory) -> None:
    store.set_("oai", "sk-oai")
    model = {
        "provider": "openai",
        "id": "m",
        "base_url": "http://localhost:8000/v1",
        "credential": {"proxy": "oai"},
    }
    vault = credentials.vault(commission(model))
    assert vault is not None
    [binding] = vault.bindings
    assert binding.match == CredentialMatch(hosts=["localhost"], schemes=["http"])
    assert binding.auth == CredentialAuth(type="bearer", credential="oai")


def test_credential_missing_from_the_vault(memory: Memory) -> None:
    model = {"provider": "anthropic", "id": "m", "credential": {"proxy": "nope"}}
    with pytest.raises(Failed, match=r"model\.credential names 'nope', which isn't in the vault"):
        credentials.vault(commission(model))


def test_provider_without_a_known_header(memory: Memory) -> None:
    store.set_("k", "v")
    model = {
        "provider": "nobody-knows",
        "id": "m",
        "base_url": "https://x.example.com",
        "credential": {"proxy": "k"},
    }
    with pytest.raises(Failed, match="doesn't know how 'nobody-knows' takes an API key"):
        credentials.vault(commission(model))


def test_mcp_header_proxy_isnt_supported_yet(memory: Memory) -> None:
    servers = [
        {
            "id": "web",
            "name": "Web",
            "type": "http",
            "url": "https://mcp.example.com/mcp",
            "headers": {"Authorization": {"proxy": "token"}},
        }
    ]
    with pytest.raises(Failed, match="can't add yet"):
        credentials.vault(commission({"provider": "anthropic", "id": "m"}, mcp_servers=servers))
