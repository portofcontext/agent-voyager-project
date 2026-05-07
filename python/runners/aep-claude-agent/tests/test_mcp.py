"""Tests for native MCP support in aep-claude-agent.

The Claude Agent SDK has first-class MCP: pass `mcp_servers` on
`ClaudeAgentOptions` and the SDK owns the connection lifecycle, tools/list
discovery, and tools/call dispatch. This translator's job is just to
translate AEP's `Config.mcp_servers[]` to the SDK's shape and tag the
resulting tool events with `aep.tool.dispatch_target = "mcp_server"`.

These tests pin:
  - Config.mcp_servers → SDK options.mcp_servers translation (stdio + http)
  - mcp_server_connected events emitted at start, one per declared server
  - Tools whose names match `mcp__<server>__<tool>` AND server is declared
    get `dispatch_target=mcp_server` + `aep.mcp_server_id` on tool_invoked
  - Tools matching the prefix but with an UNDECLARED server fall back to
    `dispatch_target=local` (we don't pretend to know what we didn't bring)
  - HTTP auth with `token_env` resolves the env var at translation time
    (so the secret never lands in the wire) — tested via env injection
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from aep import (
    Config,
    McpHttpAuth,
    McpServer,
    McpServerConnectedEvent,
    ToolInvokedEvent,
)
from aep_claude_agent import ClaudeAgentTranslator


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


def _make_translator(cfg: Config) -> tuple[ClaudeAgentTranslator, list]:
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


def _by_type(events: list, type_: type) -> list:
    return [e for e in events if isinstance(e, type_)]


# ── Translation: Config.mcp_servers → SDK options.mcp_servers ───────────────


def test_stdio_mcp_server_translates_to_sdk_shape() -> None:
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-stdio",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="github",
                transport="stdio",
                command=["npx"],
                args=["-y", "@modelcontextprotocol/server-github"],
                env={"GITHUB_TOKEN": "shhh"},
            )
        ],
    )
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    servers = opts.kwargs["mcp_servers"]
    # SDK shape is a dict keyed by server id; each entry carries the
    # transport plus stdio fields.
    assert "github" in servers
    entry = servers["github"]
    assert entry["type"] == "stdio"
    assert entry["command"] == ["npx"]
    assert entry["args"] == ["-y", "@modelcontextprotocol/server-github"]
    assert entry["env"] == {"GITHUB_TOKEN": "shhh"}


def test_http_mcp_server_with_bearer_auth_resolves_token_from_env(monkeypatch) -> None:
    """HTTP auth with `token_env` MUST be resolved to a header at
    translation time so the secret never lands in the wire (Config /
    events). The env var is read once when options are built; the
    translator passes a finished `Authorization: Bearer …` header to
    the SDK."""
    monkeypatch.setenv("MY_API_TOKEN", "secret-123")
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-http",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="weather",
                transport="http",
                url="https://mcp.example.com/weather",
                auth=McpHttpAuth(type="bearer", token_env="MY_API_TOKEN"),
            )
        ],
    )
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    entry = opts.kwargs["mcp_servers"]["weather"]
    assert entry["type"] == "http"
    assert entry["url"] == "https://mcp.example.com/weather"
    assert entry["headers"] == {"Authorization": "Bearer secret-123"}


def test_http_mcp_server_without_env_token_skips_header(monkeypatch) -> None:
    """If the env var isn't set, we don't ship an empty Authorization
    header — better to fail at the server than to send `Bearer ` and
    look like an authentication attempt."""
    monkeypatch.delenv("UNSET_TOKEN", raising=False)
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-no-token",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="public",
                transport="http",
                url="https://mcp.example.com",
                auth=McpHttpAuth(type="bearer", token_env="UNSET_TOKEN"),
            )
        ],
    )
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    entry = opts.kwargs["mcp_servers"]["public"]
    assert "headers" not in entry


def test_no_mcp_servers_omits_kwarg_entirely() -> None:
    """Backwards-compat: a Config without mcp_servers MUST NOT populate
    options.mcp_servers (so existing setups that rely on the SDK's
    filesystem-loaded MCP config keep working)."""
    cfg = Config(schema_version="0.1", run_id="no-mcp", model="claude-sonnet-4-6")
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    assert "mcp_servers" not in opts.kwargs


# ── Wire: mcp_server_connected emitted at agent_started ─────────────────────


def test_emits_mcp_server_connected_per_declared_server() -> None:
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-connected",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(id="github", transport="stdio", command=["npx", "-y", "x"]),
            McpServer(id="weather", transport="http", url="https://mcp.example.com"),
        ],
    )
    t, out = _make_translator(cfg)
    t._emit_agent_started()
    connected = _by_type(out, McpServerConnectedEvent)
    assert len(connected) == 2
    ids = {e.data.aep_mcp_server_id for e in connected}
    assert ids == {"github", "weather"}


def test_no_mcp_servers_emits_no_connected_events() -> None:
    cfg = Config(schema_version="0.1", run_id="no-mcp-events", model="claude-sonnet-4-6")
    t, out = _make_translator(cfg)
    t._emit_agent_started()
    assert not _by_type(out, McpServerConnectedEvent)


# ── Tool tagging: mcp__<server>__<tool> on PreToolUse ───────────────────────


def test_mcp_prefixed_tool_call_tags_dispatch_target_and_server_id() -> None:
    """SDK names MCP tools `mcp__<server>__<tool>`. When we see one
    AND the server is declared in our Config, we tag the tool_invoked
    event with `dispatch_target=mcp_server` + `aep.mcp_server_id` so
    consumers can correlate the tool call back to the connected event."""
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-tag",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServer(id="github", transport="stdio", command=["x"])],
    )
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-1",
                "tool_name": "mcp__github__create_issue",
                "tool_input": {"repo": "foo", "title": "bar"},
            },
            None,
            None,
        )
    )

    invoked = _by_type(out, ToolInvokedEvent)[0]
    assert invoked.data.gen_ai_tool_name == "mcp__github__create_issue"
    assert invoked.data.aep_tool_dispatch_target == "mcp_server"
    # The aep_mcp_server_id field surfaces under its dotted alias on the wire.
    wire = invoked.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["data"]["aep.mcp_server_id"] == "github"


def test_mcp_prefixed_tool_with_undeclared_server_falls_back_to_local() -> None:
    """If the SDK surfaces a tool with the `mcp__` prefix for a server
    we DIDN'T declare (e.g. filesystem-loaded SDK config, vendor
    defaults), we don't pretend to know what we didn't bring — tag as
    local. Audit-honest: the tool came from somewhere we didn't
    declare."""
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-undeclared",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServer(id="github", transport="stdio", command=["x"])],
    )
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-x",
                "tool_name": "mcp__weather__forecast",  # weather NOT declared
                "tool_input": {},
            },
            None,
            None,
        )
    )

    invoked = _by_type(out, ToolInvokedEvent)[0]
    assert invoked.data.aep_tool_dispatch_target == "local"
    wire = invoked.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "aep.mcp_server_id" not in wire["data"]


def test_non_mcp_tool_keeps_local_dispatch_target() -> None:
    """SDK built-ins (Read, Write, Bash, etc.) don't have the `mcp__`
    prefix — they stay tagged as `local`."""
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-builtin",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServer(id="github", transport="stdio", command=["x"])],
    )
    t, out = _make_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-y",
                "tool_name": "Read",
                "tool_input": {"file_path": "/tmp/foo"},
            },
            None,
            None,
        )
    )

    invoked = _by_type(out, ToolInvokedEvent)[0]
    assert invoked.data.aep_tool_dispatch_target == "local"


# ── Helper: name parsing ────────────────────────────────────────────────────


def test_mcp_server_id_extraction_handles_underscores_in_server_name() -> None:
    """Server ids may contain underscores (`my_company_tools__lookup`).
    The separator between server-id and tool-name is exactly `__`, and
    we split on the FIRST `__` after the `mcp__` prefix to keep server
    names with underscores intact."""
    extract = ClaudeAgentTranslator._mcp_server_id_from_tool_name
    assert extract("mcp__github__create_issue") == "github"
    assert extract("mcp__my_company_tools__lookup_user") == "my_company_tools"
    # Non-MCP names return None.
    assert extract("Read") is None
    assert extract("write_file") is None
    # Malformed: no separator after prefix.
    assert extract("mcp__justservername") is None
    assert extract("mcp__") is None


# ── End-to-end: the SDK options carry hooks AND mcp_servers ─────────────────


def test_options_carry_both_aep_hooks_and_mcp_servers() -> None:
    """Smoke check that adding mcp_servers doesn't break the existing
    hook installation — both keys land on the options together."""
    cfg = Config(
        schema_version="0.1",
        run_id="mcp-with-hooks",
        model="claude-sonnet-4-6",
        mcp_servers=[McpServer(id="github", transport="stdio", command=["x"])],
    )
    t, _ = _make_translator(cfg)
    opts = t._build_sdk_options()
    assert "mcp_servers" in opts.kwargs
    assert "hooks" in opts.kwargs
    assert "PreToolUse" in opts.kwargs["hooks"]
