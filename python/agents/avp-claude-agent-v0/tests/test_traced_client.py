"""Tests for TracedClaudeSDKClient — Layer 2 drop-in for the Claude Agent SDK.

The traced client inverts ClaudeAgentTranslator.run(): the user owns the
async-for over receive_response(), and the wrapper translates each SDK
message in passing. These tests pin the contract:

  - On enter / exit: agent_started / agent_stopped emitted around the
    SDK client open / close
  - Each AssistantMessage flowing through receive_response() emits the
    full per-turn AVP block (model_turn_*, text, cost) BEFORE the user
    sees the message
  - PreToolUse / PostToolUse hooks (installed on the SDK options the
    wrapper builds) emit tool_invoked / tool_returned the same way the
    agent CLI does
  - Subagent dispatch via Agent tool_use → subagent_invoked / returned
  - converged() honored when no other terminal condition fires
  - Pass-through __getattr__ forwards SDK-specific attributes

Tests use injected fakes so claude_agent_sdk doesn't need to be installed.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from avp import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Commission,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    StopReason,
    SubagentInvokedEvent,
    SubagentRef,
    SubagentReturnedEvent,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from avp_claude_agent import TracedClaudeSDKClient

# ── Lightweight SDK fakes ─────────────────────────────────────────────────────


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


@dataclass
class _FakeAgentDefinition:
    payload: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.payload = kwargs


class AssistantMessage:
    def __init__(
        self, content: list, usage: dict[str, Any] | None = None, model: str = "claude-sonnet-4-6"
    ) -> None:
        self.content = content
        self.usage = usage
        self.model = model


class ResultMessage:
    def __init__(self, total_cost_usd: float | None = None) -> None:
        self.total_cost_usd = total_cost_usd


class TextBlock:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeClient:
    """Stand-in for `ClaudeSDKClient`. Yields scripted messages from
    receive_response()."""

    def __init__(self, *, messages: list[Any] | None = None, options: Any = None) -> None:
        self.options = options
        self._messages = list(messages or [])
        self.connect_prompt: str | None = None
        self.queries: list[str] = []
        self.connected = False
        self.closed = False

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        self.closed = True

    async def connect(self, prompt: str | None = None) -> None:
        self.connect_prompt = prompt
        self.connected = True

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.queries.append(prompt)

    async def receive_response(self):
        for msg in self._messages:
            yield msg


def _client_factory(messages: list[Any] | None = None) -> Callable[..., _FakeClient]:
    def _make(options: Any = None) -> _FakeClient:
        return _FakeClient(messages=messages, options=options)

    return _make


def _make_traced(
    cfg: Commission,
    *,
    messages: list[Any] | None = None,
) -> tuple[TracedClaudeSDKClient, list]:
    out: list = []
    traced = TracedClaudeSDKClient(
        commission=cfg,
        on_event=out.append,
        sdk_client_cls=_client_factory(messages),
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
        sdk_agent_definition_cls=_FakeAgentDefinition,
    )
    return traced, out


def _basic_config(**overrides: Any) -> Commission:
    base: dict[str, Any] = {
        "schema_version": "0.1",
        "run_id": "traced-client-test",
        "model": "claude-sonnet-4-6",
        "prompt": "kick off",
    }
    base.update(overrides)
    return Commission(**base)


def _by_type(events: list, type_: type) -> list:
    return [e for e in events if isinstance(e, type_)]


def _types(events: list) -> list[str]:
    return [type(e).__name__ for e in events]


# ── Lifecycle ─────────────────────────────────────────────────────────────────


def test_enter_emits_agent_started_exit_emits_agent_stopped() -> None:
    cfg = _basic_config()
    traced, out = _make_traced(cfg)

    async def _run() -> None:
        async with traced:
            pass

    asyncio.run(_run())
    types = _types(out)
    assert types[0] == "AgentStartedEvent"
    assert types[-1] == "AgentStoppedEvent"
    started = _by_type(out, AgentStartedEvent)[0]
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert started.subject == "traced-client-test"
    # No converged() called and no exception → default to converged.
    assert stopped.data.avp_reason == StopReason.converged


def test_receive_response_emits_per_message_avp_events_before_yield() -> None:
    """One AssistantMessage flowing through receive_response() MUST emit
    model_turn_started/ended + text_emitted + cost_recorded for that turn
    BEFORE the user's async-for body sees the message — causal ordering."""
    cfg = _basic_config()
    msg = AssistantMessage(
        content=[TextBlock("hi there")],
        usage={"input_tokens": 50, "output_tokens": 10},
    )
    traced, out = _make_traced(cfg, messages=[msg])
    seen_messages: list = []

    async def _run() -> None:
        async with traced as client:
            await client.connect("ok")
            async for m in client.receive_response():
                # Snapshot what's in `out` at the moment we receive m.
                # Per-turn events MUST already be there.
                seen_messages.append((m, list(out)))
            client.converged()

    asyncio.run(_run())

    assert len(seen_messages) == 1
    _, events_at_yield = seen_messages[0]
    types_at_yield = [type(e).__name__ for e in events_at_yield]
    assert "ModelTurnStartedEvent" in types_at_yield
    assert "ModelTurnEndedEvent" in types_at_yield
    assert "TextEmittedEvent" in types_at_yield
    # And by the time the run exits, agent_stopped has fired at the end.
    assert _types(out)[-1] == "AgentStoppedEvent"


