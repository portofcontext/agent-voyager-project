"""Translator tests for ClaudeAgentTranslator.

The SDK is fully decoupled via injection (sdk_client_cls / sdk_options_cls /
sdk_hook_matcher_cls), so these tests run without claude_agent_sdk installed
and without an API key. They exercise:

  - Commission → ClaudeAgentOptions translation (_build_sdk_options)
  - AssistantMessage / ResultMessage handling (the message-stream path)
  - PreToolUse / PostToolUse hook callbacks (the hook path)
  - Full run() lifecycle with a fake ClaudeSDKClient that yields canned messages
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from avp.commission import Commission
from avp.enums import StopReason
from avp.trajectory import (
    AgentStartedEvent,
    AgentStoppedEvent,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
)
from avp_claude_agent import ClaudeAgentTranslator

# ── Lightweight fakes for the SDK surface ─────────────────────────────────────


@dataclass
class _FakeOptions:
    kwargs: dict[str, Any]

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


@dataclass
class _FakeHookMatcher:
    matcher: str | None
    hooks: list


class AssistantMessage:
    def __init__(
        self, content: list, usage: dict[str, Any] | None = None, model: str = "claude-sonnet-4-6"
    ):
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
    """Stand-in for `claude_agent_sdk.ClaudeSDKClient`.

    Configured with a list of "rounds": each round is a list of messages
    yielded by the next `receive_response()` call. Rounds advance one per
    `connect()` (the first) and one per `query()` (each subsequent), so
    inject_correction tests can assert the correction got handed to the
    SDK as a follow-up user prompt before the next round of messages.
    """

    _raise_on_invoke: BaseException | None = None

    def __init__(
        self,
        *,
        rounds: list[list[Any]] | None = None,
        raise_on_invoke: BaseException | None = None,
        options: Any = None,
    ) -> None:
        self.options = options
        self._rounds = list(rounds or [])
        self._round_idx = 0
        self.queries: list[str] = []  # follow-up prompts captured for assertions
        self.connect_prompt: str | None = None
        self._raise_on_invoke = raise_on_invoke

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def connect(self, prompt: str | None = None) -> None:
        self.connect_prompt = prompt

    async def query(self, prompt: str, session_id: str = "default") -> None:
        self.queries.append(prompt)

    async def receive_response(self) -> Any:
        if self._raise_on_invoke is not None:
            raise self._raise_on_invoke
        if self._round_idx >= len(self._rounds):
            return
        for msg in self._rounds[self._round_idx]:
            yield msg
        self._round_idx += 1


def _client_factory(
    *,
    rounds: list[list[Any]] | None = None,
    raise_on_invoke: BaseException | None = None,
) -> Callable[..., _FakeClient]:
    """Return a callable suitable for `sdk_client_cls=`.

    The translator instantiates whatever you pass to sdk_client_cls with
    `(options=...)`. We close over the rounds + error to give per-test
    canned responses.
    """

    def _make(options: Any = None) -> _FakeClient:
        return _FakeClient(rounds=rounds, raise_on_invoke=raise_on_invoke, options=options)

    return _make


# ── Helpers ───────────────────────────────────────────────────────────────────


def _new_translator(
    cfg: Commission | None = None,
    *,
    sdk_client_cls: Callable[..., Any] | None = None,
) -> tuple[ClaudeAgentTranslator, list]:
    cfg = cfg or Commission(
        schema_version="0.1",
        run_id="t1",
        model="claude-sonnet-4-6",
        prompt="hello",
        enabled_builtin_tools=["Bash"],
    )
    out: list = []
    t = ClaudeAgentTranslator(
        cfg,
        on_event=out.append,
        sdk_client_cls=sdk_client_cls,
        sdk_options_cls=_FakeOptions,
        sdk_hook_matcher_cls=_FakeHookMatcher,
    )
    return t, out


# ── Tests ─────────────────────────────────────────────────────────────────────


def test_agent_started_emitted_with_config_metadata() -> None:
    t, out = _new_translator()
    t._emit_agent_started()
    ev = out[0]
    assert isinstance(ev, AgentStartedEvent)
    assert ev.subject == "t1"
    assert ev.data.gen_ai_request_model == "claude-sonnet-4-6"
    assert ev.data.prompt == "hello"


def test_build_sdk_options_maps_config_fields() -> None:
    """AVP Commission.enabled_builtin_tools is the built-in allowlist (§9.2)
    — it maps to SDK `tools`, not SDK `allowed_tools` (auto-approve list)."""
    t, _ = _new_translator()
    opts = t._build_sdk_options()
    kw = opts.kwargs
    assert kw["tools"] == ["Bash"]
    assert "allowed_tools" not in kw  # NOT mapped here — that's auto-approve
    assert kw["model"] == "claude-sonnet-4-6"
    assert "PreToolUse" in kw["hooks"]
    assert "PostToolUse" in kw["hooks"]


def test_assistant_message_emits_turn_started_text_ended_cost() -> None:
    t, out = _new_translator()
    msg = AssistantMessage(
        content=[TextBlock("hi there")],
        usage={"input_tokens": 100, "output_tokens": 25, "cache_read_input_tokens": 0},
        model="claude-sonnet-4-6",
    )
    t._handle_assistant_message(msg)
    types = [type(ev).__name__ for ev in out]
    assert types == [
        "ModelTurnStartedEvent",
        "TextEmittedEvent",
        "ModelTurnEndedEvent",
        "CostRecordedEvent",
    ]
    assert isinstance(out[0], ModelTurnStartedEvent)
    assert isinstance(out[1], TextEmittedEvent) and out[1].data.avp_text == "hi there"
    assert isinstance(out[2], ModelTurnEndedEvent)
    assert out[2].data.gen_ai_usage_input_tokens == 100
    assert out[2].data.gen_ai_usage_output_tokens == 25
    assert out[2].data.avp_cost_usd > 0
    assert isinstance(out[3], CostRecordedEvent)
    assert out[3].data.avp_state.total_turns == 1


def test_cumulative_usage_yields_per_turn_deltas() -> None:
    """The Claude Agent SDK reports usage as cumulative-per-message — every
    AssistantMessage carries the running session total so far, NOT the delta
    for that turn alone. The translator MUST subtract the previous cumulative
    to populate AVP's per-turn ModelTurnEnded.

    Pre-fix this test would have failed: turn 2 would show the same
    cumulative cost / tokens as turn 1, double-counting.
    """
    t, out = _new_translator()

    # Turn 1: cumulative 100 input / 20 output
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("first")],
            usage={"input_tokens": 100, "output_tokens": 20},
            model="claude-sonnet-4-6",
        )
    )
    # Turn 2: cumulative 250 input / 50 output  (delta is 150 / 30)
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("second")],
            usage={"input_tokens": 250, "output_tokens": 50},
            model="claude-sonnet-4-6",
        )
    )

    turn_ended = [ev for ev in out if isinstance(ev, ModelTurnEndedEvent)]
    assert len(turn_ended) == 2

    # Turn 1 = its own cumulative (no prior context)
    assert turn_ended[0].data.gen_ai_usage_input_tokens == 100
    assert turn_ended[0].data.gen_ai_usage_output_tokens == 20

    # Turn 2 = delta, NOT cumulative. This is the load-bearing assertion.
    assert turn_ended[1].data.gen_ai_usage_input_tokens == 150, (
        f"expected delta 150 (cumulative 250 - prior 100), got {turn_ended[1].data.gen_ai_usage_input_tokens} — "
        f"translator likely treating cumulative usage as per-turn"
    )
    assert turn_ended[1].data.gen_ai_usage_output_tokens == 30, (
        f"expected delta 30, got {turn_ended[1].data.gen_ai_usage_output_tokens} — "
        f"output token cumulative-vs-delta bug"
    )

    # Cost deltas: turn 1 cost should be smaller than turn 2 cost (more tokens).
    assert turn_ended[0].data.avp_cost_usd > 0
    assert turn_ended[1].data.avp_cost_usd > turn_ended[0].data.avp_cost_usd

    # State after both turns: cumulative totals should reconcile with the SDK.
    cost_recorded = [ev for ev in out if type(ev).__name__ == "CostRecordedEvent"]
    final_state = cost_recorded[-1].data.avp_state
    assert final_state.total_turns == 2
    assert final_state.total_tokens == 300  # 100 + 20 + 150 + 30 = 300


def test_pre_and_post_tool_use_hooks_emit_invoked_and_returned() -> None:
    t, out = _new_translator()

    pre_input = {
        "tool_use_id": "c1",
        "tool_name": "bash",
        "tool_input": {"command": "ls"},
    }
    post_input = {
        "tool_use_id": "c1",
        "tool_name": "bash",
        "tool_response": "file1\nfile2",
    }
    asyncio.run(t._on_pre_tool_use_hook(pre_input, "c1", None))
    asyncio.run(t._on_post_tool_use_hook(post_input, "c1", None))

    assert isinstance(out[0], ToolInvokedEvent)
    assert out[0].data.gen_ai_tool_call_id == "c1"
    assert out[0].data.gen_ai_tool_name == "bash"
    assert out[0].data.gen_ai_tool_call_arguments == {"command": "ls"}
    assert isinstance(out[1], ToolReturnedEvent)
    assert out[1].data.avp_tool_result_text == "file1\nfile2"


def test_run_with_fake_query_emits_full_lifecycle() -> None:
    """End-to-end happy path: agent_started → assistant turn → result → agent_stopped."""

    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("done")],
                usage={"input_tokens": 50, "output_tokens": 12},
            ),
            ResultMessage(total_cost_usd=0.0042),
        ]
    ]
    t, out = _new_translator(sdk_client_cls=_client_factory(rounds=rounds))
    stop = t.run()

    assert isinstance(stop, AgentStoppedEvent)
    assert stop.data.avp_reason == StopReason.converged
    # Start, turn, ResultMessage cost reconciliation, agent_stopped
    types = [type(ev).__name__ for ev in out]
    assert types[0] == "AgentStartedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert types.count("CostRecordedEvent") >= 1
    assert types[-1] == "AgentStoppedEvent"
    # SDK-reported cost wins
    assert abs(stop.data.avp_total_cost_usd - 0.0042) < 1e-9


def test_assistant_message_with_no_new_output_or_content_is_not_a_turn() -> None:
    """trajectory.md §3.1: a 'turn' is one fresh model call with new
    output. The Claude Agent SDK emits AssistantMessages for non-turn
    things (continuations, restatements). The translator MUST skip
    those — count AVP turns only when delta_output > 0 OR new content
    is present.

    Pre-fix the translator incremented _step on every AssistantMessage,
    inflating state.total_turns above what the spec promises."""
    t, out = _new_translator()

    # Real turn 1
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("real")],
            usage={"input_tokens": 100, "output_tokens": 20},
            model="claude-sonnet-4-6",
        )
    )
    # SDK-internal restatement: same cumulative as before, no new content
    t._handle_assistant_message(
        AssistantMessage(
            content=[],
            usage={"input_tokens": 100, "output_tokens": 20},  # same as turn 1
            model="claude-sonnet-4-6",
        )
    )
    # Real turn 2
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("more")],
            usage={"input_tokens": 200, "output_tokens": 35},
            model="claude-sonnet-4-6",
        )
    )

    turn_ended = [ev for ev in out if isinstance(ev, ModelTurnEndedEvent)]
    assert len(turn_ended) == 2, "expected exactly 2 turns (the empty restatement should NOT count)"
    assert turn_ended[0].data.step == 1
    assert turn_ended[1].data.step == 2


def test_unannounced_cumulative_reset_emits_error_occurred() -> None:
    """trajectory.md §3.3: when the SDK's cumulative usage drops without
    a PreCompact / SubagentStart signal, the translator MUST emit
    error_occurred (code='accounting_reset') rather than silently
    clamping. Consumers cannot tell silent clamping apart from a quiet
    turn."""
    t, out = _new_translator()

    # Turn 1: cumulative 100 input
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("first")],
            usage={"input_tokens": 100, "output_tokens": 20},
            model="claude-sonnet-4-6",
        )
    )
    # Turn 2: cumulative DROPS to 50 input — unannounced reset
    t._handle_assistant_message(
        AssistantMessage(
            content=[
                TextBlock("after-reset"),
            ],
            usage={"input_tokens": 50, "output_tokens": 5},
            model="claude-sonnet-4-6",
        )
    )

    types = [type(ev).__name__ for ev in out]
    assert "ErrorOccurredEvent" in types
    err = next(ev for ev in out if type(ev).__name__ == "ErrorOccurredEvent")
    assert err.data.avp_error_code.value == "accounting_reset"


def test_baseline_reset_hook_handles_legitimate_compaction_gracefully() -> None:
    """A PreCompact / SubagentStart hook fire signals that the SDK is about
    to reset its cumulative usage counters. The translator MUST adopt the
    next message's cumulative as a fresh baseline rather than emitting
    accounting_reset."""
    import asyncio

    t, out = _new_translator()

    # Turn 1: cumulative 100 input
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("first")],
            usage={"input_tokens": 100, "output_tokens": 20},
            model="claude-sonnet-4-6",
        )
    )
    # Compaction signal
    asyncio.run(t._on_baseline_reset_hook({}, None, None))

    # Turn 2 after compaction: cumulative starts fresh at 30 — would normally
    # look like a drop, but the hook preceded so it's accepted as new baseline.
    t._handle_assistant_message(
        AssistantMessage(
            content=[TextBlock("after-compact")],
            usage={"input_tokens": 30, "output_tokens": 8},
            model="claude-sonnet-4-6",
        )
    )

    types = [type(ev).__name__ for ev in out]
    assert "ErrorOccurredEvent" not in types, (
        "PreCompact-preceded reset should NOT emit accounting_reset"
    )
    # The post-compact message IS a real turn (has new content)
    turn_ended = [ev for ev in out if isinstance(ev, ModelTurnEndedEvent)]
    assert len(turn_ended) == 2


def test_run_propagates_sdk_error_to_agent_stopped_error() -> None:
    """An SDK call that raises is wrapped: error_occurred + agent_stopped reason='error'."""
    t, out = _new_translator(sdk_client_cls=_client_factory(raise_on_invoke=RuntimeError("boom")))
    stop = t.run()
    assert stop.data.avp_reason == StopReason.error
    types = [type(ev).__name__ for ev in out]
    assert "ErrorOccurredEvent" in types
    assert types[-1] == "AgentStoppedEvent"
