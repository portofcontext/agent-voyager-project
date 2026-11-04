"""OAuth sign-ins to MCP servers, through the MCP SDK's OAuth client: it finds
the server's authorization server, registers avp as a client, and runs the
browser sign-in. The tokens and the client registration are one secret in the
credential store; where the token comes from and when it expires are in the
secret's `oauth`, so a run can check it without reading the store."""

import threading
import webbrowser
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlsplit

import anyio
import httpx
import httpx2
from mcp.client.auth import (
    AuthorizationCodeResult,
    OAuthClientProvider,
    OAuthFlowError,
    OAuthRegistrationError,
    OAuthTokenError,
)
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken
from pydantic import BaseModel

from avp_cli.console import Failed, detail, err
from avp_cli.vault import store

SIGN_IN_TIMEOUT_S = 300
EXPIRY_MARGIN = timedelta(minutes=5)
"""A token this close to expiring counts as expired."""

browse: Callable[[str], object] = webbrowser.open
"""Opens the sign-in page. Tests replace it."""


class Grant(BaseModel):
    """A sign-in's value in the credential store."""

    tokens: OAuthToken
    client: OAuthClientInformationFull


def login(name: str, url: str, scopes: list[str], description: str | None = None) -> store.Secret:
    """Sign in in the browser and store the tokens as `name`. Signing in again
    replaces them."""
    try:
        grant, oauth = anyio.run(_login, url, scopes)
    except Exception as error:
        # The MCP client's task groups wrap what goes wrong in exception groups.
        while isinstance(error, ExceptionGroup) and len(error.exceptions) == 1:
            error = error.exceptions[0]
        if isinstance(error, Failed):
            raise error from None
        if isinstance(error, (OAuthFlowError, OAuthRegistrationError, OAuthTokenError)):
            raise Failed(f"signing in to {url} failed: {error}") from None
        if isinstance(error, httpx2.HTTPError):
            raise Failed(f"couldn't reach {url}: {error}") from None
        raise
    store.set_(name, grant.model_dump_json(exclude_none=True), description, oauth)
    return store.find(name)


def value(name: str) -> str:
    """What a request carries for the secret: its value, or for a sign-in its
    access token, refreshed first when it has expired."""
    secret = store.find(name)
    if secret.oauth is None:
        return store.get(name)
    if expired(secret):
        detail(f"Refreshing {name}, which has expired")
        refresh(name)
    return Grant.model_validate_json(store.get(name)).tokens.access_token


def expired(secret: store.Secret) -> bool:
    """Whether the sign-in's token has expired or is about to."""
    if secret.oauth is None or secret.oauth.expires_at is None:
        return False
    return datetime.now(UTC) + EXPIRY_MARGIN >= secret.oauth.expires_at


def refresh(name: str) -> store.Secret:
    """Swap the refresh token for a new access token. Fails when the server
    gave no refresh token or refuses it; then only signing in again helps."""
    secret = store.find(name)
    oauth = secret.oauth
    if oauth is None:
        raise Failed(f"{name!r} isn't an OAuth sign-in")
    grant = Grant.model_validate_json(store.get(name))
    sign_in_again = f"Sign in again: `avp vault login {name} --url {oauth.url}`"
    if grant.tokens.refresh_token is None:
        raise Failed(f"{oauth.url} gave {name!r} no refresh token. {sign_in_again}")
    data = {"grant_type": "refresh_token", "refresh_token": grant.tokens.refresh_token}
    if oauth.resource:
        data["resource"] = oauth.resource
    method = grant.client.token_endpoint_auth_method or "none"
    detail(f"Token endpoint: {oauth.token_endpoint}, client authentication: {method}")
    auth = None
    if method == "client_secret_basic":
        auth = (grant.client.client_id or "", grant.client.client_secret or "")
    else:
        data["client_id"] = grant.client.client_id or ""
        if method == "client_secret_post":
            data["client_secret"] = grant.client.client_secret or ""
    try:
        response = httpx.post(oauth.token_endpoint, data=data, auth=auth, timeout=30)
    except httpx.HTTPError as error:
        raise Failed(f"refreshing {name!r} failed: {error}") from None
    if response.status_code != 200:
        raise Failed(
            f"{oauth.url} refused to refresh {name!r} ({response.status_code}). {sign_in_again}"
        )
    tokens = OAuthToken.model_validate_json(response.content)
    detail(
        "The server sent a new refresh token"
        if tokens.refresh_token
        else "The refresh token stays the same"
    )
    # A refresh response may leave out the refresh token and scope when they don't change.
    tokens.refresh_token = tokens.refresh_token or grant.tokens.refresh_token
    tokens.scope = tokens.scope or grant.tokens.scope
    detail(f"Scopes: {tokens.scope or 'not given'}")
    oauth = oauth.model_copy(update={"expires_at": _expires_at(tokens)})
    store.set_(name, Grant(tokens=tokens, client=grant.client).model_dump_json(), oauth=oauth)
    return store.find(name)


