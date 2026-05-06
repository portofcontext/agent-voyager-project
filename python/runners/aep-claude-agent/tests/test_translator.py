"""Translator tests for ClaudeAgentTranslator.

The SDK is fully decoupled via injection (sdk_client_cls / sdk_options_cls /
sdk_hook_matcher_cls), so these tests run without claude_agent_sdk installed
and without an API key. They exercise:

  - Config → ClaudeAgentOptions translation (_build_sdk_options)
  - AssistantMessage / ResultMessage handling (the message-stream path)
  - PreToolUse / PostToolUse hook callbacks (the hook path)
  - Full run() lifecycle with a fake ClaudeSDKClient that yields canned messages
  - Verifier dispatch at all four trigger points (before_first_turn,
    after_each_turn, on_tool:<name>, at_end)
  - on_failure: halt aborts with reason=verifier_failed
  - on_failure: inject_correction queues the correction message and submits it
    via ClaudeSDKClient.query() between turns
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from aep import (
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    StopReason,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    VerifierEvaluatedEvent,
)
from aep_claude_agent import ClaudeAgentTranslator

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
    cfg: Config | None = None,
    *,
    sdk_client_cls: Callable[..., Any] | None = None,
) -> tuple[ClaudeAgentTranslator, list]:
    cfg = cfg or Config(
        schema_version="0.1",
        run_id="t1",
        model="claude-sonnet-4-6",
        prompt="hello",
        allowed_tools=["bash"],
        boundary={"max_steps": 5, "max_cost_usd": 0.50},
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
    assert ev.run_id == "t1"
    assert ev.model == "claude-sonnet-4-6"
    assert ev.prompt == "hello"


def test_build_sdk_options_maps_config_fields() -> None:
    t, _ = _new_translator()
    opts = t._build_sdk_options()
    kw = opts.kwargs
    assert kw["allowed_tools"] == ["bash"]
    assert kw["max_turns"] == 5
    assert kw["max_budget_usd"] == 0.50
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
    assert isinstance(out[1], TextEmittedEvent) and out[1].text == "hi there"
    assert isinstance(out[2], ModelTurnEndedEvent)
    assert out[2].tokens_input == 100
    assert out[2].tokens_output == 25
    assert out[2].cost_usd > 0
    assert isinstance(out[3], CostRecordedEvent)
    assert out[3].state.total_turns == 1


def test_cumulative_usage_yields_per_turn_deltas() -> None:
    """The Claude Agent SDK reports usage as cumulative-per-message — every
    AssistantMessage carries the running session total so far, NOT the delta
    for that turn alone. The translator MUST subtract the previous cumulative
    to populate AEP's per-turn ModelTurnEnded.

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
    assert turn_ended[0].tokens_input == 100
    assert turn_ended[0].tokens_output == 20

    # Turn 2 = delta, NOT cumulative. This is the load-bearing assertion.
    assert turn_ended[1].tokens_input == 150, (
        f"expected delta 150 (cumulative 250 - prior 100), got {turn_ended[1].tokens_input} — "
        f"translator likely treating cumulative usage as per-turn"
    )
    assert turn_ended[1].tokens_output == 30, (
        f"expected delta 30, got {turn_ended[1].tokens_output} — "
        f"output token cumulative-vs-delta bug"
    )

    # Cost deltas: turn 1 cost should be smaller than turn 2 cost (more tokens).
    assert turn_ended[0].cost_usd > 0
    assert turn_ended[1].cost_usd > turn_ended[0].cost_usd

    # State after both turns: cumulative totals should reconcile with the SDK.
    cost_recorded = [ev for ev in out if type(ev).__name__ == "CostRecordedEvent"]
    final_state = cost_recorded[-1].state
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
    assert out[0].call_id == "c1"
    assert out[0].tool == "bash"
    assert out[0].input == {"command": "ls"}
    assert isinstance(out[1], ToolReturnedEvent)
    assert out[1].output == "file1\nfile2"


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
    assert stop.reason == StopReason.converged
    # Start, turn, ResultMessage cost reconciliation, agent_stopped
    types = [type(ev).__name__ for ev in out]
    assert types[0] == "AgentStartedEvent"
    assert "ModelTurnStartedEvent" in types
    assert "ModelTurnEndedEvent" in types
    assert types.count("CostRecordedEvent") >= 1
    assert types[-1] == "AgentStoppedEvent"
    # SDK-reported cost wins
    assert abs(stop.total_cost_usd - 0.0042) < 1e-9


