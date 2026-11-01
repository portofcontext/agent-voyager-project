"""`avp vault login` and `refresh` against a local MCP server that requires an
OAuth sign-in, with the browser replaced by a plain request that follows the
redirects."""

import socket
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import uvicorn
from conftest import Memory
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route
from typer.testing import CliRunner

from avp_cli.cli import app
from avp_cli.console import Failed
from avp_cli.vault import oauth, store


class Server:
    """An MCP server and its authorization server, in one app."""

    def __init__(self) -> None:
        self.base = ""
        self.token_requests: list[dict[str, str]] = []
        self.refusing = False

    def app(self) -> Starlette:
        return Starlette(
            routes=[
                Route("/mcp", self.mcp, methods=["GET", "POST", "DELETE"]),
                Route("/.well-known/oauth-protected-resource/mcp", self.resource_metadata),
                Route("/.well-known/oauth-authorization-server", self.server_metadata),
                Route("/register", self.register, methods=["POST"]),
                Route("/authorize", self.authorize),
                Route("/token", self.token, methods=["POST"]),
            ]
        )

    async def mcp(self, request: Request) -> Response:
        if request.headers.get("authorization") != "Bearer access-1":
            metadata = f"{self.base}/.well-known/oauth-protected-resource/mcp"
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": f'Bearer resource_metadata="{metadata}"'},
            )
        if request.method != "POST":
            return Response(status_code=405)
        message = await request.json()
        if "id" not in message:
            return Response(status_code=202)
        result = {
            "protocolVersion": message["params"]["protocolVersion"],
            "capabilities": {},
            "serverInfo": {"name": "test", "version": "1"},
        }
        return JSONResponse({"jsonrpc": "2.0", "id": message["id"], "result": result})

    async def resource_metadata(self, request: Request) -> Response:
        return JSONResponse({"resource": f"{self.base}/mcp", "authorization_servers": [self.base]})

    async def server_metadata(self, request: Request) -> Response:
        return JSONResponse(
            {
                "issuer": self.base,
                "authorization_endpoint": f"{self.base}/authorize",
                "token_endpoint": f"{self.base}/token",
                "registration_endpoint": f"{self.base}/register",
                "response_types_supported": ["code"],
                "grant_types_supported": ["authorization_code", "refresh_token"],
                "code_challenge_methods_supported": ["S256"],
                "token_endpoint_auth_methods_supported": ["none"],
            }
        )

    async def register(self, request: Request) -> Response:
        client = {**await request.json(), "client_id": "client-1"}
        client["token_endpoint_auth_method"] = "none"
        return JSONResponse(client, status_code=201)

    async def authorize(self, request: Request) -> Response:
        query = request.query_params
        return RedirectResponse(f"{query['redirect_uri']}?code=code-1&state={query['state']}")

    async def token(self, request: Request) -> Response:
        form = {key: str(value) for key, value in (await request.form()).items()}
        self.token_requests.append(form)
        if form["grant_type"] == "authorization_code" and form["code"] == "code-1":
            return JSONResponse(
                {
                    "access_token": "access-1",
                    "token_type": "bearer",
                    "expires_in": 3600,
                    "refresh_token": "refresh-1",
                    "scope": "read",
                }
            )
        if form["grant_type"] == "refresh_token" and not self.refusing:
            # No refresh token or scope: they don't change.
            return JSONResponse({"access_token": "access-2", "expires_in": 60})
        return JSONResponse({"error": "invalid_grant"}, status_code=400)


@pytest.fixture
def server(memory: Memory, monkeypatch: pytest.MonkeyPatch) -> Iterator[Server]:
    fake = Server()
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    fake.base = f"http://127.0.0.1:{sock.getsockname()[1]}"
    running = uvicorn.Server(uvicorn.Config(fake.app(), log_level="error"))
    thread = threading.Thread(target=running.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    while not running.started:
        threading.Event().wait(0.01)
    monkeypatch.setattr(oauth, "browse", lambda url: httpx.get(url, follow_redirects=True))
    yield fake
    running.should_exit = True
    thread.join()


def test_login_stores_the_tokens_and_when_they_expire(server: Server, memory: Memory) -> None:
    url = f"{server.base}/mcp"
    result = CliRunner().invoke(
        app, ["vault", "login", "test", "--url", url, "--scope", "read", "-d", "Test server"]
    )
    assert result.exit_code == 0, result.output

    grant = oauth.Grant.model_validate_json(memory.values[("avp", "test")])
    assert (grant.tokens.access_token, grant.tokens.refresh_token) == ("access-1", "refresh-1")
    assert grant.client.client_id == "client-1"

    secret = store.find("test")
    assert secret.description == "Test server"
    assert secret.oauth is not None
    assert secret.oauth.url == url
    assert secret.oauth.token_endpoint == f"{server.base}/token"
    assert secret.oauth.resource == url
    assert secret.oauth.scopes == ["read"]
    assert secret.oauth.expires_at is not None
    in_an_hour = datetime.now(UTC) + timedelta(hours=1)
    assert abs(secret.oauth.expires_at - in_an_hour) < timedelta(minutes=1)
    assert not oauth.expired(secret)


def test_refresh_keeps_the_refresh_token(server: Server, memory: Memory) -> None:
    oauth.login("test", f"{server.base}/mcp", [])
    result = CliRunner().invoke(app, ["vault", "refresh", "test"])
    assert result.exit_code == 0, result.output

    refresh = server.token_requests[-1]
    assert refresh["refresh_token"] == "refresh-1"
    assert refresh["client_id"] == "client-1"
    assert refresh["resource"] == f"{server.base}/mcp"

    grant = oauth.Grant.model_validate_json(memory.values[("avp", "test")])
    assert (grant.tokens.access_token, grant.tokens.refresh_token) == ("access-2", "refresh-1")
    assert grant.tokens.scope == "read"
    # 60 seconds is within the margin, so the new token already counts as expired.
    assert oauth.expired(store.find("test"))


def test_refused_refresh_says_to_sign_in_again(server: Server) -> None:
    oauth.login("test", f"{server.base}/mcp", [])
    server.refusing = True
    with pytest.raises(Failed, match=r"refused to refresh 'test' \(400\)\. Sign in again"):
        oauth.refresh("test")


def test_refresh_of_a_plain_secret_fails(memory: Memory) -> None:
    store.set_("plain", "value")
    with pytest.raises(Failed, match="isn't an OAuth sign-in"):
        oauth.refresh("plain")
