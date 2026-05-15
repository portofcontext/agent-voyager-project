"""Tests for AVPTracer — the drop-in alternative to AVPAgent.

These tests pin the contract that matters: events emitted by AVPTracer MUST
be byte-equivalent to events AVPAgent produces for the same Commission and
the same set of (turn, tool, subagent) operations. Consumers downstream
of the wire can't tell whether the trajectory came from an agent or a
traced loop. If that ever drifts, this file fails first.

Coverage:
  - Lifecycle: agent_started → model_turn → tool → text_emitted →
    cost_recorded → agent_stopped
  - Subagent context manager: invoked / returned pair, frame span pairing,
    nested events parent under the frame, usage rolls up to parent
  - Subagent failure: scope.fail() → subagent_failed (not returned)
  - tool() with .fail() emits tool_failed
  - tool() with .reject() emits tool_returned with rejected=true
"""

from __future__ import annotations

from avp import (
    AgentStartedEvent,
    AgentStoppedEvent,
    AVPTracer,
    Commission,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    SubagentFailedEvent,
    SubagentInvokedEvent,
    SubagentRef,
    SubagentReturnedEvent,
    ToolFailedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)


def _by_type(events: list, type_: type) -> list:
    return [e for e in events if isinstance(e, type_)]


def _types(events: list) -> list[str]:
    return [type(e).__name__ for e in events]


def _basic_config(**overrides) -> Commission:
    base: dict = {
        "schema_version": "0.1",
        "run_id": "tracer-test",
        "model": "claude-sonnet-4-6",
        "prompt": "do the thing",
    }
    base.update(overrides)
    return Commission(**base)


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_minimal_run_emits_full_lifecycle() -> None:
    """A trivial use of the tracer — open, one turn, converge, close —
    MUST emit the same skeleton AVPAgent does for an empty-script run."""
    out: list = []
    cfg = _basic_config()
    with AVPTracer(cfg, on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=50, tokens_output=10, cost_usd=0.001, text="hi")
        tracer.converged()

    types = _types(out)
    assert types == [
        "AgentStartedEvent",
        "ModelTurnStartedEvent",
        "ModelTurnEndedEvent",
        "TextEmittedEvent",
        "CostRecordedEvent",
        "AgentStoppedEvent",
    ]
    started = _by_type(out, AgentStartedEvent)[0]
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert started.subject == "tracer-test"
    assert stopped.data.avp_reason == "converged"