def test_assistant_message_with_no_new_output_or_content_is_not_a_turn() -> None:
    """SPEC.md §9.1: a 'turn' is one fresh model call with new output. The
    Claude Agent SDK emits AssistantMessages for non-turn things
    (continuations, restatements). The translator MUST skip those — count
    AEP turns only when delta_output > 0 OR new content is present.

    Pre-fix the translator incremented _step on every AssistantMessage,
    inflating state.total_turns above what AEP §9.2 promises."""
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
    assert turn_ended[0].step == 1
    assert turn_ended[1].step == 2


def test_unannounced_cumulative_reset_emits_error_occurred() -> None:
    """SPEC.md §9.4: when the SDK's cumulative usage drops without a
    PreCompact / SubagentStart signal, the translator MUST emit
    error_occurred (code='accounting_reset') rather than silently clamping.
    Consumers cannot tell silent clamping apart from a quiet turn."""
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
    assert err.code.value == "accounting_reset"


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
    assert stop.reason == StopReason.error
    types = [type(ev).__name__ for ev in out]
    assert "ErrorOccurredEvent" in types
    assert types[-1] == "AgentStoppedEvent"


# ── Verifier dispatch (SPEC §13.1.13–18) ─────────────────────────────────────


def _cfg_with_verifiers(verifiers: list[dict[str, Any]]) -> Config:
    return Config(
        schema_version="0.1",
        run_id="vt",
        model="claude-sonnet-4-6",
        prompt="hello",
        allowed_tools=["bash"],
        verifiers=verifiers,
        boundary={"max_steps": 5},
    )


def test_inject_correction_splices_followup_user_prompt() -> None:
    """A verifier with on_failure=inject_correction queues its
    correction_message; the translator submits it as a follow-up user prompt
    via ClaudeSDKClient.query() between turns. The agent then sees the
    correction in its next model call.

    Mirrors the AEPRunner driver-pattern semantics — driver appends user-role
    to history, translator hands the same content to the SDK as a follow-up
    user prompt.
    """
    rounds = [
        # Turn 1: assistant emits something the verifier will catch.
        [
            AssistantMessage(
                content=[TextBlock("offending content")],
                usage={"input_tokens": 10, "output_tokens": 5},
            ),
        ],
        # Turn 2 (after correction is injected): assistant complies.
        [
            AssistantMessage(
                content=[TextBlock("corrected response")],
                usage={"input_tokens": 30, "output_tokens": 8},
            ),
            ResultMessage(total_cost_usd=0.001),
        ],
    ]
    factory = _client_factory(rounds=rounds)
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "always-fail",
                "trigger": "after_each_turn",
                # `false` for the FIRST run only — second call passes via the
                # shell trick: write a state file then check it. Simpler: keep
                # always-failing; halt by max_steps after a small bound. Or
                # use a verifier that fails twice — rounds yields ResultMessage
                # at the end so the SDK loop terminates either way.
                "source": {"shell": "false"},  # always exits 1
                "on_failure": "inject_correction",
                "correction_message": "STOP. Remove the offending content.",
            }
        ]
    )
    t, out = _new_translator(cfg, sdk_client_cls=factory)
    stop = t.run()

    # The assertions that matter:
    # 1. The translator submitted the correction as a follow-up prompt.
    captured_clients: list[_FakeClient] = []
    # We can't get the client back through the factory directly, but we can
    # confirm the correction was queued and drained by checking the trajectory.

    # 2. Trajectory contains verifier_evaluated(passed=False) followed by a
    #    second turn — proof that the splice worked and the SDK got more
    #    messages to dispatch.
    assert stop.reason == StopReason.converged
    types = [type(ev).__name__ for ev in out]
    evals = [ev for ev in out if isinstance(ev, VerifierEvaluatedEvent)]
    assert len(evals) >= 1
    assert evals[0].passed is False
    assert evals[0].name == "always-fail"

    turn_ended = [ev for ev in out if isinstance(ev, ModelTurnEndedEvent)]
    assert len(turn_ended) == 2, (
        "expected 2 turns (initial + post-correction); got "
        f"{len(turn_ended)}. Inject_correction must produce a follow-up turn."
    )

    # No error_occurred: inject_correction is a SUPPORTED action on this runner.
    assert "ErrorOccurredEvent" not in types, (
        "inject_correction must not raise error_occurred — it's supported."
    )
    _ = captured_clients  # silence unused


