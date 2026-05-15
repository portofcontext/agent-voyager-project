"""Tests for AnthropicTracedClient — Layer 2 drop-in for the Anthropic SDK.

The wrapper hides AVPTracer behind a context manager so user code looks
like a vanilla Anthropic loop:

    with AnthropicTracedClient(real, commission=cfg, on_event=publish) as client:
        while True:
            resp = client.messages.create(...)
            if resp.stop_reason == "end_turn":
                client.converged()
                break
            ...

These tests pin the contract:

  - Lifecycle: agent_started on `__enter__`, agent_stopped on `__exit__`
  - One `messages.create()` call → one model_turn pair, before yield
  - Token / cost extraction matches AnthropicModelDriver
  - The wrapper returns the underlying Message UNMODIFIED
  - `client.tool(...)` and `client.subagent(...)` delegate to the
    internal tracer
  - Pass-through for non-wrapped attributes via `__getattr__`
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from avp.commission import (
    Commission,
    SubagentRef,
)
from avp.enums import StopReason
from avp.trajectory import (
    AgentStartedEvent,
    AgentStoppedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    SubagentInvokedEvent,
    SubagentReturnedEvent,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from avp_anthropic import AnthropicTracedClient


class _FakeMessages:
    """Stand-in for `anthropic.Anthropic().messages`. Returns scripted
    `anthropic.Message`-shaped responses one at a time."""

    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("test asked for more turns than scripted")
        return self._responses.pop(0)


class _FakeAnthropic:
    """Stand-in for `anthropic.Anthropic()`. Exposes `.messages` and a
    `.beta` attribute to verify __getattr__ pass-through."""

    def __init__(self, responses: list[Any]) -> None:
        self.messages = _FakeMessages(responses)
        self.beta = SimpleNamespace(some_resource="here")


def _resp(
    *,
    text: str | None = None,
    tool_use: dict | None = None,
    stop_reason: str = "end_turn",
    input_tokens: int = 50,
    output_tokens: int = 10,
    cache_read: int = 0,
    cache_write: int = 0,
    model: str = "claude-sonnet-4-6",
) -> SimpleNamespace:
    blocks: list[Any] = []
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))
    if tool_use:
        blocks.append(SimpleNamespace(type="tool_use", **tool_use))
    return SimpleNamespace(
        content=blocks,
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_write,
        ),
        stop_reason=stop_reason,
        model=model,
    )


def _basic_config(**overrides) -> Commission:
    base: dict = {
        "schema_version": "0.1",
        "run_id": "traced-client-test",
        "model": "claude-sonnet-4-6",
        "prompt": "hi",
    }
    base.update(overrides)
    return Commission(**base)


def _by_type(events: list, type_: type) -> list:
    return [e for e in events if isinstance(e, type_)]


def _types(events: list) -> list[str]:
    return [type(e).__name__ for e in events]


# ── Lifecycle ────────────────────────────────────────────────────────────────


def test_enter_exit_emit_full_lifecycle_around_a_single_create_call() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="hello", input_tokens=40, output_tokens=8)])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        resp = client.messages.create(model="claude-sonnet-4-6", messages=[])
        assert resp.stop_reason == "end_turn"
        client.converged()

    types = _types(out)
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert stopped.data.avp_reason == StopReason.converged


def test_create_call_emits_one_turn_pair() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="hello", input_tokens=40, output_tokens=8)])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()

    assert len(_by_type(out, ModelTurnStartedEvent)) == 1
    assert len(_by_type(out, ModelTurnEndedEvent)) == 1
    text_events = _by_type(out, TextEmittedEvent)
    assert len(text_events) == 1 and text_events[0].data.avp_text == "hello"


def test_messages_returns_underlying_anthropic_message_unmodified() -> None:
    """The user's existing code that walks `.content` blocks etc. must
    keep working. The wrapper does not mutate the SDK response."""
    out: list = []
    msg = _resp(text="preserved", stop_reason="end_turn")
    fake = _FakeAnthropic([msg])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        resp = client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    # Same object, same fields.
    assert resp is msg
    assert resp.stop_reason == "end_turn"
    assert resp.content[0].text == "preserved"


# ── Token / cost extraction ──────────────────────────────────────────────────


def test_token_extraction_matches_anthropic_model_driver_convention() -> None:
    """AVP convention: tokens_input INCLUDES cache reads. SDK reports
    fresh-only, so the wrapper adds cache reads/writes back. Same rule
    AnthropicModelDriver uses — must match or trajectories disagree."""
    out: list = []
    fake = _FakeAnthropic(
        [_resp(text="x", input_tokens=100, output_tokens=20, cache_read=30, cache_write=10)]
    )
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    ended = _by_type(out, ModelTurnEndedEvent)[0]
    # 100 fresh + 30 cache_read + 10 cache_write = 140
    assert ended.data.gen_ai_usage_input_tokens == 140
    assert ended.data.gen_ai_usage_output_tokens == 20
    assert ended.data.gen_ai_usage_cache_read_input_tokens == 30
    assert ended.data.gen_ai_usage_cache_creation_input_tokens == 10
    assert ended.data.avp_cost_usd > 0


def test_cost_zero_for_unknown_model() -> None:
    """An unpriced model name yields cost=0 without crashing. Same as
    AnthropicModelDriver."""
    import warnings

    out: list = []
    fake = _FakeAnthropic([_resp(text="x", model="some-unknown-model")])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
            client.messages.create(model="some-unknown-model", messages=[])
            client.converged()
    ended = _by_type(out, ModelTurnEndedEvent)[0]
    assert ended.data.avp_cost_usd == 0.0


def test_wrapper_records_finish_reason_from_stop_reason() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x", stop_reason="tool_use")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    ended = _by_type(out, ModelTurnEndedEvent)[0]
    assert ended.data.gen_ai_response_finish_reasons == ["tool_use"]


def test_two_calls_produce_two_turns_with_distinct_span_ids() -> None:
    out: list = []
    fake = _FakeAnthropic(
        [
            _resp(text="first", stop_reason="tool_use", input_tokens=30, output_tokens=10),
            _resp(text="second", stop_reason="end_turn", input_tokens=40, output_tokens=15),
        ]
    )
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        client.converged()
    starts = _by_type(out, ModelTurnStartedEvent)
    ends = _by_type(out, ModelTurnEndedEvent)
    assert len(starts) == 2 and len(ends) == 2
    assert starts[0].data.span_id != starts[1].data.span_id
    assert starts[0].data.span_id == ends[0].data.span_id
    assert starts[1].data.span_id == ends[1].data.span_id
    assert starts[0].data.avp_step == 1 and starts[1].data.avp_step == 2


# ── Tool / subagent context managers (delegate to the internal tracer) ──────


def test_tool_context_manager_emits_tool_invoked_and_returned() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with client.tool(call_id="c1", name="bash", input={"command": "ls"}) as t:
            t.record("file1\nfile2")
        client.converged()
    inv = _by_type(out, ToolInvokedEvent)[0]
    ret = _by_type(out, ToolReturnedEvent)[0]
    assert inv.data.gen_ai_tool_name == "bash"
    assert ret.data.avp_tool_result_text == "file1\nfile2"
    assert inv.data.span_id == ret.data.span_id


def test_subagent_context_manager_emits_subagent_invoked_and_returned() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    cfg = _basic_config(subagents=[SubagentRef(id="researcher", ref="sk_researcher")])
    with AnthropicTracedClient(fake, commission=cfg, on_event=out.append) as client:
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with client.subagent(name="researcher", input={"prompt": "go"}) as sa:
            with sa.turn() as turn:
                turn.record(tokens_input=5, tokens_output=2, cost_usd=0.0001, text="found 1")
            sa.record_result("found 1")
        client.converged()
    inv = _by_type(out, SubagentInvokedEvent)[0]
    ret = _by_type(out, SubagentReturnedEvent)[0]
    assert inv.data.span_id == ret.data.span_id
    assert ret.data.avp_subagent_result_text == "found 1"


# ── Pass-through ─────────────────────────────────────────────────────────────


def test_attribute_passthrough_to_underlying_client() -> None:
    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        # `beta` is on the underlying client, not wrapped explicitly.
        assert client.beta.some_resource == "here"
        assert client.real is fake
        client.converged()


def test_messages_access_before_enter_raises() -> None:
    """Accessing `client.messages` before `with` raises a clear error."""
    fake = _FakeAnthropic([])
    client = AnthropicTracedClient(fake, commission=_basic_config(), on_event=lambda _: None)
    with pytest.raises(RuntimeError, match="must be used as `with`"):
        _ = client.messages


def test_reused_client_raises() -> None:
    """A new wrapper per run — same Commission can't be reused on a single
    instance."""
    fake = _FakeAnthropic([_resp(text="x")])
    client = AnthropicTracedClient(fake, commission=_basic_config(), on_event=lambda _: None)
    with client:
        pass
    with pytest.raises(RuntimeError, match="cannot be reused"):
        with client:
            pass


# ── agent_started carries the model-facing surface ──────────────────────────


def test_agent_started_emits_subagents_when_declared() -> None:
    out: list = []
    fake = _FakeAnthropic([])
    cfg = _basic_config(subagents=[SubagentRef(id="planner", ref="sk_planner")])
    with AnthropicTracedClient(fake, commission=cfg, on_event=out.append):
        pass
    started = _by_type(out, AgentStartedEvent)[0]
    assert started.data.avp_subagents and started.data.avp_subagents[0].name == "planner"


# ── Beta surface (widened coverage) ──────────────────────────────────────────


class _FakeBeta:
    """Stand-in for `client.beta` — has its own .messages just like the real
    SDK's beta surface."""

    def __init__(self, responses: list[Any]) -> None:
        self.messages = _FakeMessages(responses)


