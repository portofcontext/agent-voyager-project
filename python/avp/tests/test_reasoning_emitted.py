"""Reasoning / thinking blocks surface as `reasoning_emitted` events.

Distinct from `text_emitted` so consumers can collapse / redact
chain-of-thought from displays without losing it from the audit log.
The wire carries `avp.reasoning.text`, optional `avp.reasoning.signature`,
and `avp.reasoning.redacted` for encrypted-only blocks.
"""

from __future__ import annotations

from avp import Commission
from avp.agent.agent import AVPAgent
from avp.agent.drivers import ModelResponse, ReasoningBlock
from avp.agent.mock import ScriptedModel, ScriptedSupervisor, ScriptedTools
from avp.types import (
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    ReasoningEmittedEvent,
    TextEmittedEvent,
)


def _by_type(traj, type_):
    return [e for e in traj if isinstance(e, type_)]


def _runner(model: ScriptedModel) -> AVPAgent:
    cfg = Commission(schema_version="0.1", run_id="reasoning", model="test/mock")
    return AVPAgent(
        config=cfg,
        model=model,
        tools=ScriptedTools(),
        supervisor=ScriptedSupervisor(),
    )


def test_plain_thinking_block_emits_reasoning_event() -> None:
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=10,
                    tokens_output=20,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="here is my answer",
                    reasoning_blocks=[
                        ReasoningBlock(text="let me think step by step...", signature="sig-abc")
                    ],
                    converged=True,
                )
            ]
        )
    )
    agent.run()

    reasoning = _by_type(agent.trajectory, ReasoningEmittedEvent)
    assert len(reasoning) == 1
    r = reasoning[0]
    assert r.data.avp_reasoning_text == "let me think step by step..."
    assert r.data.avp_reasoning_signature == "sig-abc"
    # Plain (non-redacted) blocks omit the redacted flag rather than
    # shipping a False — keeps the wire lean.
    wire = r.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert "avp.reasoning.redacted" not in wire["data"]


def test_redacted_thinking_records_occurrence_with_no_text() -> None:
    """When the provider returns thinking encrypted-only, we still emit
    the event — auditors need to count thinking turns even when the
    plaintext isn't available."""
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    reasoning_blocks=[ReasoningBlock(text="", signature="enc-blob", redacted=True)],
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    r = _by_type(agent.trajectory, ReasoningEmittedEvent)[0]
    assert r.data.avp_reasoning_text == ""
    assert r.data.avp_reasoning_redacted is True
    assert r.data.avp_reasoning_signature == "enc-blob"


def test_reasoning_emitted_parented_to_turn_span() -> None:
    """Reasoning belongs to a turn — parent_span_id is the turn span,
    not the agent root."""
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    reasoning_blocks=[ReasoningBlock(text="thought")],
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    turn_started = _by_type(agent.trajectory, ModelTurnStartedEvent)[0]
    r = _by_type(agent.trajectory, ReasoningEmittedEvent)[0]
    assert r.data.parent_span_id == turn_started.data.span_id


def test_reasoning_emitted_before_text_emitted() -> None:
    """Wire ordering: thought before speech. The model thinks first,
    then speaks — the trajectory must reconstruct that ordering even
    when the agent emits both within one turn."""
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="answer",
                    reasoning_blocks=[ReasoningBlock(text="reasoning")],
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    types = [type(e).__name__ for e in agent.trajectory]
    r_idx = types.index("ReasoningEmittedEvent")
    t_idx = types.index("TextEmittedEvent")
    assert r_idx < t_idx
    # And both come AFTER model_turn_ended.
    end_idx = types.index("ModelTurnEndedEvent")
    assert end_idx < r_idx


def test_no_reasoning_blocks_emits_no_reasoning_events() -> None:
    """Backwards-compat: a turn without thinking emits no reasoning_emitted."""
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    assert not _by_type(agent.trajectory, ReasoningEmittedEvent)
    assert _by_type(agent.trajectory, ModelTurnEndedEvent)
    assert _by_type(agent.trajectory, TextEmittedEvent)


def test_multiple_reasoning_blocks_each_emit_their_own_event() -> None:
    """Some providers return multiple thinking blocks per turn (the
    model paused and resumed). Each becomes its own event so the
    trajectory preserves the structure."""
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    reasoning_blocks=[
                        ReasoningBlock(text="first thought"),
                        ReasoningBlock(text="second thought"),
                    ],
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    reasoning = _by_type(agent.trajectory, ReasoningEmittedEvent)
    assert [r.data.avp_reasoning_text for r in reasoning] == [
        "first thought",
        "second thought",
    ]


def test_reasoning_event_serializes_under_dotted_aliases() -> None:
    agent = _runner(
        ScriptedModel(
            [
                ModelResponse(
                    tokens_input=1,
                    tokens_output=1,
                    cost_usd=0.0001,
                    duration_ms=1,
                    text="ok",
                    reasoning_blocks=[ReasoningBlock(text="t", signature="s", redacted=True)],
                    converged=True,
                )
            ]
        )
    )
    agent.run()
    r = _by_type(agent.trajectory, ReasoningEmittedEvent)[0]
    wire = r.model_dump(mode="json", by_alias=True, exclude_none=True)
    assert wire["type"] == "avp.reasoning_emitted"
    assert wire["data"]["avp.reasoning.text"] == "t"
    assert wire["data"]["avp.reasoning.signature"] == "s"
    assert wire["data"]["avp.reasoning.redacted"] is True