def test_inject_correction_passes_correction_message_to_client_query() -> None:
    """Stronger assertion: the correction_message text is the literal prompt
    handed to ClaudeSDKClient.query()."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("first")], usage={"input_tokens": 5, "output_tokens": 2}
            )
        ],
        [
            AssistantMessage(
                content=[TextBlock("second")], usage={"input_tokens": 8, "output_tokens": 2}
            ),
            ResultMessage(total_cost_usd=0.0001),
        ],
    ]
    captured_client: list[_FakeClient] = []

    def factory(options: Any = None) -> _FakeClient:
        c = _FakeClient(rounds=rounds, options=options)
        captured_client.append(c)
        return c

    cfg = _cfg_with_verifiers(
        [
            {
                "name": "redirect",
                "trigger": "after_each_turn",
                "source": {"shell": "false"},
                "on_failure": "inject_correction",
                "correction_message": "Try a different approach.",
            }
        ]
    )
    t, _ = _new_translator(cfg, sdk_client_cls=factory)
    t.run()

    assert len(captured_client) == 1
    client = captured_client[0]
    assert client.connect_prompt == "hello"
    # Every follow-up query MUST be the correction message (the verifier fails
    # every turn, so the correction is re-submitted after each turn — that's
    # exactly the behavior we want to pin: the splice routes through query()).
    assert client.queries, "expected at least one follow-up query carrying the correction"
    assert all(q == "Try a different approach." for q in client.queries), (
        f"every follow-up query must equal the correction_message verbatim; got {client.queries}"
    )


def test_after_each_turn_verifier_fires_and_emits_evaluated() -> None:
    """A passing verifier with trigger=after_each_turn fires after every
    model_turn_ended and emits verifier_evaluated(passed=True)."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("a")],
                usage={"input_tokens": 10, "output_tokens": 5},
            ),
            AssistantMessage(
                content=[TextBlock("b")],
                usage={"input_tokens": 30, "output_tokens": 10},
            ),
            ResultMessage(total_cost_usd=0.001),
        ]
    ]
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "always-pass",
                "trigger": "after_each_turn",
                "source": {"shell": "true"},
                "on_failure": "continue",
            }
        ]
    )
    t, out = _new_translator(cfg, sdk_client_cls=_client_factory(rounds=rounds))
    stop = t.run()

    assert stop.reason == StopReason.converged
    evals = [ev for ev in out if isinstance(ev, VerifierEvaluatedEvent)]
    assert len(evals) == 2, "expected one verifier_evaluated per turn (2 turns ran)"
    for ev in evals:
        assert ev.name == "always-pass"
        assert ev.passed is True
        assert ev.error is None


def test_on_tool_verifier_fires_after_post_tool_use() -> None:
    """A verifier with trigger=on_tool:<name> fires after the named tool's
    PostToolUse hook (which is also where tool_returned is emitted)."""
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "post-bash-check",
                "trigger": "on_tool:bash",
                "source": {"shell": "true"},
                "on_failure": "continue",
            }
        ]
    )
    t, out = _new_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {"tool_use_id": "c1", "tool_name": "bash", "tool_input": {"command": "ls"}},
            "c1",
            None,
        )
    )
    asyncio.run(
        t._on_post_tool_use_hook(
            {"tool_use_id": "c1", "tool_name": "bash", "tool_response": "out"},
            "c1",
            None,
        )
    )

    types = [type(ev).__name__ for ev in out]
    # tool_invoked → tool_returned → verifier_evaluated
    assert types == ["ToolInvokedEvent", "ToolReturnedEvent", "VerifierEvaluatedEvent"]
    assert out[2].name == "post-bash-check"
    assert out[2].passed is True


def test_on_tool_verifier_does_not_fire_for_other_tools() -> None:
    """on_tool:<name> only fires for the named tool — not for unrelated calls."""
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "post-bash-only",
                "trigger": "on_tool:bash",
                "source": {"shell": "true"},
                "on_failure": "continue",
            }
        ]
    )
    t, out = _new_translator(cfg)

    asyncio.run(
        t._on_pre_tool_use_hook(
            {"tool_use_id": "c1", "tool_name": "Read", "tool_input": {"path": "x"}},
            "c1",
            None,
        )
    )
    asyncio.run(
        t._on_post_tool_use_hook(
            {"tool_use_id": "c1", "tool_name": "Read", "tool_response": "data"},
            "c1",
            None,
        )
    )

    types = [type(ev).__name__ for ev in out]
    assert types == ["ToolInvokedEvent", "ToolReturnedEvent"]
    # No verifier_evaluated — the verifier is keyed to bash, not Read.