class _FakeAnthropicWithBeta(_FakeAnthropic):
    """Adds .beta.messages.create coverage — the SDK's beta surface uses
    different paths and we want to confirm `client.beta.messages.create()`
    also emits AVP events."""

    def __init__(
        self,
        responses: list[Any] | None = None,
        beta_responses: list[Any] | None = None,
    ) -> None:
        super().__init__(responses or [])
        self.beta = _FakeBeta(beta_responses or [])


def test_beta_messages_create_is_instrumented() -> None:
    """`client.beta.messages.create()` MUST emit the same AVP events as
    the non-beta path. Without this users using beta features (e.g.,
    extended-cache-ttl headers, computer-use) silently bypass tracing."""
    out: list = []
    fake = _FakeAnthropicWithBeta(beta_responses=[_resp(text="from beta")])
    with AnthropicTracedClient(fake, commission=_basic_config(), on_event=out.append) as client:
        resp = client.beta.messages.create(model="claude-sonnet-4-6", messages=[])
        assert resp.content[0].text == "from beta"
        client.converged()
    assert len(_by_type(out, ModelTurnEndedEvent)) == 1
    assert _by_type(out, TextEmittedEvent)[0].data.avp_text == "from beta"


# ── wrap_anthropic factory (active-tracer mode) ─────────────────────────────


