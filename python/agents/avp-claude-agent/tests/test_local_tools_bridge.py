"""LocalTools → Claude Agent SDK MCP-server bridge.

Lets a user write tool registration ONCE against `avp.agent.LocalTools`
and run the same setup against either agent. With avp-claude-agent the
bridge converts each registered callable into an `SdkMcpTool` and packs
them into an in-process MCP server the SDK mounts.

Tests verify:
  - Bridge produces the SDK shape the translator can consume
  - Each user callable becomes an async handler returning MCP-result shape
  - Return-value coercion: str / dict / None / ToolOutcome / exception
  - Translator integration: passing a LocalTools instance lands the
    bridged server in `options.mcp_servers`
  - The wire shape from a LocalTools-bridge tool call: `mcp__local__<tool>`
    invoked → `avp.tool.dispatch_target=local` (bridged server is NOT
    in Commission.mcp_servers, so it's a local tool from AVP's perspective)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from avp import Commission
from avp.agent.drivers import ToolOutcome
from avp.agent.local_tools import LocalTools
from avp.types import ToolInvokedEvent
from avp_claude_agent import ClaudeAgentTranslator
from avp_claude_agent.local_tools_bridge import _wrap, to_sdk_mcp_server

# ── Bridge function: shape conversion ─────────────────────────────────────


@dataclass
class _FakeSdkTool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Any


def _fake_tool_decorator(name: str, description: str, input_schema: dict[str, Any]):
    """Test stand-in for `claude_agent_sdk.tool` — wraps the handler in
    a `_FakeSdkTool` carrying the same fields the real decorator does."""

    def deco(handler):
        return _FakeSdkTool(
            name=name, description=description, input_schema=input_schema, handler=handler
        )

    return deco


def test_wrap_produces_sdk_tool_with_async_handler() -> None:
    """The bridge wraps a sync `(dict) -> Any` callable into an async
    `(dict) -> {content: [...], isError: bool}` shape the SDK expects."""
    sdk_tool = _wrap(
        name="add",
        description="Add",
        input_schema={"type": "object"},
        fn=lambda inp: f"{inp['a']} + {inp['b']}",
        tool_decorator=_fake_tool_decorator,
    )
    assert sdk_tool.name == "add"
    result = asyncio.run(sdk_tool.handler({"a": 1, "b": 2}))
    assert result == {"content": [{"type": "text", "text": "1 + 2"}], "isError": False}


def test_wrap_dict_return_renders_as_json_text() -> None:
    sdk_tool = _wrap(
        name="t",
        description="d",
        input_schema={},
        fn=lambda inp: {"sum": inp["a"] + inp["b"]},
        tool_decorator=_fake_tool_decorator,
    )
    result = asyncio.run(sdk_tool.handler({"a": 1, "b": 2}))
    assert '"sum": 3' in result["content"][0]["text"]
    assert result["isError"] is False


def test_wrap_none_return_becomes_empty_text() -> None:
    sdk_tool = _wrap(
        name="t",
        description="d",
        input_schema={},
        fn=lambda inp: None,
        tool_decorator=_fake_tool_decorator,
    )
    result = asyncio.run(sdk_tool.handler({}))
    assert result["content"][0]["text"] == ""
    assert result["isError"] is False


def test_wrap_tool_outcome_passes_through() -> None:
    """When the user returns a ToolOutcome, its output goes to text and
    its error (if set) flips isError."""
    sdk_tool = _wrap(
        name="t",
        description="d",
        input_schema={},
        fn=lambda inp: ToolOutcome(output="raw"),
        tool_decorator=_fake_tool_decorator,
    )
    result = asyncio.run(sdk_tool.handler({}))
    assert result["content"][0]["text"] == "raw"
    assert result["isError"] is False


def test_wrap_tool_outcome_with_error_marks_is_error_true() -> None:
    sdk_tool = _wrap(
        name="t",
        description="d",
        input_schema={},
        fn=lambda inp: ToolOutcome(error="bad input"),
        tool_decorator=_fake_tool_decorator,
    )
    result = asyncio.run(sdk_tool.handler({}))
    assert result["content"][0]["text"] == "bad input"
    assert result["isError"] is True


def test_wrap_exception_becomes_is_error_with_class_and_message() -> None:
    """A buggy callable doesn't take down the SDK — exception becomes
    an MCP error result the model sees as a tool failure."""

    def boom(_):
        raise ValueError("nope")

    sdk_tool = _wrap(
        name="t",
        description="d",
        input_schema={},
        fn=boom,
        tool_decorator=_fake_tool_decorator,
    )
    result = asyncio.run(sdk_tool.handler({}))
    assert result["isError"] is True
    assert "ValueError" in result["content"][0]["text"]
    assert "nope" in result["content"][0]["text"]


# ── Bridge function: full registry conversion ────────────────────────────


def test_to_sdk_mcp_server_packs_all_registered_tools(monkeypatch) -> None:
    """The full `to_sdk_mcp_server` walks the LocalTools registry and
    hands every entry to `create_sdk_mcp_server`. We patch both SDK
    callables so this test doesn't require the real SDK."""
    seen_tools: list[_FakeSdkTool] = []

    def fake_create_server(*, name, version, tools):
        seen_tools.extend(tools)
        return {"_kind": "fake_server", "name": name, "version": version, "tool_count": len(tools)}

    import claude_agent_sdk

    monkeypatch.setattr(claude_agent_sdk, "tool", _fake_tool_decorator)
    monkeypatch.setattr(claude_agent_sdk, "create_sdk_mcp_server", fake_create_server)

    tools = LocalTools()
    tools.register("a", lambda i: "ra", description="desc-a", input_schema={"type": "object"})
    tools.register("b", lambda i: "rb", description="desc-b", input_schema={"type": "object"})

    server = to_sdk_mcp_server(tools, name="local", version="0.0.1")
    assert server["name"] == "local"
    assert server["tool_count"] == 2
    names = {t.name for t in seen_tools}
    assert names == {"a", "b"}


