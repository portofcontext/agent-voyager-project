"""Tests for managed MCP support in avp-claude-agent.

The translator dereferences `Commission.mcp_servers[]` refs via the AVP
resolver protocol (spec/v0.1/resolver.md) before the SDK runs. Resolved connection
material lands on the Claude Agent SDK's `mcp_servers` parameter; the SDK
owns the connection lifecycle, tools/list discovery, and tools/call
dispatch from there. AVP records the AVP-side wire events
(`managed_ref_resolved`, then SDK-side `mcp_server_connected` after
handshake).

These tests pin the translator-side translation only; they don't run
the SDK. Real-MCP end-to-end is covered by `make smoke`'s real-LLM
target.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from avp.agent.mock import ScriptedResolver
from avp.commission import (
    Commission,
    McpServerRef,
)
from avp_claude_agent import ClaudeAgentTranslator


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


def _make_translator(
    cfg: Commission, resolver: Any | None = None
) -> tuple[ClaudeAgentTranslator, list]:
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        resolver=resolver,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


def _seed_resolved_mcp(t: ClaudeAgentTranslator, mapping: dict[str, dict[str, Any]]) -> None:
    """Stage resolved MCP material as if `_resolve_managed_assets` had run."""
    t._resolved_mcp_servers = dict(mapping)


# ── Translation: resolved material → SDK mcp_servers dict ──────────────────


def test_stdio_resolved_material_translates_to_sdk_shape() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="mcp-stdio",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServerRef(id="github", ref={"vault": "prod", "key": "gh"})],
    )
    t, _ = _make_translator(cfg)
    _seed_resolved_mcp(
        t,
        {
            "github": {
                "transport": "stdio",
                "command": ["npx"],
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_TOKEN": "shhh"},
            }
        },
    )
    opts = t._build_sdk_options()
    entry = opts.kwargs["mcp_servers"]["github"]
    assert entry["type"] == "stdio"
    assert entry["command"] == ["npx"]
    assert entry["args"] == ["-y", "@modelcontextprotocol/server-github"]
    assert entry["env"] == {"GITHUB_TOKEN": "shhh"}


def test_http_resolved_material_with_bearer_auth_becomes_authorization_header() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="mcp-http",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServerRef(id="weather", ref="prod-weather")],
    )
    t, _ = _make_translator(cfg)
    _seed_resolved_mcp(
        t,
        {
            "weather": {
                "transport": "http",
                "url": "https://weather.example.com/mcp",
                "auth": {"token": "secret-123"},
            }
        },
    )
    opts = t._build_sdk_options()
    entry = opts.kwargs["mcp_servers"]["weather"]
    assert entry["type"] == "http"
    assert entry["url"] == "https://weather.example.com/mcp"
    assert entry["headers"]["Authorization"] == "Bearer secret-123"


def test_no_mcp_servers_produces_no_kwarg() -> None:
    cfg = Commission(schema_version="0.1", run_id="r", model="claude-sonnet-4-6")
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    assert "mcp_servers" not in opts.kwargs


# ── Resolver protocol: managed_ref_resolved fires on success ──────────────


def test_resolve_managed_assets_emits_managed_ref_resolved() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="resolve-ok",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServerRef(id="github", ref="prod-gh")],
    )
    resolver = ScriptedResolver(
        resolutions={
            "mcp_server:github": {
                "result": {"transport": "http", "url": "https://x.example.com/mcp"}
            }
        }
    )
    t, out = _make_translator(cfg, resolver=resolver)
    assert t._resolve_managed_assets() is True
    resolved_events = [e for e in out if type(e).__name__ == "ManagedRefResolvedEvent"]
    assert len(resolved_events) == 1
    assert resolved_events[0].data.avp_managed_kind == "mcp_server"
    assert resolved_events[0].data.avp_managed_id == "github"


def test_resolve_managed_assets_emits_managed_ref_resolve_failed() -> None:
    cfg = Commission(
        schema_version="0.1",
        run_id="resolve-bad",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServerRef(id="github", ref="bad")],
    )
    resolver = ScriptedResolver(
        resolutions={"mcp_server:github": {"error": "boom", "error_code": "not_found"}}
    )
    t, out = _make_translator(cfg, resolver=resolver)
    assert t._resolve_managed_assets() is False
    failed = [e for e in out if type(e).__name__ == "ManagedRefResolveFailedEvent"]
    assert len(failed) == 1
    assert failed[0].data.avp_managed_id == "github"
    assert failed[0].data.avp_resolve_error_code == "not_found"