def test_wrap_anthropic_returns_proxy_that_emits_to_active_tracer() -> None:
    """`wrap_anthropic(client)` returns a proxy that finds its tracer via
    the ContextVar at call time — so the same wrapped client works
    across many traces."""
    from avp.tracer import AVPTracer
    from avp_anthropic import wrap_anthropic

    out: list = []
    fake = _FakeAnthropic([_resp(text="hello")])
    client = wrap_anthropic(fake)
    with AVPTracer(_basic_config(), on_event=out.append):
        resp = client.messages.create(model="claude-sonnet-4-6", messages=[])
        assert resp.content[0].text == "hello"
    types = _types(out)
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types


def test_wrap_anthropic_is_idempotent() -> None:
    """Re-wrapping a wrapped client returns the same instance — protects
    against accidental double-wrap when a library defensively wraps its
    own clients."""
    from avp_anthropic import wrap_anthropic

    fake = _FakeAnthropic([])
    wrapped = wrap_anthropic(fake)
    assert wrap_anthropic(wrapped) is wrapped


def test_wrap_anthropic_raises_outside_active_tracer() -> None:
    """Calling an instrumented method on a wrapped client OUTSIDE a
    `with AVPTracer(...)` block fails loud, not silent — better than
    dropping events the user expected to see."""
    from avp_anthropic import wrap_anthropic

    fake = _FakeAnthropic([_resp(text="x")])
    client = wrap_anthropic(fake)
    with pytest.raises(RuntimeError, match="No active AVPTracer"):
        client.messages.create(model="claude-sonnet-4-6", messages=[])