def test_at_end_verifier_fires_before_agent_stopped() -> None:
    """SPEC §7.2: at_end fires once after the final turn, before agent_stopped."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("done")], usage={"input_tokens": 10, "output_tokens": 3}
            ),
            ResultMessage(total_cost_usd=0.0001),
        ]
    ]
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "final-check",
                "trigger": "at_end",
                "source": {"shell": "true"},
                "on_failure": "continue",
            }
        ]
    )
    t, out = _new_translator(cfg, sdk_client_cls=_client_factory(rounds=rounds))
    stop = t.run()

    assert stop.reason == StopReason.converged
    types = [type(ev).__name__ for ev in out]
    # The last verifier_evaluated must precede agent_stopped.
    last_eval_idx = max(i for i, n in enumerate(types) if n == "VerifierEvaluatedEvent")
    last_stop_idx = types.index("AgentStoppedEvent")
    assert last_eval_idx < last_stop_idx
    final_eval = out[last_eval_idx]
    assert final_eval.name == "final-check"


def test_halt_verifier_terminates_with_verifier_failed() -> None:
    """A failing verifier with on_failure=halt aborts the SDK iteration and
    produces agent_stopped(reason=verifier_failed)."""
    rounds = [
        [
            AssistantMessage(
                content=[TextBlock("doomed")], usage={"input_tokens": 10, "output_tokens": 3}
            ),
            # If halt didn't actually abort, we'd see this message too —
            # halt raises _VerifierHalt mid-iteration which propagates out
            # of receive_response.
            AssistantMessage(
                content=[TextBlock("should-not-emit")],
                usage={"input_tokens": 25, "output_tokens": 5},
            ),
            ResultMessage(total_cost_usd=0.001),
        ]
    ]
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "always-fail",
                "trigger": "after_each_turn",
                "source": {"shell": "false"},  # exits 1 → passed=False
                "on_failure": "halt",
            }
        ]
    )
    t, out = _new_translator(cfg, sdk_client_cls=_client_factory(rounds=rounds))
    stop = t.run()

    assert stop.reason == StopReason.verifier_failed
    # Exactly one verifier_evaluated — the halting one.
    evals = [ev for ev in out if isinstance(ev, VerifierEvaluatedEvent)]
    assert len(evals) == 1
    assert evals[0].name == "always-fail"
    assert evals[0].passed is False
    # Only one model turn observed — the second was aborted by halt.
    turn_ended = [ev for ev in out if isinstance(ev, ModelTurnEndedEvent)]
    assert len(turn_ended) == 1, "halt should have aborted before turn 2"


def test_before_first_turn_verifier_fires_on_first_user_prompt_submit() -> None:
    """before_first_turn fires on the FIRST UserPromptSubmit hook fire only.
    Subsequent fires are not first turns."""
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "preflight",
                "trigger": "before_first_turn",
                "source": {"shell": "true"},
                "on_failure": "continue",
            }
        ]
    )
    t, out = _new_translator(cfg)

    asyncio.run(t._on_user_prompt_submit_hook({}, None, None))
    asyncio.run(t._on_user_prompt_submit_hook({}, None, None))  # second fire — should NOT re-run

    evals = [ev for ev in out if isinstance(ev, VerifierEvaluatedEvent)]
    assert len(evals) == 1, "before_first_turn should fire exactly once"
    assert evals[0].name == "preflight"


def test_verifier_source_unavailable_marks_error_distinguisher() -> None:
    """SPEC §7.5 / VerifierError.source_unavailable: when the verifier's
    shell command can't be located (exit 127), passed=False AND
    error='source_unavailable' so consumers can distinguish 'environment
    broken' from 'rule legitimately failed'."""
    cfg = _cfg_with_verifiers(
        [
            {
                "name": "missing-script",
                "trigger": "before_first_turn",
                "source": {"shell": "no-such-command-exists-anywhere-12345"},
                "on_failure": "continue",
            }
        ]
    )
    t, out = _new_translator(cfg)
    asyncio.run(t._on_user_prompt_submit_hook({}, None, None))

    evals = [ev for ev in out if isinstance(ev, VerifierEvaluatedEvent)]
    assert len(evals) == 1
    assert evals[0].passed is False
    assert evals[0].error is not None
    assert evals[0].error.value == "source_unavailable"