# ── Translator integration: LocalTools lands in options.mcp_servers ──────


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs):
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


def test_translator_with_local_tools_mounts_bridged_server(monkeypatch) -> None:
    """When the translator is constructed with `local_tools=...`, the
    bridged in-process MCP server lands in `ClaudeAgentOptions.mcp_servers`
    under the user-chosen key. A single AVP-LocalTools registration thus
    works against this agent without the user touching SDK APIs."""

    captured = {}

    def fake_create_server(*, name, version, tools):
        captured["name"] = name
        captured["tool_count"] = len(tools)
        return {"_kind": "fake_server", "name": name}

    import claude_agent_sdk

    monkeypatch.setattr(claude_agent_sdk, "tool", _fake_tool_decorator)
    monkeypatch.setattr(claude_agent_sdk, "create_sdk_mcp_server", fake_create_server)

    tools = LocalTools()
    tools.register(
        "calc",
        lambda inp: {"sum": inp["a"] + inp["b"]},
        description="Add",
        input_schema={"type": "object"},
    )

    commission = Commission(
        schema_version="0.1",
        run_id="lt-bridge",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    out: list = []
    t = ClaudeAgentTranslator(
        commission,
        on_event=out.append,
        local_tools=tools,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    options = t._build_sdk_options()

    # Bridged server lands under the default `local` key.
    assert "mcp_servers" in options.kwargs
    assert "local" in options.kwargs["mcp_servers"]
    assert captured["tool_count"] == 1
    assert captured["name"] == "local"


def test_translator_without_local_tools_does_not_set_mcp_servers(monkeypatch) -> None:
    """No `local_tools` arg → no in-process MCP server. Backwards-compat:
    existing CASDK setups that don't use LocalTools see no change."""
    commission = Commission(
        schema_version="0.1",
        run_id="lt-bridge-none",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    out: list = []
    t = ClaudeAgentTranslator(
        commission,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    options = t._build_sdk_options()
    assert "mcp_servers" not in options.kwargs


def test_translator_local_tools_server_name_is_configurable(monkeypatch) -> None:
    """If a user already declared a Commission.mcp_servers entry called
    `local`, they can pass a different name to avoid collision."""

    def fake_create_server(*, name, version, tools):
        return {"_kind": "fake_server", "name": name}

    import claude_agent_sdk

    monkeypatch.setattr(claude_agent_sdk, "tool", _fake_tool_decorator)
    monkeypatch.setattr(claude_agent_sdk, "create_sdk_mcp_server", fake_create_server)

    tools = LocalTools()
    tools.register("x", lambda i: "y", description="d", input_schema={})

    commission = Commission(
        schema_version="0.1",
        run_id="lt-name",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    out: list = []
    t = ClaudeAgentTranslator(
        commission,
        on_event=out.append,
        local_tools=tools,
        local_tools_server_name="my_app_tools",
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    options = t._build_sdk_options()
    assert "my_app_tools" in options.kwargs["mcp_servers"]
    assert "local" not in options.kwargs["mcp_servers"]


# ── Wire: bridged tool dispatch tags as dispatch_target=local ────────────


def test_bridged_tool_invocation_tags_dispatch_target_local() -> None:
    """The model calls a bridged tool by its SDK-namespaced name
    (`mcp__local__calc`). Because `local` is NOT in `Commission.mcp_servers`,
    the translator's existing tag-MCP-by-Commission logic correctly tags
    the resulting `tool_invoked` event with
    `avp.tool.dispatch_target=local` — same wire shape `avp-anthropic`
    produces for the same callable."""
    commission = Commission(
        schema_version="0.1",
        run_id="lt-tag",
        model="claude-sonnet-4-6",
        prompt="hi",
        exposed=["*"],
    )
    out: list = []
    t = ClaudeAgentTranslator(
        commission,
        on_event=out.append,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )

    # Simulate the SDK's PreToolUse hook firing with an MCP-style name.
    asyncio.run(
        t._on_pre_tool_use_hook(
            {
                "tool_use_id": "tu-x",
                "tool_name": "mcp__local__calc",
                "tool_input": {"a": 1, "b": 2},
            },
            None,
            None,
        )
    )

    invoked = next(e for e in out if isinstance(e, ToolInvokedEvent))
    # The bridged server "local" is NOT in Commission.mcp_servers — so even
    # though the tool name has the mcp__ prefix, dispatch_target is local.
    assert invoked.data.avp_tool_dispatch_target == "local"
    wire = invoked.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "avp.mcp_server_id" not in wire["data"]
