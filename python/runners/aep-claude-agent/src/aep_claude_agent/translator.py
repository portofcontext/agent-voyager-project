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
    AgentStartedEvent,
    AgentStoppedEvent,
    Config,
    CostRecordedEvent,
    ErrorOccurredEvent,
    ModelTurnEndedEvent,
    ModelTurnStartedEvent,
    RunStateSnapshot,
    Source,
    StopReason,
    TextEmittedEvent,
    ToolInvokedEvent,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedEvent,
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
    """Raised by _apply_on_failure when on_failure=halt fires. Caught at run()
    top-level (and around the at_end finalizer) to terminate the SDK iteration
    with reason=verifier_failed."""


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
    ) -> None:
        self.config = config
        self.on_event = on_event
        self._call_seq = itertools.count(1)
        self._step = 0
        self._started_at = now_iso()
        self._started_monotonic_ms = _monotonic_ms()
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
        # Stop hook may fire per-turn; the run() finalizer runs at_end exactly
        # once, so this flag is informational only.
        self._stop_seen = False
        # inject_correction queues correction messages here; the
        # ClaudeSDKClient.query() loop drains them between turns.
        self._pending_corrections: list[str] = []
        self._sdk_client_cls = sdk_client_cls
        self._sdk_options_cls = sdk_options_cls
        self._sdk_hook_matcher_cls = sdk_hook_matcher_cls

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
        except _VerifierHalt:
            reason = StopReason.verifier_failed
        except KeyboardInterrupt:
            reason = StopReason.interrupted
        except Exception as e:
            logger.exception("aep-claude-agent: SDK error")
            self._emit(
                ErrorOccurredEvent(
                    run_id=self.config.run_id,
                    code=ErrorCode.runner_crash,
                    message=str(e),
                )
            )
            reason = StopReason.error
            error_msg = str(e)
        finally:
            if self._turn_open:
                # Model was mid-turn when we exited — close the turn so the
                # trajectory is well-formed.
                self._emit(
                    ModelTurnEndedEvent(
                        run_id=self.config.run_id,
                        step=self._step,
                        tokens_input=0,
                        tokens_output=0,
                        cost_usd=0.0,
                        duration_ms=0,
                    )
                )
                self._turn_open = False

        # at_end verifiers fire exactly once before agent_stopped. They can
        # also halt — handle that by overriding `reason` to verifier_failed
        # if no earlier non-converged reason has been set.
        try:
            self._run_verifiers_for_trigger("at_end")
        except _VerifierHalt:
            # If the run already failed for a different reason, preserve it;
            # otherwise mark verifier_failed.
            if reason == StopReason.converged:
                reason = StopReason.verifier_failed

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
                ClaudeAgentOptions,
                ClaudeSDKClient,
                HookMatcher,
            )

            self._sdk_client_cls = ClaudeSDKClient
            self._sdk_options_cls = ClaudeAgentOptions
            self._sdk_hook_matcher_cls = HookMatcher

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
          - hooks={PreToolUse, PostToolUse} → translator-emitted tool_invoked / tool_returned
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
                    run_id=cfg.run_id,
                    code=ErrorCode.accounting_reset,
                    message=(
                        "SDK cumulative usage dropped without a PreCompact / "
                        "SubagentStart signal. Per-turn deltas may be unreliable; "
                        "treat state.total_tokens / total_cost_usd as a lower bound."
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
        self._emit(ModelTurnStartedEvent(run_id=cfg.run_id, step=self._step))
        self._turn_open = True

        for block in getattr(message, "content", []) or []:
            btype = type(block).__name__
            if btype == "TextBlock":
                text = getattr(block, "text", None)
                if text:
                    self._emit(TextEmittedEvent(run_id=cfg.run_id, step=self._step, text=text))
            # ToolUseBlock content is observed via the PreToolUse hook (which
            # fires in step with the SDK's actual tool dispatch).

        self._prev_cumulative_input_tokens = cum_ti
        self._prev_cumulative_output_tokens = cum_to
        self._prev_cumulative_cache_read = cum_cr
        self._prev_cumulative_cache_write = cum_cw
        self._prev_cumulative_cost_usd = cum_cost

        self._emit(
            ModelTurnEndedEvent(
                run_id=cfg.run_id,
                step=self._step,
                tokens_input=delta_ti,
                tokens_output=delta_to,
                cost_usd=delta_cost,
                duration_ms=0,  # the SDK message doesn't carry per-turn duration
                tokens_cache_read=delta_cr or None,
                tokens_cache_write=delta_cw or None,
            )
        )
        self._turn_open = False

        self._total_turns += 1
        self._total_cost_usd += delta_cost
        self._total_tokens += delta_ti + delta_to
        self._emit(CostRecordedEvent(run_id=cfg.run_id, state=self._snapshot()))

        # SPEC.md §7.2: after_each_turn fires after model_turn_ended.
        # _VerifierHalt raised here propagates through the SDK's async-for
        # iteration into asyncio.run() and is caught by run().
        self._run_verifiers_for_trigger("after_each_turn")

    def _handle_result_message(self, message: Any) -> None:
        """ResultMessage closes the run with authoritative cost. Reconcile if it
        differs from our per-turn sum (the SDK's number wins)."""
        sdk_cost = getattr(message, "total_cost_usd", None)
        if sdk_cost is not None:
            self._total_cost_usd = float(sdk_cost)
            self._emit(CostRecordedEvent(run_id=self.config.run_id, state=self._snapshot()))

    # ── Hook callbacks (Claude Code hooks) ─────────────────────────────────

    async def _on_pre_tool_use_hook(
        self, input_data: dict[str, Any], tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired before each tool invocation. Emits tool_invoked.

        Returns `{}` (no override) — the translator observes; it does not gate."""
        call_id = input_data.get("tool_use_id") or tool_use_id or f"sdk-{next(self._call_seq)}"
        tool = input_data.get("tool_name", "unknown")
        tool_input = input_data.get("tool_input", {}) or {}
        self._emit(
            ToolInvokedEvent(
                run_id=self.config.run_id,
                step=self._step,
                call_id=str(call_id),
                tool=str(tool),
                input=dict(tool_input),
            )
        )
        self._tools_invoked[tool] = self._tools_invoked.get(tool, 0) + 1
        return {}

    async def _on_post_tool_use_hook(
        self, input_data: dict[str, Any], tool_use_id: str | None, _context: Any
    ) -> dict[str, Any]:
        """SDK hook fired after each tool invocation. Emits tool_returned and
        fires `on_tool:<tool_name>` verifiers."""
        call_id = input_data.get("tool_use_id") or tool_use_id or "unknown"
        tool = input_data.get("tool_name", "unknown")
        response = input_data.get("tool_response", "")
        if not isinstance(response, str):
            try:
                import json

                output = json.dumps(response)
            except (TypeError, ValueError):
                output = str(response)
        else:
            output = response
        self._emit(
            ToolReturnedEvent(
                run_id=self.config.run_id,
                step=self._step,
                call_id=str(call_id),
                tool=str(tool),
                output=output,
                duration_ms=0,
            )
        )
        # SPEC.md §7.2: on_tool:<name> fires after tool_returned for the named
        # tool. _VerifierHalt raised here propagates through the SDK's hook
        # protocol back into the async-for in _async_invoke_sdk and is caught
        # by run().
        self._run_verifiers_for_trigger(f"on_tool:{tool}")
        return {}

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
        passed, error, data = self._execute_verifier(verifier)
        self._emit(
            VerifierEvaluatedEvent(
                run_id=self.config.run_id,
                name=verifier.name,
                passed=passed,
                step=self._step or None,
                error=error,
                data=data,
            )
        )
        if passed:
            return
        self._apply_on_failure(verifier)

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

    def _apply_on_failure(self, verifier: Verifier) -> None:
        if verifier.on_failure == OnFailure.continue_:
            return
        if verifier.on_failure == OnFailure.halt:
            raise _VerifierHalt()
        if verifier.on_failure == OnFailure.inject_correction:
            assert verifier.correction_message is not None
            # Queue the correction for submission via ClaudeSDKClient.query()
            # after the current response stream completes. The driver runner's
            # equivalent is appending a user-role message to its in-memory
            # history; here we hand the same content to the SDK as a follow-up
            # user prompt and let the SDK route it through its own loop.
            self._pending_corrections.append(verifier.correction_message)
            return
        raise ValueError(f"unknown on_failure {verifier.on_failure!r}")

    # ── AEP emission helpers ───────────────────────────────────────────────

    def _emit_agent_started(self) -> None:
        cfg = self.config
        tools_meta = None
        if cfg.tools:
            tools_meta = [
                {"name": t.name, "description": t.description, "input_schema": t.input_schema}
                for t in cfg.tools
            ]
        self._emit(
            AgentStartedEvent(
                run_id=cfg.run_id,
                model=cfg.model or "unspecified",
                prompt=cfg.prompt,
                system_prompt=cfg.system_prompt,
                tools=tools_meta,
                skills=[s.name for s in (cfg.skills or [])] or None,
                thread_id=cfg.thread_id,
                tags=cfg.tags,
                meta=cfg.meta,
            )
        )

    def _emit_agent_stopped(
        self, reason: StopReason, *, error_msg: str | None = None
    ) -> AgentStoppedEvent:
        snap = self._snapshot()
        ev = AgentStoppedEvent(
            run_id=self.config.run_id,
            reason=reason,
            state=snap,
            total_tokens=snap.total_tokens,
            total_cost_usd=snap.total_cost_usd,
            total_turns=snap.total_turns,
            duration_ms=snap.duration_ms,
        )
        self._emit(ev)
        return ev


# Quiet unused-import warning for the `Source` re-export at top-level.
_ = Source
