"""Provider metering: every model token a run is billed must be in its trajectory.

`check` routes each agent's provider traffic through `Meter`, a local reverse
proxy per provider origin that forwards to the real API and reads the token
usage off every completed response (Anthropic Messages, OpenAI Responses and
Chat Completions, Gemini; streamed or not). After each case, `reconcile`
compares what the provider billed with what the trajectory reports: the
`assistant_message` turns plus the `subagent_returned` rollups. A model call
the adapter never recorded, such as a probe or side request, fails the case.

Routing uses the variables a launcher sets (`<ORIGIN>_BASE_URL`, `_HOST`), so
an agent that ignores them cannot be metered and fails too: the same agent
would bypass a supervisor's credential broker.
"""

from __future__ import annotations

import http.client
import json
import threading
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

# Each origin's real API and the variables that point an agent at it. A value
# with a path is the base the variable expects (`OPENAI_BASE_URL` includes /v1).
UPSTREAMS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com",
    "google": "https://generativelanguage.googleapis.com",
    "mistral": "https://api.mistral.ai",
    "openrouter": "https://openrouter.ai",
}
ENDPOINT_VARS: dict[str, dict[str, str]] = {
    "anthropic": {"ANTHROPIC_BASE_URL": "", "ANTHROPIC_HOST": ""},
    "openai": {"OPENAI_BASE_URL": "/v1", "OPENAI_HOST": ""},
    "google": {"GOOGLE_GEMINI_BASE_URL": "", "GOOGLE_BASE_URL": "", "GOOGLE_HOST": ""},
    "mistral": {"MISTRAL_BASE_URL": "/v1", "MISTRAL_HOST": ""},
    "openrouter": {"OPENROUTER_BASE_URL": "/api/v1", "OPENROUTER_HOST": ""},
}

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-connection",
    "transfer-encoding",
    "te",
    "trailer",
    "upgrade",
    "host",
    "content-length",
    "accept-encoding",
}
_MAX_CAPTURE = 64 * 1024 * 1024
# How long `take` waits for responses still streaming. A provider can close a
# stream after its final event, when the agent has already exited.
_SETTLE_SECONDS = 30.0


@dataclass(frozen=True)
class Billed:
    """One model response, in AVP's convention: input includes cache reads and
    writes, output includes reasoning. `complete` is False for a response the
    agent hung up on (an interrupt): the provider bills it, but how much
    output it generated is unknown here."""

    path: str
    input_tokens: int
    output_tokens: int
    complete: bool = True


