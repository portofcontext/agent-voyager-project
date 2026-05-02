"""Smoke + emission tests for ClaudeAgentTranslator.

These tests exercise the AEP-emission half of the translator (what AEP events
land for which lifecycle calls), not the SDK-integration half (which is still
TODO until claude_agent_sdk is wired up).
"""

from __future__ import annotations

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    StopReason,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from aep_claude_agent import ClaudeAgentTranslator


def _new_translator() -> tuple[ClaudeAgentTranslator, list]:
    cfg = Config(
        schema_version="0.1",
        run_id="t1",
        model="claude-sonnet-4-6",
        prompt="hello",
    )
    out: list = []
    t = ClaudeAgentTranslator(cfg, on_event=out.append)
    return t, out


def test_agent_started_emitted_with_config_metadata() -> None:
    t, out = _new_translator()
    t._emit_agent_started()
    assert len(out) == 1
    ev = out[0]
    assert isinstance(ev, AgentStartedEvent)
    assert ev.run_id == "t1"
    assert ev.model == "claude-sonnet-4-6"
    assert ev.prompt == "hello"


def test_turn_lifecycle_emits_started_ended_cost() -> None:
    t, out = _new_translator()
    t._on_turn_start()
    t._on_turn_end(tokens_input=100, tokens_output=25, cost_usd=0.001, duration_ms=900)

    assert isinstance(out[0], ModelTurnStartedEvent)
    assert out[0].step == 1
    assert isinstance(out[1], ModelTurnEndedEvent)
    assert out[1].tokens_input == 100
    assert isinstance(out[2], CostRecordedEvent)
    assert out[2].state.total_turns == 1
    assert out[2].state.total_tokens == 125
    assert out[2].state.total_cost_usd == 0.001


def test_tool_lifecycle_emits_invoked_returned() -> None:
    t, out = _new_translator()
    t._on_turn_start()
    t._on_tool_invoked(call_id="c1", tool="bash", input={"command": "ls"})
    t._on_tool_returned(call_id="c1", tool="bash", output="file1\nfile2", duration_ms=10)

    invoked = out[1]
    returned = out[2]
    assert isinstance(invoked, ToolInvokedEvent)
    assert invoked.tool == "bash"
    assert invoked.input == {"command": "ls"}
    assert isinstance(returned, ToolReturnedEvent)
    assert returned.output == "file1\nfile2"


def test_run_emits_agent_stopped_with_state() -> None:
    """run() will hit NotImplementedError in _invoke_sdk; the translator should
    catch that as an unrecoverable error and emit agent_stopped reason='error'."""
    t, out = _new_translator()
    stop = t.run()
    assert isinstance(stop, AgentStoppedEvent)
    assert stop.reason == StopReason.error
    # First event should be agent_started; last should be agent_stopped.
    assert isinstance(out[0], AgentStartedEvent)
    assert out[-1] is stop


def test_run_state_accounting_matches_runner_pattern() -> None:
    t, _ = _new_translator()
    t._on_turn_start()
    t._on_turn_end(tokens_input=10, tokens_output=5, cost_usd=0.0001, duration_ms=10)
    t._on_turn_start()
    t._on_turn_end(tokens_input=20, tokens_output=8, cost_usd=0.0002, duration_ms=20)

    snap = t._snapshot()
    assert snap.total_turns == 2
    assert snap.total_tokens == (10 + 5) + (20 + 8)
    assert abs(snap.total_cost_usd - 0.0003) < 1e-9
