"""HttpResolver unit tests.

The HttpResolver dials AVP_RESOLVER_URL via JSON-RPC 2.0 over HTTP.
These tests mock `urllib.request.urlopen` so they exercise the
request-shape construction and response-parsing logic without
actually touching the network.
"""

from __future__ import annotations

import io
import json
from typing import Any
from unittest.mock import patch

import pytest

from avp.agent.drivers import ResolveError
from avp.agent.http_resolver import HttpResolver, http_resolver_from_env


class _FakeResponse:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def read(self) -> bytes:
        return self._body.getvalue()


def _captured_request_inspect(*captured: dict) -> Any:
    """Returns a `urlopen` replacement that captures the Request object
    AND returns a canned response. Lets tests assert on what was sent."""

    def _impl(request, timeout):
        captured[0]["req"] = request
        return _FakeResponse({"jsonrpc": "2.0", "id": "ok", "result": {"echo": "received"}})

    return _impl


# ── Construction ───────────────────────────────────────────────────────────


def test_http_resolver_requires_non_empty_url() -> None:
    with pytest.raises(ValueError, match="non-empty URL"):
        HttpResolver(url="")


def test_http_resolver_from_env_returns_none_when_unset(monkeypatch) -> None:
    monkeypatch.delenv("AVP_RESOLVER_URL", raising=False)
    assert http_resolver_from_env() is None


def test_http_resolver_from_env_builds_resolver_when_set(monkeypatch) -> None:
    monkeypatch.setenv("AVP_RESOLVER_URL", "https://resolver.acme.internal/avp")
    monkeypatch.setenv("AVP_RESOLVER_TOKEN", "secret")
    resolver = http_resolver_from_env()
    assert isinstance(resolver, HttpResolver)
    assert resolver._url == "https://resolver.acme.internal/avp"
    assert resolver._bearer == "secret"


# ── resolve(): request shape ─────────────────────────────────────────────


def test_resolve_posts_jsonrpc_envelope_with_kind_id_ref() -> None:
    captured = [{}]
    resolver = HttpResolver(url="https://x.example/avp", bearer_token="tok-1")
    with patch("avp.agent.http_resolver.urlopen", _captured_request_inspect(*captured)):
        result = resolver.resolve(kind="mcp_server", id="github", ref={"vault": "prod"})
    assert result == {"echo": "received"}
    req = captured[0]["req"]
    assert req.full_url == "https://x.example/avp"
    assert req.method == "POST"
    body = json.loads(req.data.decode("utf-8"))
    assert body["jsonrpc"] == "2.0"
    assert body["method"] == "avp.resolve"
    assert body["params"]["kind"] == "mcp_server"
    assert body["params"]["id"] == "github"
    assert body["params"]["ref"] == {"vault": "prod"}
    # Bearer token rides on Authorization header.
    assert req.headers.get("Authorization") == "Bearer tok-1"


# ── resolve(): error paths ────────────────────────────────────────────────


def test_resolve_raises_resolve_error_on_jsonrpc_error() -> None:
    resolver = HttpResolver(url="https://x.example/avp")
    error_payload = {
        "jsonrpc": "2.0",
        "id": "x",
        "error": {"code": -32601, "message": "method not found"},
    }

    def _err_urlopen(req, timeout):
        return _FakeResponse(error_payload)

    with patch("avp.agent.http_resolver.urlopen", _err_urlopen):
        with pytest.raises(ResolveError) as exc:
            resolver.resolve(kind="mcp_server", id="x", ref="y")
    assert "method not found" in str(exc.value)


def test_resolve_raises_resolve_error_on_malformed_json() -> None:
    resolver = HttpResolver(url="https://x.example/avp")

    def _bad_urlopen(req, timeout):
        class _R:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return None

            def read(self):
                return b"not-json"

        return _R()

    with patch("avp.agent.http_resolver.urlopen", _bad_urlopen):
        with pytest.raises(ResolveError, match="non-JSON"):
            resolver.resolve(kind="skill", id="x", ref="y")


def test_resolve_raises_resolve_error_on_transport_failure() -> None:
    from urllib.error import URLError

    resolver = HttpResolver(url="https://x.example/avp")

    def _down(req, timeout):
        raise URLError("Connection refused")

    with patch("avp.agent.http_resolver.urlopen", _down):
        with pytest.raises(ResolveError) as exc:
            resolver.resolve(kind="mcp_server", id="x", ref="y")
    assert exc.value.code == "transport_error"


# ── spawn_subagent(): result shape ────────────────────────────────────────


def test_spawn_subagent_parses_outcome() -> None:
    payload = {
        "jsonrpc": "2.0",
        "id": "x",
        "result": {
            "subagent_run_id": "child-42",
            "result": {
                "text": "found three handlers",
                "reason": "converged",
                "duration_ms": 75,
                "usage": {"total_cost_usd": 0.001, "total_tokens": 80, "total_turns": 1},
            },
        },
    }
    resolver = HttpResolver(url="https://x.example/avp")

    def _ok(req, timeout):
        return _FakeResponse(payload)

    with patch("avp.agent.http_resolver.urlopen", _ok):
        outcome = resolver.spawn_subagent(
            run_id="parent",
            id="researcher",
            ref="sk_researcher",
            input={"prompt": "find auth handlers"},
        )
    assert outcome.child_run_id == "child-42"
    assert outcome.text == "found three handlers"
    assert outcome.duration_ms == 75
    assert outcome.usage.total_cost_usd == 0.001
    assert outcome.usage.total_tokens == 80
