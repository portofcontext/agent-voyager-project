"""ClaudeAgentTranslator — observer/translator that turns Claude Agent SDK
lifecycle events into AEP v0.1 events.

Structurally different from aep-anthropic's driver pattern: the Claude Agent
SDK owns the agent loop, so we cannot drive turns ourselves. Instead, we wire
into the SDK's two natural observation surfaces:

  1. The async message stream from `query()` — delivers AssistantMessage
     (one per model call) and ResultMessage (final usage). We emit
     model_turn_started/ended, text_emitted, and cost_recorded from these.
  2. Claude Code hooks — registered through ClaudeAgentOptions.hooks.
     PreToolUse fires before each tool invocation; PostToolUse fires after.
     We emit tool_invoked / tool_returned from these. Hooks return `{}` to
     pass through (no-op observability — we observe, we don't gate).

Config → SDK options mapping is in `_build_sdk_options`. The supervisor's
`allowed_tools` is enforced natively by the SDK via ClaudeAgentOptions; the
boundary becomes max_turns + max_budget_usd. Verifiers are dispatched by
the translator at the SDK lifecycle hooks that map to AEP triggers
(UserPromptSubmit → before_first_turn, AssistantMessage post-emit →
after_each_turn, PostToolUse → on_tool:<name>, run() finalizer → at_end).
on_failure=halt aborts the SDK iteration with reason=verifier_failed;
on_failure=continue is a no-op; on_failure=inject_correction queues the
correction message and submits it as a follow-up user prompt via
`ClaudeSDKClient.query()` between turns — the same semantic as the driver
runner appending to history, just plumbed through the SDK's multi-turn
control surface.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import subprocess
import warnings
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from aep import (
    ZERO_SPAN_ID,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    Config,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    RunStateSnapshot,
    Source,
    StopReason,
    Subagent,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    TextEmittedData,
    TextEmittedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedData,
    VerifierEvaluatedEvent,
    new_span_id,
    new_trace_id,
)
from aep.enums import ErrorCode, OnFailure, VerifierError
from aep.types import now_iso

logger = logging.getLogger(__name__)


# ── Pricing (mirrors aep-anthropic's table; cost not surfaced by the SDK per turn) ──


@dataclass(frozen=True)
class _ModelPrice:
    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


_DEFAULT_PRICES: dict[str, _ModelPrice] = {
    "claude-opus-4-7": _ModelPrice(input=15.0, output=75.0, cache_read=1.50, cache_write=18.75),
    "claude-sonnet-4-6": _ModelPrice(input=3.0, output=15.0, cache_read=0.30, cache_write=3.75),
    "claude-haiku-4-5-20251001": _ModelPrice(
        input=1.0, output=5.0, cache_read=0.10, cache_write=1.25
    ),
}


def _compute_cost(model: str, usage: dict[str, Any] | None) -> tuple[int, int, int, int, float]:
    """Return (tokens_input, tokens_output, cache_read, cache_write, cost_usd) for one turn.

    AEP convention: tokens_input INCLUDES cache reads. Anthropic reports the
    fresh-only number, so we add cache reads/writes back."""
    if not usage:
        return 0, 0, 0, 0, 0.0
    input_t = int(usage.get("input_tokens", 0) or 0)
    output_t = int(usage.get("output_tokens", 0) or 0)
    cache_r = int(usage.get("cache_read_input_tokens", 0) or 0)
    cache_w = int(usage.get("cache_creation_input_tokens", 0) or 0)
    aep_input = input_t + cache_r + cache_w

    p = _DEFAULT_PRICES.get(model)
    if p is None:
        warnings.warn(
            f"aep-claude-agent: no price for model {model!r}; cost reported as 0.0", stacklevel=2
        )
        return aep_input, output_t, cache_r, cache_w, 0.0
    fresh = max(0, aep_input - cache_r - cache_w)
    cost = (
        fresh * p.input / 1_000_000
        + cache_r * p.cache_read / 1_000_000
        + cache_w * p.cache_write / 1_000_000
        + output_t * p.output / 1_000_000
    )
    return aep_input, output_t, cache_r, cache_w, cost


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


class _VerifierHalt(Exception):
    """Raised by the verifier-action dispatcher when a halt action fires.

    `success` distinguishes halt-on-success (declarative convergence,
    maps to `StopReason.converged`) from halt-on-failure (invariant
    broken, maps to `StopReason.verifier_failed`).
    """

    def __init__(self, *, success: bool = False) -> None:
        self.success = success
        super().__init__(
            "verifier halted run "
            + ("on success (declarative convergence)" if success else "on failure")
        )


class ClaudeAgentTranslator:
    """Translates a Claude Agent SDK run into AEP v0.1 events.

    Construct with a Config and an `on_event` callback that receives each
    emitted AEP event (Pydantic model). Call .run() to start the SDK; events
    fire as the SDK progresses.

    Optional `sdk_client_cls` / `sdk_options_cls` / `sdk_hook_matcher_cls`
    injection points let tests (and the supervisor's mock-SDK example) substitute
    fakes without installing claude_agent_sdk. `sdk_client_cls` is a callable
    that returns an object with the ClaudeSDKClient surface
    (`async with`-able, `connect()`, `query()`, `receive_response()`).
    """

    def __init__(
        self,
        config: Config,
        on_event: Callable[[BaseModel], None],
        *,
        sdk_client_cls: Callable[..., Any] | None = None,
        sdk_options_cls: type | None = None,
        sdk_hook_matcher_cls: type | None = None,
        sdk_agent_definition_cls: type | None = None,
        parent_trace_id: str | None = None,
        parent_agent_span_id: str | None = None,
        suppress_lifecycle: bool = False,
        parent_tracer: Any | None = None,
    ) -> None:
        """Translates Claude Agent SDK events to AEP wire events.

        `parent_trace_id` / `parent_agent_span_id` / `suppress_lifecycle`
        opt this translator into "delegated" mode — used by
        `traced_claude_sdk_client()` when an outer `AEPTracer` is already
        managing the run. In delegated mode the translator emits
        per-message events under the parent's trace_id/agent_span (so the
        wire is one tree) and skips its own `agent_started` / `at_end` /
        `agent_stopped` emission (the parent emits those on its own
        lifecycle bookends).
        """
        self.config = config
        self.on_event = on_event
        self._call_seq = itertools.count(1)
        self._sa_seq = itertools.count(1)
        self._step = 0
        self._started_at = now_iso()
        self._started_monotonic_ms = _monotonic_ms()
        # Span tree state. trace_id is allocated per run unless the
        # caller hands us a parent's IDs (delegated mode).
        self._trace_id = parent_trace_id or new_trace_id()
        self._agent_span_id = parent_agent_span_id or new_span_id()
        self._suppress_lifecycle = suppress_lifecycle
        # In delegated mode, push per-turn deltas into the parent tracer
        # so its cumulative state (boundary, agent_stopped totals)
        # reflects this translator's spend. Without this, the wire shows
        # real per-turn cost but agent_stopped reports zeros — see
        # `_handle_assistant_message` for the per-turn push.
        self._parent_tracer = parent_tracer
        self._current_turn_span_id: str | None = None
        self._tool_span_by_call_id: dict[str, str] = {}
        # Subagent lifecycle bookkeeping. The Claude Agent SDK surfaces a
        # subagent invocation as a parent-side `Agent` tool_use with
        # `input.subagent_type` naming the declared subagent. When PreToolUse
        # detects this we emit `subagent_invoked` (not `tool_invoked`) and
        # stash the frame span_id keyed by tool_use_id; PostToolUse pops it
        # and emits `subagent_returned`.
        self._subagents_by_name: dict[str, Subagent] = {
            sa.name: sa for sa in (config.subagents or [])
        }
        self._subagent_invocations: dict[
            str, dict[str, Any]
        ] = {}  # tool_use_id → {frame_span_id, sa_name, t0, invocation_id}
        self._total_turns = 0
        self._total_cost_usd = 0.0
        self._total_tokens = 0
        self._tools_invoked: dict[str, int] = {}
        self._turn_open = False  # True between model_turn_started and model_turn_ended
        # Claude Agent SDK reports usage as cumulative-per-message, not per-turn delta.
        # We track the previous cumulative so we can compute this turn's actual cost.
        self._prev_cumulative_input_tokens = 0
        self._prev_cumulative_output_tokens = 0
        self._prev_cumulative_cache_read = 0
        self._prev_cumulative_cache_write = 0
        self._prev_cumulative_cost_usd = 0.0
        # Set by PreCompact / SubagentStart hooks so the next AssistantMessage's
        # cumulative-drop is treated as a deliberate baseline reset (graceful)
        # rather than as an unexpected accounting reset (errored).
        self._baseline_reset_pending = False
        # First UserPromptSubmit fires before_first_turn verifiers exactly once.
        self._before_first_turn_fired = False
        # When True (default), `after_each_turn` verifiers run inline at the
        # end of `_handle_assistant_message` — matches AEPRunner / the runner
        # CLI semantics. The traced-client wrapper sets this False and runs
        # the trigger itself AFTER yielding the message to the user, so the
        # user's async-for body sees every message that completed
        # translation before a halting verifier can terminate the iterator.
        # That mirrors AEPTracer's `with tracer.turn():` semantic, where the
        # verifier fires when the with-block exits — not before.
        self._run_inline_after_each_turn = True
        # Stop hook may fire per-turn; the run() finalizer runs at_end exactly
        # once, so this flag is informational only.
        self._stop_seen = False
        # inject_correction queues correction messages here; the
        # ClaudeSDKClient.query() loop drains them between turns.
        self._pending_corrections: list[str] = []
        self._sdk_client_cls = sdk_client_cls
        self._sdk_options_cls = sdk_options_cls
        self._sdk_hook_matcher_cls = sdk_hook_matcher_cls
        self._sdk_agent_definition_cls = sdk_agent_definition_cls

    # ── Snapshot ────────────────────────────────────────────────────────────

    def _snapshot(self) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self._total_cost_usd,
            total_tokens=self._total_tokens,
            total_turns=self._total_turns,
            tools_invoked=dict(self._tools_invoked) or None,
            started_at=self._started_at,
            duration_ms=max(0, _monotonic_ms() - self._started_monotonic_ms),
        )

    def _emit(self, event: BaseModel) -> None:
        self.on_event(event)

    # ── Span helpers ────────────────────────────────────────────────────────

    def _own_span(self, parent_span_id: str) -> dict[str, str]:
        return {
            "trace_id": self._trace_id,
            "span_id": new_span_id(),
            "parent_span_id": parent_span_id,
        }

    def _shared_span(self, span_id: str, parent_span_id: str) -> dict[str, str]:
        return {
            "trace_id": self._trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
        }

    def _current_parent_for_run_event(self) -> str:
        return self._current_turn_span_id or self._agent_span_id

    # ── Public lifecycle ────────────────────────────────────────────────────

    def run(self) -> AgentStoppedEvent:
        """Start the Claude Agent SDK run and emit AEP events as it progresses.

        Returns the terminal AgentStoppedEvent."""
        self._emit_agent_started()

        reason: StopReason
        error_msg: str | None = None
        try:
            asyncio.run(self._async_invoke_sdk())
            reason = StopReason.converged
        except _VerifierHalt as halt:
            reason = StopReason.converged if halt.success else StopReason.verifier_failed
        except KeyboardInterrupt:
            reason = StopReason.interrupted
        except Exception as e:
            logger.exception("aep-claude-agent: SDK error")
            self._emit(
                ErrorOccurredEvent(
                    subject=self.config.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{
                            "aep.error.code": ErrorCode.runner_crash,
                            "aep.error.message": str(e),
                        },
                    ),
                )
            )
            reason = StopReason.error
            error_msg = str(e)
        finally:
            if self._turn_open:
                # Model was mid-turn when we exited — close the turn so the
                # trajectory is well-formed.
                assert self._current_turn_span_id is not None
                self._emit(
                    ModelTurnEndedEvent(
                        subject=self.config.run_id,
                        data=ModelTurnEndedData(
                            **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                            step=self._step,
                            duration_ms=0,
                            **{
                                "gen_ai.usage.input_tokens": 0,
                                "gen_ai.usage.output_tokens": 0,
                                "aep.cost_usd": 0.0,
                            },
                        ),
                    )
                )
                self._turn_open = False

        # at_end verifiers fire exactly once before agent_stopped. They can
        # also halt — halt-on-success keeps reason=converged; halt-on-failure
        # overrides to verifier_failed (unless a more-specific failure was
        # already set during the run, in which case we preserve it).
        try:
            self._run_verifiers_for_trigger("at_end")
        except _VerifierHalt as halt:
            if reason == StopReason.converged:
                reason = StopReason.converged if halt.success else StopReason.verifier_failed

        return self._emit_agent_stopped(reason, error_msg=error_msg)

    # ── SDK integration ────────────────────────────────────────────────────

    async def _async_invoke_sdk(self) -> None:
        """Drive the Claude Agent SDK with multi-turn control via ClaudeSDKClient.

        The outer loop alternates between (a) draining the SDK's response stream
        for the current turn (`receive_response()`) and (b) submitting any
        correction messages queued by inject_correction verifiers as a follow-up
        user prompt (`client.query(...)`). When no correction is pending after
        a response stream completes, the conversation is over and we return.

        Mirrors the AEPRunner driver-pattern semantics for inject_correction:
        the driver appends a user-role message to its in-memory history before
        the next turn; the translator hands that same content to the SDK as a
        new user prompt and lets the SDK route it through its own loop. The
        agent sees a user-role correction either way.
        """
        if self._sdk_client_cls is None:
            from claude_agent_sdk import (
                AgentDefinition,
                ClaudeAgentOptions,
                ClaudeSDKClient,
                HookMatcher,
            )

            self._sdk_client_cls = ClaudeSDKClient
            self._sdk_options_cls = ClaudeAgentOptions
            self._sdk_hook_matcher_cls = HookMatcher
            self._sdk_agent_definition_cls = AgentDefinition

        options = self._build_sdk_options()
        prompt = self.config.prompt or ""

        async with self._sdk_client_cls(options=options) as client:
            await client.connect(prompt)
            while True:
                async for message in client.receive_response():
                    self._on_sdk_message(message)
                # The current response stream is exhausted. If a verifier
                # queued an inject_correction during this turn, hand it to
                # the SDK as a follow-up user prompt and re-enter the
                # response loop. Otherwise the conversation is over.
                correction = self._drain_pending_correction()
                if correction is None:
                    break
                await client.query(correction)

    def _build_sdk_options(self) -> Any:
        """Translate Config → ClaudeAgentOptions.

        Mapping:
          - Config.allowed_tools  → options.allowed_tools  (SDK enforces natively)
          - Config.system_prompt  → options.system_prompt
          - Config.boundary.max_steps    → options.max_turns
          - Config.boundary.max_cost_usd → options.max_budget_usd
          - Config.model          → options.model
          - Config.subagents      → options.agents = {name: AgentDefinition(...)}
          - hooks={PreToolUse, PostToolUse} → translator-emitted tool_invoked / tool_returned
                                              OR subagent_invoked / subagent_returned when
                                              the tool_use is the SDK's `Agent` tool with
                                              a subagent_type matching a declared subagent
        """
        cfg = self.config
        assert self._sdk_options_cls is not None
        assert self._sdk_hook_matcher_cls is not None

        kwargs: dict[str, Any] = {}
        if cfg.allowed_tools is not None:
            kwargs["allowed_tools"] = list(cfg.allowed_tools)
        if cfg.system_prompt:
            kwargs["system_prompt"] = cfg.system_prompt
        if cfg.model:
            kwargs["model"] = cfg.model
        if cfg.boundary is not None:
            if cfg.boundary.max_steps is not None:
                kwargs["max_turns"] = cfg.boundary.max_steps
            if cfg.boundary.max_cost_usd is not None:
                kwargs["max_budget_usd"] = cfg.boundary.max_cost_usd
        if cfg.subagents:
            kwargs["agents"] = self._build_sdk_agents()

        kwargs["hooks"] = {
            "PreToolUse": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_pre_tool_use_hook]),
            ],
            "PostToolUse": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_post_tool_use_hook]),
            ],
            # before_first_turn verifiers fire on the first UserPromptSubmit.
            # The Claude SDK has no standalone session-start hook with prompt
            # visibility, so this is the closest equivalent.
            "UserPromptSubmit": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_user_prompt_submit_hook]),
            ],
            # at_end verifiers fire from the run() finalizer. Stop can fire
            # per-turn in some configurations; we just record the signal.
            "Stop": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_stop_hook]),
            ],
            # PreCompact + SubagentStart signal the SDK is about to reset its
            # cumulative usage counters — the translator adopts the next
            # cumulative as a fresh baseline rather than emitting accounting_reset.
            "PreCompact": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_baseline_reset_hook]),
            ],
            "SubagentStart": [
                self._sdk_hook_matcher_cls(matcher=None, hooks=[self._on_baseline_reset_hook]),
            ],
        }

        # Forward the Claude CLI's stderr to the supervisor's stderr so users
        # can see the real reason if `Command failed with exit code 1` happens.
        # Without this the underlying CLI error is swallowed and only the
        # generic "Check stderr output for details" surfaces.
        import sys as _sys

        def _forward_stderr(line: str) -> None:
            _sys.stderr.write(f"[claude-cli] {line}")
            _sys.stderr.flush()

        kwargs.setdefault("stderr", _forward_stderr)

        return self._sdk_options_cls(**kwargs)

    def _build_sdk_agents(self) -> dict[str, Any]:
        """Translate Config.subagents → ClaudeAgentOptions.agents.

        Maps the AEP Subagent shape onto Claude Agent SDK's `AgentDefinition`:

          AEP Subagent.name           → key in the agents dict
          AEP Subagent.description    → AgentDefinition.description
          AEP Subagent.system_prompt  → AgentDefinition.prompt
          AEP Subagent.model          → AgentDefinition.model
          AEP Subagent.allowed_tools  → AgentDefinition.tools (allowlist)

        v0.1 prototype: subagent.tools / verifiers / skills / inherit_tools /
        nested subagents are not yet wired into the SDK side. The Subagent
        type accepts them; this runner ignores them (with a warning would be
        louder, but the prototype's job is to demonstrate the wire shape, not
        ship full v1 mapping).

        Falls back to constructing a plain dict when AgentDefinition isn't
        injected — the SDK accepts dicts in some versions; tests rely on this.
        """
        agents: dict[str, Any] = {}
        for sa in self.config.subagents or []:
            payload: dict[str, Any] = {"description": sa.description}
            if sa.system_prompt:
                payload["prompt"] = sa.system_prompt
            if sa.model:
                payload["model"] = sa.model
            if sa.allowed_tools is not None:
                payload["tools"] = list(sa.allowed_tools)
            if self._sdk_agent_definition_cls is not None:
                agents[sa.name] = self._sdk_agent_definition_cls(**payload)
            else:
                agents[sa.name] = payload
        return agents

    def _on_sdk_message(self, message: Any) -> None:
        """Route a single SDK Message instance to translator emitters.

        Type detection is duck-typed so tests can pass plain stand-ins."""
        cls = type(message).__name__
        if cls == "AssistantMessage":
            self._handle_assistant_message(message)
        elif cls == "ResultMessage":
            self._handle_result_message(message)
        # SystemMessage / UserMessage / others — the AEP wire doesn't surface them.

    def _handle_assistant_message(self, message: Any) -> None:
        """One AssistantMessage MAY correspond to one AEP turn — or not.

        SPEC.md §9.1: an AEP turn is one fresh model call. The Claude Agent
        SDK emits AssistantMessages for things that aren't fresh calls
        (continuations, internal restatements, follow-ups around tool
        results). We use the SDK's cumulative usage to detect: a message
        with NO new output tokens AND no fresh content is not a turn — skip
        the turn-started / turn-ended emission entirely.

        SPEC.md §9.4: when the SDK's cumulative drops without a deliberate
        reset signal (PreCompact / SubagentStart), emit error_occurred
        rather than silently clamping the delta.
        """
        cfg = self.config
        usage = getattr(message, "usage", None)
        model_id = getattr(message, "model", cfg.model or "unspecified")
        cum_ti, cum_to, cum_cr, cum_cw, cum_cost = _compute_cost(model_id, usage)

        # Detect unexpected cumulative-reset BEFORE computing deltas.
        unexpected_reset = (
            cum_ti < self._prev_cumulative_input_tokens
            or cum_to < self._prev_cumulative_output_tokens
            or cum_cost < self._prev_cumulative_cost_usd
        ) and not self._baseline_reset_pending
        if unexpected_reset:
            self._emit(
                ErrorOccurredEvent(
                    subject=cfg.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{
                            "aep.error.code": ErrorCode.accounting_reset,
                            "aep.error.message": (
                                "SDK cumulative usage dropped without a PreCompact / "
                                "SubagentStart signal. Per-turn deltas may be unreliable; "
                                "treat state.total_tokens / total_cost_usd as a lower bound."
                            ),
                        },
                    ),
                )
            )
            # Reset our baseline to the new cumulative so subsequent messages
            # produce sane deltas rather than a cascade of negative-delta errors.
            self._prev_cumulative_input_tokens = cum_ti
            self._prev_cumulative_output_tokens = cum_to
            self._prev_cumulative_cache_read = cum_cr
            self._prev_cumulative_cache_write = cum_cw
            self._prev_cumulative_cost_usd = cum_cost
            return

        if self._baseline_reset_pending:
            # PreCompact / SubagentStart fired: the next cumulative is a
            # fresh-start total, not a delta from prior. Adopt it directly.
            self._prev_cumulative_input_tokens = cum_ti
            self._prev_cumulative_output_tokens = cum_to
            self._prev_cumulative_cache_read = cum_cr
            self._prev_cumulative_cache_write = cum_cw
            self._prev_cumulative_cost_usd = cum_cost
            self._baseline_reset_pending = False
            # The first post-reset message IS a real turn IFF it has new content;
            # fall through to the regular emission path with prev=cum (delta=0).

        delta_ti = max(0, cum_ti - self._prev_cumulative_input_tokens)
        delta_to = max(0, cum_to - self._prev_cumulative_output_tokens)
        delta_cr = max(0, cum_cr - self._prev_cumulative_cache_read)
        delta_cw = max(0, cum_cw - self._prev_cumulative_cache_write)
        delta_cost = max(0.0, cum_cost - self._prev_cumulative_cost_usd)

        # Determine whether this message represents a real AEP turn. Two
        # signals: (a) the SDK reported new output tokens, OR (b) the message
        # carries content the model produced (TextBlocks). Empty deltas with
        # no content = SDK-internal restatement, not a turn.
        has_text_content = any(
            type(b).__name__ == "TextBlock" and getattr(b, "text", "")
            for b in (getattr(message, "content", []) or [])
        )
        is_real_turn = delta_to > 0 or has_text_content

        if not is_real_turn:
            # Don't bump _step or emit turn events — this isn't a turn.
            return

        self._step += 1
        self._current_turn_span_id = new_span_id()
        self._emit(
            ModelTurnStartedEvent(
                subject=cfg.run_id,
                data=ModelTurnStartedData(
                    **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                    step=self._step,
                ),
            )
        )
        self._turn_open = True

        for block in getattr(message, "content", []) or []:
            btype = type(block).__name__
            if btype == "TextBlock":
                text = getattr(block, "text", None)
                if text:
                    self._emit(
                        TextEmittedEvent(
                            subject=cfg.run_id,
                            data=TextEmittedData(
                                **self._own_span(self._current_turn_span_id),
                                step=self._step,
                                **{"aep.text": text},
                            ),
                        )
                    )
            # ToolUseBlock content is observed via the PreToolUse hook (which
            # fires in step with the SDK's actual tool dispatch).

        self._prev_cumulative_input_tokens = cum_ti
        self._prev_cumulative_output_tokens = cum_to
        self._prev_cumulative_cache_read = cum_cr
        self._prev_cumulative_cache_write = cum_cw
        self._prev_cumulative_cost_usd = cum_cost

        ended_kwargs: dict[str, Any] = {
            "gen_ai.usage.input_tokens": delta_ti,
            "gen_ai.usage.output_tokens": delta_to,
            "aep.cost_usd": delta_cost,
            "gen_ai.response.model": model_id,
        }
        if delta_cr:
            ended_kwargs["gen_ai.usage.cache_read.input_tokens"] = delta_cr
        if delta_cw:
            ended_kwargs["gen_ai.usage.cache_creation.input_tokens"] = delta_cw

        self._emit(
            ModelTurnEndedEvent(
                subject=cfg.run_id,
                data=ModelTurnEndedData(
                    **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                    step=self._step,
                    duration_ms=0,  # the SDK message doesn't carry per-turn duration
                    **ended_kwargs,
                ),
            )
        )
        self._turn_open = False

        self._total_turns += 1
        self._total_cost_usd += delta_cost
        self._total_tokens += delta_ti + delta_to
        # Delegated mode: also push the delta into the parent tracer's
        # cumulative state. Without this push, the parent's
        # `agent_stopped.aep_state` shows zeros and parent-side
        # boundary checks (max_steps / max_cost_usd / max_tokens) miss
        # all CASDK-driven turns.
        if self._parent_tracer is not None:
            self._parent_tracer.accumulate_external(
                tokens_input=delta_ti,
                tokens_output=delta_to,
                cost_usd=delta_cost,
                cache_read=delta_cr,
                cache_write=delta_cw,
            )
        self._emit(
            CostRecordedEvent(
                subject=cfg.run_id,
                data=CostRecordedData(
                    **self._own_span(self._current_turn_span_id),
                    **{"aep.state": self._snapshot()},
                ),
            )
        )

        # SPEC.md §7.2: after_each_turn fires after model_turn_ended.
        # _VerifierHalt raised here propagates through the SDK's async-for
        # iteration into asyncio.run() and is caught by run(). The traced
        # client opts out (sets `_run_inline_after_each_turn=False`) and
        # dispatches the trigger itself after yielding the message, so the
        # user's loop body always sees a message that completed translation.
        if self._run_inline_after_each_turn:
            self._run_verifiers_for_trigger("after_each_turn")

    def _handle_result_message(self, message: Any) -> None:
        """ResultMessage closes the run with authoritative cost. Reconcile if it
        differs from our per-turn sum (the SDK's number wins)."""
        sdk_cost = getattr(message, "total_cost_usd", None)
        if sdk_cost is not None:
            self._total_cost_usd = float(sdk_cost)
            self._emit(
                CostRecordedEvent(
                    subject=self.config.run_id,
                    data=CostRecordedData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **{"aep.state": self._snapshot()},
                    ),
                )
            )

    # ── Hook callbacks (Claude Code hooks) ─────────────────────────────────

    async def _on_pre_tool_use_hook(
        self, input_data: dict[str, Any], tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired before each tool invocation. Emits tool_invoked —
        OR `subagent_invoked` if the tool_use is the SDK's `Agent` tool with
        a `subagent_type` matching a declared Config.subagent.

        Returns `{}` (no override) — the translator observes; it does not gate."""
        call_id = str(input_data.get("tool_use_id") or tool_use_id or f"sdk-{next(self._call_seq)}")
        tool = str(input_data.get("tool_name", "unknown"))
        tool_input = input_data.get("tool_input", {}) or {}

        # Subagent dispatch: Claude Agent SDK exposes the parent's invocation
        # of a declared subagent as a `tool_use` whose name is `Agent` and
        # whose input includes `subagent_type`. The actual subagent run is
        # opaque to the parent's observer surface (per CASDK research) — the
        # parent only sees this one tool_use → tool_result pair. AEP surfaces
        # it as `subagent_invoked` / `subagent_returned` so consumers don't
        # have to special-case the `Agent` tool at every layer.
        sa_name: str | None = None
        if tool == "Agent":
            candidate = tool_input.get("subagent_type")
            if isinstance(candidate, str) and candidate in self._subagents_by_name:
                sa_name = candidate

        if sa_name is not None:
            self._handle_subagent_pre(call_id=call_id, sa_name=sa_name, tool_input=tool_input)
            return {}

        tool_span_id = new_span_id()
        self._tool_span_by_call_id[call_id] = tool_span_id
        parent = self._current_turn_span_id or self._agent_span_id
        self._emit(
            ToolInvokedEvent(
                subject=self.config.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    **{
                        "gen_ai.tool.call.id": call_id,
                        "gen_ai.tool.name": tool,
                        "gen_ai.tool.call.arguments": dict(tool_input),
                        "aep.tool.dispatch_target": "local",
                    },
                ),
            )
        )
        self._tools_invoked[tool] = self._tools_invoked.get(tool, 0) + 1
        return {}

    async def _on_post_tool_use_hook(
        self, input_data: dict[str, Any], tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired after each tool invocation. Emits tool_returned —
        OR `subagent_returned` if the matching pre-hook had diverted to the
        subagent lifecycle. Fires `on_tool:<tool_name>` verifiers in both
        cases (the model still saw a tool result; downstream verifiers can
        match on the SDK's `Agent` tool name if they want subagent-call
        semantics)."""
        call_id = str(input_data.get("tool_use_id") or tool_use_id or "unknown")
        tool = str(input_data.get("tool_name", "unknown"))
        response = input_data.get("tool_response", "")

        if call_id in self._subagent_invocations:
            self._handle_subagent_post(call_id=call_id, response=response)
            self._run_verifiers_for_trigger(f"on_tool:{tool}")
            return {}

        output: str
        output_structured: Any | None
        if not isinstance(response, str):
            try:
                import json

                output = json.dumps(response)
                output_structured = response
            except (TypeError, ValueError):
                output = str(response)
                output_structured = None
        else:
            output = response
            output_structured = None
        tool_span_id = self._tool_span_by_call_id.get(call_id, new_span_id())
        parent = self._current_turn_span_id or self._agent_span_id
        returned_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": call_id,
            "gen_ai.tool.name": tool,
            "aep.tool.result.text": output,
        }
        if output_structured is not None:
            returned_kwargs["aep.tool.result.structured"] = output_structured
        self._emit(
            ToolReturnedEvent(
                subject=self.config.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, parent),
                    step=self._step,
                    duration_ms=0,
                    **returned_kwargs,
                ),
            )
        )
        # SPEC.md §7.2: on_tool:<name> fires after tool_returned for the named
        # tool. _VerifierHalt raised here propagates through the SDK's hook
        # protocol back into the async-for in _async_invoke_sdk and is caught
        # by run().
        self._run_verifiers_for_trigger(f"on_tool:{tool}")
        return {}

    def _handle_subagent_pre(
        self, *, call_id: str, sa_name: str, tool_input: dict[str, Any]
    ) -> None:
        """Emit `subagent_invoked` and stash the frame state for the matching
        post-hook. Strips the SDK's `subagent_type` discriminator from the
        recorded input so the AEP wire shows just what the parent actually
        passed to the subagent (matches the AnthropicSubagentDriver shape)."""
        sa = self._subagents_by_name[sa_name]
        invocation_id = f"sa-{next(self._sa_seq)}"
        frame_span_id = new_span_id()
        self._tool_span_by_call_id[call_id] = frame_span_id  # for verifier subject_call_ids
        self._tools_invoked[sa_name] = self._tools_invoked.get(sa_name, 0) + 1
        # Record bookkeeping so the post-hook can pair to this frame.
        self._subagent_invocations[call_id] = {
            "frame_span_id": frame_span_id,
            "sa_name": sa_name,
            "invocation_id": invocation_id,
            "t0_monotonic_ms": _monotonic_ms(),
        }
        # Sanitize the input — drop SDK-internal `subagent_type`. What's left
        # is what the parent agent actually intended to pass.
        sanitized_input = {k: v for k, v in tool_input.items() if k != "subagent_type"}
        parent = self._current_turn_span_id or self._agent_span_id
        invoked_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa.name,
            "aep.subagent.invocation_id": invocation_id,
            "aep.subagent.input": sanitized_input,
        }
        if sa.description:
            invoked_data["gen_ai.agent.description"] = sa.description
        self._emit(
            SubagentInvokedEvent(
                subject=self.config.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, parent),
                    **invoked_data,
                ),
            )
        )

    def _handle_subagent_post(self, *, call_id: str, response: Any) -> None:
        """Emit `subagent_returned` paired with the matching `subagent_invoked`.

        The Claude Agent SDK does not surface the subagent's internal turns
        or per-subagent usage breakdown to the parent's observer surface —
        the wire shape from this runner is "thin": invoked + returned with
        no nested model_turn events and a zeroed-out `aep.subagent.usage`
        rollup. The subagent's actual spend is rolled into the parent's
        cumulative state via the SDK's own usage accounting (it counts as
        part of the parent run's tokens/cost), so the parent's
        RunStateSnapshot is correct; only the per-subagent attribution is
        unavailable here. Future versions may use the SDK's SubagentStart
        hook to recover some breakdown.
        """
        frame = self._subagent_invocations.pop(call_id)
        frame_span_id: str = frame["frame_span_id"]
        sa_name: str = frame["sa_name"]
        invocation_id: str = frame["invocation_id"]
        duration_ms = max(0, _monotonic_ms() - frame["t0_monotonic_ms"])

        # Coerce the SDK's tool_response (string or structured) into the AEP
        # text + structured pair, same convention tool_returned uses.
        if isinstance(response, str):
            result_text = response
            result_structured: Any | None = None
        else:
            try:
                import json

                result_text = json.dumps(response)
                result_structured = response
            except (TypeError, ValueError):
                result_text = str(response)
                result_structured = None

        # Per-subagent usage isn't surfaced by the SDK — emit a zero rollup.
        # The parent's cumulative RunStateSnapshot still includes the spend.
        zero_usage = RunStateSnapshot(total_cost_usd=0.0, total_tokens=0, total_turns=0)

        returned_data: dict[str, Any] = {
            "step": self._step,
            "gen_ai.agent.name": sa_name,
            "aep.subagent.invocation_id": invocation_id,
            "duration_ms": duration_ms,
            "aep.subagent.result.text": result_text,
            "aep.subagent.reason": StopReason.converged,
            "aep.subagent.usage": zero_usage,
        }
        if result_structured is not None:
            returned_data["aep.subagent.result.structured"] = result_structured

        parent = self._current_turn_span_id or self._agent_span_id
        self._emit(
            SubagentReturnedEvent(
                subject=self.config.run_id,
                data=SubagentReturnedData(
                    **self._shared_span(frame_span_id, parent),
                    **returned_data,
                ),
            )
        )

    async def _on_user_prompt_submit_hook(
        self, _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired when a user prompt is submitted. We use the FIRST
        such fire to run `before_first_turn` verifiers (Claude SDK has no
        standalone session-start hook with prompt visibility for this case).
        Subsequent fires are not first turns and are ignored."""
        if not self._before_first_turn_fired:
            self._before_first_turn_fired = True
            self._run_verifiers_for_trigger("before_first_turn")
        return {}

    async def _on_stop_hook(
        self, _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK Stop hook. Records the signal but does not run at_end verifiers
        directly — Stop can fire per-turn in some configurations. The run()
        finalizer runs at_end exactly once before agent_stopped."""
        self._stop_seen = True
        return {}

    async def _on_baseline_reset_hook(
        self, _input_data: dict[str, Any], _tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """PreCompact / SubagentStart fire BEFORE the SDK's cumulative usage
        counters reset. Mark the next AssistantMessage's cumulative as a
        fresh baseline rather than as a delta; this avoids spurious
        accounting_reset errors during legitimate context-management
        operations."""
        self._baseline_reset_pending = True
        return {}

    # ── Verifier dispatch (mirrors AEPRunner._run_verifier semantics) ──────

    def _drain_pending_correction(self) -> str | None:
        """Pop one queued inject_correction message, or None if the queue is
        empty. The translator submits drained corrections as follow-up user
        prompts via `ClaudeSDKClient.query()` between turns."""
        if not self._pending_corrections:
            return None
        return self._pending_corrections.pop(0)

    def _run_verifiers_for_trigger(self, trigger: str) -> None:
        """Execute every Config verifier whose trigger matches.

        Raises _VerifierHalt if any verifier with on_failure=halt fails;
        otherwise emits verifier_evaluated and returns normally."""
        cfg = self.config
        if not cfg.verifiers:
            return
        for verifier in cfg.verifiers:
            if verifier.trigger != trigger:
                continue
            self._run_verifier(verifier)

    def _run_verifier(self, verifier: Verifier) -> None:
        import time as _time

        t0 = _time.monotonic()
        passed, error, data = self._execute_verifier(verifier)
        duration_ms = int((_time.monotonic() - t0) * 1000)
        kwargs: dict[str, Any] = {
            "aep.verifier.name": verifier.name,
            "aep.verifier.passed": passed,
            "aep.verifier.duration_ms": duration_ms,
        }
        if self._step:
            kwargs["step"] = self._step
        if error is not None:
            kwargs["aep.verifier.error"] = error
        if data:
            kwargs["aep.verifier.data"] = data
        self._emit(
            VerifierEvaluatedEvent(
                subject=self.config.run_id,
                data=VerifierEvaluatedData(
                    **self._own_span(self._current_parent_for_run_event()),
                    **kwargs,
                ),
            )
        )
        action = verifier.on_success if passed else verifier.on_failure
        self._apply_verifier_action(verifier, action, success=passed)

    def _execute_verifier(
        self, verifier: Verifier
    ) -> tuple[bool, VerifierError | None, dict[str, Any] | None]:
        """Execute a verifier source. Returns (passed, error, optional data dict).

        `error` distinguishes environment failures from rule failures:
          - source_timed_out: subprocess.TimeoutExpired
          - source_unavailable: shell exit 127 ("command not found")
          - source_crashed: any other unexpected subprocess error
          - None: the script ran to completion; exit 0 is pass, non-0 is rule fail

        Mirrors AEPRunner._execute_verifier so trajectories from both runners
        produce identical verifier_evaluated events for the same Config.
        """
        src = verifier.source
        try:
            result = subprocess.run(
                ["sh", "-c", src.shell],
                capture_output=True,
                text=True,
                check=False,
                timeout=verifier.timeout_ms / 1000.0,
            )
        except subprocess.TimeoutExpired:
            return (
                False,
                VerifierError.source_timed_out,
                {
                    "command": src.shell,
                    "timeout_ms": verifier.timeout_ms,
                },
            )
        except OSError as e:
            return (
                False,
                VerifierError.source_crashed,
                {
                    "command": src.shell,
                    "stderr": str(e)[:2000],
                },
            )

        data: dict[str, Any] = {
            "command": src.shell,
            "exit_code": result.returncode,
        }
        if result.stdout:
            data["stdout"] = result.stdout[:2000]
        if result.stderr:
            data["stderr"] = result.stderr[:2000]

        if result.returncode == 127:
            return False, VerifierError.source_unavailable, data
        passed = result.returncode == 0
        return passed, None, data

    def _apply_verifier_action(
        self, verifier: Verifier, action: OnFailure, *, success: bool
    ) -> None:
        if action == OnFailure.continue_:
            return
        if action == OnFailure.halt:
            raise _VerifierHalt(success=success)
        if action == OnFailure.inject_correction:
            assert verifier.correction_message is not None
            # Queue the correction for submission via ClaudeSDKClient.query()
            # after the current response stream completes. The driver runner's
            # equivalent is appending a user-role message to its in-memory
            # history; here we hand the same content to the SDK as a follow-up
            # user prompt and let the SDK route it through its own loop.
            self._pending_corrections.append(verifier.correction_message)
            return
        raise ValueError(f"unknown verifier action {action!r}")

    # ── AEP emission helpers ───────────────────────────────────────────────

    def _emit_agent_started(self) -> None:
        # In delegated mode (running under an outer AEPTracer), the parent
        # already emitted agent_started — emitting again would put two
        # agent_started events on the wire under the same trace_id, which
        # consumers can't reconcile.
        if self._suppress_lifecycle:
            return
        cfg = self.config
        tools_meta = None
        if cfg.tools:
            tools_meta = [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema,
                    "aep.dispatch_target": "supervisor_rpc",
                }
                for t in cfg.tools
            ]
        subagents_meta = None
        if cfg.subagents:
            subagents_meta = [
                {
                    "name": sa.name,
                    "description": sa.description,
                    **({"inputSchema": sa.inputSchema} if sa.inputSchema is not None else {}),
                }
                for sa in cfg.subagents
            ]
        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": cfg.prompt,
            "system_prompt": cfg.system_prompt,
            "tools": tools_meta,
            "skills": [s.name for s in (cfg.skills or [])] or None,
            "subagents": subagents_meta,
        }
        if cfg.model:
            data_kwargs["gen_ai.request.model"] = cfg.model
        if cfg.thread_id:
            data_kwargs["aep.thread_id"] = cfg.thread_id
        if cfg.tags:
            data_kwargs["aep.tags"] = cfg.tags
        if cfg.meta:
            data_kwargs["aep.meta"] = cfg.meta
        self._emit(
            AgentStartedEvent(
                subject=cfg.run_id,
                data=AgentStartedData(**data_kwargs),
            )
        )

    def _emit_agent_stopped(
        self, reason: StopReason, *, error_msg: str | None = None
    ) -> AgentStoppedEvent | None:
        # In delegated mode the parent's __exit__ emits agent_stopped with
        # the parent's run state. Suppress here to avoid duplicates.
        if self._suppress_lifecycle:
            return None
        snap = self._snapshot()
        ev = AgentStoppedEvent(
            subject=self.config.run_id,
            data=AgentStoppedData(
                trace_id=self._trace_id,
                span_id=self._agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                **{
                    "aep.reason": reason,
                    "aep.state": snap,
                    "aep.total_tokens": snap.total_tokens,
                    "aep.total_cost_usd": snap.total_cost_usd,
                    "aep.total_turns": snap.total_turns,
                    "aep.duration_ms": snap.duration_ms,
                },
            ),
        )
        self._emit(ev)
        return ev


# Quiet unused-import warning for the `Source` re-export at top-level.
_ = Source
