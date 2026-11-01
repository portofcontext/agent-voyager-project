"""OAuth vault handles: browser login, token refresh, and the broker's retry.

A fake MCP server and authorization server stand in for the real ones. Login
runs the full discovery, registration, PKCE, and code exchange against them;
the broker tests check that the agent's run token is swapped for a live access
token, refreshed after a 401, and that rotated refresh tokens persist.
"""

from __future__ import annotations

import base64
import hashlib
import json
import stat
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import pytest

from avp_cli import broker, oauth, vault


class FakeAuth:
    """An MCP server that is also its own authorization server."""

    def __init__(self) -> None:
        self.valid = {"at-1"}
        self.issued = 0
        self.challenges: dict[str, str] = {}
        self.token_forms: list[dict[str, str]] = []
        self.seen_auth: list[str | None] = []
        self.refresh_tokens = {"rt-1"}
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.origin = f"http://127.0.0.1:{self.srv.server_address[1]}"
        self.mcp = f"{self.origin}/mcp"

    def _issue(self) -> dict:
        self.issued += 1
        at, rt = f"at-{self.issued}", f"rt-{self.issued}"
        self.valid = {at}
        self.refresh_tokens = {rt}
        return {"access_token": at, "refresh_token": rt, "expires_in": 3600, "token_type": "Bearer"}

    def _handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code: int, body: dict, headers: dict | None = None) -> None:
                raw = json.dumps(body).encode()
                self.send_response(code)
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> bytes:
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_GET(self):
                split = urlsplit(self.path)
                if split.path == "/.well-known/oauth-protected-resource/mcp":
                    return self._json(
                        200, {"resource": fake.mcp, "authorization_servers": [fake.origin]}
                    )
                if split.path == "/.well-known/oauth-authorization-server":
                    return self._json(
                        200,
                        {
                            "issuer": fake.origin,
                            "authorization_endpoint": f"{fake.origin}/authorize",
                            "token_endpoint": f"{fake.origin}/token",
                            "registration_endpoint": f"{fake.origin}/register",
                            "code_challenge_methods_supported": ["S256"],
                        },
                    )
                if split.path == "/authorize":
                    q = {k: v[0] for k, v in parse_qs(split.query).items()}
                    assert q["resource"] == fake.mcp and q["code_challenge_method"] == "S256"
                    fake.challenges["code-1"] = q["code_challenge"]
                    loc = (
                        f"{q['redirect_uri']}?{urlencode({'code': 'code-1', 'state': q['state']})}"
                    )
                    self.send_response(302)
                    self.send_header("Location", loc)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return None
                self.send_error(404)
                return None

            def do_POST(self):
                body = self._body()
                path = urlsplit(self.path).path
                if path == "/mcp":
                    auth = self.headers.get("authorization")
                    fake.seen_auth.append(auth)
                    if auth and auth.removeprefix("Bearer ") in fake.valid:
                        return self._json(200, {"jsonrpc": "2.0", "id": 1, "result": {}})
                    meta = f"{fake.origin}/.well-known/oauth-protected-resource/mcp"
                    return self._json(
                        401,
                        {"error": "unauthorized"},
                        {"WWW-Authenticate": f'Bearer resource_metadata="{meta}"'},
                    )
                if path == "/register":
                    assert json.loads(body)["token_endpoint_auth_method"] == "none"
                    return self._json(201, {"client_id": "client-1"})
                if path == "/token":
                    form = {k: v[0] for k, v in parse_qs(body.decode()).items()}
                    fake.token_forms.append(form)
                    if form.get("resource") != fake.mcp:
                        return self._json(400, {"error": "invalid_target"})
                    if form["grant_type"] == "authorization_code":
                        digest = hashlib.sha256(form["code_verifier"].encode()).digest()
                        expect = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
                        if fake.challenges.get(form["code"]) != expect:
                            return self._json(400, {"error": "invalid_grant"})
                        return self._json(200, fake._issue())
                    if form["grant_type"] == "refresh_token":
                        if form["refresh_token"] not in fake.refresh_tokens:
                            return self._json(400, {"error": "invalid_grant"})
                        return self._json(200, fake._issue())
                self.send_error(404)
                return None

        return H


@pytest.fixture
def fake(tmp_path, monkeypatch):
    monkeypatch.setenv("AVP_HOME", str(tmp_path))
    f = FakeAuth()
    yield f
    f.srv.shutdown()


