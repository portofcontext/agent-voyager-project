"""AEPRunner — the v0.1 normative loop.

The agent runs inside the supervisor's declared environment. Boundary, tools,
verifiers all come from Config. The supervisor does not reach in mid-run; the
agent enforces declared rules and emits facts. The only mid-run wire interaction
is tool_exec, an agent-initiated RPC into a service the supervisor stood up at
Config time.

Each emitted event is a CloudEvent 1.0 envelope carrying typed `data`. Span
identification (`trace_id`, `span_id`, `parent_span_id`) follows OpenTelemetry
conventions so the trajectory reconstructs as a span tree:

    agent span (root)                                       agent_started/stopped
    ├── skill span                                          skill_loaded/executed
    ├── verifier span                                       verifier_evaluated (run-level triggers)
    ├── error span                                          error_occurred (run-level)
    ├── model_turn span (per turn)                          model_turn_started/ended
    │   ├── text span                                       text_emitted
    │   ├── cost span                                       cost_recorded
    │   ├── verifier span                                   verifier_evaluated (per-turn triggers)
    │   └── tool span (per tool call)                       tool_invoked/returned/failed
    │       └── rpc span (per agent-initiated RPC)          tool_exec_request/resolved/timed_out
"""

from __future__ import annotations

import itertools
import subprocess
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel

from aep.enums import ErrorCode, OnFailure, StopReason, VerifierError
from aep.runner.boundary import (
    check_consumption,
    check_step_projection,
)
from aep.runner.drivers import (
    ModelDriver,
    SubagentDriver,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from aep.types import (
    ZERO_SPAN_ID,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    ApprovalRequestedData,
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
    Config,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
    JsonRpcRequestPayload,
    McpServer,
    McpServerConnectedData,
    McpServerConnectedEvent,
    McpServerDisconnectedData,
    McpServerDisconnectedEvent,
    ModelTurnEndedData,
    ModelTurnEndedEvent,
    ModelTurnStartedData,
    ModelTurnStartedEvent,
    ReasoningEmittedData,
    ReasoningEmittedEvent,
    RefusalRecordedData,
    RefusalRecordedEvent,
    RunStateSnapshot,
    SkillLoadedData,
    SkillLoadedEvent,
    Subagent,
    SubagentFailedData,
    SubagentFailedEvent,
    SubagentInvokedData,
    SubagentInvokedEvent,
    SubagentReturnedData,
    SubagentReturnedEvent,
    TextEmittedData,
    TextEmittedEvent,
    Tool,
    ToolExecRequestData,
    ToolExecRequestEvent,
    ToolExecResolvedEvent,
    ToolExecTimedOutData,
    ToolExecTimedOutEvent,
    ToolFailedData,
    ToolFailedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    Verifier,
    VerifierEvaluatedData,
    VerifierEvaluatedEvent,
    VerifierSourceApproval,
    new_span_id,
    new_trace_id,
    now_iso,
)

MCP_PROTOCOL_VERSION = "2025-11-25"

# ── Local mutable state ──────────────────────────────────────────────────────


@dataclass
class _MutableState:
    started_at: str
    started_monotonic_ms: int
    total_turns: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    tokens_input_total: int = 0
    tokens_output_total: int = 0
    tokens_cache_read_total: int = 0
    tokens_cache_write_total: int = 0
    tools_invoked: dict[str, int] = field(default_factory=dict)

    def snapshot(self, now_monotonic_ms: int) -> RunStateSnapshot:
        return RunStateSnapshot(
            total_cost_usd=self.total_cost_usd,
            total_tokens=self.total_tokens,
            total_turns=self.total_turns,
            tokens_input_total=self.tokens_input_total or None,
            tokens_output_total=self.tokens_output_total or None,
            tokens_cache_read_total=self.tokens_cache_read_total or None,
            tokens_cache_write_total=self.tokens_cache_write_total or None,
            tools_invoked=dict(self.tools_invoked) or None,
            started_at=self.started_at,
            duration_ms=max(0, now_monotonic_ms - self.started_monotonic_ms),
        )


def _monotonic_ms() -> int:
    return int(datetime.now(UTC).timestamp() * 1000)


# ── The runner ────────────────────────────────────────────────────────────────


class _VerifierHalt(Exception):
    """Raised internally when a verifier with halt action fires.

    `success` distinguishes halt-on-success (treated as `converged`,
    semantically "the agent achieved the declared goal") from
    halt-on-failure (treated as `verifier_failed`, semantically "the
    agent broke an invariant"). Caught at run() top-level and
    translated to the corresponding `StopReason`.
    """

    def __init__(self, *, success: bool = False) -> None:
        self.success = success
        super().__init__(
            "verifier halted run "
            + ("on success (declarative convergence)" if success else "on failure")
        )


class AEPRunner:
    """Reference AEP runner. v0.1 model: declarative environment, no mid-run reach-in."""

    def __init__(
        self,
        config: Config,
        model: ModelDriver,
        tools: ToolDriver,
        supervisor: SupervisorDriver,
        runner_builtin_tools: list[dict[str, Any]] | None = None,
        subagent_driver: SubagentDriver | None = None,
        *,
        on_event: Callable[[BaseModel], None] | None = None,
    ) -> None:
        """`runner_builtin_tools` declares the runner's built-in tool catalog.
        Each entry is `{name, description, input_schema}` (snake_case, internal).
        Used to compute the effective tool surface for `agent_started.data.tools`.

        `subagent_driver` is required iff `config.subagents` is non-empty.
        Without one declared, subagent invocations fail with a clear error
        rather than silently degrading.

        `on_event` is an optional callback invoked synchronously as each event
        is emitted, BEFORE it lands in `self.trajectory`. The runner still
        accumulates the trajectory in memory for in-process consumers (tests,
        the CLI's post-run summary); the callback is for streaming consumers
        (workers writing events to durable storage as they happen, multi-host
        supervisors observing the run live, etc.). Mirrors `AEPTracer`'s
        `on_event` shape so the embedded-runner and drop-in-tracer paths feel
        identical to consumers. The callback MUST NOT mutate the event; it
        runs on the runner's thread and any exception propagates out.
        """
        self.config = config
        self.model = model
        self.tools = tools
        self.supervisor = supervisor
        self._on_event = on_event
        self.trajectory: list[BaseModel | dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._supervisor_tools_by_name: dict[str, Tool] = {t.name: t for t in (config.tools or [])}
        self._subagents_by_name: dict[str, Subagent] = {
            sa.name: sa for sa in (config.subagents or [])
        }
        self._subagent_driver = subagent_driver
        self._runner_builtin_tools = list(runner_builtin_tools or [])
        self._allowed_tools: frozenset[str] | None = (
            frozenset(config.allowed_tools) if config.allowed_tools is not None else None
        )
        self._req_seq = itertools.count(1)
        self._next_request_id = lambda: f"req-{next(self._req_seq)}"
        self._sa_seq = itertools.count(1)
        self._next_subagent_invocation_id = lambda: f"sa-{next(self._sa_seq)}"
        self._approval_seq = itertools.count(1)
        self._next_approval_id = lambda: f"ap-{next(self._approval_seq)}"
        self._approval_span_by_id: dict[str, str] = {}

        # Span tree state. trace_id is allocated per run; agent_span_id is the
        # root span (lifetime = the run); turn / tool / rpc spans are nested.
        self._trace_id: str = new_trace_id()
        self._agent_span_id: str = new_span_id()
        self._current_turn_span_id: str | None = None
        self._tool_span_by_call_id: dict[str, str] = {}
        self._rpc_span_by_request_id: dict[str, str] = {}

    # ── Span helpers ───────────────────────────────────────────────────────

    def _own_span(self, parent_span_id: str) -> dict[str, str]:
        """Triple for an event that owns its own span (atomic observation).
        The span has no paired open/close; the event itself records the moment."""
        return {
            "trace_id": self._trace_id,
            "span_id": new_span_id(),
            "parent_span_id": parent_span_id,
        }

    def _shared_span(self, span_id: str, parent_span_id: str) -> dict[str, str]:
        """Triple for an event that participates in a multi-event span (e.g.,
        tool_invoked + tool_returned share one span describing one tool call)."""
        return {
            "trace_id": self._trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
        }

    def _current_parent_for_run_event(self) -> str:
        """Parent for events that pair with a turn when one is active, else
        with the agent span (e.g., verifier_evaluated, error_occurred)."""
        return self._current_turn_span_id or self._agent_span_id

    # ── Emission ────────────────────────────────────────────────────────────

    def _emit(self, event: BaseModel) -> None:
        # Callback fires BEFORE trajectory append so a worker writing to
        # durable storage sees the event in the same order an in-process
        # consumer reading `trajectory` will. If the callback raises, the
        # event isn't appended either — the run aborts with the exception
        # propagated out of run(), matching the "runner errors are loud"
        # principle (no silent dropped events).
        if self._on_event is not None:
            self._on_event(event)
        self.trajectory.append(event)
        self.supervisor.observe(event)

    # ── Run lifecycle ───────────────────────────────────────────────────────

    def run(self) -> AgentStoppedEvent:
        state = _MutableState(
            started_at=now_iso(),
            started_monotonic_ms=_monotonic_ms(),
        )
        self._state = state

        self._emit_agent_started()
        self._emit_skills_loaded()
        self._emit_mcp_connections()

        if not self._validate_allowed_tools():
            return self._emit_agent_stopped(StopReason.error)

        try:
            self._run_verifiers_for("before_first_turn")
            self._main_loop()
        except _VerifierHalt as halt:
            reason = StopReason.converged if halt.success else StopReason.verifier_failed
            return self._emit_agent_stopped(reason)

        # Normal exit (loop returned) — close MCP connections cleanly before
        # the agent_stopped this path emits.
        for ev in reversed(self.trajectory):
            if isinstance(ev, AgentStoppedEvent):
                return ev
        raise RuntimeError("AEPRunner: trajectory missing agent_stopped — invariant violation")

    # ── Main loop ───────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        state = self._state
        cfg = self.config

        while True:
            decision = check_step_projection(state.snapshot(_monotonic_ms()), cfg.boundary)
            if decision.stop:
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(decision.reason or StopReason.turn_limit)
                return

            state.total_turns += 1
            self._current_turn_span_id = new_span_id()
            turn_started_kwargs: dict[str, Any] = {"aep.context_messages": len(self._history)}
            self._emit(
                ModelTurnStartedEvent(
                    subject=cfg.run_id,
                    data=ModelTurnStartedData(
                        **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                        step=state.total_turns,
                        **turn_started_kwargs,
                    ),
                )
            )
            response = self.model.step(self._history)
            ended_kwargs: dict[str, Any] = {
                "gen_ai.usage.input_tokens": response.tokens_input,
                "gen_ai.usage.output_tokens": response.tokens_output,
                "gen_ai.usage.cache_read.input_tokens": response.tokens_cache_read,
                "gen_ai.usage.cache_creation.input_tokens": response.tokens_cache_write,
                "gen_ai.usage.reasoning.output_tokens": response.tokens_reasoning_output,
                "aep.cost_usd": response.cost_usd,
                "aep.cost.source": response.cost_source,
            }
            if response.response_model is not None:
                ended_kwargs["gen_ai.response.model"] = response.response_model
            if response.finish_reasons:
                ended_kwargs["gen_ai.response.finish_reasons"] = response.finish_reasons
            if response.time_to_first_chunk_s is not None:
                ended_kwargs["gen_ai.response.time_to_first_chunk"] = response.time_to_first_chunk_s
            self._emit(
                ModelTurnEndedEvent(
                    subject=cfg.run_id,
                    data=ModelTurnEndedData(
                        **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                        step=state.total_turns,
                        duration_ms=response.duration_ms,
                        **ended_kwargs,
                    ),
                )
            )

            state.total_cost_usd += response.cost_usd
            state.total_tokens += response.tokens_input + response.tokens_output
            state.tokens_input_total += response.tokens_input
            state.tokens_output_total += response.tokens_output
            if response.tokens_cache_read:
                state.tokens_cache_read_total += response.tokens_cache_read
            if response.tokens_cache_write:
                state.tokens_cache_write_total += response.tokens_cache_write

            self._emit(
                CostRecordedEvent(
                    subject=cfg.run_id,
                    data=CostRecordedData(
                        **self._own_span(self._current_turn_span_id),
                        **{"aep.state": state.snapshot(_monotonic_ms())},
                    ),
                )
            )

            decision = check_consumption(state.snapshot(_monotonic_ms()), cfg.boundary)
            if decision.stop:
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(decision.reason or StopReason.budget_exhausted)
                return

            # Reasoning / thinking blocks land BEFORE text and tool calls —
            # the wire reconstructs the turn as "thought, then spoke / acted".
            # Each block becomes its own event so consumers can collapse
            # chain-of-thought from displays without losing it from the audit.
            for rb in response.reasoning_blocks:
                reasoning_kwargs: dict[str, Any] = {"aep.reasoning.text": rb.text}
                if rb.signature:
                    reasoning_kwargs["aep.reasoning.signature"] = rb.signature
                if rb.redacted:
                    reasoning_kwargs["aep.reasoning.redacted"] = rb.redacted
                self._emit(
                    ReasoningEmittedEvent(
                        subject=cfg.run_id,
                        data=ReasoningEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **reasoning_kwargs,
                        ),
                    )
                )

            if response.text:
                self._emit(
                    TextEmittedEvent(
                        subject=cfg.run_id,
                        data=TextEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **{"aep.text": response.text},
                        ),
                    )
                )

            # Refusal handling. If the driver detected a refusal-flavored
            # signal (Anthropic stop_reason="refusal"|"sensitive", OpenAI
            # content_filter, Gemini SAFETY/BLOCKLIST/etc.), emit
            # `refusal_recorded` and terminate with StopReason.refused.
            # The refused turn produced no useful content — we don't
            # append it to history, so a higher-level supervisor can
            # reset and retry without re-feeding the refused turn.
            if response.refusal is not None:
                refusal_kwargs: dict[str, Any] = {
                    "aep.refusal.reason": response.refusal.reason,
                }
                if response.refusal.message:
                    refusal_kwargs["aep.refusal.message"] = response.refusal.message
                if response.refusal.category:
                    refusal_kwargs["aep.refusal.category"] = response.refusal.category
                if response.refusal.provider:
                    refusal_kwargs["aep.refusal.provider"] = response.refusal.provider
                self._emit(
                    RefusalRecordedEvent(
                        subject=cfg.run_id,
                        data=RefusalRecordedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **refusal_kwargs,
                        ),
                    )
                )
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(StopReason.refused)
                return

            # Server-side tool calls (e.g. Anthropic's MCP connector running
            # `mcp_tool_use` blocks inline during the request, or hosted
            # `web_search_tool_use` blocks). These ALREADY happened — no
            # runner dispatch — so we emit synthetic tool_invoked /
            # tool_returned events for per-call wire fidelity, parented to
            # the turn span so the trajectory tree stays consistent.
            for stc in response.server_tool_calls:
                self._emit_server_tool_call(stc, state)

            # Always record the assistant turn (text + tool_calls if any) before
            # dispatching tools. Without the assistant message, the next model
            # turn would receive a user-role tool_result that references a
            # tool_use_id with no matching tool_use block in the conversation —
            # which Anthropic (and most LLM APIs) reject as malformed.
            if response.text or response.tool_calls:
                self._history.append(
                    {
                        "role": "assistant",
                        "content": response.text or "",
                        "tool_calls": [
                            {"call_id": tc.call_id, "tool": tc.tool, "input": tc.input}
                            for tc in response.tool_calls
                        ]
                        if response.tool_calls
                        else None,
                    }
                )

            for tc in response.tool_calls:
                self._handle_tool_call(tc, state)
                decision = check_consumption(state.snapshot(_monotonic_ms()), cfg.boundary)
                if decision.stop:
                    self._run_verifiers_for("at_end")
                    self._emit_agent_stopped(decision.reason or StopReason.budget_exhausted)
                    return
                self._run_verifiers_for(f"on_tool:{tc.tool}")

            self._run_verifiers_for("after_each_turn")

            if response.converged:
                self._run_verifiers_for("at_end")
                self._emit_agent_stopped(StopReason.converged)
                return

    # ── Tool handling ────────────────────────────────────────────────────────

    def _validate_allowed_tools(self) -> bool:
        """Cross-field checks at run start:
        - Subagent names MUST NOT collide with tool names (the model sees a
          single name → one resource).
        - Every Config.tools name AND every Config.subagents name MUST be in
          allowed_tools (when set).
        """
        cfg = self.config
        tool_names = {t.name for t in (cfg.tools or [])}
        builtin_names = {bt["name"] for bt in self._runner_builtin_tools}
        subagent_names = {sa.name for sa in (cfg.subagents or [])}
        collisions = sorted(subagent_names & (tool_names | builtin_names))
        if collisions:
            self._emit(
                ErrorOccurredEvent(
                    subject=cfg.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "aep.error.code": ErrorCode.unknown,
                            "aep.error.message": (
                                "Config.subagents[].name must not collide with tool names; "
                                f"colliding: {collisions}"
                            ),
                        },
                    ),
                )
            )
            return False
        if self._allowed_tools is None:
            return True
        declared = tool_names | subagent_names
        excluded = sorted(declared - self._allowed_tools)
        if excluded:
            self._emit(
                ErrorOccurredEvent(
                    subject=cfg.run_id,
                    data=ErrorOccurredData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "aep.error.code": ErrorCode.unknown,
                            "aep.error.message": (
                                "Config.allowed_tools must include every name in "
                                f"Config.tools and Config.subagents; missing: {excluded}"
                            ),
                        },
                    ),
                )
            )
            return False
        return True

    def _emit_server_tool_call(self, stc, state: _MutableState) -> None:
        """Emit synthetic tool_invoked + tool_returned (or tool_failed) for a
        tool the API/SDK ran server-side during this turn.

        These events are observational — no runner dispatch happens. We
        share one span across the pair so consumers can correlate them
        the same way they correlate runner-dispatched tools.
        Parent span is the current turn (the call happened inline during
        that model request). Tags `aep.tool.dispatch_target` and, when
        present, `aep.mcp_server_id` come from the driver.
        """
        cfg = self.config
        tool_span_id = new_span_id()
        invoked_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": stc.call_id,
            "gen_ai.tool.name": stc.tool,
            "gen_ai.tool.call.arguments": dict(stc.input),
            "aep.tool.dispatch_target": stc.dispatch_target,
        }
        if stc.server_id:
            invoked_kwargs["aep.mcp_server_id"] = stc.server_id
        if stc.subtype:
            invoked_kwargs["aep.tool.subtype"] = stc.subtype
        self._emit(
            ToolInvokedEvent(
                subject=cfg.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    **invoked_kwargs,
                ),
            )
        )
        if stc.is_error:
            self._emit(
                ToolFailedEvent(
                    subject=cfg.run_id,
                    data=ToolFailedData(
                        **self._shared_span(tool_span_id, self._current_turn_span_id),
                        step=state.total_turns,
                        **{
                            "gen_ai.tool.call.id": stc.call_id,
                            "gen_ai.tool.name": stc.tool,
                            "aep.tool.error": stc.output_text or "server-side tool reported error",
                        },
                    ),
                )
            )
            return
        returned_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": stc.call_id,
            "gen_ai.tool.name": stc.tool,
            "aep.tool.result.text": stc.output_text,
        }
        if stc.output_structured is not None:
            returned_kwargs["aep.tool.result.structured"] = stc.output_structured
        self._emit(
            ToolReturnedEvent(
                subject=cfg.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    duration_ms=stc.duration_ms,
                    **returned_kwargs,
                ),
            )
        )

    def _emit_tool_failed(self, tc, state: _MutableState, error: str) -> None:
        """Emit `tool_failed` AND record an error tool_result in history.

        Anthropic-style APIs require every `tool_use` block in an assistant
        turn to be answered with a matching `tool_result` block in the next
        message — even when the tool failed. Without history.append here, the
        next model call sends an unmatched `tool_use` and the API rejects.
        """
        cfg = self.config
        tool_span_id = self._tool_span_by_call_id.get(tc.call_id) or new_span_id()
        self._emit(
            ToolFailedEvent(
                subject=cfg.run_id,
                data=ToolFailedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    **{
                        "gen_ai.tool.call.id": tc.call_id,
                        "gen_ai.tool.name": tc.tool,
                        "aep.tool.error": error,
                    },
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": f"Error: {error}",
            }
        )

    def _handle_tool_call(self, tc, state: _MutableState) -> None:
        cfg = self.config

        # pre_tool:<name> verifiers gate dispatch. They run BEFORE the
        # tool fires; their outcome decides whether the tool runs at
        # all. on_failure=halt → run terminates with verifier_failed;
        # on_failure=inject_correction → tool skipped, correction
        # injected (agent retries next turn); on_failure=continue →
        # tool skipped, surfaces to the model as tool_failed.
        if not self._run_pre_tool_verifiers(tc, state):
            return

        # Subagent invocations route through their own lifecycle
        # (subagent_invoked / subagent_returned / subagent_failed) — they do
        # not surface as tool_invoked. The subagent's frame is its own span;
        # its internal model_turn / tool / text events nest under that frame.
        if tc.tool in self._subagents_by_name:
            if self._allowed_tools is not None and tc.tool not in self._allowed_tools:
                # Allowed-tools applies to subagent names too — they're what
                # the model sees. Emit tool_failed (same rejection shape as
                # any other allowlist miss); never emit subagent_invoked for
                # an invocation we never dispatched.
                tool_span_id = new_span_id()
                self._tool_span_by_call_id[tc.call_id] = tool_span_id
                self._emit(
                    ToolInvokedEvent(
                        subject=cfg.run_id,
                        data=ToolInvokedData(
                            **self._shared_span(tool_span_id, self._current_turn_span_id),
                            step=state.total_turns,
                            **{
                                "gen_ai.tool.call.id": tc.call_id,
                                "gen_ai.tool.name": tc.tool,
                                "gen_ai.tool.call.arguments": tc.input,
                            },
                        ),
                    )
                )
                self._emit_tool_failed(
                    tc, state, f"subagent {tc.tool!r} not in Config.allowed_tools"
                )
                return
            self._handle_subagent_call(tc, state)
            return

        tool_span_id = new_span_id()
        self._tool_span_by_call_id[tc.call_id] = tool_span_id

        is_rpc = tc.tool in self._supervisor_tools_by_name
        is_local = self.tools.is_local(tc.tool)
        if is_rpc:
            dispatch_target = "supervisor_rpc"
        elif is_local:
            dispatch_target = "local"
        else:
            dispatch_target = None

        invoked_data_kwargs: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.tool.call.id": tc.call_id,
            "gen_ai.tool.name": tc.tool,
            "gen_ai.tool.call.arguments": tc.input,
        }
        if dispatch_target is not None:
            invoked_data_kwargs["aep.tool.dispatch_target"] = dispatch_target

        self._emit(
            ToolInvokedEvent(
                subject=cfg.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    **invoked_data_kwargs,
                ),
            )
        )
        state.tools_invoked[tc.tool] = state.tools_invoked.get(tc.tool, 0) + 1

        if self._allowed_tools is not None and tc.tool not in self._allowed_tools:
            self._emit_tool_failed(tc, state, f"tool {tc.tool!r} not in Config.allowed_tools")
            return

        if is_rpc:
            self._handle_rpc_tool(tc, state)
            return

        if not is_local:
            self._emit_tool_failed(tc, state, f"unknown tool {tc.tool!r}")
            return

        outcome: ToolOutcome = self.tools.invoke(tc.tool, tc.input)
        if outcome.error is not None and not outcome.rejected:
            self._emit_tool_failed(tc, state, outcome.error)
            return

        out_str = outcome.output if outcome.output is not None else ""
        returned_kwargs: dict[str, Any] = {
            "step": state.total_turns,
            "duration_ms": outcome.duration_ms,
            "gen_ai.tool.call.id": tc.call_id,
            "gen_ai.tool.name": tc.tool,
            "aep.tool.result.text": out_str,
        }
        if outcome.output_json is not None:
            returned_kwargs["aep.tool.result.structured"] = outcome.output_json
        if outcome.rejected:
            returned_kwargs["aep.tool.rejected"] = True
        if outcome.rejection_reason:
            returned_kwargs["aep.tool.rejection_reason"] = outcome.rejection_reason

        self._emit(
            ToolReturnedEvent(
                subject=cfg.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    **returned_kwargs,
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": out_str,
            }
        )

    def _handle_rpc_tool(self, tc, state: _MutableState) -> None:
        cfg = self.config
        tool_decl = self._supervisor_tools_by_name[tc.tool]
        tool_span_id = self._tool_span_by_call_id[tc.call_id]
        request_id = self._next_request_id()
        rpc_span_id = new_span_id()
        self._rpc_span_by_request_id[request_id] = rpc_span_id

        # MCP / JSON-RPC payload: method `tools/call`, params {name, arguments}.
        rpc_request = JsonRpcRequestPayload(
            id=request_id,
            method="tools/call",
            params={"name": tc.tool, "arguments": tc.input},
        )
        timeout_ms = (tool_decl.meta or {}).get("aep", {}).get("timeout_ms")
        if not isinstance(timeout_ms, int) or timeout_ms <= 0:
            timeout_ms = 30000  # SPEC default

        self._emit(
            ToolExecRequestEvent(
                subject=cfg.run_id,
                data=ToolExecRequestData(
                    **self._shared_span(rpc_span_id, tool_span_id),
                    step=state.total_turns,
                    rpc=rpc_request,
                    **{
                        "aep.request_id": request_id,
                        "gen_ai.tool.call.id": tc.call_id,
                        "aep.timeout_ms": timeout_ms,
                        "aep.tool.dispatch_target": "supervisor_rpc",
                        "gen_ai.tool.name": tc.tool,
                    },
                ),
            )
        )

        msg = self.supervisor.get_tool_exec_response(request_id, timeout_ms)
        if msg is None:
            self._emit(
                ToolExecTimedOutEvent(
                    subject=cfg.run_id,
                    data=ToolExecTimedOutData(
                        **self._shared_span(rpc_span_id, tool_span_id),
                        step=state.total_turns,
                        **{
                            "aep.request_id": request_id,
                            "gen_ai.tool.call.id": tc.call_id,
                            "gen_ai.tool.name": tc.tool,
                            "aep.timeout_ms": timeout_ms,
                        },
                    ),
                )
            )
            # SPEC.md §9.3: model-visible output on timeout is an "Error: "-prefixed
            # string for symmetry with §8 step-4 (the same prefix on
            # tool_exec_resolved.error). Models can therefore use a single
            # convention to detect 'tool didn't return useful data, consider retry'.
            output = f"Error: tool execution timed out after {timeout_ms}ms"
            output_structured: Any | None = None
        else:
            assert isinstance(msg, ToolExecResolvedEvent)
            # Stamp the runner's trace context onto the supervisor's reply so
            # the span tree is consistent. Also echo the tool name (which the
            # supervisor may not have known to set). The supervisor produced
            # the reply but didn't know our trace IDs.
            new_data = msg.data.model_copy(
                update={
                    "trace_id": self._trace_id,
                    "span_id": rpc_span_id,
                    "parent_span_id": tool_span_id,
                    "gen_ai_tool_name": tc.tool,
                }
            )
            msg = msg.model_copy(update={"data": new_data})
            self._emit(msg)
            err = msg.data.rpc.error
            result = msg.data.rpc.result
            if err is not None:
                # JSON-RPC error: present an "Error: " string to the model.
                msg_text = err.message
                output = f"Error: {msg_text}"
                output_structured = None
            else:
                # Successful result. If it's a string, it's the model-visible text;
                # if a dict, fold it into the structured slot AND a JSON serialization
                # for the model.
                if isinstance(result, str):
                    output = result
                    output_structured = None
                else:
                    import json

                    output = json.dumps(result, separators=(",", ":"))
                    output_structured = result

        returned_kwargs: dict[str, Any] = {
            "step": state.total_turns,
            "duration_ms": 1,
            "gen_ai.tool.call.id": tc.call_id,
            "gen_ai.tool.name": tc.tool,
            "aep.tool.result.text": output,
        }
        if output_structured is not None:
            returned_kwargs["aep.tool.result.structured"] = output_structured

        self._emit(
            ToolReturnedEvent(
                subject=cfg.run_id,
                data=ToolReturnedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    **returned_kwargs,
                ),
            )
        )
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": output,
            }
        )

    def _handle_subagent_call(self, tc, state: _MutableState) -> None:
        """Dispatch a parent-agent tool call to a declared subagent.

        Emits `subagent_invoked` to open a frame span, runs the subagent
        through `self._subagent_driver`, then emits either `subagent_returned`
        (success) or `subagent_failed` (driver returned an error or raised).
        Internal turns of the subagent observe via `parent_observer` —
        their `parent_span_id` chains through the frame span_id this method
        allocates, so the trajectory reconstructs as a nested tree.

        The subagent's result is appended to the parent's history as a
        `tool` message keyed by `tc.call_id`, so the parent's next model
        turn sees the result the same way it sees any tool reply. (The
        model invoked the subagent through a tool_use block; it expects a
        matching tool_result.)
        """
        cfg = self.config
        sa = self._subagents_by_name[tc.tool]
        invocation_id = self._next_subagent_invocation_id()
        frame_span_id = new_span_id()
        # Reuse the tool_span map so inject_correction / on_tool verifiers
        # that look up subject_call_ids still find the subagent invocation.
        self._tool_span_by_call_id[tc.call_id] = frame_span_id
        state.tools_invoked[tc.tool] = state.tools_invoked.get(tc.tool, 0) + 1

        invoked_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": sa.name,
            "aep.subagent.invocation_id": invocation_id,
            "aep.subagent.input": dict(tc.input or {}),
        }
        if sa.description:
            invoked_data["gen_ai.agent.description"] = sa.description

        self._emit(
            SubagentInvokedEvent(
                subject=cfg.run_id,
                data=SubagentInvokedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **invoked_data,
                ),
            )
        )

        if self._subagent_driver is None:
            self._emit_subagent_failed(
                tc=tc,
                state=state,
                sa=sa,
                invocation_id=invocation_id,
                frame_span_id=frame_span_id,
                error="no SubagentDriver configured for this runner",
                error_code="not_configured",
                duration_ms=0,
            )
            return

        t0 = _time.monotonic()
        try:
            outcome = self._subagent_driver.invoke(
                sa,
                dict(tc.input or {}),
                parent_trace_id=self._trace_id,
                parent_frame_span_id=frame_span_id,
                parent_observer=self._emit,
            )
        except Exception as e:
            duration_ms = int((_time.monotonic() - t0) * 1000)
            self._emit_subagent_failed(
                tc=tc,
                state=state,
                sa=sa,
                invocation_id=invocation_id,
                frame_span_id=frame_span_id,
                error=f"{type(e).__name__}: {e}",
                error_code="driver_exception",
                duration_ms=duration_ms,
            )
            return

        # Roll the subagent's spend into the parent's cumulative state so the
        # parent's boundary checks see the true total. The breakdown is
        # preserved on subagent_returned.data.aep.subagent.usage for
        # attribution.
        sa_usage = outcome.usage
        state.total_cost_usd += sa_usage.total_cost_usd
        state.total_tokens += sa_usage.total_tokens
        state.tokens_input_total += sa_usage.tokens_input_total or 0
        state.tokens_output_total += sa_usage.tokens_output_total or 0
        if sa_usage.tokens_cache_read_total:
            state.tokens_cache_read_total += sa_usage.tokens_cache_read_total
        if sa_usage.tokens_cache_write_total:
            state.tokens_cache_write_total += sa_usage.tokens_cache_write_total

        if outcome.error is not None:
            self._emit_subagent_failed(
                tc=tc,
                state=state,
                sa=sa,
                invocation_id=invocation_id,
                frame_span_id=frame_span_id,
                error=outcome.error,
                error_code=outcome.error_code,
                duration_ms=outcome.duration_ms,
            )
            return

        returned_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": sa.name,
            "aep.subagent.invocation_id": invocation_id,
            "duration_ms": outcome.duration_ms,
            "aep.subagent.result.text": outcome.text,
            "aep.subagent.reason": outcome.reason,
            "aep.subagent.usage": sa_usage,
        }
        if outcome.structured is not None:
            returned_data["aep.subagent.result.structured"] = outcome.structured

        self._emit(
            SubagentReturnedEvent(
                subject=cfg.run_id,
                data=SubagentReturnedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **returned_data,
                ),
            )
        )
        # Push the subagent's result back into the parent's history so the
        # parent's next model turn sees it as a normal tool_result. The model
        # invoked the subagent through a tool_use block; without a matching
        # tool_result the API rejects the next turn.
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": outcome.text,
            }
        )

    def _emit_subagent_failed(
        self,
        *,
        tc,
        state: _MutableState,
        sa: Subagent,
        invocation_id: str,
        frame_span_id: str,
        error: str,
        error_code: str | None,
        duration_ms: int,
    ) -> None:
        cfg = self.config
        failed_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": sa.name,
            "aep.subagent.invocation_id": invocation_id,
            "duration_ms": duration_ms,
            "aep.subagent.error": error,
        }
        if error_code is not None:
            failed_data["aep.subagent.error.code"] = error_code

        self._emit(
            SubagentFailedEvent(
                subject=cfg.run_id,
                data=SubagentFailedData(
                    **self._shared_span(frame_span_id, self._current_turn_span_id),
                    **failed_data,
                ),
            )
        )
        # Per the same constraint as _emit_tool_failed: the model's tool_use
        # MUST be answered with a tool_result, even on failure, or the next
        # API call rejects with an unmatched-tool_use_id error.
        self._history.append(
            {
                "role": "tool",
                "tool": tc.tool,
                "call_id": tc.call_id,
                "output": f"Error: {error}",
            }
        )

    # ── Verifier handling ──────────────────────────────────────────────────

    def _run_verifiers_for(self, trigger: str) -> None:
        cfg = self.config
        if not cfg.verifiers:
            return
        for verifier in cfg.verifiers:
            if verifier.trigger != trigger:
                continue
            self._run_verifier(verifier)

    def _run_pre_tool_verifiers(self, tc, state: _MutableState) -> bool:
        """Run all `pre_tool:<tc.tool>` verifiers in declaration order
        before the tool dispatches. Returns True if dispatch should
        proceed, False if the tool was skipped (or run halted).

        - Verifier passes (or has no `pre_tool:<name>` verifier):
          dispatch proceeds. True.
        - Verifier fails with `on_failure: halt`: raises `_VerifierHalt`,
          caught at run() and translated to `verifier_failed`. (Doesn't
          return.)
        - Verifier fails with `on_failure: inject_correction`: the
          correction is queued; the tool is treated as a soft rejection
          so the model has a matching tool_result on the wire and the
          next turn picks up the correction. False.
        - Verifier fails with `on_failure: continue`: the tool is also
          treated as soft-rejected; the model gets `tool_failed` with
          the verifier's reason. False.
        """
        cfg = self.config
        if not cfg.verifiers:
            return True
        trigger = f"pre_tool:{tc.tool}"
        for verifier in cfg.verifiers:
            if verifier.trigger != trigger:
                continue
            t0 = _time.monotonic()
            passed, error, data = self._execute_verifier(verifier, tc=tc)
            duration_ms = int((_time.monotonic() - t0) * 1000)
            kwargs: dict[str, Any] = {
                "aep.verifier.name": verifier.name,
                "aep.verifier.passed": passed,
                "aep.verifier.duration_ms": duration_ms,
                "aep.verifier.subject_call_ids": [tc.call_id],
            }
            if self._state.total_turns:
                kwargs["step"] = self._state.total_turns
            if error is not None:
                kwargs["aep.verifier.error"] = error
            if data:
                kwargs["aep.verifier.data"] = data
            self._emit(
                VerifierEvaluatedEvent(
                    subject=cfg.run_id,
                    data=VerifierEvaluatedData(
                        **self._own_span(self._current_parent_for_run_event()),
                        **kwargs,
                    ),
                )
            )
            if passed:
                # on_success may halt (declarative convergence) or no-op.
                self._apply_verifier_action(verifier, verifier.on_success, success=True)
                continue  # check next pre_tool verifier
            # Failed → tool MUST NOT dispatch. Apply on_failure, then
            # surface to the model as a tool failure if we didn't halt.
            if verifier.on_failure == OnFailure.halt:
                raise _VerifierHalt(success=False)
            # Emit tool_invoked so the trajectory is faithful (agent
            # attempted the call), then tool_failed so the model has a
            # matching tool_result on the wire.
            tool_span_id = new_span_id()
            self._tool_span_by_call_id[tc.call_id] = tool_span_id
            self._emit(
                ToolInvokedEvent(
                    subject=cfg.run_id,
                    data=ToolInvokedData(
                        **self._shared_span(tool_span_id, self._current_turn_span_id),
                        step=state.total_turns,
                        **{
                            "gen_ai.tool.call.id": tc.call_id,
                            "gen_ai.tool.name": tc.tool,
                            "gen_ai.tool.call.arguments": tc.input,
                        },
                    ),
                )
            )
            error_msg = f"pre_tool verifier {verifier.name!r} failed"
            self._emit_tool_failed(tc, state, error_msg)
            # If inject_correction, the correction is appended after
            # tool_failed; the model sees the rejected tool_result this
            # turn and the correction message next turn.
            if verifier.on_failure == OnFailure.inject_correction:
                assert verifier.correction_message is not None
                self._history.append(
                    {
                        "role": "user",
                        "content": verifier.correction_message,
                        "kind": "correction",
                        "verifier_name": verifier.name,
                    }
                )
            return False
        return True

    def _run_verifier(self, verifier: Verifier) -> None:
        t0 = _time.monotonic()
        passed, error, data = self._execute_verifier(verifier)
        duration_ms = int((_time.monotonic() - t0) * 1000)
        cfg = self.config
        kwargs: dict[str, Any] = {
            "aep.verifier.name": verifier.name,
            "aep.verifier.passed": passed,
            "aep.verifier.duration_ms": duration_ms,
        }
        if self._state.total_turns:
            kwargs["step"] = self._state.total_turns
        if error is not None:
            kwargs["aep.verifier.error"] = error
        if data:
            kwargs["aep.verifier.data"] = data

        self._emit(
            VerifierEvaluatedEvent(
                subject=cfg.run_id,
                data=VerifierEvaluatedData(
                    **self._own_span(self._current_parent_for_run_event()),
                    **kwargs,
                ),
            )
        )
        action = verifier.on_success if passed else verifier.on_failure
        self._apply_verifier_action(verifier, action, success=passed)

    def _execute_verifier(
        self, verifier: Verifier, *, tc: Any | None = None
    ) -> tuple[bool, VerifierError | None, dict[str, Any] | None]:
        """Execute a verifier source. Returns (passed, error, optional data dict).

        `error` distinguishes environment failures from rule failures:
          - source_timed_out: subprocess.TimeoutExpired or approval RPC timed out
          - source_unavailable: shell exit 127 ("command not found")
          - source_crashed: any other unexpected subprocess error
          - None: the source ran to completion (exit 0 = pass / approved;
            non-0 = rule fail / denied)

        For approval-source verifiers, `tc` carries the tool-call context
        for the gate so the supervisor sees what's being approved.
        """
        src = verifier.source
        if isinstance(src, VerifierSourceApproval):
            return self._execute_approval_verifier(verifier, tc=tc)
        # Shell source (existing path)
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
                {"command": src.shell, "timeout_ms": verifier.timeout_ms},
            )
        except OSError as e:
            return (
                False,
                VerifierError.source_crashed,
                {"command": src.shell, "stderr": str(e)[:2000]},
            )

        data: dict[str, Any] = {"command": src.shell, "exit_code": result.returncode}
        if result.stdout:
            data["stdout"] = result.stdout[:2000]
        if result.stderr:
            data["stderr"] = result.stderr[:2000]

        # Exit 127 = "command not found" from sh. Treat as source-unavailable
        # so consumers can distinguish "the rule script wasn't there" from
        # "the rule script ran and said no."
        if result.returncode == 127:
            return False, VerifierError.source_unavailable, data
        passed = result.returncode == 0
        return passed, None, data

    def _execute_approval_verifier(
        self, verifier: Verifier, *, tc: Any | None
    ) -> tuple[bool, VerifierError | None, dict[str, Any] | None]:
        """Run an approval-source verifier: emit `approval_requested`,
        suspend until the supervisor replies with `approval_resolved`,
        record the reply, and return passed=approved.

        Timeout is treated as a denial — same effect as
        `aep.approval.approved=false`. The trajectory shows
        `aep.verifier.error = source_timed_out` so consumers can
        distinguish "supervisor said no" from "supervisor went away."
        """
        cfg = self.config
        assert isinstance(verifier.source, VerifierSourceApproval)
        approval_id = self._next_approval_id()
        rpc_span_id = new_span_id()
        self._approval_span_by_id[approval_id] = rpc_span_id

        request_data: dict[str, Any] = {
            "step": self._state.total_turns,
            "aep.approval.id": approval_id,
            "aep.timeout_ms": verifier.timeout_ms,
            "aep.verifier.name": verifier.name,
        }
        if verifier.source.approval.prompt:
            request_data["aep.approval.prompt"] = verifier.source.approval.prompt
        if tc is not None:
            request_data["gen_ai.tool.name"] = tc.tool
            request_data["gen_ai.tool.call.id"] = tc.call_id
            request_data["gen_ai.tool.call.arguments"] = dict(tc.input or {})

        self._emit(
            ApprovalRequestedEvent(
                subject=cfg.run_id,
                data=ApprovalRequestedData(
                    **self._shared_span(rpc_span_id, self._current_parent_for_run_event()),
                    **request_data,
                ),
            )
        )

        msg = self.supervisor.get_approval_response(approval_id, verifier.timeout_ms)
        if msg is None:
            # Timeout — treat as denial.
            return (
                False,
                VerifierError.source_timed_out,
                {
                    "approval_id": approval_id,
                    "timeout_ms": verifier.timeout_ms,
                    "reason": "supervisor did not respond within timeout",
                },
            )

        assert isinstance(msg, ApprovalResolvedEvent)
        # Re-stamp the supervisor's reply with our trace context so the
        # span tree is consistent (same pattern as tool_exec_resolved).
        new_data = msg.data.model_copy(
            update={
                "trace_id": self._trace_id,
                "span_id": rpc_span_id,
                "parent_span_id": self._current_parent_for_run_event(),
            }
        )
        msg = msg.model_copy(update={"data": new_data})
        self._emit(msg)

        approved = msg.data.aep_approval_approved
        data: dict[str, Any] = {"approval_id": approval_id, "approved": approved}
        if msg.data.aep_approval_reason:
            data["reason"] = msg.data.aep_approval_reason
        return approved, None, data

    def _apply_verifier_action(
        self, verifier: Verifier, action: OnFailure, *, success: bool
    ) -> None:
        """Take the configured action after a verifier completes.

        `action` is `verifier.on_success` when the check passed,
        `verifier.on_failure` when it failed. `success` is recorded on
        `_VerifierHalt` so run() can map halt-on-success to
        `StopReason.converged` (declarative convergence) and
        halt-on-failure to `StopReason.verifier_failed` (invariant
        broken).
        """
        if action == OnFailure.continue_:
            return
        if action == OnFailure.halt:
            raise _VerifierHalt(success=success)
        if action == OnFailure.inject_correction:
            assert verifier.correction_message is not None
            self._history.append(
                {
                    "role": "user",
                    "content": verifier.correction_message,
                    "kind": "correction",
                    "verifier_name": verifier.name,
                }
            )
            return
        raise ValueError(f"unknown verifier action {action!r}")

    # ── First / last events ─────────────────────────────────────────────────

    def _build_tool_decls(self) -> list[dict[str, Any]] | None:
        """Effective tool surface for `agent_started.data.tools` -- what the model
        can actually call. = (Config.tools RPC + runner built-ins) filtered by
        Config.allowed_tools when set. MCP-shaped (camelCase `inputSchema`)."""
        cfg = self.config
        candidates: list[dict[str, Any]] = []
        if cfg.tools:
            for t in cfg.tools:
                entry: dict[str, Any] = {"name": t.name}
                if t.description is not None:
                    entry["description"] = t.description
                if t.inputSchema is not None:
                    entry["inputSchema"] = t.inputSchema
                entry["aep.dispatch_target"] = "supervisor_rpc"
                candidates.append(entry)
        for bt in self._runner_builtin_tools:
            entry = {"name": bt["name"]}
            if "description" in bt and bt["description"] is not None:
                entry["description"] = bt["description"]
            schema = bt.get("inputSchema") or bt.get("input_schema")
            if schema is not None:
                entry["inputSchema"] = schema
            entry["aep.dispatch_target"] = "local"
            candidates.append(entry)
        if self._allowed_tools is not None:
            candidates = [c for c in candidates if c["name"] in self._allowed_tools]
        return candidates or None

    def _build_subagent_decls(self) -> list[dict[str, Any]] | None:
        """Subagent descriptors for `agent_started.data.subagents`. Filtered
        by allowed_tools when set (same rule as tools — the model only sees
        what's permitted)."""
        cfg = self.config
        if not cfg.subagents:
            return None
        decls: list[dict[str, Any]] = []
        for sa in cfg.subagents:
            entry: dict[str, Any] = {"name": sa.name, "description": sa.description}
            if sa.inputSchema is not None:
                entry["inputSchema"] = sa.inputSchema
            decls.append(entry)
        if self._allowed_tools is not None:
            decls = [d for d in decls if d["name"] in self._allowed_tools]
        return decls or None

    def _emit_agent_started(self) -> None:
        cfg = self.config
        tools_meta = self._build_tool_decls()
        skills_meta = [s.name for s in (cfg.skills or [])] or None
        subagents_meta = self._build_subagent_decls()

        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": cfg.prompt,
            "system_prompt": cfg.system_prompt,
            "tools": tools_meta,
            "skills": skills_meta,
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
        if cfg.system_prompt:
            self._history.append({"role": "system", "content": cfg.system_prompt})
        if cfg.prompt:
            self._history.append({"role": "user", "content": cfg.prompt})

    def _emit_skills_loaded(self) -> None:
        cfg = self.config
        if not cfg.skills:
            return
        for skill in cfg.skills:
            self._emit(
                SkillLoadedEvent(
                    subject=cfg.run_id,
                    data=SkillLoadedData(
                        **self._own_span(self._agent_span_id),
                        step=0,
                        **{
                            "aep.skill.name": skill.name,
                            "aep.skill.source": skill.aep_source,
                        },
                    ),
                )
            )

    def _emit_mcp_connections(self) -> None:
        """v0.1: emit `mcp_server_connected` for each declared MCP server. The
        wire format ships now; the live transport (real `initialize` /
        `tools/list` over HTTP or stdio) is deferred to a future minor — the
        reference runner emits a stub event so supervisors can pin the
        lifecycle in tests today."""
        cfg = self.config
        if not cfg.mcp_servers:
            return
        for server in cfg.mcp_servers:
            self._emit_mcp_connected(server)

    def _emit_mcp_connected(self, server: McpServer) -> None:
        cfg = self.config
        self._emit(
            McpServerConnectedEvent(
                subject=cfg.run_id,
                data=McpServerConnectedData(
                    **self._own_span(self._agent_span_id),
                    **{
                        "aep.mcp.server_id": server.id,
                        "aep.mcp.protocol_version": MCP_PROTOCOL_VERSION,
                        "aep.mcp.tool_count": 0,
                    },
                ),
            )
        )

    def _emit_mcp_disconnections(self, reason: str) -> None:
        cfg = self.config
        if not cfg.mcp_servers:
            return
        for server in cfg.mcp_servers:
            self._emit(
                McpServerDisconnectedEvent(
                    subject=cfg.run_id,
                    data=McpServerDisconnectedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "aep.mcp.server_id": server.id,
                            "aep.mcp.disconnect_reason": reason,
                        },
                    ),
                )
            )

    def _emit_agent_stopped(self, reason: StopReason) -> AgentStoppedEvent:
        cfg = self.config
        # Emit MCP disconnect events idempotently — _emit_mcp_disconnections
        # already returns when mcp_servers is empty. Callers that knew they
        # had to disconnect early (validation failure, _VerifierHalt) call it
        # before this; the normal exit path relies on this finalizer.
        self._emit_mcp_disconnections("clean")
        snap = self._state.snapshot(_monotonic_ms())
        ev = AgentStoppedEvent(
            subject=cfg.run_id,
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


__all__ = ["AEPRunner"]