async def _login(url: str, scopes: list[str]) -> tuple[Grant, store.OAuth]:
    storage = _Storage()
    with _Callback() as callback:
        detail(f"Waiting for the sign-in at {callback.uri}")
        provider = OAuthClientProvider(
            server_url=url,
            client_metadata=OAuthClientMetadata(
                client_name="avp",
                redirect_uris=[callback.uri],
                grant_types=["authorization_code", "refresh_token"],
                scope=" ".join(scopes) or None,
            ),
            storage=storage,
            redirect_handler=_open,
            callback_handler=callback.wait,
        )
        async with (
            httpx2.AsyncClient(auth=provider, timeout=30) as http,
            streamable_http_client(url, http_client=http) as (read, write),
            ClientSession(read, write) as session,
        ):
            await session.initialize()
    context = provider.context
    metadata = context.oauth_metadata
    if storage.tokens is None or storage.client is None or metadata is None:
        raise Failed(f"{url} didn't ask to sign in, so there is nothing to store")
    oauth = store.OAuth(
        url=url,
        token_endpoint=str(metadata.token_endpoint),
        resource=(
            context.get_resource_url()
            if context.should_include_resource_param(context.protocol_version)
            else None
        ),
        scopes=scopes,
        expires_at=_expires_at(storage.tokens),
    )
    detail(f"Authorization server: {metadata.issuer}")
    detail(f"Token endpoint: {oauth.token_endpoint}")
    if metadata.registration_endpoint:
        detail(f"Registration endpoint: {metadata.registration_endpoint}")
    detail(f"Client ID: {storage.client.client_id}")
    detail(f"Resource: {oauth.resource or 'none'}")
    detail(f"Scopes granted: {storage.tokens.scope or 'not given'}")
    return Grant(tokens=storage.tokens, client=storage.client), oauth


def _expires_at(tokens: OAuthToken) -> datetime | None:
    if tokens.expires_in is None:
        return None
    return datetime.now(UTC) + timedelta(seconds=tokens.expires_in)


async def _open(url: str) -> None:
    err.print(f"Sign in in your browser. If it doesn't open, go to:\n{url}", highlight=False)
    browse(url)


class _Storage:
    """Holds what the SDK's OAuth client finds until the sign-in finishes."""

    def __init__(self) -> None:
        self.tokens: OAuthToken | None = None
        self.client: OAuthClientInformationFull | None = None

    async def get_tokens(self) -> OAuthToken | None:
        return self.tokens

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.tokens = tokens

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        return self.client

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.client = client_info


class _Callback:
    """A web server on the loopback address that the sign-in redirects the
    browser to with its code (RFC 8252)."""

    def __init__(self) -> None:
        self.params: dict[str, str] | None = None
        self.server = HTTPServer(("127.0.0.1", 0), self._handler())
        self.uri = f"http://127.0.0.1:{self.server.server_port}/callback"
        self.done = threading.Event()

    def __enter__(self) -> "_Callback":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def __exit__(self, *_: object) -> None:
        self.server.shutdown()
        self.server.server_close()

    async def wait(self) -> AuthorizationCodeResult:
        if not await anyio.to_thread.run_sync(self.done.wait, SIGN_IN_TIMEOUT_S):
            raise Failed(f"no sign-in after {SIGN_IN_TIMEOUT_S // 60} minutes")
        params = self.params or {}
        if "code" not in params:
            reason = params.get("error_description") or params.get("error", "no code")
            raise Failed(f"the sign-in failed: {reason}")
        return AuthorizationCodeResult(
            code=params["code"], state=params.get("state"), iss=params.get("iss")
        )

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        callback = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                request = urlsplit(self.path)
                if request.path != "/callback" or callback.done.is_set():
                    self.send_error(404)
                    return
                callback.params = {k: v[0] for k, v in parse_qs(request.query).items()}
                callback.done.set()
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"avp: done. You can close this tab.")

            def log_message(self, format: str, *args: object) -> None:
                pass

        return Handler
