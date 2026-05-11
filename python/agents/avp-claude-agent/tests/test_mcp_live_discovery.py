"""Live MCP server discovery on agent start.

After `ClaudeSDKClient.connect()` returns, the SDK has completed the
MCP handshake (initialize + tools/list per server). The translator
calls `client.get_mcp_status()` to fetch the SDK's authoritative view
and emits one `mcp_server_connected` event per server with the live
tool list, real `serverInfo`, and connection status.

Pre-fix the translator emitted these events synchronously from
`_emit_agent_started` with stub data (tool_count=0, no real tools, no
status). Auditors had to derive the actual MCP tool surface from
post-hoc `tool_invoked` events. Now the connect events carry it
upfront — answers "what tools did this MCP server expose?" without
needing to wait for invocations.

Fallback: when get_mcp_status isn't available (test fakes, older SDK)
or raises, the translator falls back to one Commission-time stub event
per Commission.mcp_servers entry. Pinned by tests in test_mcp.py.
"""

from __future__ import annotations

import asyncio
from typing import Any

from avp import Commission
from avp.types import McpServerConnectedEvent
from avp_claude_agent.translator import ClaudeAgentTranslator

from .test_translator import _FakeHookMatcher, _FakeOptions


def _make_translator(cfg: Commission) -> tuple[ClaudeAgentTranslator, list]:
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


