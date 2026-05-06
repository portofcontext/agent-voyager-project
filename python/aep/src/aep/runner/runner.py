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
    RunStateSnapshot,
    SkillLoadedData,
    SkillLoadedEvent,
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
    """Raised internally when a verifier with on_failure=halt fails."""


class AEPRunner:
    """Reference AEP runner. v0.1 model: declarative environment, no mid-run reach-in."""

    def __init__(
        self,
        config: Config,
        model: ModelDriver,
        tools: ToolDriver,
        supervisor: SupervisorDriver,
        runner_builtin_tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """`runner_builtin_tools` declares the runner's built-in tool catalog.
        Each entry is `{name, description, input_schema}` (snake_case, internal).
        Used to compute the effective tool surface for `agent_started.data.tools`."""
        self.config = config
        self.model = model
        self.tools = tools
        self.supervisor = supervisor
        self.trajectory: list[BaseModel | dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._supervisor_tools_by_name: dict[str, Tool] = {t.name: t for t in (config.tools or [])}
        self._runner_builtin_tools = list(runner_builtin_tools or [])
        self._allowed_tools: frozenset[str] | None = (
            frozenset(config.allowed_tools) if config.allowed_tools is not None else None
        )
        self._req_seq = itertools.count(1)
        self._next_request_id = lambda: f"req-{next(self._req_seq)}"

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
        except _VerifierHalt:
            return self._emit_agent_stopped(StopReason.verifier_failed)

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
        """Cross-field check: every Config.tools name MUST be in allowed_tools (when set)."""
        if self._allowed_tools is None:
            return True
        cfg = self.config
        declared = {t.name for t in (cfg.tools or [])}
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
                                f"Config.tools; missing: {excluded}"
                            ),
                        },
                    ),
                )
            )
            return False
        return True

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

    # ── Verifier handling ──────────────────────────────────────────────────

    def _run_verifiers_for(self, trigger: str) -> None:
        cfg = self.config
        if not cfg.verifiers:
            return
        for verifier in cfg.verifiers:
            if verifier.trigger != trigger:
                continue
            self._run_verifier(verifier)

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

    def _apply_on_failure(self, verifier: Verifier) -> None:
        if verifier.on_failure == OnFailure.continue_:
            return
        if verifier.on_failure == OnFailure.halt:
            raise _VerifierHalt()
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
            return
        raise ValueError(f"unknown on_failure {verifier.on_failure!r}")

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

    def _emit_agent_started(self) -> None:
        cfg = self.config
        tools_meta = self._build_tool_decls()
        skills_meta = [s.name for s in (cfg.skills or [])] or None

        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": cfg.prompt,
            "system_prompt": cfg.system_prompt,
            "tools": tools_meta,
            "skills": skills_meta,
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
