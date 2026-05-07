"""Tests for native MCP support in aep-anthropic.

Anthropic's Messages API has a server-side MCP connector: pass an
`mcp_servers` parameter on `messages.create(...)` and the API itself
connects to remote MCP servers, runs the MCP protocol loop, and
returns assistant content with the tool calls embedded. The connector
is HTTP-only — stdio servers in `Config.mcp_servers[]` MUST be skipped
with a warning (host them from your supervisor instead).

These tests pin:
  - Config.mcp_servers (HTTP) → API shape `{type: url, name, url, ...}`
  - HTTP auth with `token_env` resolves to `authorization_token` at
    translation time so the secret never lands on the wire
  - Stdio servers in Config.mcp_servers are skipped with a warning
  - `mcp_servers_param=None` (or empty) on the driver omits the kwarg
  - The driver forwards `mcp_servers` through to `messages.create()`
    when set
"""

from __future__ import annotations

import warnings
from types import SimpleNamespace

from aep import Config, McpHttpAuth, McpServer
from aep_anthropic import AnthropicModelDriver, build_anthropic_mcp_servers


def _mock_response(*, content: list[dict], usage: dict, stop_reason: str) -> SimpleNamespace:
    blocks = [SimpleNamespace(**b) for b in content]
    return SimpleNamespace(content=blocks, usage=SimpleNamespace(**usage), stop_reason=stop_reason)


class _MockClient:
    def __init__(self, response: SimpleNamespace) -> None:
        self._response = response
        self.calls: list[dict] = []
        self.messages = self  # so client.messages.create(...) works

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


# ── build_anthropic_mcp_servers: Config → API shape ─────────────────────────


def test_http_server_translates_to_api_url_shape() -> None:
    cfg = Config(
        schema_version="0.1",
        run_id="anthropic-mcp-http",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="weather",
                transport="http",
                url="https://mcp.example.com/weather",
            )
        ],
    )
    out = build_anthropic_mcp_servers(cfg)
    assert out == [
        {
            "type": "url",
            "name": "weather",
            "url": "https://mcp.example.com/weather",
        }
    ]


def test_http_server_with_bearer_auth_resolves_token_at_translation_time(
    monkeypatch,
) -> None:
    """`token_env` MUST be resolved to a literal `authorization_token`
    when we build the API parameter — the secret never lands on the
    wire (Config / events) because the runner ships the resolved token
    straight to the API and not into any AEP event."""
    monkeypatch.setenv("MY_API_TOKEN", "secret-123")
    cfg = Config(
        schema_version="0.1",
        run_id="anthropic-mcp-auth",
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
    out = build_anthropic_mcp_servers(cfg)
    assert len(out) == 1
    entry = out[0]
    assert entry["type"] == "url"
    assert entry["name"] == "weather"
    assert entry["url"] == "https://mcp.example.com/weather"
    assert entry["authorization_token"] == "secret-123"


def test_http_server_with_unset_token_env_omits_authorization_token(
    monkeypatch,
) -> None:
    """If the env var isn't set, no `authorization_token` field is
    shipped — better to fail at the server than to send an empty token
    that looks like an authentication attempt."""
    monkeypatch.delenv("UNSET_TOKEN", raising=False)
    cfg = Config(
        schema_version="0.1",
        run_id="anthropic-mcp-no-token",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="public",
                transport="http",
                url="https://mcp.example.com/public",
                auth=McpHttpAuth(type="bearer", token_env="UNSET_TOKEN"),
            )
        ],
    )
    out = build_anthropic_mcp_servers(cfg)
    assert "authorization_token" not in out[0]


def test_stdio_server_is_skipped_with_warning() -> None:
    """The Anthropic API MCP connector is HTTP-only. Stdio servers in
    Config.mcp_servers[] are skipped with a warning so users notice
    rather than silently miss tools."""
    cfg = Config(
        schema_version="0.1",
        run_id="anthropic-mcp-stdio-skip",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="github",
                transport="stdio",
                command=["npx"],
                args=["-y", "@modelcontextprotocol/server-github"],
            ),
            McpServer(
                id="weather",
                transport="http",
                url="https://mcp.example.com/weather",
            ),
        ],
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        out = build_anthropic_mcp_servers(cfg)
    # Only the HTTP server made it through.
    assert len(out) == 1
    assert out[0]["name"] == "weather"
    # The stdio server triggered a warning that names the offending id.
    msgs = [str(w.message) for w in caught]
    assert any("github" in m and "HTTP" in m for m in msgs), msgs


