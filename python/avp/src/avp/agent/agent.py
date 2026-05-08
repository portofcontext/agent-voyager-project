"""AVPAgent — the v0.1 normative loop.

The agent runs inside the supervisor's declared environment. Tools come
from Commission; the supervisor does not reach in mid-run; the agent emits
facts. The only mid-run wire interaction is tool_exec, an agent-initiated
RPC into a service the supervisor stood up at Commission time.

Each emitted event is a CloudEvent 1.0 envelope carrying typed `data`. Span
identification (`trace_id`, `span_id`, `parent_span_id`) follows OpenTelemetry
conventions so the trajectory reconstructs as a span tree:

    agent span (root)                                       agent_started/stopped
    ├── skill span                                          skill_loaded/executed
    ├── error span                                          error_occurred (run-level)
    ├── model_turn span (per turn)                          model_turn_started/ended
    │   ├── text span                                       text_emitted
    │   ├── cost span                                       cost_recorded
    │   └── tool span (per tool call)                       tool_invoked/returned/failed
    │       └── rpc span (per agent-initiated RPC)          tool_exec_request/resolved/timed_out
"""

from __future__ import annotations

import itertools
import time as _time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from avp.agent.drivers import (
    ModelDriver,
    ModelDriverError,
    SubagentDriver,
    SupervisorDriver,
    ToolDriver,
    ToolOutcome,
)
from avp.enums import ErrorCode, StopReason
from avp.types import (
    ZERO_SPAN_ID,
    AgentDescribedData,
    AgentDescribedEvent,
    AgentManifest,
    AgentStartedData,
    AgentStartedEvent,
    AgentStoppedData,
    AgentStoppedEvent,
    Commission,
    CostRecordedData,
    CostRecordedEvent,
    ErrorOccurredData,
    ErrorOccurredEvent,
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
    RunRequestedData,
    RunRequestedEvent,
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
    ToolFailedData,
    ToolFailedEvent,
    ToolInvokedData,
    ToolInvokedEvent,
    ToolReturnedData,
    ToolReturnedEvent,
    new_span_id,
    new_trace_id,
    now_iso,
)

MCP_PROTOCOL_VERSION = "2025-11-25"


class _UnsupportedSkillSource(Exception):
    """Raised by `_read_skill_source` when an avp.source URI scheme is
    valid in the spec but not implemented by this agent build (e.g.,
    mcp:// in the reference agent which has no live MCP transport)."""


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


# ── The agent ────────────────────────────────────────────────────────────────


