"""Bridge: AEP `LocalTools` → Claude Agent SDK in-process MCP server.

User B writes their tool registration ONCE against `aep.runner.LocalTools`
and runs the same Config against either runner. With aep-anthropic,
`LocalTools` is the `ToolDriver` directly (the runner already accepts
`tools: ToolDriver`). With aep-claude-agent, the SDK owns the loop and
expects in-process tools registered via its own `@tool` /
`create_sdk_mcp_server` mechanism — this bridge converts the AEP
registry to that shape so the SDK can dispatch them.

Wire-shape consequence: bridged tools land on the AEP wire as
`mcp__<server>__<tool>` with `dispatch_target=local` (the SDK names
them MCP-style, but the bridged server isn't in `Config.mcp_servers[]`,
so the translator's existing tag-MCP-by-Config logic correctly tags
them as local). Same on-the-wire shape `aep-anthropic` produces for
the same callable.

Return-value coercion: each bridged tool wraps the user's sync
callable in an async shim that calls it and renders the result to
MCP-result shape (`{"content": [{"type": "text", "text": "..."}],
"isError": bool}`). Coercion rules mirror `LocalTools._invoke`:
ToolOutcome → text/json, str → text, dict/list → JSON-coerced,
exception → `isError: True`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aep.runner.local_tools import LocalTools

DEFAULT_SERVER_NAME = "local"


def to_sdk_mcp_server(
    local_tools: LocalTools,
    *,
    name: str = DEFAULT_SERVER_NAME,
    version: str = "1.0.0",
) -> Any:
    """Convert a `LocalTools` registry into a Claude Agent SDK in-process MCP server.

    Returns the value you pass to
    `ClaudeAgentOptions.mcp_servers={<name>: ...}`. The SDK calls each
    tool's async handler when the model invokes it; the AEP translator's
    existing PreToolUse / PostToolUse hooks observe the dispatch and
    emit `tool_invoked` / `tool_returned` events.

    `name` is the MCP server key the SDK uses to namespace tool calls
    (the model sees `mcp__<name>__<tool>`). Default `"local"` matches
    the AEP convention; pick a different name only if you've already
    declared a `local` server in `Config.mcp_servers[]`.
    """
    # Lazy import — claude_agent_sdk is only required when this bridge
    # is actually used. Tests can substitute via the module-level
    # _build_tool / _build_server hooks below.
    from claude_agent_sdk import create_sdk_mcp_server, tool

    sdk_tools = [
        _wrap(
            name=tname,
            description=schema["description"],
            input_schema=schema["input_schema"],
            fn=fn,
            tool_decorator=tool,
        )
        for tname, fn, schema in local_tools.entries()
    ]
    return create_sdk_mcp_server(name=name, version=version, tools=sdk_tools)


def _wrap(
    *,
    name: str,
    description: str,
    input_schema: dict[str, Any],
    fn: Any,
    tool_decorator: Any,
) -> Any:
    """Wrap one LocalTools callable into an SdkMcpTool.

    The user's callable is sync `(dict) -> Any`; the SDK wants async
    `(dict) -> {"content": [...], "isError": bool}`. We bridge by
    awaiting nothing (just calling sync) inside an async shim and
    rendering the return value to MCP-result shape.
    """

    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        # Import lazily so test mocks don't pull in the real ToolOutcome
        # if a user only exercises the bridge function.
        from aep.runner.drivers import ToolOutcome

        try:
            result = fn(args)
        except Exception as exc:
            return _mcp_result_text(f"{type(exc).__name__}: {exc}", is_error=True)

        if isinstance(result, ToolOutcome):
            if result.error:
                return _mcp_result_text(result.error, is_error=True)
            text = result.output or ""
            return _mcp_result_text(text, is_error=False)
        if result is None:
            return _mcp_result_text("", is_error=False)
        if isinstance(result, str):
            return _mcp_result_text(result, is_error=False)
        try:
            rendered = json.dumps(result, default=str)
        except (TypeError, ValueError):
            rendered = repr(result)
        return _mcp_result_text(rendered, is_error=False)

    return tool_decorator(name, description, input_schema)(handler)


def _mcp_result_text(text: str, *, is_error: bool) -> dict[str, Any]:
    """MCP CallToolResult shape: a list of content blocks plus an
    optional `isError` flag. Single-text-block is the common case."""
    return {
        "content": [{"type": "text", "text": text}],
        "isError": is_error,
    }
