"""Anthropic hosted-tool blocks (web_search, code_execution, etc.)
surface as ServerToolCalls with dispatch_target=local and
avp.tool.subtype set.

These are tools the API runs server-side BUT aren't MCP — they're
provider-hosted. Same per-call wire fidelity as MCP via the
ServerToolCall machinery; the discriminator on the wire is the
dispatch_target + subtype combination.
"""

from __future__ import annotations

from types import SimpleNamespace

from avp.content import ServerToolResultBlock, ServerToolUseBlock
from avp_anthropic import AnthropicModelDriver, ModelResponse, model_response_to_content
from avp_anthropic.translate import ServerToolCall


def _mock_response(*, content: list[dict], usage: dict, stop_reason: str) -> SimpleNamespace:
    blocks = [SimpleNamespace(**b) for b in content]
    return SimpleNamespace(content=blocks, usage=SimpleNamespace(**usage), stop_reason=stop_reason)


class _MockClient:
    def __init__(self, response):
        self._response = response
        self.calls: list[dict] = []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self._response


# ── Driver: hosted block parsing ──────────────────────────────────────────


def test_web_search_blocks_become_server_tool_call_with_subtype() -> None:
    resp = _mock_response(
        content=[
            {
                "type": "web_search_tool_use",
                "id": "ws_01",
                "name": "web_search",
                "input": {"query": "AVP protocol"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "ws_01",
                "content": [
                    {"type": "web_search_result", "url": "https://x.com", "title": "X"},
                    {"type": "web_search_result", "url": "https://y.com", "title": "Y"},
                ],
            },
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])

    assert len(out.server_tool_calls) == 1
    stc = out.server_tool_calls[0]
    assert stc.call_id == "ws_01"
    assert stc.tool == "web_search"
    assert stc.dispatch_target == "local"
    assert stc.server_id is None  # not an MCP server
    assert stc.input == {"query": "AVP protocol"}
    # Render extracted titles (or first available text field) per block.
    assert "X" in stc.output_text
    assert "Y" in stc.output_text


def test_code_execution_blocks_render_stdout_and_flag_nonzero_exit() -> None:
    resp = _mock_response(
        content=[
            {
                "type": "code_execution_tool_use",
                "id": "ce_01",
                "name": "code_execution",
                "input": {"code": "print('hi')"},
            },
            {
                "type": "code_execution_tool_result",
                "tool_use_id": "ce_01",
                "content": {"stdout": "hi\n", "stderr": "", "return_code": 0},
            },
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    assert len(out.server_tool_calls) == 1
    stc = out.server_tool_calls[0]
    assert "hi" in stc.output_text
    assert stc.is_error is False


def test_code_execution_nonzero_exit_marks_error() -> None:
    resp = _mock_response(
        content=[
            {
                "type": "code_execution_tool_use",
                "id": "ce_err",
                "name": "code_execution",
                "input": {"code": "raise"},
            },
            {
                "type": "code_execution_tool_result",
                "tool_use_id": "ce_err",
                "content": {"stdout": "", "stderr": "boom", "return_code": 1},
            },
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    stc = out.server_tool_calls[0]
    assert stc.is_error is True
    assert "boom" in stc.output_text
    assert "exit: 1" in stc.output_text


def test_mcp_and_hosted_tools_in_one_response_both_recorded() -> None:
    """A single response can contain both MCP and hosted tool calls.
    They MUST land on the same `server_tool_calls` list with the
    correct `dispatch_target` discriminating them."""
    resp = _mock_response(
        content=[
            {
                "type": "mcp_tool_use",
                "id": "mcp_01",
                "name": "lookup",
                "server_name": "db",
                "input": {},
            },
            {
                "type": "mcp_tool_result",
                "tool_use_id": "mcp_01",
                "is_error": False,
                "content": [{"type": "text", "text": "row"}],
            },
            {
                "type": "web_search_tool_use",
                "id": "ws_02",
                "name": "web_search",
                "input": {"query": "x"},
            },
            {
                "type": "web_search_tool_result",
                "tool_use_id": "ws_02",
                "content": [{"type": "web_search_result", "title": "result"}],
            },
        ],
        usage={"input_tokens": 5, "output_tokens": 5},
        stop_reason="end_turn",
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=_MockClient(resp))
    out = driver.step([{"role": "user", "content": "x"}])
    by_dispatch = {stc.dispatch_target for stc in out.server_tool_calls}
    assert by_dispatch == {"mcp_server", "local"}
    hosted = next(s for s in out.server_tool_calls if s.dispatch_target == "local")
    assert hosted.tool == "web_search"


# ── Content: hosted/server tool calls surface as content blocks ───────────


def test_server_tool_call_surfaces_as_content_blocks() -> None:
    """In the v0.1 wire, a server-side tool call (the API ran it inline)
    surfaces in `assistant_message.avp.content` as a `ServerToolUseBlock`
    paired with a `ServerToolResultBlock` — NOT as a separate dispatched
    `tool_invoked` event (the agent never dispatched it). `model_response_to_content`
    is the shared converter both the reference agent and the traced client use."""
    mr = ModelResponse(
        tokens_input=1,
        tokens_output=1,
        cost_usd=0.0001,
        duration_ms=1,
        text="ok",
        converged=True,
        server_tool_calls=[
            ServerToolCall(
                call_id="ws_X",
                tool="web_search",
                input={"query": "q"},
                output_text="results",
                dispatch_target="local",
            )
        ],
    )
    blocks = model_response_to_content(mr)
    use = next(b for b in blocks if isinstance(b, ServerToolUseBlock))
    assert use.id == "ws_X"
    assert use.name == "web_search"
    assert use.input == {"query": "q"}
    result = next(b for b in blocks if isinstance(b, ServerToolResultBlock))
    assert result.tool_use_id == "ws_X"
    assert result.content == "results"
    assert result.is_error is None