class AVPAgent:
    """Reference AVP agent. v0.1 model: declarative environment, no mid-run reach-in."""

    def __init__(
        self,
        commission: Commission,
        model: ModelDriver,
        tools: ToolDriver,
        supervisor: SupervisorDriver,
        agent_builtin_tools: list[dict[str, Any]] | None = None,
        subagent_driver: SubagentDriver | None = None,
        *,
        manifest: AgentManifest | None = None,
        on_event: Callable[[BaseModel], None] | None = None,
    ) -> None:
        """`agent_builtin_tools` declares the agent's built-in tool catalog.
        Each entry is `{name, description, input_schema}` (snake_case, internal).
        Used to compute the effective tool surface for `agent_started.data.tools`.

        `subagent_driver` is required iff `commission.subagents` is non-empty.
        Without one declared, subagent invocations fail with a clear error
        rather than silently degrading.

        `manifest` is the agent's self-description (see `AgentManifest`).
        When provided, the agent opens the trajectory with the
        `run_requested` → `agent_described` prelude before `agent_started`.
        When None, the prelude is skipped — used by embedded callers
        (the in-process supervisor example, conformance harness) that drive
        AVPAgent against a synthetic Commission without a packaged agent
        identity. Top-level CLI invocations (`avp-anthropic`,
        `avp-claude-agent`) MUST pass a manifest so the wire is complete.

        `on_event` is an optional callback invoked synchronously as each event
        is emitted, BEFORE it lands in `self.trajectory`. The agent still
        accumulates the trajectory in memory for in-process consumers (tests,
        the CLI's post-run summary); the callback is for streaming consumers
        (workers writing events to durable storage as they happen, multi-host
        supervisors observing the run live, etc.). Mirrors `AVPTracer`'s
        `on_event` shape so the embedded-agent and drop-in-tracer paths feel
        identical to consumers. The callback MUST NOT mutate the event; it
        runs on the agent's thread and any exception propagates out.
        """
        self.commission = commission
        self.model = model
        self.tools = tools
        self.supervisor = supervisor
        self._manifest = manifest
        self._on_event = on_event
        self.trajectory: list[BaseModel | dict[str, Any]] = []
        self._history: list[dict[str, Any]] = []
        self._subagents_by_name: dict[str, Subagent] = {
            sa.name: sa for sa in (commission.subagents or [])
        }
        self._subagent_driver = subagent_driver
        self._agent_builtin_tools = list(agent_builtin_tools or [])
        # Commission.exposed is the supervisor-declared exhaustive surface.
        # Stored verbatim here; resolution happens in `_validate_exposed`
        # after mcp_server_connected events fire (so the catalog is known).
        # Built-in / subagent filtering during `_emit_agent_started` uses
        # `_matches_exposed` directly against the patterns.
        self._exposed_patterns: list[str] = list(commission.exposed)
        # Populated by `_validate_exposed` post-MCP-handshake. Used at
        # runtime to gate model-attempted tool calls. Stays None until
        # validation has run (which is after agent_started so consumers
        # of agent_started.data.tools see the partial built-ins-only view).
        self._resolved_exposed: frozenset[str] | None = None
        # Populated by `_load_skill_bodies` during run prelude — maps
        # skill name → SKILL.md body text. `_emit_agent_started` consults
        # it to build the effective system prompt; `_emit_skills_loaded`
        # only fires for skills whose body is in this dict (so the
        # `skill_loaded` event truthfully signals "body in context").
        self._loaded_skill_bodies: dict[str, str] = {}
        self._sa_seq = itertools.count(1)
        self._next_subagent_invocation_id = lambda: f"sa-{next(self._sa_seq)}"

        # Span tree state. trace_id is allocated per run; agent_span_id is the
        # root span (lifetime = the run); turn / tool spans are nested.
        self._trace_id: str = new_trace_id()
        self._agent_span_id: str = new_span_id()
        self._current_turn_span_id: str | None = None
        self._tool_span_by_call_id: dict[str, str] = {}

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
        with the agent span (e.g., error_occurred)."""
        return self._current_turn_span_id or self._agent_span_id

    # ── Emission ────────────────────────────────────────────────────────────

    def _emit(self, event: BaseModel) -> None:
        # Callback fires BEFORE trajectory append so a worker writing to
        # durable storage sees the event in the same order an in-process
        # consumer reading `trajectory` will. If the callback raises, the
        # event isn't appended either — the run aborts with the exception
        # propagated out of run(), matching the "agent errors are loud"
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

        self._emit_run_prelude()
        # Resolve skill bodies BEFORE agent_started so the system prompt
        # the model sees actually contains them. A failed resolution
        # short-circuits with error_occurred + agent_stopped(error).
        if not self._load_skill_bodies():
            self._emit_agent_started()
            return self._emit_agent_stopped(StopReason.error)
        self._emit_agent_started()
        self._emit_skills_loaded()
        self._emit_mcp_connections()

        if not self._validate_supported_model():
            return self._emit_agent_stopped(StopReason.error)
        if not self._validate_exposed():
            return self._emit_agent_stopped(StopReason.error)

        self._main_loop()

        # Normal exit (loop returned) — close MCP connections cleanly before
        # the agent_stopped this path emits.
        for ev in reversed(self.trajectory):
            if isinstance(ev, AgentStoppedEvent):
                return ev
        raise RuntimeError("AVPAgent: trajectory missing agent_stopped — invariant violation")

    # ── Main loop ───────────────────────────────────────────────────────────

    def _main_loop(self) -> None:
        state = self._state
        commission = self.commission

        while True:
            state.total_turns += 1
            self._current_turn_span_id = new_span_id()
            turn_started_kwargs: dict[str, Any] = {"avp.context_messages": len(self._history)}
            self._emit(
                ModelTurnStartedEvent(
                    subject=commission.run_id,
                    data=ModelTurnStartedData(
                        **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                        step=state.total_turns,
                        **turn_started_kwargs,
                    ),
                )
            )
            try:
                response = self.model.step(self._history)
            except ModelDriverError as e:
                # Driver classified the failure (rate_limit / auth_error /
                # context_limit / etc.) — emit error_occurred with that
                # code, close the turn span without usage, and stop with
                # reason=error. Untyped exceptions fall through to the
                # outer crash handler which emits agent_crash.
                self._emit(
                    ModelTurnEndedEvent(
                        subject=commission.run_id,
                        data=ModelTurnEndedData(
                            **self._shared_span(self._current_turn_span_id, self._agent_span_id),
                            step=state.total_turns,
                            duration_ms=0,
                            **{
                                "gen_ai.usage.input_tokens": 0,
                                "gen_ai.usage.output_tokens": 0,
                                "avp.cost_usd": 0.0,
                            },
                        ),
                    )
                )
                self._emit(
                    ErrorOccurredEvent(
                        subject=commission.run_id,
                        data=ErrorOccurredData(
                            **self._own_span(self._agent_span_id),
                            **{
                                "avp.error.code": e.code,
                                "avp.error.message": str(e),
                            },
                        ),
                    )
                )
                self._emit_agent_stopped(StopReason.error)
                return
            ended_kwargs: dict[str, Any] = {
                "gen_ai.usage.input_tokens": response.tokens_input,
                "gen_ai.usage.output_tokens": response.tokens_output,
                "gen_ai.usage.cache_read.input_tokens": response.tokens_cache_read,
                "gen_ai.usage.cache_creation.input_tokens": response.tokens_cache_write,
                "gen_ai.usage.reasoning.output_tokens": response.tokens_reasoning_output,
                "avp.cost_usd": response.cost_usd,
                "avp.cost.source": response.cost_source,
            }
            if response.response_model is not None:
                ended_kwargs["gen_ai.response.model"] = response.response_model
            if response.finish_reasons:
                ended_kwargs["gen_ai.response.finish_reasons"] = response.finish_reasons
            if response.time_to_first_chunk_s is not None:
                ended_kwargs["gen_ai.response.time_to_first_chunk"] = response.time_to_first_chunk_s
            self._emit(
                ModelTurnEndedEvent(
                    subject=commission.run_id,
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
                    subject=commission.run_id,
                    data=CostRecordedData(
                        **self._own_span(self._current_turn_span_id),
                        **{"avp.state": state.snapshot(_monotonic_ms())},
                    ),
                )
            )

            # Reasoning / thinking blocks land BEFORE text and tool calls —
            # the wire reconstructs the turn as "thought, then spoke / acted".
            # Each block becomes its own event so consumers can collapse
            # chain-of-thought from displays without losing it from the audit.
            for rb in response.reasoning_blocks:
                reasoning_kwargs: dict[str, Any] = {"avp.reasoning.text": rb.text}
                if rb.signature:
                    reasoning_kwargs["avp.reasoning.signature"] = rb.signature
                if rb.redacted:
                    reasoning_kwargs["avp.reasoning.redacted"] = rb.redacted
                self._emit(
                    ReasoningEmittedEvent(
                        subject=commission.run_id,
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
                        subject=commission.run_id,
                        data=TextEmittedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **{"avp.text": response.text},
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
                    "avp.refusal.reason": response.refusal.reason,
                }
                if response.refusal.message:
                    refusal_kwargs["avp.refusal.message"] = response.refusal.message
                if response.refusal.category:
                    refusal_kwargs["avp.refusal.category"] = response.refusal.category
                if response.refusal.provider:
                    refusal_kwargs["avp.refusal.provider"] = response.refusal.provider
                self._emit(
                    RefusalRecordedEvent(
                        subject=commission.run_id,
                        data=RefusalRecordedData(
                            **self._own_span(self._current_turn_span_id),
                            step=state.total_turns,
                            **refusal_kwargs,
                        ),
                    )
                )
                self._emit_agent_stopped(StopReason.refused)
                return

            # Server-side tool calls (e.g. Anthropic's MCP connector running
            # `mcp_tool_use` blocks inline during the request, or hosted
            # `web_search_tool_use` blocks). These ALREADY happened — no
            # agent dispatch — so we emit synthetic tool_invoked /
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

            if response.converged:
                self._emit_agent_stopped(StopReason.converged)
                return

    # ── Tool handling ────────────────────────────────────────────────────────

    def _load_skill_bodies(self) -> bool:
        """Resolve each `Commission.skills[]` entry's `avp.source` and
        read the SKILL.md body. Stores the body in
        `self._loaded_skill_bodies` keyed by skill name; the
        `_emit_agent_started` history seed and `_emit_skills_loaded`
        event emission both consult it.

        URI schemes:

          - **Relative path** (e.g. `./skills/code-review` or
            `./skills/code-review/SKILL.md`): resolved against the agent's
            CWD. If the path is a directory, `SKILL.md` at its root is
            read. YAML frontmatter is stripped; the body is what remains.
          - **`mcp://<server-id>/<resource-path>`**: deferred. The
            reference agent doesn't drive a live MCP transport; production
            agents that do MUST call `resources/read` on the named server
            and return the body content here. The reference agent emits
            `error_occurred(unknown)` for these and returns False so the
            run stops cleanly with reason=error.

        Returns False (and emits `error_occurred`) on any resolution
        failure — the run-level error gate then terminates with
        reason=error. Returns True when every skill resolved cleanly,
        OR when there are no skills declared.
        """
        commission = self.commission
        if not commission.skills:
            return True
        for skill in commission.skills:
            source = skill.avp_source or ""
            try:
                body = self._read_skill_source(source)
            except _UnsupportedSkillSource as e:
                self._emit_skill_load_error(skill.name, source, str(e))
                return False
            except FileNotFoundError as e:
                self._emit_skill_load_error(skill.name, source, f"file not found: {e}")
                return False
            except Exception as e:
                self._emit_skill_load_error(skill.name, source, f"{type(e).__name__}: {e}")
                return False
            self._loaded_skill_bodies[skill.name] = body
        return True

    @staticmethod
    def _read_skill_source(source: str) -> str:
        """Resolve a skill source URI to its SKILL.md body text. See
        `_load_skill_bodies` for URI scheme rules."""
        if source.startswith("mcp://"):
            raise _UnsupportedSkillSource(
                f"mcp:// skill resolution requires a live MCP transport; "
                f"the reference agent ships filesystem resolution only "
                f"(source={source!r})"
            )
        path = Path(source)
        if path.is_dir():
            path = path / "SKILL.md"
        text = path.read_text()
        # Strip YAML frontmatter (--- ... ---) if present.
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end > 0:
                # Skip past the closing fence and any trailing newline.
                tail = text[end + 4 :]
                text = tail.lstrip("\n")
        return text.strip()

    def _emit_skill_load_error(self, skill_name: str, source: str, message: str) -> None:
        self._emit(
            ErrorOccurredEvent(
                subject=self.commission.run_id,
                data=ErrorOccurredData(
                    **self._own_span(self._agent_span_id),
                    **{
                        "avp.error.code": ErrorCode.unknown,
                        "avp.error.message": (
                            f"Failed to load skill {skill_name!r} from {source!r}: {message}"
                        ),
                    },
                ),
            )
        )

    def _validate_supported_model(self) -> bool:
        """Cross-check Commission.model against the agent's
        manifest.supported_models (glob list). Skipped when no manifest is
        published, when the manifest declares no constraint, or when the
        Commission omits `model` (drivers fall back to their own default).

        Mismatch → emit `error_occurred(code=unsupported_model)` and signal
        stop with reason=error. Catches the avp-claude-agent + gpt-4 case
        cleanly at startup instead of at the first provider call.
        """
        import fnmatch

        commission = self.commission
        manifest = self._manifest
        if manifest is None or manifest.supported_models is None:
            return True
        if not commission.model:
            return True
        if any(fnmatch.fnmatchcase(commission.model, p) for p in manifest.supported_models):
            return True
        self._emit(
            ErrorOccurredEvent(
                subject=commission.run_id,
                data=ErrorOccurredData(
                    **self._own_span(self._agent_span_id),
                    **{
                        "avp.error.code": ErrorCode.unsupported_model,
                        "avp.error.message": (
                            f"Commission.model={commission.model!r} is not supported by "
                            f"{manifest.agent_name}@{manifest.agent_version}; "
                            f"supported_models={manifest.supported_models}"
                        ),
                    },
                ),
            )
        )
        return False

    @staticmethod
    def _is_glob(pattern: str) -> bool:
        """fnmatch glob characters: `*`, `?`, `[`."""
        return any(c in pattern for c in "*?[")

    def _matches_exposed(self, name: str) -> bool:
        """Check whether `name` matches any pattern in Commission.exposed."""
        import fnmatch

        return any(fnmatch.fnmatchcase(name, p) for p in self._exposed_patterns)

    def _validate_exposed(self) -> bool:
        """Resolve `Commission.exposed` against the full model-facing
        surface and build the runtime-gating set in `_resolved_exposed`.

        Cross-field rules enforced here (per SPEC §8.2):

          1. Subagent names MUST NOT collide with built-in tool names.
          2. Literal entries in `exposed` MUST resolve to at least one
             real name. Glob entries MAY resolve to zero (patterns describe
             sets; an empty set is legitimate).
          3. Every `Commission.subagents[].name` MUST be matched by some
             entry in `exposed` (literal or glob).

        Runs AFTER `mcp_server_connected` events fire so the live MCP
        catalog is available. Sources of "available" names:

          - `manifest.built_in_tools[].name`
          - `manifest.built_in_subagents[].name`
          - `Commission.subagents[].name`
          - Each connected MCP server's catalog from
            `mcp_server_connected.data.avp.mcp.tools[].name`

        On failure: emit `error_occurred(code: "exposed_unresolved")`
        and return False (the run-prelude gate then stops with reason=error).
        """
        import fnmatch

        commission = self.commission

        builtin_tool_names = {bt["name"] for bt in self._agent_builtin_tools}
        if self._manifest is not None:
            builtin_tool_names |= {t.name for t in (self._manifest.built_in_tools or [])}
            builtin_subagent_names = {s.name for s in (self._manifest.built_in_subagents or [])}
        else:
            builtin_subagent_names = set()
        commission_subagent_names = {sa.name for sa in (commission.subagents or [])}

        mcp_tool_names: set[str] = set()
        for ev in self.trajectory:
            if isinstance(ev, McpServerConnectedEvent):
                for tool in ev.data.avp_mcp_tools or []:
                    mcp_tool_names.add(tool.name)

        available = (
            builtin_tool_names | builtin_subagent_names | commission_subagent_names | mcp_tool_names
        )

        # Rule 1: subagent / built-in tool name collision.
        collisions = sorted(commission_subagent_names & builtin_tool_names)
        if collisions:
            self._emit_exposed_error(
                f"Commission.subagents[].name must not collide with tool names; "
                f"colliding: {collisions}"
            )
            return False

        # Rule 2: resolve each entry; literals must match at least one name.
        resolved: set[str] = set()
        unresolved_literals: list[str] = []
        for entry in self._exposed_patterns:
            if self._is_glob(entry):
                resolved |= {n for n in available if fnmatch.fnmatchcase(n, entry)}
            elif entry in available:
                resolved.add(entry)
            else:
                unresolved_literals.append(entry)

        if unresolved_literals:
            self._emit_exposed_error(
                f"Commission.exposed contains literal name(s) that resolved "
                f"to nothing: {unresolved_literals}. Available names at "
                f"validation time: {sorted(available)}. Use a glob pattern "
                f"(e.g. 'mcp__server__*') for trust-the-namespace exposure, "
                f"or remove names the agent no longer offers."
            )
            return False

        # Rule 3: every declared subagent must be matched.
        excluded_subagents = sorted(commission_subagent_names - resolved)
        if excluded_subagents:
            self._emit_exposed_error(
                f"Commission.exposed must match every name in "
                f"Commission.subagents (literal or glob); missing: "
                f"{excluded_subagents}"
            )
            return False

        self._resolved_exposed = frozenset(resolved)
        return True

    def _emit_exposed_error(self, message: str) -> None:
        self._emit(
            ErrorOccurredEvent(
                subject=self.commission.run_id,
                data=ErrorOccurredData(
                    **self._own_span(self._agent_span_id),
                    **{
                        "avp.error.code": ErrorCode.exposed_unresolved,
                        "avp.error.message": message,
                    },
                ),
            )
        )

    def _emit_server_tool_call(self, stc, state: _MutableState) -> None:
        """Emit synthetic tool_invoked + tool_returned (or tool_failed) for a
        tool the API/SDK ran server-side during this turn.

        These events are observational — no agent dispatch happens. We
        share one span across the pair so consumers can correlate them
        the same way they correlate agent-dispatched tools.
        Parent span is the current turn (the call happened inline during
        that model request). Tags `avp.tool.dispatch_target` and, when
        present, `avp.mcp_server_id` come from the driver.
        """
        commission = self.commission
        tool_span_id = new_span_id()
        invoked_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": stc.call_id,
            "gen_ai.tool.name": stc.tool,
            "gen_ai.tool.call.arguments": dict(stc.input),
            "avp.tool.dispatch_target": stc.dispatch_target,
        }
        if stc.server_id:
            invoked_kwargs["avp.mcp_server_id"] = stc.server_id
        if stc.subtype:
            invoked_kwargs["avp.tool.subtype"] = stc.subtype
        self._emit(
            ToolInvokedEvent(
                subject=commission.run_id,
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
                    subject=commission.run_id,
                    data=ToolFailedData(
                        **self._shared_span(tool_span_id, self._current_turn_span_id),
                        step=state.total_turns,
                        **{
                            "gen_ai.tool.call.id": stc.call_id,
                            "gen_ai.tool.name": stc.tool,
                            "avp.tool.error": stc.output_text or "server-side tool reported error",
                        },
                    ),
                )
            )
            return
        returned_kwargs: dict[str, Any] = {
            "gen_ai.tool.call.id": stc.call_id,
            "gen_ai.tool.name": stc.tool,
            "avp.tool.result.text": stc.output_text,
        }
        if stc.output_structured is not None:
            returned_kwargs["avp.tool.result.structured"] = stc.output_structured
        self._emit(
            ToolReturnedEvent(
                subject=commission.run_id,
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
        commission = self.commission
        tool_span_id = self._tool_span_by_call_id.get(tc.call_id) or new_span_id()
        self._emit(
            ToolFailedEvent(
                subject=commission.run_id,
                data=ToolFailedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    step=state.total_turns,
                    **{
                        "gen_ai.tool.call.id": tc.call_id,
                        "gen_ai.tool.name": tc.tool,
                        "avp.tool.error": error,
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
        commission = self.commission

        # Subagent invocations route through their own lifecycle
        # (subagent_invoked / subagent_returned / subagent_failed) — they do
        # not surface as tool_invoked. The subagent's frame is its own span;
        # its internal model_turn / tool / text events nest under that frame.
        if tc.tool in self._subagents_by_name:
            if not self._matches_exposed(tc.tool):
                # `exposed` applies to subagent names too — they're what the
                # model sees. Emit tool_failed (same rejection shape as any
                # other surface miss); never emit subagent_invoked for an
                # invocation we never dispatched.
                tool_span_id = new_span_id()
                self._tool_span_by_call_id[tc.call_id] = tool_span_id
                self._emit(
                    ToolInvokedEvent(
                        subject=commission.run_id,
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
                self._emit_tool_failed(tc, state, f"subagent {tc.tool!r} not in Commission.exposed")
                return
            self._handle_subagent_call(tc, state)
            return

        tool_span_id = new_span_id()
        self._tool_span_by_call_id[tc.call_id] = tool_span_id

        is_local = self.tools.is_local(tc.tool)
        dispatch_target = "local" if is_local else None

        invoked_data_kwargs: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.tool.call.id": tc.call_id,
            "gen_ai.tool.name": tc.tool,
            "gen_ai.tool.call.arguments": tc.input,
        }
        if dispatch_target is not None:
            invoked_data_kwargs["avp.tool.dispatch_target"] = dispatch_target

        self._emit(
            ToolInvokedEvent(
                subject=commission.run_id,
                data=ToolInvokedData(
                    **self._shared_span(tool_span_id, self._current_turn_span_id),
                    **invoked_data_kwargs,
                ),
            )
        )
        state.tools_invoked[tc.tool] = state.tools_invoked.get(tc.tool, 0) + 1

        if not self._matches_exposed(tc.tool):
            self._emit_tool_failed(tc, state, f"tool {tc.tool!r} not in Commission.exposed")
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
            "avp.tool.result.text": out_str,
        }
        if outcome.output_json is not None:
            returned_kwargs["avp.tool.result.structured"] = outcome.output_json
        if outcome.rejected:
            returned_kwargs["avp.tool.rejected"] = True
        if outcome.rejection_reason:
            returned_kwargs["avp.tool.rejection_reason"] = outcome.rejection_reason

        self._emit(
            ToolReturnedEvent(
                subject=commission.run_id,
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
        commission = self.commission
        sa = self._subagents_by_name[tc.tool]
        invocation_id = self._next_subagent_invocation_id()
        frame_span_id = new_span_id()
        self._tool_span_by_call_id[tc.call_id] = frame_span_id
        state.tools_invoked[tc.tool] = state.tools_invoked.get(tc.tool, 0) + 1

        invoked_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": sa.name,
            "avp.subagent.invocation_id": invocation_id,
            "avp.subagent.input": dict(tc.input or {}),
        }
        if sa.description:
            invoked_data["gen_ai.agent.description"] = sa.description

        self._emit(
            SubagentInvokedEvent(
                subject=commission.run_id,
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
                error="no SubagentDriver configured for this agent",
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

        # Roll the subagent's spend into the parent's cumulative state so
        # observers see the true total. The breakdown is preserved on
        # subagent_returned.data.avp.subagent.usage for attribution.
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
            "avp.subagent.invocation_id": invocation_id,
            "duration_ms": outcome.duration_ms,
            "avp.subagent.result.text": outcome.text,
            "avp.subagent.reason": outcome.reason,
            "avp.subagent.usage": sa_usage,
        }
        if outcome.structured is not None:
            returned_data["avp.subagent.result.structured"] = outcome.structured

        self._emit(
            SubagentReturnedEvent(
                subject=commission.run_id,
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
        commission = self.commission
        failed_data: dict[str, Any] = {
            "step": state.total_turns,
            "gen_ai.agent.name": sa.name,
            "avp.subagent.invocation_id": invocation_id,
            "duration_ms": duration_ms,
            "avp.subagent.error": error,
        }
        if error_code is not None:
            failed_data["avp.subagent.error.code"] = error_code

        self._emit(
            SubagentFailedEvent(
                subject=commission.run_id,
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

    # ── First / last events ─────────────────────────────────────────────────

    def _build_tool_decls(self) -> list[dict[str, Any]] | None:
        """Effective built-in tool surface for `agent_started.data.tools` —
        what the agent's local-dispatch built-ins surface to the model
        for this run. Filtered by `Commission.exposed` (literal or glob
        match against each built-in's name). MCP-server tools surface
        separately on `mcp_server_connected.data.avp.mcp.tools`. MCP-shaped
        (camelCase `inputSchema`).
        """
        candidates: list[dict[str, Any]] = []
        for bt in self._agent_builtin_tools:
            entry = {"name": bt["name"]}
            if "description" in bt and bt["description"] is not None:
                entry["description"] = bt["description"]
            schema = bt.get("inputSchema") or bt.get("input_schema")
            if schema is not None:
                entry["inputSchema"] = schema
            entry["avp.dispatch_target"] = "local"
            candidates.append(entry)
        candidates = [c for c in candidates if self._matches_exposed(c["name"])]
        return candidates or None

    def _build_subagent_decls(self) -> list[dict[str, Any]] | None:
        """Subagent descriptors for `agent_started.data.subagents`. Filtered
        by `Commission.exposed` (same rule as tools — the model only sees
        names matched by an exposed pattern)."""
        commission = self.commission
        if not commission.subagents:
            return None
        decls: list[dict[str, Any]] = []
        for sa in commission.subagents:
            if not self._matches_exposed(sa.name):
                continue
            entry: dict[str, Any] = {"name": sa.name, "description": sa.description}
            if sa.inputSchema is not None:
                entry["inputSchema"] = sa.inputSchema
            decls.append(entry)
        return decls or None

    def _emit_run_prelude(self) -> None:
        """Emit the two prelude events that open every AVP trajectory:
        `run_requested` (supervisor-attributed; agent-relayed) and
        `agent_described` (agent's manifest).

        Skipped when no manifest was supplied — embedded callers (in-process
        supervisor example, conformance harness building a Commission without a
        agent identity) drive AVPAgent without one. Top-level CLI agents
        always pass a manifest so the wire is complete.

        Both events are root-level (parent_span_id = ZERO) and sit above the
        `agent_started` span — they describe the run BEFORE it starts. Each
        event owns a fresh span; they are not paired.
        """
        if self._manifest is None:
            return
        commission = self.commission
        sup = commission.supervisor
        # Commission snapshot — full round-trip via JSON form so consumers reading
        # the wire see exactly what the supervisor sent. Excluding null fields
        # keeps the snapshot tight; supervisors that want the dense form can
        # populate explicitly.
        commission_snapshot = commission.model_dump(by_alias=True, exclude_none=True, mode="json")
        run_requested_kwargs: dict[str, Any] = {
            "avp.supervisor.name": sup.name if sup is not None else "unknown",
            "avp.commission": commission_snapshot,
        }
        if sup is not None and sup.version is not None:
            run_requested_kwargs["avp.supervisor.version"] = sup.version
        self._emit(
            RunRequestedEvent(
                subject=commission.run_id,
                data=RunRequestedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **run_requested_kwargs,
                ),
            )
        )
        self._emit(
            AgentDescribedEvent(
                subject=commission.run_id,
                data=AgentDescribedData(
                    trace_id=self._trace_id,
                    span_id=new_span_id(),
                    parent_span_id=ZERO_SPAN_ID,
                    **{"avp.manifest": self._manifest},
                ),
            )
        )

    def _emit_agent_started(self) -> None:
        commission = self.commission
        tools_meta = self._build_tool_decls()
        skills_meta = [
            {"name": s.name, "avp.source": s.avp_source} for s in (commission.skills or [])
        ] or None
        subagents_meta = self._build_subagent_decls()

        data_kwargs: dict[str, Any] = {
            "trace_id": self._trace_id,
            "span_id": self._agent_span_id,
            "parent_span_id": ZERO_SPAN_ID,
            "prompt": commission.prompt,
            "system_prompt": commission.system_prompt,
            "tools": tools_meta,
            "skills": skills_meta,
            "subagents": subagents_meta,
        }
        if commission.model:
            data_kwargs["gen_ai.request.model"] = commission.model
        if commission.thread_id:
            data_kwargs["avp.thread_id"] = commission.thread_id
        if commission.tags:
            data_kwargs["avp.tags"] = commission.tags
        if commission.meta:
            data_kwargs["avp.meta"] = commission.meta

        self._emit(
            AgentStartedEvent(
                subject=commission.run_id,
                data=AgentStartedData(**data_kwargs),
            )
        )
        # Eager skill loading: read SKILL.md bodies for each filesystem-source
        # skill and append to the system prompt. Skills with mcp:// sources
        # are deferred to production agents that implement live MCP
        # transport — the reference agent's MCP layer is stub-only.
        sys_parts: list[str] = []
        if commission.system_prompt:
            sys_parts.append(commission.system_prompt)
        for skill in commission.skills or []:
            body = self._loaded_skill_bodies.get(skill.name)
            if body:
                sys_parts.append(f'<skill name="{skill.name}">\n{body}\n</skill>')
        if sys_parts:
            self._history.append({"role": "system", "content": "\n\n".join(sys_parts)})
        if commission.prompt:
            self._history.append({"role": "user", "content": commission.prompt})

    def _emit_skills_loaded(self) -> None:
        """Eager-load each Commission.skill, then emit skill_loaded(step=0)
        for each one whose body actually entered the agent's history.

        Per the v0.1 spec, `skill_loaded` means "the SKILL.md body has
        been added to the active context window." This agent claims the
        `skills:eager` capability, so injection happens at startup and
        the events fire at step=0.

        Filesystem-path sources are read here. mcp:// sources are
        deferred (the reference agent's MCP layer doesn't drive a real
        handshake yet) — they emit `error_occurred(unsupported_model)`
        ... no wait, just skip with a clear message via error_occurred.
        Production agents that implement live MCP MUST resolve them via
        `resources/read` on the named server before turn 1.
        """
        commission = self.commission
        if not commission.skills:
            return
        for skill in commission.skills:
            if skill.name in self._loaded_skill_bodies:
                self._emit(
                    SkillLoadedEvent(
                        subject=commission.run_id,
                        data=SkillLoadedData(
                            **self._own_span(self._agent_span_id),
                            step=0,
                            **{
                                "avp.skill.name": skill.name,
                                "avp.skill.source": skill.avp_source,
                            },
                        ),
                    )
                )

    def _emit_mcp_connections(self) -> None:
        """v0.1: emit `mcp_server_connected` for each declared MCP server. The
        wire format ships now; the live transport (real `initialize` /
        `tools/list` over HTTP or stdio) is deferred to a future minor — the
        reference agent emits a stub event so supervisors can pin the
        lifecycle in tests today."""
        commission = self.commission
        if not commission.mcp_servers:
            return
        for server in commission.mcp_servers:
            self._emit_mcp_connected(server)

    def _emit_mcp_connected(self, server: McpServer) -> None:
        commission = self.commission
        self._emit(
            McpServerConnectedEvent(
                subject=commission.run_id,
                data=McpServerConnectedData(
                    **self._own_span(self._agent_span_id),
                    **{
                        "avp.mcp.server_id": server.id,
                        "avp.mcp.protocol_version": MCP_PROTOCOL_VERSION,
                        "avp.mcp.tool_count": 0,
                    },
                ),
            )
        )

    def _emit_mcp_disconnections(self, reason: str) -> None:
        commission = self.commission
        if not commission.mcp_servers:
            return
        for server in commission.mcp_servers:
            self._emit(
                McpServerDisconnectedEvent(
                    subject=commission.run_id,
                    data=McpServerDisconnectedData(
                        **self._own_span(self._agent_span_id),
                        **{
                            "avp.mcp.server_id": server.id,
                            "avp.mcp.disconnect_reason": reason,
                        },
                    ),
                )
            )

    def _emit_agent_stopped(self, reason: StopReason) -> AgentStoppedEvent:
        commission = self.commission
        # Emit MCP disconnect events idempotently — _emit_mcp_disconnections
        # already returns when mcp_servers is empty. Callers that knew they
        # had to disconnect early (validation failure) call it before this;
        # the normal exit path relies on this finalizer.
        self._emit_mcp_disconnections("clean")
        snap = self._state.snapshot(_monotonic_ms())
        ev = AgentStoppedEvent(
            subject=commission.run_id,
            data=AgentStoppedData(
                trace_id=self._trace_id,
                span_id=self._agent_span_id,
                parent_span_id=ZERO_SPAN_ID,
                **{
                    "avp.reason": reason,
                    "avp.state": snap,
                    "avp.total_tokens": snap.total_tokens,
                    "avp.total_cost_usd": snap.total_cost_usd,
                    "avp.total_turns": snap.total_turns,
                    "avp.duration_ms": snap.duration_ms,
                },
            ),
        )
        self._emit(ev)
        return ev


__all__ = ["AVPAgent"]
