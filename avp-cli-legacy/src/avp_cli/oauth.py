"""OAuth vault handles: log in once on the host, and the broker keeps the token fresh.

`login` runs the MCP authorization flow against an HTTP MCP server: protected
resource metadata (RFC 9728), authorization server metadata (RFC 8414, with the
OpenID discovery fallback), dynamic client registration (RFC 7591) unless a
client id is given, and the authorization code grant with PKCE (RFC 7636)
through a loopback redirect, scoped to the server with a resource indicator
(RFC 8707). Servers without resource metadata fall back to treating the
server's origin as the authorization server.

The grant lives on the host in `~/.avp/oauth/<handle>.json` (0600) under the
same handle a Commission references (`{"vault": "<handle>"}`). A `Token` wraps
it for the broker, which injects the access token, refreshes it near expiry or
after an upstream 401, and persists rotated refresh tokens. The grant never
enters the sandbox or the wire.
"""

from __future__ import annotations

import base64
import contextlib
import fcntl
import hashlib
import json
import os
import re
import secrets
import threading
import time
import webbrowser
from collections.abc import Callable
from dataclasses import asdict, dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import httpx

from avp_cli import paths

__all__ = ["Grant", "OAuthError", "Token", "grant_path", "load", "login", "names", "remove"]

# Refresh this many seconds before the access token's stated expiry, so a
# request in flight never carries a token that lapses on the way.
_EXPIRY_SKEW_S = 60
_LOGIN_TIMEOUT_S = 300
_HTTP_TIMEOUT = httpx.Timeout(30.0, connect=15.0)
# The SecretRef vault pattern; a handle also names the grant's file.
_HANDLE_RE = re.compile(r"^[a-z0-9_-]+$")


class OAuthError(Exception):
    """An OAuth login or refresh failed, or no usable grant exists."""


@dataclass
class Grant:
    """Everything needed to use and refresh one OAuth login."""

    resource: str
    token_endpoint: str
    client_id: str
    access_token: str
    client_secret: str | None = None
    token_auth_method: str = "none"
    refresh_token: str | None = None
    expires_at: float | None = None
    scope: str | None = None


# ── storage ──────────────────────────────────────────────────────────────────


def _oauth_dir() -> Path:
    return paths.avp_home() / "oauth"


def grant_path(handle: str) -> Path:
    return _oauth_dir() / f"{handle}.json"


def load(handle: str) -> Grant | None:
    path = grant_path(handle)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return Grant(**{k: v for k, v in data.items() if k in Grant.__dataclass_fields__})


