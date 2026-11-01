"""Proxy credentials for the sandbox's Credential Vault."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import Memory
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from opensandbox.models.sandboxes import CredentialAuth, CredentialMatch, CustomHeaderEntry

from avp.commission import Commission
from avp_cli.console import Failed
from avp_cli.runs import credentials
from avp_cli.vault import oauth, store

MODEL = {"provider": "anthropic", "id": "m"}


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


def server(headers: dict[str, Any], url: str = "https://mcp.example.com/mcp") -> dict[str, Any]:
    return {"id": "web", "name": "Web", "type": "http", "url": url, "headers": headers}


def sign_in(name: str, access_token: str) -> None:
    grant = oauth.Grant(
        tokens=OAuthToken(access_token=access_token, refresh_token="r"),
        client=OAuthClientInformationFull(client_id="c", redirect_uris=["http://127.0.0.1/"]),
    )
    expires_at = datetime.now(UTC) + timedelta(hours=1)
    url = "https://mcp.example.com/mcp"
    details = store.OAuth(url=url, token_endpoint=url, expires_at=expires_at)
    store.set_(name, grant.model_dump_json(), oauth=details)


def test_mcp_headers_get_the_values_as_stored(memory: Memory) -> None:
    store.set_("docs", "Token abc")
    headers = {"Authorization": {"proxy": "docs"}, "X-Plain": "not a secret"}
    vault = credentials.vault(commission(MODEL, mcp_servers=[server(headers)]))
    assert vault is not None
    assert [(c.name, c.source.value) for c in vault.credentials] == [("docs", "Token abc")]  # ty: ignore[unresolved-attribute]
    [binding] = vault.bindings
    assert binding.name == "mcp-web"
    assert binding.match == CredentialMatch(hosts=["mcp.example.com"], schemes=["https"])
    assert binding.auth == CredentialAuth(
        type="customHeaders",
        headers=[CustomHeaderEntry(name="Authorization", credential="docs")],
    )


def test_sign_in_is_a_bearer_token_in_authorization_only(memory: Memory) -> None:
    sign_in("linear", "access-1")
    headers = {"Authorization": {"proxy": "linear"}, "X-Token": {"proxy": "linear"}}
    vault = credentials.vault(commission(MODEL, mcp_servers=[server(headers)]))
    assert vault is not None
    assert [(c.name, c.source.value) for c in vault.credentials] == [  # ty: ignore[unresolved-attribute]
        ("linear", "Bearer access-1"),
        ("linear-2", "access-1"),
    ]
    assert vault.bindings[0].auth.headers == [  # ty: ignore[unresolved-attribute]
        CustomHeaderEntry(name="Authorization", credential="linear"),
        CustomHeaderEntry(name="X-Token", credential="linear-2"),
    ]


def test_model_and_mcp_server_at_one_host_fail(memory: Memory) -> None:
    store.set_("ant", "sk-ant")
    store.set_("docs", "t")
    model = {"provider": "anthropic", "id": "m", "credential": {"proxy": "ant"}}
    servers = [server({"Authorization": {"proxy": "docs"}}, url="https://api.anthropic.com/mcp")]
    with pytest.raises(Failed, match=r"both need the vault at api\.anthropic\.com"):
        credentials.vault(commission(model, mcp_servers=servers))
