"""Handoff → subagent mapping edge cases.

The Agents SDK's `on_handoff` fires once per control transfer. We treat
each handoff as a subagent invocation: emit `subagent_invoked` on the
transfer, then `subagent_returned` when the target's `on_agent_end`
fires. Behaviors covered here:

  - Multiple sequential handoffs each get their own invocation_id and
    frame span.
  - The active frame's span_id parents the subagent's own turns.
  - on_agent_end for the *root* agent does NOT emit subagent_returned.
  - on_agent_end for a target with no open handoff is a no-op (defensive).
  - The invocation_id is unique across siblings.
"""

from __future__ import annotations

import asyncio
from typing import Any

from avp_openai_agent import OpenAIAgentTranslator, descriptor

from avp import (
    Commission,
    ModelTurnStartedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
)


class _FakeAgent:
    def __init__(self, name: str) -> None:
        self.name = name
        self.tools: list[Any] = []
        self.model = "gpt-5-nano"


def _new() -> tuple[OpenAIAgentTranslator, list[Any]]:
    captured: list[Any] = []
    c = Commission.model_validate(
        {
            "schema_version": "0.1",
            "run_id": "subagent-test",
            "model": "gpt-5-nano",
            "prompt": "hi",
            "subagents": [
                {"id": "researcher", "ref": "x://researcher"},
                {"id": "writer", "ref": "x://writer"},
            ],
        }
    )
    t = OpenAIAgentTranslator(c, on_event=captured.append, descriptor=descriptor())
    t._root_agent_name = "root"
    return t, captured


def test_sequential_handoffs_each_get_unique_invocation_id() -> None:
    t, captured = _new()
    root = _FakeAgent("root")
    researcher = _FakeAgent("researcher")
    writer = _FakeAgent("writer")

    asyncio.run(t.on_agent_start(None, root))
    asyncio.run(t.on_handoff(None, root, researcher))
    asyncio.run(t.on_agent_end(None, researcher, "research notes"))
    asyncio.run(t.on_handoff(None, researcher, writer))
    asyncio.run(t.on_agent_end(None, writer, "final report"))

    invoked = [ev for ev in captured if isinstance(ev, SubagentInvokedEvent)]
    returned = [ev for ev in captured if isinstance(ev, SubagentReturnedEvent)]
    assert len(invoked) == 2
    assert len(returned) == 2
    ids = {ev.data.avp_subagent_invocation_id for ev in invoked}
    assert len(ids) == 2  # unique
    # Pair-matching: invoked[i].invocation_id == returned[i].invocation_id
    for i, ev in enumerate(invoked):
        assert ev.data.avp_subagent_invocation_id == returned[i].data.avp_subagent_invocation_id


def test_turns_during_handoff_parent_under_subagent_frame() -> None:
    """When a handoff is mid-flight and on_llm_start fires, the turn's
    parent_span_id is the subagent frame's span — NOT the root agent
    span. This keeps the trajectory tree consistent: target's work
    nests inside its invocation."""
    t, captured = _new()
    root = _FakeAgent("root")
    target = _FakeAgent("researcher")

    asyncio.run(t.on_agent_start(None, root))
    asyncio.run(t.on_handoff(None, root, target))
    # Capture the subagent_invoked to recover its frame span_id.
    invoked = next(ev for ev in captured if isinstance(ev, SubagentInvokedEvent))
    frame_span_id = invoked.data.span_id

    asyncio.run(t.on_agent_start(None, target))
    asyncio.run(t.on_llm_start(None, target, None, []))

    turn = next(ev for ev in captured if isinstance(ev, ModelTurnStartedEvent))
    assert turn.data.parent_span_id == frame_span_id


def test_on_agent_end_without_open_handoff_is_no_op() -> None:
    """If on_agent_end fires for an agent that wasn't handed off to
    (the root, or a target whose return we already emitted), the
    translator MUST NOT emit a stray subagent_returned."""
    t, captured = _new()
    root = _FakeAgent("root")
    asyncio.run(t.on_agent_start(None, root))
    asyncio.run(t.on_agent_end(None, root, "done"))
    returned = [ev for ev in captured if isinstance(ev, SubagentReturnedEvent)]
    assert returned == []


def test_subagent_returned_carries_result_text_and_invocation_id() -> None:
    t, captured = _new()
    root = _FakeAgent("root")
    target = _FakeAgent("researcher")
    asyncio.run(t.on_agent_start(None, root))
    asyncio.run(t.on_handoff(None, root, target))
    asyncio.run(t.on_agent_end(None, target, "the answer is 42"))

    invoked = next(ev for ev in captured if isinstance(ev, SubagentInvokedEvent))
    returned = next(ev for ev in captured if isinstance(ev, SubagentReturnedEvent))
    assert returned.data.gen_ai_agent_name == "researcher"
    assert returned.data.avp_subagent_invocation_id == invoked.data.avp_subagent_invocation_id
    assert returned.data.avp_subagent_result_text == "the answer is 42"
    # avp.subagent.usage is zero-rolled-up: the Agents SDK doesn't surface
    # per-target token breakdowns to RunHooks, so per-subagent attribution
    # isn't recoverable (the parent's RunStateSnapshot still has the spend).
    assert returned.data.avp_subagent_usage.total_tokens == 0


def test_structured_handoff_output_serialized_alongside_text() -> None:
    """When the target's output is non-string (e.g. dict from a typed
    Agent output), the translator JSON-encodes it for `avp.subagent.result.text`
    and ALSO surfaces the raw structure under `avp.subagent.result.structured`."""
    t, captured = _new()
    root = _FakeAgent("root")
    target = _FakeAgent("researcher")
    asyncio.run(t.on_agent_start(None, root))
    asyncio.run(t.on_handoff(None, root, target))
    structured = {"summary": "ok", "score": 0.9}
    asyncio.run(t.on_agent_end(None, target, structured))

    returned = next(ev for ev in captured if isinstance(ev, SubagentReturnedEvent))
    assert returned.data.avp_subagent_result_structured == structured
    # text mirror is JSON-encoded.
    import json

    assert json.loads(returned.data.avp_subagent_result_text) == structured
