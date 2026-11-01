"""Proxy credentials: each `{"proxy": NAME}` in the Commission is read from
`avp vault` and written to the sandbox's OpenSandbox Credential Vault, which
adds it to the agent's matching requests. The agent never sees the value; it
sends a stand-in, which the vault replaces.

- `model.credential`: added to requests to the model's host, in the header
  the SDK's endpoints give for the provider.
"""

from urllib.parse import urlparse

from opensandbox.models.sandboxes import (
    Credential,
    CredentialAuth,
    CredentialBinding,
    CredentialMatch,
)

from avp.commission import Commission, McpServerHttp, ProxySecret
from avp.utils.endpoints import bundled_endpoints, provider_auth
from avp_cli.console import Failed
from avp_cli.runs import network
from avp_cli.sandbox.sandboxes import Vault
from avp_cli.vault import oauth, store

BEARER = ("authorization", "Bearer ")


def vault(commission: Commission) -> Vault | None:
    """The Credential Vault for the Commission's proxy credentials, or None when
    it has none. Fails before the run when a credential isn't in `avp vault`
    or no proxy rule can add it."""
    for server in commission.mcp_servers or []:
        if isinstance(server, McpServerHttp):
            for header, value in (server.headers or {}).items():
                if isinstance(value, ProxySecret):
                    raise Failed(
                        f"MCP server {server.id!r}'s {header} header is a proxy credential,"
                        " which avp run can't add yet"
                    )
    credential = commission.model.credential
    if not isinstance(credential, ProxySecret):
        return None
    binding = _model_binding(commission, credential.proxy)
    return Vault(
        credentials=[_credential(credential.proxy, "model.credential")], bindings=[binding]
    )


def _model_binding(commission: Commission, name: str) -> CredentialBinding:
    provider = commission.model.provider
    base_url = network.model_url(commission)
    if not base_url:
        raise Failed(
            f"avp knows no URL for {provider!r} models, so the vault can't add"
            " model.credential; set model.base_url"
        )
    auth = provider_auth(bundled_endpoints(), provider)
    if auth is None:
        raise Failed(
            f"avp doesn't know how {provider!r} takes an API key, so the vault can't add"
            ' model.credential; use {"env": NAME} with --env'
        )
    if (auth.header, auth.prefix) == BEARER:
        rule = CredentialAuth(type="bearer", credential=name)
    elif not auth.prefix:
        rule = CredentialAuth(type="apiKey", name=auth.header, credential=name)
    else:
        raise Failed(
            f"{provider!r} takes its key as {auth.header}: {auth.prefix}<key>, which the"
            ' vault can\'t add; use {"env": NAME} with --env'
        )
    url = urlparse(base_url)
    scheme = "http" if url.scheme == "http" else "https"
    return CredentialBinding(
        name="model",
        match=CredentialMatch(hosts=[url.hostname or ""], schemes=[scheme]),
        auth=rule,
    )


def _credential(name: str, where: str) -> Credential:
    if name not in {secret.name for secret in store.secrets()}:
        raise Failed(
            f"{where} names {name!r}, which isn't in the vault; add it with `avp vault set`"
        )
    return Credential(name=name, source={"type": "inline", "value": oauth.value(name)})