def test_emitted_events_match_avp_envelope_shape() -> None:
    """CloudEvents 1.0 envelope invariants. Same as AVPAgent."""
    out: list = []
    with AVPTracer(_basic_config(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=1, tokens_output=1, cost_usd=0.0, text="ok")
        tracer.converged()
    for ev in out:
        wire = ev.model_dump(mode="json", by_alias=True, exclude_none=True)
        assert wire["specversion"] == "1.0"
        assert wire["source"] == "avp://agent"
        assert wire["subject"] == "tracer-test"
        assert "trace_id" in wire["data"]
        assert "span_id" in wire["data"]
        assert "parent_span_id" in wire["data"]


def test_span_tree_consistent_one_trace_id_root_agent_span() -> None:
    """All events in one run share trace_id; agent_started/stopped pair
    shares span_id; each turn shares its own span_id across started/ended."""
    out: list = []
    with AVPTracer(_basic_config(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=1, tokens_output=1, cost_usd=0.0, text="ok")

    trace_ids = {ev.data.trace_id for ev in out}
    assert len(trace_ids) == 1, "all events MUST share trace_id"

    started = _by_type(out, AgentStartedEvent)[0]
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert started.data.span_id == stopped.data.span_id, "agent span paired"

    turn_started = _by_type(out, ModelTurnStartedEvent)[0]
    turn_ended = _by_type(out, ModelTurnEndedEvent)[0]
    assert turn_started.data.span_id == turn_ended.data.span_id, "turn span paired"
    assert turn_started.data.parent_span_id == started.data.span_id, "turn under agent"


# ── Tool ─────────────────────────────────────────────────────────────────────


def test_tool_call_records_invoked_and_returned() -> None:
    out: list = []
    with AVPTracer(_basic_config(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=10, tokens_output=5, cost_usd=0.0, text=None)
        with tracer.tool(call_id="c1", name="bash", input={"command": "ls"}) as t:
            t.record("file1\nfile2\n")
        tracer.converged()
    inv = _by_type(out, ToolInvokedEvent)[0]
    ret = _by_type(out, ToolReturnedEvent)[0]
    assert inv.data.gen_ai_tool_name == "bash"
    assert inv.data.gen_ai_tool_call_arguments == {"command": "ls"}
    assert ret.data.avp_tool_result_text == "file1\nfile2\n"
    assert inv.data.span_id == ret.data.span_id, "tool span paired"


def test_tool_call_fail_emits_tool_failed_not_returned() -> None:
    out: list = []
    with AVPTracer(_basic_config(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=1, tokens_output=1, cost_usd=0.0)
        with tracer.tool(call_id="c1", name="bash", input={"command": "x"}) as t:
            t.fail("command not found")
    assert _by_type(out, ToolFailedEvent), "tool_failed MUST be emitted"
    assert not _by_type(out, ToolReturnedEvent), "tool_returned MUST NOT be emitted on fail"


def test_tool_call_reject_marks_rejected_on_returned() -> None:
    out: list = []
    with AVPTracer(_basic_config(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=1, tokens_output=1, cost_usd=0.0)
        with tracer.tool(call_id="c1", name="bash", input={"command": "rm -rf /"}) as t:
            t.reject("denied", reason="dangerous_path")
    ret = _by_type(out, ToolReturnedEvent)[0]
    assert ret.data.avp_tool_rejected is True
    assert ret.data.avp_tool_rejection_reason == "dangerous_path"


# ── Subagent ─────────────────────────────────────────────────────────────────


def _cfg_with_subagent() -> Commission:
    return _basic_config(subagents=[SubagentRef(id="summarizer", ref="sk_summarizer_v1")])


def test_subagent_scope_emits_invoked_and_returned_with_paired_span() -> None:
    out: list = []
    with AVPTracer(_cfg_with_subagent(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=20, tokens_output=5, cost_usd=0.001)
        with tracer.subagent(name="summarizer", input={"prompt": "passage"}) as sa:
            with sa.turn() as t:
                t.record(tokens_input=15, tokens_output=10, cost_usd=0.0005, text="bullet")
            sa.record_result("bullet")
        tracer.converged()

    inv = _by_type(out, SubagentInvokedEvent)[0]
    ret = _by_type(out, SubagentReturnedEvent)[0]
    assert inv.data.span_id == ret.data.span_id, "frame span paired"
    assert inv.data.gen_ai_agent_name == "summarizer"
    # Description / inputSchema land on resolved metadata, not on the bare
    # SubagentRef in Commission. The tracer emits id-based name only in v0.1.
    assert inv.data.gen_ai_operation_name == "invoke_agent"
    assert ret.data.avp_subagent_result_text == "bullet"


def test_subagent_inner_turns_chain_through_frame_span() -> None:
    """The model_turn started/ended emitted by sa.turn() MUST have
    parent_span_id == frame_span_id. This is what makes the trajectory
    a tree."""
    out: list = []
    with AVPTracer(_cfg_with_subagent(), on_event=out.append) as tracer:
        with tracer.subagent(name="summarizer", input={}) as sa:
            with sa.turn() as t:
                t.record(tokens_input=1, tokens_output=1, cost_usd=0.0, text="x")
            sa.record_result("x")
        tracer.converged()

    inv = _by_type(out, SubagentInvokedEvent)[0]
    frame_id = inv.data.span_id
    nested = [e for e in _by_type(out, ModelTurnStartedEvent) if e.data.parent_span_id == frame_id]
    assert len(nested) == 1, "subagent's model_turn MUST chain under frame span"


def test_subagent_usage_rolls_into_parent_state_and_appears_on_returned() -> None:
    """The subagent's spend goes to the parent's RunStateSnapshot AND is
    preserved on subagent_returned.avp.subagent.usage so consumers can
    attribute spend per subagent."""
    out: list = []
    with AVPTracer(_cfg_with_subagent(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=10, tokens_output=5, cost_usd=0.001)
        with tracer.subagent(name="summarizer", input={}) as sa:
            with sa.turn() as t:
                t.record(tokens_input=20, tokens_output=15, cost_usd=0.002, text="x")
            sa.record_result("x")
        tracer.converged()

    ret = _by_type(out, SubagentReturnedEvent)[0]
    sa_usage = ret.data.avp_subagent_usage
    # Subagent's own breakdown — only the inner turn.
    assert sa_usage.total_cost_usd == 0.002
    assert sa_usage.total_tokens == 35  # 20 + 15
    assert sa_usage.total_turns == 1

    # Parent's cumulative — both turns rolled in.
    stopped = _by_type(out, AgentStoppedEvent)[0]
    parent_state = stopped.data.avp_state
    assert parent_state.total_cost_usd == 0.001 + 0.002
    assert parent_state.total_tokens == 15 + 35
    assert parent_state.total_turns == 2


def test_subagent_fail_emits_subagent_failed_not_returned() -> None:
    out: list = []
    with AVPTracer(_cfg_with_subagent(), on_event=out.append) as tracer:
        with tracer.subagent(name="summarizer", input={}) as sa:
            sa.fail("subagent rejected the task", code="rejected")
        tracer.converged()
    assert _by_type(out, SubagentFailedEvent)
    assert not _by_type(out, SubagentReturnedEvent)
    fail = _by_type(out, SubagentFailedEvent)[0]
    assert fail.data.avp_subagent_error == "subagent rejected the task"
    assert fail.data.avp_subagent_error_code == "rejected"


def test_subagent_undeclared_name_raises() -> None:
    """Calling tracer.subagent(name=X) where X isn't in Commission.subagents
    is a programming error — fail loudly, not silently."""
    import pytest

    with AVPTracer(_basic_config(), on_event=lambda _: None) as tracer:
        with pytest.raises(ValueError, match="not declared"):
            with tracer.subagent(name="ghost", input={}):
                pass


# ── Misc ─────────────────────────────────────────────────────────────────────


def test_turn_record_cannot_be_called_twice() -> None:
    import pytest

    with AVPTracer(_basic_config(), on_event=lambda _: None) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=1, tokens_output=1, cost_usd=0.0)
            with pytest.raises(RuntimeError, match="called twice"):
                turn.record(tokens_input=1, tokens_output=1, cost_usd=0.0)
        tracer.converged()


def test_subagents_appear_in_agent_started_data() -> None:
    out: list = []
    with AVPTracer(_cfg_with_subagent(), on_event=out.append) as tracer:
        tracer.converged()
    started = _by_type(out, AgentStartedEvent)[0]
    assert started.data.subagents and len(started.data.subagents) == 1
    assert started.data.subagents[0].name == "summarizer"


# ── format_event / print_event ───────────────────────────────────────────────


def test_format_event_covers_lifecycle_events() -> None:
    """`format_event` MUST handle every event type AVPTracer emits without
    crashing — so a user passing `print_event` as the on_event sink for
    a real run never sees a traceback. Pin the per-type formatting at
    the same time."""
    from avp import format_event

    out: list = []
    with AVPTracer(_cfg_with_subagent(), on_event=out.append) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=10, tokens_output=5, cost_usd=0.001, text="hi")
        with tracer.tool(call_id="c1", name="bash", input={"command": "ls"}) as t:
            t.record("file1\nfile2")
        with tracer.subagent(name="summarizer", input={"prompt": "go"}) as sa:
            with sa.turn() as st:
                st.record(tokens_input=5, tokens_output=3, cost_usd=0.0005, text="ok")
            sa.record_result("ok")
        tracer.converged()

    # Every event renders to a string OR returns None (intentionally
    # quieted: model_turn_started, cost_recorded). No tracebacks.
    for ev in out:
        rendered = format_event(ev)
        assert rendered is None or isinstance(rendered, str), (
            f"format_event({type(ev).__name__}) returned {type(rendered).__name__}"
        )

    # And the events that should produce visible lines actually do.
    visible_types = {type(ev).__name__ for ev in out if format_event(ev) is not None}
    assert "AgentStartedEvent" in visible_types
    assert "ModelTurnEndedEvent" in visible_types
    assert "TextEmittedEvent" in visible_types
    assert "ToolInvokedEvent" in visible_types
    assert "ToolReturnedEvent" in visible_types
    assert "SubagentInvokedEvent" in visible_types
    assert "SubagentReturnedEvent" in visible_types
    assert "AgentStoppedEvent" in visible_types


def test_format_event_reasoning_renders_text_or_redacted_marker() -> None:
    """`format_event(ReasoningEmittedEvent)` MUST surface either the
    summary text or a `<redacted>` marker, NOT fall through to the bare
    class name. The fall-through was confusing in real output: a
    redacted reasoning event followed by a real text_emitted looked
    like one event with two unrelated lines."""
    from avp import (
        ZERO_SPAN_ID,
        ReasoningEmittedData,
        ReasoningEmittedEvent,
        format_event,
        new_span_id,
        new_trace_id,
    )

    tid = new_trace_id()
    plain = ReasoningEmittedEvent(
        subject="r",
        data=ReasoningEmittedData(
            trace_id=tid,
            span_id=new_span_id(),
            parent_span_id=ZERO_SPAN_ID,
            step=1,
            **{
                "avp.reasoning.text": "thinking out loud about the plan",
                "avp.reasoning.redacted": False,
            },
        ),
    )
    redacted = ReasoningEmittedEvent(
        subject="r",
        data=ReasoningEmittedData(
            trace_id=tid,
            span_id=new_span_id(),
            parent_span_id=ZERO_SPAN_ID,
            step=1,
            **{"avp.reasoning.text": "", "avp.reasoning.redacted": True},
        ),
    )
    assert "thinking out loud" in format_event(plain)
    assert "<redacted>" in format_event(redacted)
    # Neither line should be the bare class name (the regression we fixed).
    assert "ReasoningEmittedEvent" not in format_event(plain)
    assert "ReasoningEmittedEvent" not in format_event(redacted)


def test_print_event_writes_to_stdout(capsys) -> None:
    """`print_event(ev)` writes a one-line summary to stdout. Use as
    `on_event=print_event` for examples / debugging without writing
    your own dispatch over event types."""
    from avp import print_event

    with AVPTracer(_basic_config(), on_event=print_event) as tracer:
        with tracer.turn() as turn:
            turn.record(tokens_input=10, tokens_output=5, cost_usd=0.001, text="hello")
        tracer.converged()

    captured = capsys.readouterr()
    # Spot-check the lines the formatter emits — agent_started, the turn
    # line, the text, and the STOPPED footer.
    assert "agent_started" in captured.out
    assert "[turn 1]" in captured.out
    assert "hello" in captured.out
    assert "STOPPED" in captured.out
    assert "converged" in captured.out
