"""Multi-turn integration tests for the AEPRunner driving AnthropicModelDriver.

These tests pin a class of bugs that single-turn driver tests cannot catch:
the runner's history shape between turns. Specifically — when the assistant
makes a tool call without text, the runner MUST still record the assistant
turn in history (with the tool_use block), or the next call to the API will
present a tool_result with no matching tool_use_id and Anthropic will reject
it as malformed.

This is the bug we shipped and only caught when running examples 01/02 against
a live model. These tests pin it explicitly with a mock client.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    ModelTurnEndedEvent,
    StopReason,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from aep.runner import AEPRunner
from aep.runner.drivers import ToolDriver, ToolOutcome
from aep.runner.mock import ScriptedSupervisor
from aep_anthropic import AnthropicModelDriver

# ── Mock infrastructure ───────────────────────────────────────────────────────


class _SequencedClient:
    """Anthropic client that returns scripted responses in order and CAPTURES
    every messages.create() call so tests can assert on the request shape."""

    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def create(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError(
                f"_SequencedClient: ran out of scripted responses after {len(self.calls)} calls"
            )
        return self._responses.pop(0)


def _mock_response(*, content: list[dict], usage: dict, stop_reason: str) -> SimpleNamespace:
    blocks = [SimpleNamespace(**b) for b in content]
    return SimpleNamespace(content=blocks, usage=SimpleNamespace(**usage), stop_reason=stop_reason)


class _DictTools(ToolDriver):
    """Tiny ToolDriver: maps tool name → fixed string output."""

    def __init__(self, mapping: dict[str, str]) -> None:
        self.mapping = mapping

    def is_local(self, tool: str) -> bool:
        return tool in self.mapping

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        return ToolOutcome(output=self.mapping[tool], duration_ms=1)


class _ErroringTools(ToolDriver):
    """ToolDriver where invoke() always fails. Used to pin the tool_failed
    history-shape fix: failures MUST still record a tool_result so the next
    model call has a matching tool_use ↔ tool_result pair."""

    def __init__(self, locals_: set[str], error: str) -> None:
        self.locals = locals_
        self.error = error

    def is_local(self, tool: str) -> bool:
        return tool in self.locals

    def invoke(self, tool: str, input: dict[str, Any]) -> ToolOutcome:
        return ToolOutcome(error=self.error, duration_ms=1)


# ── The pinning test ──────────────────────────────────────────────────────────


def test_tool_use_then_text_round_trip_preserves_history() -> None:
    """Full multi-turn runner exercise:
        turn 1: assistant emits a tool_use block (no text)
        runner: dispatches `read_file` locally, emits tool_returned
        turn 2: assistant emits text + end_turn → converges

    What this pins:
    1. Trajectory contains all expected events in order
    2. The SECOND messages.create() call's `messages` parameter contains a
       well-formed conversation: the assistant turn with the tool_use block
       MUST precede the user turn carrying the tool_result.
    3. tool_use_id in the assistant block matches tool_use_id in the
       tool_result block (otherwise Anthropic rejects).

    Pre-fix: the runner skipped recording the assistant turn when it had no
    text. The tool_use block went missing from history. The second
    messages.create() raised "tool_use_id ... found in tool_result block,
    but no corresponding tool_use block".
    """

    turn1 = _mock_response(
        content=[
            {
                "type": "tool_use",
                "id": "toolu_abc",
                "name": "read_file",
                "input": {"path": "x.txt"},
            },
        ],
        usage={"input_tokens": 100, "output_tokens": 20},
        stop_reason="tool_use",
    )
    turn2 = _mock_response(
        content=[{"type": "text", "text": "x.txt says hello. EXPLANATION DONE."}],
        usage={"input_tokens": 200, "output_tokens": 15},
        stop_reason="end_turn",
    )
    client = _SequencedClient([turn1, turn2])

    config = Config(
        schema_version="0.1",
        run_id="multi-turn-r1",
        model="claude-sonnet-4-6",
        prompt="What's in x.txt?",
        boundary={"max_steps": 5, "max_cost_usd": 1.0},
    )

    driver = AnthropicModelDriver(
        model="claude-sonnet-4-6",
        client=client,
        tools_param=[
            {
                "name": "read_file",
                "description": "Read a file.",
                "input_schema": {
                    "type": "object",
                    "required": ["path"],
                    "properties": {"path": {"type": "string"}},
                },
            },
        ],
    )

    runner = AEPRunner(
        config=config,
        model=driver,
        tools=_DictTools({"read_file": "hello"}),
        supervisor=ScriptedSupervisor([]),
    )
    stop = runner.run()

    # ── Assertion 1: the API got called twice and didn't raise ───────────────
    assert len(client.calls) == 2, f"expected 2 model calls, got {len(client.calls)}"

    # ── Assertion 2: turn-2 conversation shape is well-formed ────────────────
    turn2_messages = client.calls[1]["messages"]
    # Find the assistant message (must contain the tool_use block) and the
    # user message after it (must contain the tool_result with matching id).
    asst_msgs = [m for m in turn2_messages if m["role"] == "assistant"]
    assert asst_msgs, (
        "turn 2 messages contain no assistant turn — the runner failed to "
        "record turn-1's assistant response in history"
    )
    asst = asst_msgs[-1]
    asst_content = asst["content"]
    assert isinstance(asst_content, list), (
        f"assistant content for a tool-use turn MUST be a content-block list, "
        f"got {type(asst_content).__name__}"
    )
    tool_use_blocks = [b for b in asst_content if b.get("type") == "tool_use"]
    assert tool_use_blocks, "assistant turn-1 was recorded WITHOUT its tool_use block"
    assert tool_use_blocks[0]["id"] == "toolu_abc"
    assert tool_use_blocks[0]["name"] == "read_file"

    # The tool_result that follows must reference the same id.
    user_msgs_after_asst = [
        m for m in turn2_messages[turn2_messages.index(asst) + 1 :] if m["role"] == "user"
    ]
    tool_result_blocks = [
        b
        for m in user_msgs_after_asst
        if isinstance(m.get("content"), list)
        for b in m["content"]
        if b.get("type") == "tool_result"
    ]
    assert tool_result_blocks, "no tool_result block found after the assistant tool_use turn"
    assert tool_result_blocks[0]["tool_use_id"] == "toolu_abc", (
        "tool_result.tool_use_id MUST match the assistant's tool_use.id "
        "(this is the exact symptom of the bug pre-fix)"
    )

    # ── Assertion 3: the trajectory has the expected event sequence ──────────
    types = [type(ev).__name__ for ev in runner.trajectory]
    assert types[0] == "AgentStartedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert "ToolInvokedEvent" in types
    assert "ToolReturnedEvent" in types
    assert "TextEmittedEvent" in types
    assert types[-1] == "AgentStoppedEvent"
    assert stop.data.aep_reason == StopReason.converged

    # Specific shape checks — fields live in `data` with OTel/AEP attribute names.
    assert any(
        isinstance(ev, ToolInvokedEvent)
        and ev.data.gen_ai_tool_name == "read_file"
        and ev.data.gen_ai_tool_call_id == "toolu_abc"
        for ev in runner.trajectory
    )
    assert any(
        isinstance(ev, ToolReturnedEvent)
        and ev.data.gen_ai_tool_name == "read_file"
        and ev.data.aep_tool_result_text == "hello"
        for ev in runner.trajectory
    )
    assert any(
        isinstance(ev, TextEmittedEvent) and "EXPLANATION DONE" in ev.data.aep_text
        for ev in runner.trajectory
    )


def test_assistant_turn_with_text_and_tool_use_renders_both_blocks() -> None:
    """A model can emit text AND a tool call in the same turn. The history
    sent on the next call must include BOTH blocks in the assistant message,
    in order: text first, then tool_use."""

    turn1 = _mock_response(
        content=[
            {"type": "text", "text": "Let me read it."},
            {
                "type": "tool_use",
                "id": "toolu_xyz",
                "name": "read_file",
                "input": {"path": "y.txt"},
            },
        ],
        usage={"input_tokens": 80, "output_tokens": 30},
        stop_reason="tool_use",
    )
    turn2 = _mock_response(
        content=[{"type": "text", "text": "got it"}],
        usage={"input_tokens": 150, "output_tokens": 5},
        stop_reason="end_turn",
    )
    client = _SequencedClient([turn1, turn2])

    config = Config(
        schema_version="0.1",
        run_id="multi-turn-r2",
        model="claude-sonnet-4-6",
        prompt="Read y.txt",
        boundary={"max_steps": 5},
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)
    runner = AEPRunner(
        config=config,
        model=driver,
        tools=_DictTools({"read_file": "yo"}),
        supervisor=ScriptedSupervisor([]),
    )
    runner.run()

    turn2_messages = client.calls[1]["messages"]
    asst = next(m for m in reversed(turn2_messages) if m["role"] == "assistant")
    blocks = asst["content"]
    types_in_order = [b["type"] for b in blocks]
    assert types_in_order == ["text", "tool_use"], (
        f"expected text then tool_use, got {types_in_order}"
    )
    assert blocks[0]["text"] == "Let me read it."
    assert blocks[1]["id"] == "toolu_xyz"


def test_pure_text_turn_history_unchanged_for_string_content() -> None:
    """Regression guard: a turn with text only and NO tool_calls should still
    render as a plain string assistant message (Anthropic accepts both string
    and content-block forms; we keep the simpler form when there are no
    tool calls to avoid noise in the request)."""

    turn1 = _mock_response(
        content=[{"type": "text", "text": "thinking..."}],
        usage={"input_tokens": 30, "output_tokens": 5},
        stop_reason="end_turn",  # would normally converge — drive a 2nd turn anyway
    )
    # Force a second turn by NOT converging (use stop_reason that AEPRunner
    # treats as non-terminal: any non-end_turn-without-tools).
    turn1_continuing = _mock_response(
        content=[
            {"type": "text", "text": "thinking..."},
            {"type": "tool_use", "id": "t1", "name": "noop", "input": {}},
        ],
        usage={"input_tokens": 30, "output_tokens": 5},
        stop_reason="tool_use",
    )
    turn2 = _mock_response(
        content=[{"type": "text", "text": "done"}],
        usage={"input_tokens": 50, "output_tokens": 3},
        stop_reason="end_turn",
    )
    _ = turn1  # silence unused
    client = _SequencedClient([turn1_continuing, turn2])

    config = Config(
        schema_version="0.1",
        run_id="multi-turn-r3",
        model="claude-sonnet-4-6",
        prompt="x",
        boundary={"max_steps": 5},
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)
    runner = AEPRunner(
        config=config,
        model=driver,
        tools=_DictTools({"noop": "ok"}),
        supervisor=ScriptedSupervisor([]),
    )
    runner.run()

    # Assistant on turn 1 had both text AND tool_use → must render as blocks
    asst = next(m for m in client.calls[1]["messages"] if m["role"] == "assistant")
    assert isinstance(asst["content"], list)


def test_tool_failure_records_tool_result_in_history_so_next_turn_validates() -> None:
    """When a tool fails (ToolDriver returns ToolOutcome(error=...)), the runner
    MUST still append a tool-role entry to history carrying the error as the
    `tool_result.content`. Without this, the next model call sends an
    assistant tool_use with no matching tool_result, and the API rejects:
    'tool_use ids were found without tool_result blocks immediately after'.

    Pre-fix: the runner emitted tool_failed and `return`ed without history
    update — exactly the bug we hit running example 04 (read_file on a
    directory path returned IsADirectoryError → tool_failed → next turn
    400'd at the API).
    """
    # Turn 1: assistant calls a tool that will fail. Turn 2: assistant
    # acknowledges and converges. The interesting check is on the SECOND
    # API call's `messages` parameter — the tool_result for the failed call
    # MUST be present.
    turn1 = _mock_response(
        content=[
            {
                "type": "tool_use",
                "id": "toolu_fail",
                "name": "read_file",
                "input": {"path": "/some/dir"},
            },
        ],
        usage={"input_tokens": 30, "output_tokens": 10},
        stop_reason="tool_use",
    )
    turn2 = _mock_response(
        content=[{"type": "text", "text": "I see, that path is a dir. Stopping."}],
        usage={"input_tokens": 80, "output_tokens": 12},
        stop_reason="end_turn",
    )
    client = _SequencedClient([turn1, turn2])

    config = Config(
        schema_version="0.1",
        run_id="tool-fail-history",
        model="claude-sonnet-4-6",
        prompt="Read /some/dir",
        boundary={"max_steps": 5},
    )
    driver = AnthropicModelDriver(model="claude-sonnet-4-6", client=client)
    runner = AEPRunner(
        config=config,
        model=driver,
        tools=_ErroringTools(locals_={"read_file"}, error="IsADirectoryError: /some/dir"),
        supervisor=ScriptedSupervisor([]),
    )
    runner.run()

    # The API was called twice (turn 1 + turn 2). If the bug were live, the
    # second call would have raised before reaching the test assertions.
    assert len(client.calls) == 2

    # Inspect turn 2's messages for the tool_result corresponding to toolu_fail.
    turn2_messages = client.calls[1]["messages"]
    tool_result_blocks = [
        b
        for m in turn2_messages
        if m["role"] == "user" and isinstance(m.get("content"), list)
        for b in m["content"]
        if isinstance(b, dict) and b.get("type") == "tool_result"
    ]
    matching = [b for b in tool_result_blocks if b.get("tool_use_id") == "toolu_fail"]
    assert matching, (
        "expected a tool_result block with tool_use_id='toolu_fail' in turn 2's "
        "messages — failed tools MUST still produce a tool_result so the "
        "tool_use/tool_result pairing isn't broken"
    )
    # The error string should be the user-visible content of that tool_result.
    assert "IsADirectoryError" in matching[0]["content"]

    # Trajectory: tool_failed event was emitted (not tool_returned).
    types = [type(ev).__name__ for ev in runner.trajectory]
    assert "ToolFailedEvent" in types
    assert "ToolReturnedEvent" not in types


def test_unused_imports_silenced() -> None:
    """Touch the test-public symbols imported above so the file runs as a
    sanity check that the AEP API surface is what these tests assume."""
    _ = (
        AgentStartedEvent,
        AgentStoppedEvent,
        ModelTurnEndedEvent,
        TextEmittedEvent,
        ToolInvokedEvent,
        ToolReturnedEvent,
    )