def test_no_mcp_servers_returns_empty_list() -> None:
    cfg = Config(
        schema_version="0.1",
        run_id="no-mcp",
        model="claude-sonnet-4-6",
    )
    assert build_anthropic_mcp_servers(cfg) == []


# ── Driver.step: forwards mcp_servers to messages.create ────────────────────


def test_driver_forwards_mcp_servers_param_to_api() -> None:
    """When `mcp_servers_param` is set, it MUST land on
    `messages.create(...)` so Anthropic's API connector picks it up."""
    resp = _mock_response(
        content=[{"type": "text", "text": "ok"}],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    client = _MockClient(resp)
    mcp_servers = [{"type": "url", "name": "weather", "url": "https://mcp.example.com/weather"}]
    driver = AnthropicModelDriver(
        model="claude-sonnet-4-6",
        client=client,
        mcp_servers_param=mcp_servers,
    )

    driver.step([{"role": "user", "content": "what's the weather?"}])

    assert len(client.calls) == 1
    assert client.calls[0]["mcp_servers"] == mcp_servers


def test_driver_omits_mcp_servers_when_none() -> None:
    """No `mcp_servers_param` (or empty/None) → no `mcp_servers` kwarg.
    Backwards-compat: callers that don't use MCP keep working without
    the API rejecting an empty `mcp_servers` field."""
    resp = _mock_response(
        content=[{"type": "text", "text": "ok"}],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    client = _MockClient(resp)
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)

    driver.step([{"role": "user", "content": "hi"}])

    assert "mcp_servers" not in client.calls[0]


def test_driver_keeps_tools_and_mcp_servers_side_by_side() -> None:
    """`tools` and `mcp_servers` are independent; both can be present."""
    resp = _mock_response(
        content=[{"type": "text", "text": "ok"}],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    client = _MockClient(resp)
    tools = [{"name": "deploy", "description": "ship it", "input_schema": {"type": "object"}}]
    mcp_servers = [{"type": "url", "name": "weather", "url": "https://mcp.example.com"}]
    driver = AnthropicModelDriver(
        model="claude-sonnet-4-6",
        client=client,
        tools_param=tools,
        mcp_servers_param=mcp_servers,
    )

    driver.step([{"role": "user", "content": "hi"}])

    call = client.calls[0]
    assert call["tools"] == tools
    assert call["mcp_servers"] == mcp_servers


# ── End-to-end: build_anthropic_mcp_servers → driver → API ──────────────────


def test_end_to_end_config_mcp_servers_to_api_call(monkeypatch) -> None:
    """The CLI / supervisor pipes Config.mcp_servers[] through
    `build_anthropic_mcp_servers` into the driver. This pins the wire
    that the CLI relies on so a refactor of either side breaks the test
    instead of breaking real users."""
    monkeypatch.setenv("WEATHER_TOKEN", "tok-xyz")
    cfg = Config(
        schema_version="0.1",
        run_id="end-to-end",
        model="claude-sonnet-4-6",
        mcp_servers=[
            McpServer(
                id="weather",
                transport="http",
                url="https://mcp.example.com/weather",
                auth=McpHttpAuth(type="bearer", token_env="WEATHER_TOKEN"),
            )
        ],
    )

    resp = _mock_response(
        content=[{"type": "text", "text": "sunny"}],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    client = _MockClient(resp)
    driver = AnthropicModelDriver(
        model=cfg.model,
        client=client,
        mcp_servers_param=build_anthropic_mcp_servers(cfg) or None,
    )
    driver.step([{"role": "user", "content": "weather?"}])

    assert client.calls[0]["mcp_servers"] == [
        {
            "type": "url",
            "name": "weather",
            "url": "https://mcp.example.com/weather",
            "authorization_token": "tok-xyz",
        }
    ]


# ── Per-call wire events: mcp_tool_use + mcp_tool_result block parsing ──────


def test_mcp_tool_use_block_becomes_server_tool_call() -> None:
    """When the API runs an MCP tool inline, the response carries paired
    `mcp_tool_use` + `mcp_tool_result` blocks. The driver MUST surface
    them on `ModelResponse.server_tool_calls` so the runner can emit
    per-call tool_invoked / tool_returned events."""
    resp = _mock_response(
        content=[
            {"type": "text", "text": "Looking it up."},
            {
                "type": "mcp_tool_use",
                "id": "srvtu_01",
                "name": "get_forecast",
                "server_name": "weather",
                "input": {"city": "NYC"},
            },
            {
                "type": "mcp_tool_result",
                "tool_use_id": "srvtu_01",
                "is_error": False,
                "content": [{"type": "text", "text": "sunny, 72F"}],
            },
            {"type": "text", "text": " It's sunny."},
        ],
        usage={"input_tokens": 10, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "weather?"}])
    assert len(out.server_tool_calls) == 1
    stc = out.server_tool_calls[0]
    assert stc.call_id == "srvtu_01"
    assert stc.tool == "get_forecast"
    assert stc.server_id == "weather"
    assert stc.input == {"city": "NYC"}
    assert stc.output_text == "sunny, 72F"
    assert stc.dispatch_target == "mcp_server"
    assert stc.is_error is False
    # Text from text blocks is concatenated normally.
    assert out.text == "Looking it up. It's sunny."
    # tool_calls (model-requested dispatch) is empty — these are server-side.
    assert out.tool_calls == []


def test_mcp_tool_result_with_error_flag_marks_server_tool_call_as_error() -> None:
    resp = _mock_response(
        content=[
            {
                "type": "mcp_tool_use",
                "id": "srvtu_err",
                "name": "broken",
                "server_name": "weather",
                "input": {},
            },
            {
                "type": "mcp_tool_result",
                "tool_use_id": "srvtu_err",
                "is_error": True,
                "content": [{"type": "text", "text": "connection refused"}],
            },
        ],
        usage={"input_tokens": 5, "output_tokens": 1},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert len(out.server_tool_calls) == 1
    assert out.server_tool_calls[0].is_error is True
    assert out.server_tool_calls[0].output_text == "connection refused"


def test_mcp_tool_use_without_matching_result_becomes_error_call() -> None:
    """If the API returns a `mcp_tool_use` block but no matching
    `mcp_tool_result` (network drop, partial response), the driver
    still records the attempt — surfaced as an error ServerToolCall so
    the trajectory shows the tool was invoked but didn't return."""
    resp = _mock_response(
        content=[
            {
                "type": "mcp_tool_use",
                "id": "srvtu_orphan",
                "name": "x",
                "server_name": "weather",
                "input": {},
            }
        ],
        usage={"input_tokens": 1, "output_tokens": 1},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert len(out.server_tool_calls) == 1
    assert out.server_tool_calls[0].is_error is True
    assert "missing" in out.server_tool_calls[0].output_text


def test_mcp_result_with_string_content_is_preserved() -> None:
    """Some vendors return `content` as a bare string instead of a list
    of blocks. The driver MUST handle both shapes — string is used as
    output_text directly."""
    resp = _mock_response(
        content=[
            {
                "type": "mcp_tool_use",
                "id": "srvtu_str",
                "name": "x",
                "server_name": "s",
                "input": {},
            },
            {
                "type": "mcp_tool_result",
                "tool_use_id": "srvtu_str",
                "is_error": False,
                "content": "raw string result",
            },
        ],
        usage={"input_tokens": 1, "output_tokens": 1},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.server_tool_calls[0].output_text == "raw string result"


def test_response_without_mcp_blocks_emits_no_server_tool_calls() -> None:
    """Backwards-compat: responses with no MCP blocks behave exactly
    as before — empty `server_tool_calls` list, no synthetic events
    downstream."""
    resp = _mock_response(
        content=[{"type": "text", "text": "hi"}],
        usage={"input_tokens": 1, "output_tokens": 1},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert out.server_tool_calls == []


def test_mcp_tool_use_alongside_regular_tool_use_routes_correctly() -> None:
    """The model can request a runner-dispatched tool AND have an MCP
    tool run inline in the SAME response. The driver MUST keep them
    separate: `tool_calls` for runner dispatch, `server_tool_calls`
    for inline."""
    resp = _mock_response(
        content=[
            {
                "type": "mcp_tool_use",
                "id": "srvtu_inline",
                "name": "lookup",
                "server_name": "db",
                "input": {"q": "x"},
            },
            {
                "type": "mcp_tool_result",
                "tool_use_id": "srvtu_inline",
                "is_error": False,
                "content": [{"type": "text", "text": "row1"}],
            },
            {
                "type": "tool_use",
                "id": "toolu_01",
                "name": "deploy",
                "input": {"target": "prod"},
            },
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="tool_use",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert len(out.tool_calls) == 1
    assert out.tool_calls[0].tool == "deploy"
    assert len(out.server_tool_calls) == 1
    assert out.server_tool_calls[0].tool == "lookup"
    # tool_use stop_reason → not converged (model wants us to dispatch deploy).
    assert out.converged is False