class _StubClient:
    """Minimal stand-in for `ClaudeSDKClient.get_mcp_status()`. The
    real method returns an `McpStatusResponse` TypedDict with
    `mcpServers: list[McpServerStatus]`. We mirror the dict shape."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response

    async def get_mcp_status(self) -> dict[str, Any]:
        return self._response


# ── Live discovery happy path: tools, names, status ─────────────────────


def test_live_status_emits_real_tool_names_per_server() -> None:
    """SDK reports two connected servers, each with real tools. The
    translator emits one event per server with `avp.mcp.tools`
    populated and `avp.mcp.tool_count` matching the actual count."""
    cfg = Commission(
        schema_version="0.1",
        run_id="live-mcp",
        model="claude-sonnet-4-6",
        prompt="hi",
    )
    t, out = _make_translator(cfg)

    response = {
        "mcpServers": [
            {
                "name": "github",
                "status": "connected",
                "serverInfo": {"name": "github-mcp", "version": "1.2.3"},
                "tools": [
                    {"name": "create_issue", "description": "Open a new issue"},
                    {"name": "list_issues", "description": "List recent issues"},
                ],
            },
            {
                "name": "weather",
                "status": "connected",
                "serverInfo": {"name": "weather-mcp", "version": "0.4"},
                "tools": [{"name": "get_forecast"}],
            },
        ]
    }
    asyncio.run(t._emit_mcp_connections_after_connect(_StubClient(response)))

    events = _by_type(out, McpServerConnectedEvent)
    by_id = {e.data.avp_mcp_server_id: e for e in events}
    assert set(by_id) == {"github", "weather"}

    github = by_id["github"]
    assert github.data.avp_mcp_tool_count == 2
    assert github.data.avp_mcp_status == "connected"
    assert github.data.avp_mcp_server_name == "github-mcp"
    assert github.data.avp_mcp_server_version == "1.2.3"
    # Live tool list with names + descriptions.
    tool_names = [t_.name for t_ in github.data.avp_mcp_tools or []]
    assert tool_names == ["create_issue", "list_issues"]
    # Each tool decl carries dispatch_target + server_id for cross-correlation
    # with `tool_invoked` events.
    wire = github.model_dump(mode="json", by_alias=True, exclude_none=True)
    for tool in wire["data"]["avp.mcp.tools"]:
        assert tool["avp.dispatch_target"] == "mcp_server"
        assert tool["avp.mcp_server_id"] == "github"


def test_tool_descriptions_when_provided_by_server() -> None:
    """McpToolInfo's `description` is NotRequired. When the server
    provides one, surface it; when missing, leave description out
    (honest-null beats authored-prose for tools we don't author)."""
    cfg = Commission(schema_version="0.1", run_id="desc", model="claude-sonnet-4-6", prompt="hi")
    t, out = _make_translator(cfg)
    response = {
        "mcpServers": [
            {
                "name": "s1",
                "status": "connected",
                "tools": [
                    {"name": "described", "description": "Has a real description"},
                    {"name": "bare"},  # no description
                ],
            }
        ]
    }
    asyncio.run(t._emit_mcp_connections_after_connect(_StubClient(response)))
    ev = _by_type(out, McpServerConnectedEvent)[0]
    wire = ev.model_dump(mode="json", by_alias=True, exclude_none=True)
    by_name = {t_["name"]: t_ for t_ in wire["data"]["avp.mcp.tools"]}
    assert by_name["described"]["description"] == "Has a real description"
    assert "description" not in by_name["bare"]


# ── Failure modes: status + error surfaced ──────────────────────────────


def test_failed_server_status_and_error_surface_on_event() -> None:
    """When SDK reports `status=failed` with an error message, both
    fields land on the wire so audit consumers can spot which servers
    didn't connect and why."""
    cfg = Commission(schema_version="0.1", run_id="fail", model="claude-sonnet-4-6", prompt="hi")
    t, out = _make_translator(cfg)
    response = {
        "mcpServers": [
            {
                "name": "broken",
                "status": "failed",
                "error": "ECONNREFUSED on https://broken.example.com/mcp",
            }
        ]
    }
    asyncio.run(t._emit_mcp_connections_after_connect(_StubClient(response)))
    ev = _by_type(out, McpServerConnectedEvent)[0]
    assert ev.data.avp_mcp_server_id == "broken"
    assert ev.data.avp_mcp_status == "failed"
    assert ev.data.avp_mcp_error is not None
    assert "ECONNREFUSED" in ev.data.avp_mcp_error
    # No tools when the server failed.
    assert ev.data.avp_mcp_tool_count == 0
    assert ev.data.avp_mcp_tools is None


def test_needs_auth_status_surfaced() -> None:
    """`needs-auth` is a distinct state — server is reachable but
    authentication wasn't accepted. Same wire shape, different status
    value."""
    cfg = Commission(schema_version="0.1", run_id="auth", model="claude-sonnet-4-6", prompt="hi")
    t, out = _make_translator(cfg)
    response = {
        "mcpServers": [
            {
                "name": "private",
                "status": "needs-auth",
                "error": "401 Unauthorized",
            }
        ]
    }
    asyncio.run(t._emit_mcp_connections_after_connect(_StubClient(response)))
    ev = _by_type(out, McpServerConnectedEvent)[0]
    assert ev.data.avp_mcp_status == "needs-auth"


# ── Fallback: SDK without get_mcp_status ───────────────────────────────


def test_fallback_when_client_has_no_get_mcp_status() -> None:
    """Older SDK versions (or test fakes) without `get_mcp_status` →
    the translator falls back to emitting one stub event per
    Commission.mcp_servers entry. Same v0.1 behavior; lifecycle marker
    still on the wire."""
    from avp import McpServerRef

    class _ClientWithoutStatus:
        pass

    cfg = Commission(
        schema_version="0.1",
        run_id="no-status",
        model="claude-sonnet-4-6",
        prompt="hi",
        mcp_servers=[
            McpServerRef(id="legacy", ref={"transport": "http", "url": "https://x.example.com"})
        ],
    )
    t, out = _make_translator(cfg)
    asyncio.run(t._emit_mcp_connections_after_connect(_ClientWithoutStatus()))
    events = _by_type(out, McpServerConnectedEvent)
    assert len(events) == 1
    assert events[0].data.avp_mcp_server_id == "legacy"
    # Stub: no live tool data, no status, count=0.
    assert events[0].data.avp_mcp_tool_count == 0
    assert events[0].data.avp_mcp_tools is None
    assert events[0].data.avp_mcp_status is None


def test_fallback_when_get_mcp_status_raises() -> None:
    """If get_mcp_status raises (transport hiccup, version mismatch),
    the translator falls back to stubs rather than crashing the run."""
    from avp import McpServerRef

    class _Boom:
        async def get_mcp_status(self):
            raise RuntimeError("transport went away")

    cfg = Commission(
        schema_version="0.1",
        run_id="boom",
        model="claude-sonnet-4-6",
        prompt="hi",
        mcp_servers=[
            McpServerRef(id="resilience", ref={"transport": "http", "url": "https://x.example.com"})
        ],
    )
    t, out = _make_translator(cfg)
    asyncio.run(t._emit_mcp_connections_after_connect(_Boom()))
    events = _by_type(out, McpServerConnectedEvent)
    assert len(events) == 1
    assert events[0].data.avp_mcp_server_id == "resilience"


def test_no_servers_no_events_when_status_empty() -> None:
    """SDK reports zero servers and Commission has none → zero events.
    Symmetric with the no-MCP case."""
    cfg = Commission(schema_version="0.1", run_id="empty", model="claude-sonnet-4-6", prompt="hi")
    t, out = _make_translator(cfg)
    asyncio.run(t._emit_mcp_connections_after_connect(_StubClient({"mcpServers": []})))
    assert not _by_type(out, McpServerConnectedEvent)


# ── SDK-discovered servers not in Commission still surface ──────────────────


def test_sdk_discovered_server_not_in_config_still_emits() -> None:
    """If the SDK loads MCP servers from a settings.json the user has
    on disk (without those servers being in Commission.mcp_servers), the
    SDK still reports them via get_mcp_status. The translator surfaces
    them — auditors see the FULL set of connected servers, not just
    the Commission-declared ones. Keeps the wire honest about what was
    actually connected."""
    cfg = Commission(
        schema_version="0.1",
        run_id="filesystem-mcp",
        model="claude-sonnet-4-6",
        prompt="hi",
        # Note: NO mcp_servers in Commission. The SDK reads them from
        # ~/.claude/settings.json or similar.
    )
    t, out = _make_translator(cfg)
    response = {
        "mcpServers": [
            {
                "name": "user-local",
                "status": "connected",
                "tools": [{"name": "do_thing"}],
            }
        ]
    }
    asyncio.run(t._emit_mcp_connections_after_connect(_StubClient(response)))
    events = _by_type(out, McpServerConnectedEvent)
    assert len(events) == 1
    assert events[0].data.avp_mcp_server_id == "user-local"
    assert events[0].data.avp_mcp_tool_count == 1