def test_receive_response_yields_messages_unchanged() -> None:
    """The wrapper MUST yield the SDK's Message instances UNCHANGED — user
    code walking `.content` blocks etc. keeps working unmodified."""
    cfg = _basic_config()
    msg = AssistantMessage(
        content=[TextBlock("preserved")],
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    traced, _out = _make_traced(cfg, messages=[msg])
    received: list = []

    async def _run() -> None:
        async with traced as client:
            await client.connect("p")
            async for m in client.receive_response():
                received.append(m)

    asyncio.run(_run())
    assert len(received) == 1
    assert received[0] is msg
    assert received[0].content[0].text == "preserved"


def test_connect_and_query_forward_to_underlying_client() -> None:
    cfg = _basic_config()
    traced, _out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced as client:
            await client.connect("hello")
            await client.query("follow-up")

    asyncio.run(_run())
    fake = traced._client
    assert fake.connect_prompt == "hello"
    assert fake.queries == ["follow-up"]


def test_attribute_access_passes_through_to_sdk_client() -> None:
    """SDK-specific helpers attached to ClaudeSDKClient should keep
    working without the wrapper shadowing them. __getattr__ forwards."""
    cfg = _basic_config()
    traced, _out = _make_traced(cfg, messages=[])

    async def _run() -> tuple:
        async with traced as client:
            # The fake exposes `connected` after connect().
            await client.connect("p")
            return client.connected, client.queries

    connected, queries = asyncio.run(_run())
    assert connected is True
    assert queries == []


# ── Tools (via PreToolUse / PostToolUse hooks the wrapper installs) ──────────


def test_pre_post_tool_use_hooks_fire_emitting_tool_lifecycle() -> None:
    """The hooks the wrapper installs on SDK options are the same ones
    ClaudeAgentTranslator uses. Calling them produces tool_invoked /
    tool_returned just like the agent CLI does."""
    cfg = _basic_config()
    traced, out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced:
            # Reach into the translator and invoke the hook directly —
            # this is what the SDK does internally when it runs a tool.
            await traced._translator._on_pre_tool_use_hook(
                {
                    "tool_use_id": "tu-1",
                    "tool_name": "bash",
                    "tool_input": {"command": "ls"},
                },
                None,
                None,
            )
            await traced._translator._on_post_tool_use_hook(
                {
                    "tool_use_id": "tu-1",
                    "tool_name": "bash",
                    "tool_response": "file1\nfile2\n",
                },
                None,
                None,
            )

    asyncio.run(_run())
    inv = _by_type(out, ToolInvokedEvent)[0]
    ret = _by_type(out, ToolReturnedEvent)[0]
    assert inv.data.gen_ai_tool_name == "bash"
    assert ret.data.avp_tool_result_text == "file1\nfile2\n"
    assert inv.data.span_id == ret.data.span_id, "tool span paired"


# ── Subagents ─────────────────────────────────────────────────────────────────


def test_agent_tool_with_declared_subagent_diverts_to_subagent_lifecycle() -> None:
    """Same divert logic as ClaudeAgentTranslator: an `Agent` tool_use
    whose subagent_type matches a declared Commission.subagent emits
    subagent_invoked / subagent_returned (NOT tool_invoked / tool_returned)."""
    cfg = _basic_config(subagents=[SubagentRef(id="researcher", ref="sk_researcher")])
    traced, out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced:
            await traced._translator._on_pre_tool_use_hook(
                {
                    "tool_use_id": "tu-2",
                    "tool_name": "Agent",
                    "tool_input": {"subagent_type": "researcher", "prompt": "go"},
                },
                None,
                None,
            )
            await traced._translator._on_post_tool_use_hook(
                {
                    "tool_use_id": "tu-2",
                    "tool_name": "Agent",
                    "tool_response": "found 3 things",
                },
                None,
                None,
            )

    asyncio.run(_run())
    inv = _by_type(out, SubagentInvokedEvent)[0]
    ret = _by_type(out, SubagentReturnedEvent)[0]
    assert inv.data.gen_ai_agent_name == "researcher"
    assert ret.data.avp_subagent_result_text == "found 3 things"
    assert inv.data.span_id == ret.data.span_id  # frame paired
    # And the SDK's Agent tool was NOT also surfaced as tool_invoked.
    assert not _by_type(out, ToolInvokedEvent)


# ── Control signals ──────────────────────────────────────────────────────────


def test_converged_marks_stop_reason_converged() -> None:
    """When the user calls converged() and exits cleanly, the run reports
    reason=converged. (Default behavior — explicit signal honored over
    the implicit fallback.)"""
    cfg = _basic_config()
    traced, out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced as client:
            client.converged()

    asyncio.run(_run())
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert stopped.data.avp_reason == StopReason.converged


def test_exception_inside_block_yields_reason_error() -> None:
    """An unhandled exception inside the `async with` block sets reason=error
    on the agent_stopped event (mirrors AVPAgent / translator behavior)."""
    cfg = _basic_config()
    traced, out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced:
            raise RuntimeError("boom")

    import contextlib

    with contextlib.suppress(RuntimeError):
        asyncio.run(_run())
    stopped = _by_type(out, AgentStoppedEvent)[0]
    assert stopped.data.avp_reason == StopReason.error


def test_subagents_appear_in_agent_started_data() -> None:
    cfg = _basic_config(subagents=[SubagentRef(id="planner", ref="sk_planner")])
    traced, out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced:
            pass

    asyncio.run(_run())
    started = _by_type(out, AgentStartedEvent)[0]
    assert started.data.subagents and started.data.subagents[0].name == "planner"


def test_options_carry_avp_hooks_so_sdk_dispatches_through_us() -> None:
    """Build SDK options once on enter and verify our hooks are registered
    — without this the SDK would never invoke our PreToolUse / PostToolUse
    callbacks and the wire would be missing tool events."""
    cfg = _basic_config()
    traced, _out = _make_traced(cfg, messages=[])

    async def _run() -> None:
        async with traced:
            # The fake client captures the options it was constructed with.
            opts = traced._client.options
            kw = opts.kwargs
            assert "PreToolUse" in kw["hooks"]
            assert "PostToolUse" in kw["hooks"]
            assert "UserPromptSubmit" in kw["hooks"]
            assert "Stop" in kw["hooks"]

    asyncio.run(_run())


def test_two_assistant_messages_yield_two_turn_pairs() -> None:
    cfg = _basic_config()
    msgs = [
        AssistantMessage(
            content=[TextBlock("first")],
            usage={"input_tokens": 100, "output_tokens": 20},
        ),
        AssistantMessage(
            content=[TextBlock("second")],
            usage={"input_tokens": 250, "output_tokens": 50},  # cumulative
        ),
    ]
    traced, out = _make_traced(cfg, messages=msgs)

    async def _run() -> None:
        async with traced as client:
            await client.connect("p")
            async for _ in client.receive_response():
                pass
            client.converged()

    asyncio.run(_run())
    turn_starts = _by_type(out, ModelTurnStartedEvent)
    turn_ends = _by_type(out, ModelTurnEndedEvent)
    text = _by_type(out, TextEmittedEvent)
    assert len(turn_starts) == 2
    assert len(turn_ends) == 2
    assert len(text) == 2
    # Per-turn delta math — the second turn's tokens are 250-100=150 in / 50-20=30 out.
    assert turn_ends[1].data.gen_ai_usage_input_tokens == 150
    assert turn_ends[1].data.gen_ai_usage_output_tokens == 30


# ── traced_claude_sdk_client() factory (active-tracer mode) ─────────────────


def test_factory_requires_active_tracer() -> None:
    """`traced_claude_sdk_client()` outside a `with AVPTracer(...)` block
    raises a clear error pointing at the missing context."""
    import pytest

    from avp_claude_agent import traced_claude_sdk_client

    with pytest.raises(RuntimeError, match="active AVPTracer"):
        traced_claude_sdk_client()


def test_factory_pulls_config_and_on_event_from_active_tracer() -> None:
    """Inside `with AVPTracer(config, on_event=publish):`, the factory
    constructs a TracedClaudeSDKClient that emits events through the
    same `publish` callback. No need to repeat config / on_event."""
    from avp import AVPTracer
    from avp_claude_agent import traced_claude_sdk_client

    cfg = _basic_config()
    out: list = []

    msg = AssistantMessage(
        content=[TextBlock("hi")],
        usage={"input_tokens": 10, "output_tokens": 5},
    )

    async def _run() -> None:
        with AVPTracer(cfg, on_event=out.append):
            client = traced_claude_sdk_client(
                sdk_client_cls=_client_factory([msg]),
                sdk_options_cls=_FakeOptions,
                sdk_hook_matcher_cls=_FakeHookMatcher,
            )
            async with client:
                await client.connect("p")
                async for _ in client.receive_response():
                    pass

    asyncio.run(_run())

    # The wire shows ONE agent_started / agent_stopped pair — emitted by
    # AVPTracer, NOT by the translator (it's in delegated mode).
    started = _by_type(out, AgentStartedEvent)
    stopped = _by_type(out, AgentStoppedEvent)
    assert len(started) == 1
    assert len(stopped) == 1


def test_factory_translator_shares_trace_id_with_active_tracer() -> None:
    """Delegated mode: the translator's events MUST carry the AVPTracer's
    trace_id, not a fresh one. Without this, consumers reconstruct two
    disjoint trees instead of one."""
    from avp import AVPTracer
    from avp_claude_agent import traced_claude_sdk_client

    cfg = _basic_config()
    out: list = []
    msg = AssistantMessage(
        content=[TextBlock("hi")],
        usage={"input_tokens": 10, "output_tokens": 5},
    )

    async def _run() -> None:
        with AVPTracer(cfg, on_event=out.append):
            client = traced_claude_sdk_client(
                sdk_client_cls=_client_factory([msg]),
                sdk_options_cls=_FakeOptions,
                sdk_hook_matcher_cls=_FakeHookMatcher,
            )
            async with client:
                await client.connect("p")
                async for _ in client.receive_response():
                    pass

    asyncio.run(_run())

    # Every event under one trace_id.
    trace_ids = {ev.data.trace_id for ev in out}
    assert len(trace_ids) == 1, f"events split across trace_ids: {trace_ids}"


def test_factory_suppresses_translator_lifecycle_emission() -> None:
    """The translator MUST NOT emit its own agent_started / agent_stopped
    in delegated mode — the outer AVPTracer already did. Two of either
    on the wire under the same trace_id is malformed."""
    from avp import AVPTracer
    from avp_claude_agent import traced_claude_sdk_client

    out: list = []

    async def _run() -> None:
        with AVPTracer(_basic_config(), on_event=out.append):
            client = traced_claude_sdk_client(
                sdk_client_cls=_client_factory([]),
                sdk_options_cls=_FakeOptions,
                sdk_hook_matcher_cls=_FakeHookMatcher,
            )
            async with client:
                pass

    asyncio.run(_run())

    assert len(_by_type(out, AgentStartedEvent)) == 1
    assert len(_by_type(out, AgentStoppedEvent)) == 1


def test_self_contained_form_still_works_unchanged() -> None:
    """Backwards-compat: the existing `TracedClaudeSDKClient(config=,
    on_event=)` form is untouched — it owns its own lifecycle and emits
    its own agent_started / agent_stopped. Nothing about the refactor
    should break it."""
    cfg = _basic_config()
    msg = AssistantMessage(
        content=[TextBlock("hi")],
        usage={"input_tokens": 10, "output_tokens": 5},
    )
    traced, out = _make_traced(cfg, messages=[msg])

    async def _run() -> None:
        async with traced as client:
            await client.connect("p")
            async for _ in client.receive_response():
                pass

    asyncio.run(_run())

    # Self-contained mode: translator emits its OWN agent_started / stopped
    # (no outer AVPTracer). One of each.
    assert len(_by_type(out, AgentStartedEvent)) == 1
    assert len(_by_type(out, AgentStoppedEvent)) == 1


def test_factory_pushes_per_turn_spend_into_parent_tracer_state() -> None:
    """Regression test for the make-smoke example-07 bug. In delegated
    mode the translator MUST push each turn's delta into the parent
    AVPTracer's cumulative state — otherwise `agent_stopped.avp_state`
    reports zeros even though per-turn cost_recorded events show real
    spend.

    Pinning this with a scripted run so a future refactor that drops
    the push fails this test before failing `make smoke`."""
    from avp import AVPTracer
    from avp_claude_agent import traced_claude_sdk_client

    cfg = _basic_config()
    out: list = []
    msgs = [
        AssistantMessage(
            content=[TextBlock("hi")],
            usage={"input_tokens": 100, "output_tokens": 20},
        ),
        AssistantMessage(
            content=[TextBlock("there")],
            usage={"input_tokens": 250, "output_tokens": 50},  # cumulative
        ),
    ]

    async def _run() -> None:
        with AVPTracer(cfg, on_event=out.append):
            client = traced_claude_sdk_client(
                sdk_client_cls=_client_factory(msgs),
                sdk_options_cls=_FakeOptions,
                sdk_hook_matcher_cls=_FakeHookMatcher,
            )
            async with client:
                await client.connect("p")
                async for _ in client.receive_response():
                    pass

    asyncio.run(_run())

    stopped = _by_type(out, AgentStoppedEvent)[0]
    snap = stopped.data.avp_state
    # Two scripted turns; deltas summed into parent.
    # turn 1: input=100 output=20 / turn 2 (cumulative-delta): input=150 output=30
    # Total tokens summed = 100+20+150+30 = 300. total_turns = 2.
    assert snap.total_tokens == 300, (
        f"parent's total_tokens MUST include CASDK turns, got {snap.total_tokens}"
    )
    assert snap.total_turns == 2
    assert snap.total_cost_usd > 0, (
        "parent's total_cost_usd MUST reflect CASDK spend (was the example-07 bug)"
    )