def _save(handle: str, grant: Grant) -> None:
    directory = _oauth_dir()
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    path = grant_path(handle)
    tmp = path.with_suffix(".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(asdict(grant), f, indent=2)
    tmp.replace(path)


def names() -> list[str]:
    directory = _oauth_dir()
    if not directory.exists():
        return []
    return sorted(p.stem for p in directory.glob("*.json"))


def remove(handle: str) -> bool:
    path = grant_path(handle)
    if not path.exists():
        return False
    path.unlink()
    return True


@contextlib.contextmanager
def _file_lock(handle: str):
    """Serialize refreshes across processes: two evals sharing a handle must not
    both spend a rotating refresh token."""
    _oauth_dir().mkdir(parents=True, exist_ok=True)
    with open(_oauth_dir() / f".{handle}.lock", "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


# ── the broker's view of a grant ─────────────────────────────────────────────


class Token:
    """A refreshable access token for one handle, shared by a broker's threads."""

    def __init__(self, handle: str, grant: Grant, client: httpx.Client | None = None) -> None:
        self.handle = handle
        self._grant = grant
        self._lock = threading.Lock()
        self._client = client

    def access_token(self) -> str:
        """The current access token, refreshed first if it is about to expire."""
        with self._lock:
            current = self._grant.access_token
        if _expiring(self._grant):
            self.refresh(stale=current)
        return self._grant.access_token

    def refresh(self, stale: str) -> None:
        """Replace `stale` with a fresh access token. A no-op when another thread
        or process already replaced it."""
        with self._lock, _file_lock(self.handle):
            if self._grant.access_token != stale and not _expiring(self._grant):
                return
            on_disk = load(self.handle)
            if on_disk is not None and on_disk.access_token != stale and not _expiring(on_disk):
                self._grant = on_disk
                return
            grant = on_disk or self._grant
            if not grant.refresh_token:
                raise OAuthError(
                    f"the OAuth token for {self.handle!r} expired and has no refresh token. "
                    f"Run `avp env secret login {self.handle} --url {grant.resource}`."
                )
            form = {"grant_type": "refresh_token", "refresh_token": grant.refresh_token}
            if grant.scope:
                form["scope"] = grant.scope
            try:
                body = _token_request(grant, form, self._client)
            except OAuthError as exc:
                raise OAuthError(
                    f"refreshing {self.handle!r} failed ({exc}). "
                    f"Run `avp env secret login {self.handle} --url {grant.resource}`."
                ) from exc
            self._grant = _apply_token_response(grant, body)
            _save(self.handle, self._grant)


def _expiring(grant: Grant) -> bool:
    return grant.expires_at is not None and time.time() >= grant.expires_at - _EXPIRY_SKEW_S


# ── token endpoint ───────────────────────────────────────────────────────────


def _token_request(grant: Grant, form: dict[str, str], client: httpx.Client | None) -> dict:
    form = {**form, "resource": grant.resource}
    auth = None
    if grant.token_auth_method == "client_secret_basic" and grant.client_secret:
        auth = (grant.client_id, grant.client_secret)
    else:
        form["client_id"] = grant.client_id
        if grant.client_secret:
            form["client_secret"] = grant.client_secret
    owned = client is None
    client = client or httpx.Client(timeout=_HTTP_TIMEOUT)
    try:
        resp = client.post(
            grant.token_endpoint, data=form, auth=auth, headers={"Accept": "application/json"}
        )
    except httpx.HTTPError as exc:
        raise OAuthError(f"token endpoint unreachable: {exc}") from exc
    finally:
        if owned:
            client.close()
    try:
        body = resp.json()
    except ValueError:
        body = {}
    if resp.status_code != 200 or "access_token" not in body:
        detail = body.get("error_description") or body.get("error") or resp.text[:200]
        raise OAuthError(f"token endpoint returned {resp.status_code}: {detail}")
    return body


def _apply_token_response(grant: Grant, body: dict) -> Grant:
    expires_in = body.get("expires_in")
    return Grant(
        **{
            **asdict(grant),
            "access_token": body["access_token"],
            # Servers that don't rotate refresh tokens omit it; keep the old one.
            "refresh_token": body.get("refresh_token") or grant.refresh_token,
            "expires_at": time.time() + float(expires_in) if expires_in else None,
            "scope": body.get("scope") or grant.scope,
        }
    )


# ── discovery ────────────────────────────────────────────────────────────────


def _canonical_resource(url: str) -> str:
    """The RFC 8707 resource for an MCP server: scheme and host lowercased, no
    fragment, no trailing slash."""
    s = urlsplit(url)
    return urlunsplit((s.scheme.lower(), s.netloc.lower(), s.path.rstrip("/"), s.query, ""))


def _origin(url: str) -> str:
    s = urlsplit(url)
    return f"{s.scheme}://{s.netloc}"


def _well_known(url: str, suffix: str) -> list[str]:
    """RFC 8414 / RFC 9728 well-known URLs: path-inserted first, then root."""
    s = urlsplit(url)
    path = s.path.rstrip("/")
    urls = [f"{_origin(url)}/.well-known/{suffix}{path}"] if path else []
    urls.append(f"{_origin(url)}/.well-known/{suffix}")
    return urls


def _www_authenticate_params(header: str) -> dict[str, str]:
    return {k.lower(): v for k, v in re.findall(r'(\w+)="([^"]*)"', header)}


def _get_json(client: httpx.Client, url: str) -> dict | None:
    try:
        resp = client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _discover(client: httpx.Client, server_url: str) -> tuple[dict, dict, str | None]:
    """Return (resource metadata, authorization server metadata, challenged scope)."""
    challenge: dict[str, str] = {}
    try:
        probe = client.post(
            server_url,
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            headers={"Accept": "application/json, text/event-stream"},
        )
        if probe.status_code == 401:
            challenge = _www_authenticate_params(probe.headers.get("www-authenticate", ""))
    except httpx.HTTPError as exc:
        raise OAuthError(f"cannot reach {server_url}: {exc}") from exc

    candidates = [challenge["resource_metadata"]] if "resource_metadata" in challenge else []
    candidates += _well_known(server_url, "oauth-protected-resource")
    resource_meta = next((m for u in candidates if (m := _get_json(client, u))), None) or {}

    issuers = resource_meta.get("authorization_servers") or [_origin(server_url)]
    issuer = issuers[0]
    as_urls = _well_known(issuer, "oauth-authorization-server") + _well_known(
        issuer, "openid-configuration"
    )
    if urlsplit(issuer).path.rstrip("/"):
        as_urls.append(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
    as_meta = next((m for u in as_urls if (m := _get_json(client, u))), None)
    if as_meta is None:
        if resource_meta:
            raise OAuthError(f"no authorization server metadata found for {issuer}")
        # Servers predating resource metadata serve OAuth at default paths.
        base = _origin(server_url)
        as_meta = {
            "authorization_endpoint": f"{base}/authorize",
            "token_endpoint": f"{base}/token",
            "registration_endpoint": f"{base}/register",
        }
    methods = as_meta.get("code_challenge_methods_supported")
    if methods is not None and "S256" not in methods:
        raise OAuthError(f"{issuer} does not support PKCE with S256")
    return resource_meta, as_meta, challenge.get("scope")


def _register(client: httpx.Client, as_meta: dict, redirect_uri: str) -> tuple[str, str | None]:
    endpoint = as_meta.get("registration_endpoint")
    if not endpoint:
        raise OAuthError(
            "the authorization server does not support dynamic client registration. "
            "Register a client with it and pass --client-id (and --client-secret)."
        )
    resp = client.post(
        endpoint,
        json={
            "client_name": "avp",
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    if resp.status_code not in (200, 201):
        raise OAuthError(f"client registration returned {resp.status_code}: {resp.text[:200]}")
    body = resp.json()
    return body["client_id"], body.get("client_secret")


def _auth_method(as_meta: dict, client_secret: str | None) -> str:
    if not client_secret:
        return "none"
    supported = as_meta.get("token_endpoint_auth_methods_supported") or ["client_secret_basic"]
    return "client_secret_post" if "client_secret_post" in supported else "client_secret_basic"


# ── login ────────────────────────────────────────────────────────────────────


class _Callback(HTTPServer):
    result: dict[str, str]


def _callback_server(port: int) -> _Callback:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args: object) -> None:
            pass

        def do_GET(self) -> None:
            split = urlsplit(self.path)
            if split.path != "/callback":
                self.send_error(404)
                return
            params = {k: v[0] for k, v in parse_qs(split.query).items()}
            self.server.result = params  # type: ignore[attr-defined]
            ok = "code" in params
            page = (
                "avp is signed in. You can close this tab."
                if ok
                else f"avp sign-in failed: {params.get('error_description') or params.get('error')}"
            ).encode()
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)

    server = _Callback(("127.0.0.1", port), Handler)
    server.result = {}
    server.timeout = 1
    return server


def _pkce() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode()).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def login(
    handle: str,
    server_url: str,
    *,
    client_id: str | None = None,
    client_secret: str | None = None,
    scope: str | None = None,
    port: int = 0,
    open_url: Callable[[str], object] = webbrowser.open,
    timeout_s: float = _LOGIN_TIMEOUT_S,
) -> Grant:
    """Sign in to `server_url` in the browser and store the grant under `handle`."""
    if not _HANDLE_RE.match(handle):
        raise OAuthError(
            f"invalid handle {handle!r}: use lowercase letters, digits, '-', '_' "
            "(the SecretRef vault pattern a Commission references)"
        )
    resource = _canonical_resource(server_url)
    callback = _callback_server(port)
    redirect_uri = f"http://127.0.0.1:{callback.server_address[1]}/callback"
    try:
        with httpx.Client(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
            resource_meta, as_meta, challenged_scope = _discover(client, server_url)
            if client_id is None:
                client_id, client_secret = _register(client, as_meta, redirect_uri)
            scope = (
                scope or challenged_scope or " ".join(resource_meta.get("scopes_supported") or [])
            )
            verifier, challenge = _pkce()
            state = secrets.token_urlsafe(24)
            query = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": state,
                "resource": resource,
            }
            if scope:
                query["scope"] = scope
            authorize = as_meta["authorization_endpoint"]
            sep = "&" if urlsplit(authorize).query else "?"
            open_url(f"{authorize}{sep}{urlencode(query)}")

            deadline = time.monotonic() + timeout_s
            while not callback.result and time.monotonic() < deadline:
                callback.handle_request()
            result = callback.result
            if not result:
                raise OAuthError("timed out waiting for the browser sign-in")
            if result.get("state") != state:
                raise OAuthError("sign-in callback had the wrong state; try again")
            if "code" not in result:
                raise OAuthError(
                    f"sign-in failed: {result.get('error_description') or result.get('error')}"
                )

            grant = Grant(
                resource=resource,
                token_endpoint=as_meta["token_endpoint"],
                client_id=client_id,
                client_secret=client_secret,
                token_auth_method=_auth_method(as_meta, client_secret),
                access_token="",
                scope=scope or None,
            )
            body = _token_request(
                grant,
                {
                    "grant_type": "authorization_code",
                    "code": result["code"],
                    "redirect_uri": redirect_uri,
                    "code_verifier": verifier,
                },
                client,
            )
    finally:
        callback.server_close()
    grant = _apply_token_response(grant, body)
    _save(handle, grant)
    return grant