def test_wrap_anthropic_works_across_multiple_traces() -> None:
    """The big payoff of the wrap-once-use-many pattern: the same
    wrapped client survives multiple `with AVPTracer` blocks. Compare
    to the constructor form which couples one wrapper to one run."""
    from avp.tracer import AVPTracer
    from avp_anthropic import wrap_anthropic

    fake = _FakeAnthropic([_resp(text="t1"), _resp(text="t2")])
    client = wrap_anthropic(fake)

    out_a: list = []
    cfg_a = _basic_config(run_id="run-a")
    with AVPTracer(cfg_a, on_event=out_a.append):
        client.messages.create(model="claude-sonnet-4-6", messages=[])

    out_b: list = []
    cfg_b = _basic_config(run_id="run-b")
    with AVPTracer(cfg_b, on_event=out_b.append):
        client.messages.create(model="claude-sonnet-4-6", messages=[])

    assert _types(out_a)[0] == "AgentStartedEvent" and _types(out_a)[-1] == "AgentStoppedEvent"
    assert _types(out_b)[0] == "AgentStartedEvent" and _types(out_b)[-1] == "AgentStoppedEvent"
    assert _by_type(out_a, AgentStartedEvent)[0].subject == "run-a"
    assert _by_type(out_b, AgentStartedEvent)[0].subject == "run-b"
    a_trace = _by_type(out_a, AgentStartedEvent)[0].data.trace_id
    b_trace = _by_type(out_b, AgentStartedEvent)[0].data.trace_id
    assert a_trace != b_trace


def test_wrap_anthropic_attribute_passthrough() -> None:
    from avp_anthropic import wrap_anthropic

    fake = _FakeAnthropic([])
    client = wrap_anthropic(fake)
    assert client.beta.some_resource == "here"
    assert client.real is fake


def test_wrap_anthropic_unknown_client_type_returns_unchanged() -> None:
    """If the SDK class isn't recognized (third-party Anthropic-compatible
    client, vendored fork), don't crash — return as-is. Caller can opt
    into instrumentation explicitly."""
    from avp_anthropic import wrap_anthropic

    class SomeOtherClient:
        pass

    obj = SomeOtherClient()
    assert wrap_anthropic(obj) is obj


# ── Module-level helpers from avp.tracer reach the active tracer ────────────


def test_module_level_tool_helper_works_with_wrap_anthropic() -> None:
    """The wrap-once flow: wrap the client at module load, use
    `avp.tracer.tool(...)` for tool dispatch inside an AVPTracer block.
    Both find the active tracer via the ContextVar."""
    from avp.tracer import AVPTracer
    from avp.tracer import tool as avp_tool
    from avp_anthropic import wrap_anthropic

    out: list = []
    fake = _FakeAnthropic([_resp(text="x")])
    client = wrap_anthropic(fake)

    with AVPTracer(_basic_config(), on_event=out.append):
        client.messages.create(model="claude-sonnet-4-6", messages=[])
        with avp_tool(call_id="c1", name="bash", input={"command": "ls"}) as t:
            t.record("ok")

    assert _by_type(out, ToolInvokedEvent)[0].data.gen_ai_tool_name == "bash"
    assert _by_type(out, ToolReturnedEvent)[0].data.avp_tool_result_text == "ok"


# ── Async surface ────────────────────────────────────────────────────────────


class _FakeAsyncMessages:
    def __init__(self, responses: list[Any]) -> None:
        self._responses = list(responses)

    async def create(self, **kwargs: Any) -> Any:
        if not self._responses:
            raise AssertionError("test asked for more turns than scripted")
        return self._responses.pop(0)


class _FakeAsyncAnthropic:
    def __init__(self, responses: list[Any]) -> None:
        self.messages = _FakeAsyncMessages(responses)


def test_wrap_anthropic_handles_async_client() -> None:
    """`anthropic.AsyncAnthropic` users should get the same instrumentation
    as sync users. The proxy detects async-vs-sync by the underlying
    class name."""
    import asyncio

    from avp.tracer import AVPTracer
    from avp_anthropic import wrap_anthropic

    fake = _FakeAsyncAnthropic([_resp(text="async hello")])
    # type name needs to contain "AsyncAnthropic" for the dispatcher
    fake.__class__.__name__ = "AsyncAnthropic"
    client = wrap_anthropic(fake)

    out: list = []

    async def _run() -> None:
        with AVPTracer(_basic_config(), on_event=out.append):
            resp = await client.messages.create(model="claude-sonnet-4-6", messages=[])
            assert resp.content[0].text == "async hello"

    asyncio.run(_run())
    assert _by_type(out, ModelTurnEndedEvent)
    assert _by_type(out, TextEmittedEvent)[0].data.avp_text == "async hello"