def _browser(url: str) -> None:
    """Stand in for the user: follow the authorize redirect to the loopback callback."""
    threading.Thread(
        target=lambda: httpx.get(url, follow_redirects=True, timeout=10), daemon=True
    ).start()


def _grant(fake: FakeAuth, **over) -> oauth.Grant:
    base = {
        "resource": fake.mcp,
        "token_endpoint": f"{fake.origin}/token",
        "client_id": "client-1",
        "access_token": "at-1",
        "refresh_token": "rt-1",
        "expires_at": time.time() + 3600,
    }
    return oauth.Grant(**{**base, **over})


def test_login_discovers_registers_and_stores_the_grant(fake) -> None:
    grant = oauth.login("pctx", fake.mcp, open_url=_browser, timeout_s=10)

    assert grant.client_id == "client-1"
    assert grant.access_token == "at-1" and grant.refresh_token == "rt-1"
    assert grant.resource == fake.mcp
    exchange = fake.token_forms[0]
    assert exchange["grant_type"] == "authorization_code" and exchange["client_id"] == "client-1"
    path = oauth.grant_path("pctx")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert oauth.load("pctx") == grant
    assert vault.oauth_names() == ["pctx"]


def test_login_rejects_an_invalid_handle(fake) -> None:
    with pytest.raises(oauth.OAuthError, match="invalid handle"):
        oauth.login("Bad Handle", fake.mcp, open_url=_browser, timeout_s=1)


def test_vault_resolves_an_expired_login_by_refreshing(fake) -> None:
    oauth._save("pctx", _grant(fake, access_token="stale", expires_at=time.time() - 5))

    token = vault.resolve("pctx")

    assert isinstance(token, oauth.Token)
    assert token.access_token() == "at-1"
    assert fake.token_forms[-1]["grant_type"] == "refresh_token"
    assert oauth.load("pctx").refresh_token == "rt-1"  # rotated token persisted


def test_vault_reports_a_lapsed_login(fake) -> None:
    oauth._save("pctx", _grant(fake, refresh_token="revoked", expires_at=time.time() - 5))
    with pytest.raises(vault.VaultError, match="avp env secret login pctx"):
        vault.resolve("pctx")


def test_static_secret_wins_over_an_oauth_login(fake, monkeypatch) -> None:
    oauth._save("pctx", _grant(fake))
    monkeypatch.setenv("AVP_VAULT_PCTX", "static")
    assert vault.resolve("pctx") == "static"


def test_remove_deletes_the_oauth_login(fake) -> None:
    oauth._save("pctx", _grant(fake))
    assert vault.remove("pctx") is True
    assert oauth.load("pctx") is None


def test_broker_refreshes_after_a_401_and_retries(fake) -> None:
    oauth._save("pctx", _grant(fake, access_token="revoked-early"))
    token = vault.resolve("pctx")
    brk = broker.Broker()
    brk.add_route(
        "mcp/pctx",
        broker.Route(upstream=fake.mcp, header="authorization", prefix="Bearer ", secret=token),
    )
    brk.start()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{brk.port}/mcp/pctx",
            headers={"authorization": f"Bearer {brk.token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        )
        assert r.status_code == 200
        assert fake.seen_auth == ["Bearer revoked-early", "Bearer at-1"]
        assert brk.token not in str(fake.seen_auth)  # the run token never leaves the host
        assert oauth.load("pctx").access_token == "at-1"
    finally:
        brk.stop()


def test_broker_returns_401_when_the_login_cannot_refresh(fake) -> None:
    oauth._save("pctx", _grant(fake, access_token="revoked-early", refresh_token="revoked"))
    token = vault.resolve("pctx")
    brk = broker.Broker()
    brk.add_route(
        "mcp/pctx",
        broker.Route(upstream=fake.mcp, header="authorization", prefix="Bearer ", secret=token),
    )
    brk.start()
    try:
        r = httpx.post(
            f"http://127.0.0.1:{brk.port}/mcp/pctx",
            headers={"authorization": f"Bearer {brk.token}"},
            json={},
        )
        assert r.status_code == 401
    finally:
        brk.stop()


def test_token_adopts_a_refresh_done_by_another_process(fake) -> None:
    token = oauth.Token("pctx", _grant(fake, access_token="old", expires_at=time.time() - 5))
    oauth._save("pctx", _grant(fake, access_token="fresh-from-elsewhere"))

    assert token.access_token() == "fresh-from-elsewhere"
    assert fake.token_forms == []  # no second refresh spent
