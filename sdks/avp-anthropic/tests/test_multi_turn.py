"""Driver history-rendering tests (the translator ↔ SDK seam).

These pin a class of bugs single-block translation can't catch: how the
driver renders an ACCUMULATED AVP history into the Anthropic `messages`
array. Specifically — an assistant turn that made a tool call MUST render
as a content-block list with the `tool_use` block, and the matching
`role:tool` entry MUST render as a user `tool_result` with the same
`tool_use_id`. Otherwise the API rejects the next turn with "tool_use_id
... found in tool_result block, but no corresponding tool_use block".

The loop that ACCUMULATES this history is the agent's (see the reference
agent's `run_agent` and its multi-turn seam test in the supervisor
package). Here we pin the driver half: given a well-formed accumulated
history, `messages` comes out well-formed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from avp_anthropic import AnthropicModelDriver


class _CapturingClient:
    """Anthropic client that captures every `messages.create(**kwargs)` call
    and returns a fixed minimal response."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="ok")],
            usage=SimpleNamespace(input_tokens=1, output_tokens=1),
            stop_reason="end_turn",
        )


def test_assistant_tool_use_turn_renders_with_matching_tool_result() -> None:
    """A history with an assistant turn carrying `tool_calls` plus the
    matching `role:tool` entry renders as: an assistant content-block list
    with the `tool_use` block, then a user message whose `tool_result`
    references the same id."""
    client = _CapturingClient()
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)
    history = [
        {"role": "user", "content": "What's in x.txt?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"call_id": "toolu_abc", "tool": "read_file", "input": {"path": "x"}}],
        },
        {"role": "tool", "call_id": "toolu_abc", "output": "hello"},
    ]
    driver.step(history)

    messages = client.calls[0]["messages"]
    asst = next(m for m in messages if m["role"] == "assistant")
    assert isinstance(asst["content"], list), "tool-use turn must render as a content-block list"
    tool_use = [b for b in asst["content"] if b.get("type") == "tool_use"]
    assert tool_use and tool_use[0]["id"] == "toolu_abc"
    assert tool_use[0]["name"] == "read_file"

    tool_results = [
        b
        for m in messages
        if m["role"] == "user" and isinstance(m.get("content"), list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]
    assert tool_results and tool_results[0]["tool_use_id"] == "toolu_abc"
    assert tool_results[0]["content"] == "hello"


def test_assistant_text_and_tool_use_render_text_first() -> None:
    """An assistant turn with both text and a tool call renders both blocks,
    text before tool_use."""
    client = _CapturingClient()
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)
    history = [
        {"role": "user", "content": "Read y.txt"},
        {
            "role": "assistant",
            "content": "Let me read it.",
            "tool_calls": [{"call_id": "toolu_xyz", "tool": "read_file", "input": {"path": "y"}}],
        },
        {"role": "tool", "call_id": "toolu_xyz", "output": "yo"},
    ]
    driver.step(history)

    asst = next(m for m in client.calls[0]["messages"] if m["role"] == "assistant")
    types_in_order = [b["type"] for b in asst["content"]]
    assert types_in_order == ["text", "tool_use"]
    assert asst["content"][0]["text"] == "Let me read it."


def test_pure_text_assistant_turn_renders_as_string() -> None:
    """An assistant turn with text and no tool_calls renders as a plain
    string (the simpler form the API also accepts)."""
    client = _CapturingClient()
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)
    history = [
        {"role": "user", "content": "x"},
        {"role": "assistant", "content": "thinking...", "tool_calls": []},
        {"role": "user", "content": "continue"},
    ]
    driver.step(history)

    asst = next(m for m in client.calls[0]["messages"] if m["role"] == "assistant")
    assert asst["content"] == "thinking..."
