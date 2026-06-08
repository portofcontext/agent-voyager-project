"""The vault broker: a host-side credential-injecting reverse proxy.

The vault's promise is "the agent can *use* a credential it can never *read*."
The wire keeps secrets off the Commission (credentials travel as handles); this
broker keeps the resolved value out of the sandbox entirely.

How it fits together. OpenSandbox filters egress by DNS only, so a sandboxed
agent can reach a host process at `host.docker.internal` once that name is in
the egress allowlist (verified empirically). avp points the agent's provider
base_url and MCP urls at this broker and hands the agent only sentinels; the
broker, running on the host where the real secret lives, overwrites the auth
header with the real value and forwards over TLS to the real upstream. The
secret never crosses into the sandbox; only the broker (host) and the upstream
ever see it.

The broker is per-run: started in `run_agent`, its routes built from the
Commission + resolved vault handles, torn down in the run's `finally`. Secrets
live only in the in-memory route table; nothing is written to disk.

This is also the real egress boundary for secret-bearing traffic: a request
that matches no route is refused, so the broker can only ever reach the
commission-declared upstreams (tighter than the DNS allowlist, and
destination-specific).
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit, urlunsplit

import httpx

__all__ = ["Broker", "Route"]

# The host alias an OpenSandbox bridge container uses to reach the host. avp
# adds this to the egress allowlist for broker-mode runs.
SANDBOX_HOST_ALIAS = "host.docker.internal"

# Hop-by-hop / recomputed headers we never forward verbatim.
_DROP_REQUEST_HEADERS = frozenset(
    {"host", "content-length", "connection", "keep-alive", "transfer-encoding", "te", "upgrade"}
)
_DROP_RESPONSE_HEADERS = frozenset(
    {"connection", "keep-alive", "transfer-encoding", "te", "upgrade", "content-encoding"}
)


@dataclass(frozen=True)
class Route:
    """One destination the broker injects credentials for.

    `upstream` is where the request is forwarded. For a provider it is the
    origin (`https://api.anthropic.com`) and the agent's SDK supplies the path;
    for an MCP server it is the full real url. `header`/`prefix` name the auth
    header to overwrite (e.g. `authorization` + `Bearer `, or `x-api-key` + ``);
    `secret` is the resolved value, held only here on the host.
    """

    upstream: str
    header: str
    prefix: str
    secret: str


class Broker:
    """A per-run credential-injecting reverse proxy bound on the host.

    Add routes keyed by the first two path segments (`llm/<id>`, `mcp/<id>`),
    then `start()`. The sandbox reaches it at `base_url()`.
    """

    def __init__(self) -> None:
        self._routes: dict[str, Route] = {}
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._client = httpx.Client(
            timeout=httpx.Timeout(600.0, connect=15.0), follow_redirects=False
        )

    def add_route(self, key: str, route: Route) -> None:
        """Register a route. `key` is the path prefix after the leading slash,
        e.g. `llm/anthropic` or `mcp/network`."""
        self._routes[key.strip("/")] = route

    @property
    def port(self) -> int:
        if self._server is None:
            raise RuntimeError("broker not started")
        return self._server.server_address[1]

    def base_url(self) -> str:
        """The URL the sandboxed agent uses to reach the broker."""
        return f"http://{SANDBOX_HOST_ALIAS}:{self.port}"

    def route_url(self, key: str) -> str:
        """The full broker URL for a given route key."""
        return f"{self.base_url()}/{key.strip('/')}"

    def start(self) -> None:
        # Bind on all interfaces so the bridge can reach us; port 0 = ephemeral.
        handler = _make_handler(self)
        self._server = ThreadingHTTPServer(("0.0.0.0", 0), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._client.close()

    def __enter__(self) -> Broker:
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.stop()

    # ── request handling ─────────────────────────────────────────────────────

    def _match(self, path: str) -> tuple[Route, str] | None:
        """Resolve a request path to (route, remainder-after-key)."""
        parts = path.lstrip("/").split("/", 2)
        if len(parts) < 2:
            return None
        key = f"{parts[0]}/{parts[1]}"
        route = self._routes.get(key)
        if route is None:
            return None
        remainder = f"/{parts[2]}" if len(parts) == 3 else ""
        return route, remainder

    def _target_url(self, route: Route, remainder: str, query: str) -> str:
        base = route.upstream.rstrip("/")
        url = base + remainder if remainder else base
        if query:
            url = f"{url}?{query}"
        return url

    def _forward_headers(self, route: Route, headers: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for name, value in headers.items():
            low = name.lower()
            if low in _DROP_REQUEST_HEADERS or low == route.header.lower():
                continue
            out[name] = value
        # Overwrite (never append) the auth header with the real secret.
        out[route.header] = f"{route.prefix}{route.secret}"
        # Pin Host to the upstream so the upstream's TLS/vhost routing is correct.
        out["Host"] = urlsplit(self._target_url(route, "", "")).netloc
        return out


def _make_handler(broker: Broker) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:  # silence default logging
            pass

        def _health(self) -> bool:
            if self.path.rstrip("/") == "/health":
                self.send_response(200)
                self.send_header("Content-Length", "2")
                self.end_headers()
                self.wfile.write(b"ok")
                return True
            return False

        def _handle(self) -> None:
            if self._health():
                return
            split = urlsplit(self.path)
            matched = broker._match(split.path)
            if matched is None:
                self.send_error(404, "no broker route")
                return
            route, remainder = matched
            target = broker._target_url(route, remainder, split.query)
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            headers = broker._forward_headers(route, dict(self.headers.items()))
            try:
                with broker._client.stream(
                    self.command, target, headers=headers, content=body
                ) as upstream:
                    self.send_response(upstream.status_code)
                    for name, value in upstream.headers.items():
                        if name.lower() in _DROP_RESPONSE_HEADERS:
                            continue
                        self.send_header(name, value)
                    self.send_header("Transfer-Encoding", "chunked")
                    self.end_headers()
                    for chunk in upstream.iter_raw():
                        if chunk:
                            self.wfile.write(f"{len(chunk):X}\r\n".encode())
                            self.wfile.write(chunk)
                            self.wfile.write(b"\r\n")
                            self.wfile.flush()
                    self.wfile.write(b"0\r\n\r\n")
            except Exception as exc:  # upstream unreachable / stream error
                self.send_error(502, f"broker upstream error: {exc}")

        do_GET = _handle
        do_POST = _handle
        do_PUT = _handle
        do_DELETE = _handle
        do_PATCH = _handle

    return Handler


def origin_of(url: str) -> str:
    """The scheme://host[:port] origin of a url (provider routes forward here;
    the agent SDK supplies the path)."""
    s = urlsplit(url)
    return urlunsplit((s.scheme, s.netloc, "", "", ""))