def usage_of(body: bytes, content_type: str) -> tuple[int, int] | None:
    """The `(input, output)` tokens a response body reports, or None when it is
    not a model response (a model list, a token count)."""
    payloads: list[Any] = []
    text = body.decode("utf-8", "replace")
    if "text/event-stream" in content_type:
        for line in text.splitlines():
            if line.startswith("data:"):
                data = line[5:].strip()
                if data and data != "[DONE]":
                    try:
                        payloads.append(json.loads(data))
                    except json.JSONDecodeError:
                        continue
    else:
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        # A Gemini stream without `alt=sse` is one JSON array of chunks.
        payloads = parsed if isinstance(parsed, list) else [parsed]

    found: tuple[int, int] | None = None
    anthropic: dict[str, int] = {}
    for p in payloads:
        if not isinstance(p, dict):
            continue
        kind = p.get("type")
        if kind == "message_start":
            anthropic.update(_ints(p.get("message", {}).get("usage")))
        elif kind == "message_delta":
            anthropic.update(_ints(p.get("usage")))
        elif kind == "message" and isinstance(p.get("usage"), dict):
            anthropic = _ints(p["usage"])
        elif kind == "response.completed":
            found = _openai_responses(p.get("response", {}).get("usage"))
        elif p.get("object") == "response" and p.get("status") == "completed":
            found = _openai_responses(p.get("usage"))
        elif p.get("object") in ("chat.completion", "chat.completion.chunk") and p.get("usage"):
            u = _ints(p["usage"])
            found = (u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        elif isinstance(p.get("usageMetadata"), dict):
            u = _ints(p["usageMetadata"])
            # Chunks repeat the running total; the last one is the response's.
            found = (
                u.get("promptTokenCount", 0) + u.get("toolUsePromptTokenCount", 0),
                u.get("candidatesTokenCount", 0) + u.get("thoughtsTokenCount", 0),
            )
    if anthropic:
        found = (
            anthropic.get("input_tokens", 0)
            + anthropic.get("cache_read_input_tokens", 0)
            + anthropic.get("cache_creation_input_tokens", 0),
            anthropic.get("output_tokens", 0),
        )
    return found


def _ints(usage: Any) -> dict[str, int]:
    if not isinstance(usage, dict):
        return {}
    return {k: v for k, v in usage.items() if isinstance(v, int) and not isinstance(v, bool)}


def _openai_responses(usage: Any) -> tuple[int, int] | None:
    u = _ints(usage)
    return (u["input_tokens"], u.get("output_tokens", 0)) if "input_tokens" in u else None


class Meter:
    """Reverse proxies, one per provider origin, recording `Billed` responses."""

    def __init__(self, upstreams: dict[str, str] | None = None) -> None:
        self._upstreams = upstreams if upstreams is not None else UPSTREAMS
        self._servers: dict[str, ThreadingHTTPServer] = {}
        self._billed: list[Billed] = []
        self._in_flight = 0
        self._lock = threading.Condition()

    def start(self) -> Meter:
        for origin, upstream in self._upstreams.items():
            server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler(urlsplit(upstream)))
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            self._servers[origin] = server
        return self

    def stop(self) -> None:
        for server in self._servers.values():
            server.shutdown()
            server.server_close()

    def __enter__(self) -> Meter:
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def url(self, origin: str) -> str:
        return f"http://127.0.0.1:{self._servers[origin].server_address[1]}"

    def env(self) -> dict[str, str]:
        """Variables routing every known origin through its proxy."""
        return {
            var: self.url(origin) + suffix
            for origin, variables in ENDPOINT_VARS.items()
            if origin in self._servers
            for var, suffix in variables.items()
        }

    def take(self, settle: float = _SETTLE_SECONDS) -> list[Billed]:
        """The responses billed since the last call, once the responses still
        in flight finish (waiting at most `settle` seconds)."""
        with self._lock:
            self._lock.wait_for(lambda: self._in_flight == 0, timeout=settle)
            billed, self._billed = self._billed, []
        return billed

    def _record(self, billed: Billed) -> None:
        with self._lock:
            self._billed.append(billed)

    def _track(self, delta: int) -> None:
        with self._lock:
            self._in_flight += delta
            self._lock.notify_all()

    def _handler(self, upstream: Any) -> type[BaseHTTPRequestHandler]:
        meter = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args: Any) -> None:
                pass

            def _forward(self) -> None:
                meter._track(1)
                try:
                    self._proxy()
                finally:
                    meter._track(-1)

            def _proxy(self) -> None:
                body = self._request_body()
                headers = {k: v for k, v in self.headers.items() if k.lower() not in _HOP_BY_HOP}
                headers["Accept-Encoding"] = "identity"
                conn_cls = (
                    http.client.HTTPSConnection
                    if upstream.scheme == "https"
                    else http.client.HTTPConnection
                )
                conn = conn_cls(upstream.netloc, timeout=600)
                try:
                    conn.request(
                        self.command, upstream.path + self.path, body=body, headers=headers
                    )
                    resp = conn.getresponse()
                    self.send_response(resp.status)
                    for k, v in resp.getheaders():
                        if k.lower() not in _HOP_BY_HOP:
                            self.send_header(k, v)
                    self.send_header("Connection", "close")
                    self.end_headers()
                    captured = bytearray()
                    complete = True
                    while chunk := resp.read1(65536):
                        if len(captured) < _MAX_CAPTURE:
                            captured += chunk
                        try:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        except OSError:
                            # The agent hung up mid-response (an interrupt).
                            complete = False
                            break
                    if 200 <= resp.status < 300:
                        usage = usage_of(bytes(captured), resp.getheader("content-type") or "")
                        if usage is not None:
                            meter._record(Billed(self.path, *usage, complete=complete))
                        elif not complete:
                            meter._record(Billed(self.path, 0, 0, complete=False))
                finally:
                    conn.close()
                self.close_connection = True

            def _request_body(self) -> bytes | None:
                if self.headers.get("transfer-encoding", "").lower() == "chunked":
                    out = bytearray()
                    while True:
                        size = int(self.rfile.readline().split(b";")[0].strip(), 16)
                        if size == 0:
                            self.rfile.readline()
                            return bytes(out)
                        out += self.rfile.read(size)
                        self.rfile.readline()
                length = int(self.headers.get("content-length") or 0)
                return self.rfile.read(length) if length else None

            do_GET = do_POST = do_PUT = do_DELETE = do_PATCH = _forward

        return Handler


