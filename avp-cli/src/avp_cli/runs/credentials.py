"""Proxy credentials: each `{"proxy": NAME}` in the Commission is read from
`avp vault` and written to the sandbox's OpenSandbox Credential Vault, which
adds it to the agent's matching requests. The agent never sees the value; it
sends a stand-in, which the vault replaces.

- `model.credential`: added to requests to the model's host, in the header
  the SDK's endpoints give for the provider.
- An HTTP MCP server's `headers`: each set on requests to the server's host,
  to the secret's value as stored. For an OAuth sign-in, the value is its
  access token, after `Bearer ` in an `Authorization` header.

The vault rejects a request that two bindings match, so each host gets one
binding: the model's, or one MCP server's for all its headers.
"""

from urllib.parse import urlparse

from opensandbox.models.sandboxes import (
    Credential,
    CredentialAuth,
    CredentialBinding,
    CredentialMatch,
    CustomHeaderEntry,
)

from avp.commission import Commission, McpServerHttp, ProxySecret
from avp.utils.endpoints import bundled_endpoints, provider_auth
from avp_cli.console import Failed, detail
from avp_cli.runs import network
from avp_cli.sandbox.sandboxes import Vault
from avp_cli.vault import oauth, store

BEARER = ("authorization", "Bearer ")


def vault(commission: Commission) -> Vault | None:
    """The Credential Vault for the Commission's proxy credentials, or None when
    it has none. Fails before the run when a credential isn't in `avp vault`
    or no proxy rule can add it."""
    builder = _Builder()
    credential = commission.model.credential
    if isinstance(credential, ProxySecret):
        builder.bind("model.credential", *_model_binding(commission, builder, credential.proxy))
    for server in commission.mcp_servers or []:
        if not isinstance(server, McpServerHttp):
            continue
        where = f"MCP server {server.id!r}"
        headers = [
            CustomHeaderEntry(name=header, credential=builder.add(value.proxy, where, header))
            for header, value in (server.headers or {}).items()
            if isinstance(value, ProxySecret)
        ]
        if headers:
            rule = CredentialAuth(type="customHeaders", headers=headers)
            builder.bind(where, f"mcp-{server.id}", _match(server.url), rule)
    return builder.vault()


class _Builder:
    """Credentials by their name in the sandbox's vault, and one binding per host."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.forms: dict[str, tuple[str, bool]] = {}
        """Each credential's secret in `avp vault`, and whether its value has `Bearer ` added."""
        self.read: dict[str, str] = {}
        self.bindings: list[CredentialBinding] = []
        self.wheres: list[str] = []
        """What each binding is for, such as `model.credential`."""
        self.hosts: dict[str, str] = {}

    def add(self, name: str, where: str, header: str | None = None) -> str:
        """The vault's name for the secret `name` as `where` uses it. A secret
        used in two forms, such as an access token bare and after `Bearer `,
        is two credentials."""
        if name not in {secret.name for secret in store.secrets()}:
            raise Failed(
                f"{where} names {name!r}, which isn't in the vault; add it with `avp vault set`"
            )
        if name not in self.read:
            self.read[name] = oauth.value(name)
        value = self.read[name]
        bearer = bool(header and header.lower() == "authorization" and store.find(name).oauth)
        if bearer:
            value = f"Bearer {value}"
        vault_name, n = name, 1
        while self.values.get(vault_name, value) != value:
            n += 1
            vault_name = f"{name}-{n}"
        self.values[vault_name] = value
        self.forms[vault_name] = (name, bearer)
        return vault_name

    def bind(self, where: str, name: str, match: CredentialMatch, auth: CredentialAuth) -> None:
        for host in match.hosts:
            if host in self.hosts:
                raise Failed(
                    f"{self.hosts[host]} and {where} both need the vault at {host}, which"
                    " can add credentials for one of them only"
                )
            self.hosts[host] = where
        self.bindings.append(CredentialBinding(name=name, match=match, auth=auth))
        self.wheres.append(where)

    def vault(self) -> Vault | None:
        if not self.bindings:
            return None
        self._describe()
        credentials = [
            Credential(name=name, source={"type": "inline", "value": value})
            for name, value in self.values.items()
        ]
        return Vault(credentials=credentials, bindings=self.bindings)

    def _describe(self) -> None:
        """With --verbose: each binding's matching rule, and the header it sets
        from each secret. Never a value."""
        detail(
            f"Credential Vault: {len(self.bindings)} bindings, {len(self.values)} credentials."
            " On a matching request, each header replaces what the agent sent"
        )
        for where, binding in zip(self.wheres, self.bindings, strict=True):
            match, auth = binding.match, binding.auth
            assert isinstance(match, CredentialMatch) and isinstance(auth, CredentialAuth)
            detail(f"Binding {binding.name}, for {where}: {_describe_match(match)}")
            if auth.type == "bearer":
                headers = [("Authorization", auth.credential or "", True)]
            elif auth.type == "apiKey":
                headers = [(auth.name or "", auth.credential or "", False)]
            else:
                headers = [(h.name, h.credential, False) for h in auth.headers or []]
            for header, credential, prefixed in headers:
                detail(f"  {header}: {self._describe_value(credential, prefixed)}")

    def _describe_value(self, credential: str, prefixed: bool) -> str:
        """Such as `"Bearer " + secret linear's access token, which expires 17:45`."""
        name, bearer = self.forms[credential]
        signed_in = store.find(name).oauth
        what = f"secret {name}'s access token" if signed_in else f"secret {name}"
        if bearer or prefixed:
            what = f'"Bearer " + {what}'
        if signed_in and signed_in.expires_at:
            what += f", which expires {signed_in.expires_at.astimezone():%Y-%m-%d %H:%M}"
        if credential != name:
            what += f" (credential {credential})"
        return what


def _describe_match(match: CredentialMatch) -> str:
    """Such as `https://api.anthropic.com, any method and path`. The scheme sets
    the port."""
    urls = ", ".join(f"{scheme}://{host}" for scheme in match.schemes or [] for host in match.hosts)
    limits = [
        f"{label} {', '.join(values)}"
        for label, values in (
            ("methods", match.methods),
            ("paths", match.paths),
        )
        if values
    ]
    return ", ".join([urls, *limits]) if limits else f"{urls}, any method and path"


def _match(url: str) -> CredentialMatch:
    parsed = urlparse(url)
    scheme = "http" if parsed.scheme == "http" else "https"
    return CredentialMatch(hosts=[parsed.hostname or ""], schemes=[scheme])


def _model_binding(
    commission: Commission, builder: _Builder, secret: str
) -> tuple[str, CredentialMatch, CredentialAuth]:
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
    name = builder.add(secret, "model.credential")
    if (auth.header, auth.prefix) == BEARER:
        rule = CredentialAuth(type="bearer", credential=name)
    elif not auth.prefix:
        rule = CredentialAuth(type="apiKey", name=auth.header, credential=name)
    else:
        raise Failed(
            f"{provider!r} takes its key as {auth.header}: {auth.prefix}<key>, which the"
            ' vault can\'t add; use {"env": NAME} with --env'
        )
    return "model", _match(base_url), rule