def accounted(events: list[dict]) -> tuple[int, int, int | None]:
    """The trajectory's `(input, output, unsplit)` tokens: every turn's usage
    plus each subagent rollup. `unsplit` sums the rollups that report only a
    total; it is None when every rollup splits input from output."""
    inp = out = 0
    unsplit: int | None = None
    for e in events:
        data = e.get("data") or {}
        if e.get("type") == "avp.assistant_message":
            usage = data.get("avp.usage") or {}
            inp += usage.get("input_tokens") or 0
            out += usage.get("output_tokens") or 0
        elif e.get("type") == "avp.subagent_returned":
            usage = data.get("avp.subagent.usage") or {}
            if "tokens_input" in usage or "tokens_output" in usage:
                inp += usage.get("tokens_input") or 0
                out += usage.get("tokens_output") or 0
            elif "total_tokens" in usage:
                unsplit = (unsplit or 0) + usage["total_tokens"]
    return inp, out, unsplit


def reconcile(billed: list[Billed], events: list[dict]) -> list[str]:
    """Reasons the provider's bill and the trajectory disagree (empty if they match).

    A cut-off response's full usage is unknown, so when one exists the
    trajectory must record at least the completed responses' tokens rather
    than exactly the bill.

    Matching totals is not enough: usage filed on the wrong turn still sums
    right. When every response completed and no subagent rolled up its spend,
    each billed response must also be one turn's usage. Responses can finish
    out of order, so the two are compared as multisets."""
    done = [b for b in billed if b.complete]
    b_in = sum(b.input_tokens for b in done)
    b_out = sum(b.output_tokens for b in done)
    cut = len(billed) - len(done)
    a_in, a_out, unsplit = accounted(events)
    turns = sum(1 for e in events if e.get("type") == "avp.assistant_message")
    if unsplit is not None:
        b_all, a_all = b_in + b_out, a_in + a_out + unsplit
        if b_all == a_all or (cut and a_all >= b_all):
            return []
        where = f"{b_all} tokens"
        recorded = f"{a_all}"
    else:
        if (b_in, b_out) == (a_in, a_out) and not cut and not _has_rollups(events):
            return _per_response(done, events)
        if (b_in, b_out) == (a_in, a_out) or (cut and a_in >= b_in and a_out >= b_out):
            return []
        where = f"{b_in} input / {b_out} output tokens"
        recorded = f"{a_in} / {a_out}"
    partial = f", plus {cut} cut off," if cut else ""
    return [
        f"metering: the provider billed {where} across {len(done)} completed "
        f"response(s){partial}; the trajectory records {recorded} ({turns} turn(s))"
    ]


def _has_rollups(events: list[dict]) -> bool:
    return any(
        e.get("type") == "avp.subagent_returned" and (e.get("data") or {}).get("avp.subagent.usage")
        for e in events
    )


def _per_response(billed: list[Billed], events: list[dict]) -> list[str]:
    """Reasons the bill's responses are not the trajectory's turns, one for one."""
    responses = sorted((b.input_tokens, b.output_tokens) for b in billed)
    turns = sorted(
        (usage.get("input_tokens") or 0, usage.get("output_tokens") or 0)
        for e in events
        if e.get("type") == "avp.assistant_message"
        for usage in [(e.get("data") or {}).get("avp.usage") or {}]
    )
    if responses == turns:
        return []
    return [
        "metering: the totals match but the turns do not: the provider billed "
        f"responses {responses} (input, output); the trajectory's turns record {turns}"
    ]
